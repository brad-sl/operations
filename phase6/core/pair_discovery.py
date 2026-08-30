#!/usr/bin/env python3
"""
Emerging-pair discovery funnel (shadow-first) — no sentiment budget on the wide pass.

Stages
------
0. UNIVERSE  — Coinbase public /products (USD, online, tradable). Free.
1. PREQUAL   — 24h stats energy screen (volume notional, range, return). Free public API.
               NO X/Reddit/sentiment. Rate-limited parallel stats fetch.
2. QUALITY   — shortlist only: hourly candles → momentum/vol expansion/volume accel.
               Still no sentiment.
3. DEEP (opt)— only top K contenders may request RSI/sentiment later (budgeted; off by default).
4. PROMOTE   — emit contenders for pool_cycling to displace weak active names (shadow).

Philosophy
----------
Fixed-list rotation optimizes incremental reallocation. This funnel hunts *emerging
high-energy* names: liquidity + expansion + upside impulse, then filters hard before
any paid signal spend or basket membership change.
"""
from __future__ import annotations

import json
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

from phase6.core.paths import PROJECT_ROOT, TRADING_CONFIG_PHASE6, load_trading_basket

logger = logging.getLogger(__name__)

PUBLIC = "https://api.exchange.coinbase.com"
UA = {"User-Agent": "phase6-pair-discovery/1.0 (shadow; research)"}

STATE_DIR = PROJECT_ROOT / "data" / "state"
LATEST_JSON = STATE_DIR / "pair_discovery_latest.json"
JSONL = STATE_DIR / "pair_discovery_runs.jsonl"
CONTENDERS_JSON = STATE_DIR / "pair_discovery_contenders.json"

# Quote/stable junk — never "emerging upside" for our long basket
EXCLUDE_BASES = {
    "USD", "USDT", "USDC", "DAI", "EUR", "EURC", "GBP", "PYUSD", "GUSD", "PAX",
    "USDP", "TUSD", "FDUSD", "USDS", "CUSD", "SUSD", "FRAX", "LUSD", "CRVUSD",
    "CBETH", "WBTC", "WETH", "STETH", "MSOL", "TBTC",
}
# Base names that are pure stables or fiat wrappers when quoted USD
EXCLUDE_IDS_EXACT = {
    "USDT-USD", "USDC-USD", "DAI-USD", "EURC-USD", "PYUSD-USD", "GUSD-USD",
    "PAX-USD", "USDP-USD", "TUSD-USD", "FDUSD-USD",
}


@dataclass
class DiscoveryConfig:
    # Stage 1
    max_stats_workers: int = 12
    stats_timeout_s: float = 12.0
    # Liquidity floor (USD notional ≈ volume_base * mid). Tune for Coinbase retail book.
    min_quote_volume_24h_usd: float = 2_000_000.0
    # Keep top-N by raw energy before candle quality (cost control on stage 2).
    prequal_top_n: int = 40
    # Stage 2 candles
    candle_granularity: int = 3600  # 1h
    candle_limit: int = 168  # ~7d
    quality_top_n: int = 12
    # Energy weights (prequal)
    w_volume: float = 0.40
    w_return: float = 0.35
    w_range: float = 0.25
    # Quality weights
    w_mom_3d: float = 0.35
    w_mom_7d: float = 0.15
    w_vol_expand: float = 0.25
    w_vol_accel: float = 0.25
    # Quality gates
    min_candles: int = 48
    min_quality_score: float = 0.35
    require_nonneg_3d_mom: bool = False  # high-energy can be bounce; default allow either side impulse via abs then prefer +
    prefer_positive_impulse: bool = True
    # Contenders: require some upside impulse (not pure dump-vol energy)
    require_upside_for_promote: bool = True
    min_promote_mom_3d: float = -0.02  # allow mild pullback if 24h still green
    min_promote_ret_24h: float = 0.0
    # Contenders handed to pool cycling / operator
    contender_top_n: int = 5
    # Optional deep (default OFF — no sentiment budget)
    run_deep: bool = False
    deep_top_k: int = 3
    # Exclude current active from "emerging" contenders (still scored for context)
    exclude_active_from_contenders: bool = True
    sleep_between_batches_s: float = 0.05


@dataclass
class ProductRow:
    product_id: str
    base: str
    quote: str
    status: str
    min_market_funds: float
    trading_disabled: bool


@dataclass
class PrequalRow:
    product_id: str
    last: float
    open_24h: float
    high: float
    low: float
    volume_base: float
    volume_quote_usd: float
    ret_24h: float
    range_pct: float
    energy: float = 0.0
    rank_energy: int = 0
    note: str = ""


@dataclass
class QualityRow:
    product_id: str
    prequal_energy: float
    mom_3d: float
    mom_7d: float
    vol_expand: float
    vol_accel: float
    quality_score: float
    n_candles: int
    last_close: float
    pass_gate: bool
    reason: str = ""


@dataclass
class Contender:
    product_id: str
    stage: str
    prequal_energy: float
    quality_score: float
    volume_quote_usd: float
    ret_24h: float
    mom_3d: float
    mom_7d: float
    in_active_basket: bool
    promote_eligible: bool
    reasons: List[str] = field(default_factory=list)


@dataclass
class DiscoveryReport:
    timestamp: str
    config: Dict[str, Any]
    universe_n: int
    prequal_n: int
    quality_n: int
    contenders: List[Dict[str, Any]]
    prequal_top: List[Dict[str, Any]]
    quality_ranked: List[Dict[str, Any]]
    active_basket: List[str]
    sentiment_calls: int
    note: str


def _get_json(
    url: str,
    params: Optional[dict] = None,
    timeout: float = 20.0,
    *,
    retries: int = 4,
    backoff_s: float = 1.5,
) -> Any:
    """GET JSON with retries for transient DNS/connection blips (cron-safe)."""
    last_exc: Optional[BaseException] = None
    attempts = max(1, int(retries))
    for attempt in range(1, attempts + 1):
        try:
            r = requests.get(url, headers=UA, params=params or {}, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
        ) as e:
            last_exc = e
            if attempt >= attempts:
                break
            sleep_for = backoff_s * (2 ** (attempt - 1))
            logger.warning(
                "pair_discovery GET retry %s/%s after %ss: %s (%s)",
                attempt,
                attempts,
                sleep_for,
                url,
                type(e).__name__,
            )
            time.sleep(sleep_for)
        except requests.exceptions.HTTPError as e:
            # Retry only transient 5xx / 429
            status = getattr(getattr(e, "response", None), "status_code", None)
            last_exc = e
            if status not in (429, 500, 502, 503, 504) or attempt >= attempts:
                raise
            sleep_for = backoff_s * (2 ** (attempt - 1))
            logger.warning(
                "pair_discovery GET HTTP %s retry %s/%s after %ss: %s",
                status,
                attempt,
                attempts,
                sleep_for,
                url,
            )
            time.sleep(sleep_for)
    assert last_exc is not None
    raise last_exc


def load_active_basket(cfg_path: Path = TRADING_CONFIG_PHASE6) -> List[str]:
    try:
        raw = json.loads(Path(cfg_path).read_text())
        pairs = (raw.get("global_settings") or {}).get("pairs") or []
        if pairs:
            return [str(p) for p in pairs]
    except Exception:
        pass
    return list(load_trading_basket())


def stage0_universe(cfg: DiscoveryConfig) -> List[ProductRow]:
    """All tradable USD spot products (public)."""
    products = _get_json(f"{PUBLIC}/products", timeout=30.0)
    out: List[ProductRow] = []
    for p in products:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "")
        quote = str(p.get("quote_currency") or "")
        base = str(p.get("base_currency") or "")
        if quote != "USD":
            continue
        if p.get("status") != "online":
            continue
        if p.get("trading_disabled") or p.get("cancel_only") or p.get("auction_mode"):
            continue
        # Allow limit_only? usually still tradable via limit; skip post_only-only weirdness
        if p.get("post_only"):
            continue
        if pid in EXCLUDE_IDS_EXACT or base.upper() in EXCLUDE_BASES:
            continue
        # Skip obvious leveraged / bearer wrappers by suffix heuristics
        bu = base.upper()
        if bu.endswith("3L") or bu.endswith("3S") or bu.endswith("UP") or bu.endswith("DOWN"):
            continue
        try:
            mmf = float(p.get("min_market_funds") or 0)
        except (TypeError, ValueError):
            mmf = 0.0
        out.append(
            ProductRow(
                product_id=pid,
                base=base,
                quote=quote,
                status=str(p.get("status")),
                min_market_funds=mmf,
                trading_disabled=bool(p.get("trading_disabled")),
            )
        )
    return out


def _fetch_stats(product_id: str, timeout: float) -> Optional[dict]:
    try:
        return _get_json(f"{PUBLIC}/products/{product_id}/stats", timeout=timeout)
    except Exception as e:
        logger.debug("stats fail %s: %s", product_id, e)
        return None


def _prequal_from_stats(pid: str, st: dict) -> Optional[PrequalRow]:
    try:
        last = float(st.get("last") or 0)
        open_ = float(st.get("open") or 0)
        high = float(st.get("high") or 0)
        low = float(st.get("low") or 0)
        vol = float(st.get("volume") or 0)
    except (TypeError, ValueError):
        return None
    if last <= 0 or open_ <= 0:
        return None
    mid = (high + low) / 2.0 if high > 0 and low > 0 else last
    vol_usd = vol * mid
    ret = (last / open_) - 1.0
    rng = ((high - low) / open_) if open_ > 0 else 0.0
    return PrequalRow(
        product_id=pid,
        last=last,
        open_24h=open_,
        high=high,
        low=low,
        volume_base=vol,
        volume_quote_usd=vol_usd,
        ret_24h=ret,
        range_pct=rng,
    )


def _norm_rank(values: Sequence[float], higher_is_better: bool = True) -> List[float]:
    """Percentile-ish 0..1 ranks."""
    n = len(values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: values[i], reverse=higher_is_better)
    out = [0.0] * n
    if n == 1:
        return [1.0]
    for rank, i in enumerate(order):
        out[i] = 1.0 - (rank / (n - 1))
    return out


def stage1_prequal(
    universe: Sequence[ProductRow],
    cfg: DiscoveryConfig,
) -> List[PrequalRow]:
    """Wide free energy screen via /stats — no sentiment."""
    rows: List[PrequalRow] = []
    ids = [u.product_id for u in universe]
    with ThreadPoolExecutor(max_workers=cfg.max_stats_workers) as ex:
        futs = {ex.submit(_fetch_stats, pid, cfg.stats_timeout_s): pid for pid in ids}
        for fut in as_completed(futs):
            pid = futs[fut]
            st = fut.result()
            if not st:
                continue
            row = _prequal_from_stats(pid, st)
            if not row:
                continue
            if row.volume_quote_usd < cfg.min_quote_volume_24h_usd:
                continue
            rows.append(row)
            if cfg.sleep_between_batches_s:
                time.sleep(cfg.sleep_between_batches_s / max(cfg.max_stats_workers, 1))

    if not rows:
        return []

    # Prefer upside impulse in energy: use max(ret, 0) heavily but keep range/vol
    rets = [max(r.ret_24h, 0.0) for r in rows]
    # Also give partial credit to large |move| (breakouts either way → still "energy")
    abs_rets = [abs(r.ret_24h) for r in rows]
    ranges = [r.range_pct for r in rows]
    vols = [math.log1p(r.volume_quote_usd) for r in rows]

    nr = _norm_rank(rets, True)
    na = _norm_rank(abs_rets, True)
    ng = _norm_rank(ranges, True)
    nv = _norm_rank(vols, True)
    # Blend signed upside with absolute energy (70/30 inside return component)
    for i, r in enumerate(rows):
        ret_comp = 0.7 * nr[i] + 0.3 * na[i]
        r.energy = round(
            cfg.w_volume * nv[i] + cfg.w_return * ret_comp + cfg.w_range * ng[i],
            4,
        )

    rows.sort(key=lambda x: x.energy, reverse=True)
    for i, r in enumerate(rows):
        r.rank_energy = i + 1
    return rows[: cfg.prequal_top_n]


def _fetch_candles(product_id: str, gran: int, limit: int, timeout: float = 15.0) -> List[list]:
    """Public candles: [time, low, high, open, close, volume], newest first."""
    try:
        data = _get_json(
            f"{PUBLIC}/products/{product_id}/candles",
            params={"granularity": gran},
            timeout=timeout,
        )
        if not isinstance(data, list):
            return []
        # oldest first
        rows = list(reversed(data))
        return rows[-limit:]
    except Exception as e:
        logger.debug("candles fail %s: %s", product_id, e)
        return []


def stage2_quality(
    prequal: Sequence[PrequalRow],
    cfg: DiscoveryConfig,
) -> List[QualityRow]:
    """Candle-based quality on prequal shortlist only — still no sentiment."""
    pq_map = {p.product_id: p for p in prequal}
    results: List[QualityRow] = []

    def one(pid: str) -> Optional[QualityRow]:
        candles = _fetch_candles(pid, cfg.candle_granularity, cfg.candle_limit)
        n = len(candles)
        pq = pq_map[pid]
        if n < cfg.min_candles:
            return QualityRow(
                product_id=pid,
                prequal_energy=pq.energy,
                mom_3d=0.0,
                mom_7d=0.0,
                vol_expand=0.0,
                vol_accel=0.0,
                quality_score=0.0,
                n_candles=n,
                last_close=pq.last,
                pass_gate=False,
                reason=f"insufficient_candles n={n}",
            )
        closes = [float(c[4]) for c in candles if len(c) >= 5]
        vols = [float(c[5]) for c in candles if len(c) >= 6]
        if len(closes) < cfg.min_candles:
            return None
        last = closes[-1]
        def ret_lookback(hours: int) -> float:
            idx = max(0, len(closes) - 1 - hours)
            base = closes[idx]
            return (last / base - 1.0) if base > 0 else 0.0

        mom_3d = ret_lookback(72)
        mom_7d = ret_lookback(min(167, len(closes) - 1))

        # vol expansion: recent 24h range vs prior 24h range (using highs/lows)
        highs = [float(c[2]) for c in candles]
        lows = [float(c[1]) for c in candles]
        def band(start: int, end: int) -> float:
            h = max(highs[start:end]) if end > start else 0
            lo = min(lows[start:end]) if end > start else 0
            mid = (h + lo) / 2 if h and lo else 0
            return ((h - lo) / mid) if mid > 0 else 0.0

        n = len(highs)
        recent = band(max(0, n - 24), n)
        prior = band(max(0, n - 48), max(0, n - 24)) or 1e-9
        vol_expand = min(recent / prior, 5.0)  # cap

        # volume accel: last 24h vol / prior 24h vol
        v_rec = sum(vols[max(0, len(vols) - 24) :]) or 0.0
        v_pri = sum(vols[max(0, len(vols) - 48) : max(0, len(vols) - 24)]) or 1e-9
        vol_accel = min(v_rec / v_pri, 5.0)

        return QualityRow(
            product_id=pid,
            prequal_energy=pq.energy,
            mom_3d=mom_3d,
            mom_7d=mom_7d,
            vol_expand=vol_expand,
            vol_accel=vol_accel,
            quality_score=0.0,  # fill after rank-norm
            n_candles=len(closes),
            last_close=last,
            pass_gate=False,
            reason="",
        )

    with ThreadPoolExecutor(max_workers=min(8, cfg.max_stats_workers)) as ex:
        futs = [ex.submit(one, p.product_id) for p in prequal]
        for fut in as_completed(futs):
            row = fut.result()
            if row:
                results.append(row)

    if not results:
        return []

    # Rank-normalize quality components among this shortlist
    def pos_mom(x: float) -> float:
        return max(x, 0.0) if cfg.prefer_positive_impulse else abs(x)

    m3 = [pos_mom(r.mom_3d) for r in results]
    m7 = [pos_mom(r.mom_7d) for r in results]
    ve = [r.vol_expand for r in results]
    va = [r.vol_accel for r in results]
    n3 = _norm_rank(m3)
    n7 = _norm_rank(m7)
    ne = _norm_rank(ve)
    na = _norm_rank(va)
    pe = _norm_rank([r.prequal_energy for r in results])

    for i, r in enumerate(results):
        q = (
            cfg.w_mom_3d * n3[i]
            + cfg.w_mom_7d * n7[i]
            + cfg.w_vol_expand * ne[i]
            + cfg.w_vol_accel * na[i]
        )
        # Blend a bit of prequal energy so liquid leaders don't vanish
        r.quality_score = round(0.85 * q + 0.15 * pe[i], 4)
        reasons = []
        ok = r.quality_score >= cfg.min_quality_score and r.n_candles >= cfg.min_candles
        if cfg.require_nonneg_3d_mom and r.mom_3d < 0:
            ok = False
            reasons.append("neg_3d_mom")
        if r.vol_accel < 0.8 and r.mom_3d < 0.02:
            # dead tape
            reasons.append("low_accel_flat_tape")
            if r.quality_score < cfg.min_quality_score + 0.05:
                ok = False
        r.pass_gate = ok
        r.reason = ",".join(reasons) if reasons else ("pass" if ok else "below_min_quality")

    results.sort(key=lambda x: x.quality_score, reverse=True)
    return results


def build_contenders(
    quality: Sequence[QualityRow],
    prequal: Sequence[PrequalRow],
    active: Sequence[str],
    cfg: DiscoveryConfig,
) -> List[Contender]:
    pq = {p.product_id: p for p in prequal}
    active_set = set(active)
    contenders: List[Contender] = []
    for r in quality:
        if not r.pass_gate:
            continue
        in_active = r.product_id in active_set
        if cfg.exclude_active_from_contenders and in_active:
            continue
        pqr = pq.get(r.product_id)
        reasons = [
            f"quality={r.quality_score:.3f}",
            f"energy={r.prequal_energy:.3f}",
            f"mom3d={r.mom_3d:.2%}",
            f"vol_accel={r.vol_accel:.2f}x",
            f"vol_expand={r.vol_expand:.2f}x",
        ]
        if pqr:
            reasons.append(f"vol24h≈${pqr.volume_quote_usd:,.0f}")
            reasons.append(f"ret24h={pqr.ret_24h:.2%}")

        promote = not in_active and r.pass_gate
        if promote and cfg.require_upside_for_promote:
            ret24 = pqr.ret_24h if pqr else 0.0
            upside_ok = (r.mom_3d >= cfg.min_promote_mom_3d and ret24 >= cfg.min_promote_ret_24h) or (
                r.mom_3d >= 0.05
            )
            if not upside_ok:
                promote = False
                reasons.append("blocked_no_upside_impulse")

        contenders.append(
            Contender(
                product_id=r.product_id,
                stage="quality",
                prequal_energy=r.prequal_energy,
                quality_score=r.quality_score,
                volume_quote_usd=pqr.volume_quote_usd if pqr else 0.0,
                ret_24h=pqr.ret_24h if pqr else 0.0,
                mom_3d=r.mom_3d,
                mom_7d=r.mom_7d,
                in_active_basket=in_active,
                promote_eligible=promote,
                reasons=reasons,
            )
        )
        if len(contenders) >= cfg.contender_top_n:
            break
    return contenders


def run_discovery(cfg: Optional[DiscoveryConfig] = None, write: bool = True) -> DiscoveryReport:
    cfg = cfg or DiscoveryConfig()
    active = load_active_basket()
    t0 = time.time()

    universe = stage0_universe(cfg)
    prequal = stage1_prequal(universe, cfg)
    quality = stage2_quality(prequal, cfg)
    contenders = build_contenders(quality, prequal, active, cfg)

    sentiment_calls = 0
    deep_note = "deep/sentiment skipped (budget preserved)"
    if cfg.run_deep and contenders:
        # Placeholder hook — intentional no-op unless wired later.
        # Only top deep_top_k would spend RSI/X here.
        deep_note = (
            f"deep requested for {min(cfg.deep_top_k, len(contenders))} — "
            "not auto-wired to X (manual/opt-in path)."
        )

    report = DiscoveryReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        config=asdict(cfg),
        universe_n=len(universe),
        prequal_n=len(prequal),
        quality_n=sum(1 for q in quality if q.pass_gate),
        contenders=[asdict(c) for c in contenders],
        # Full prequal window + full quality scored set (needed for retro why-not).
        # Previously top-15 only — that hid most reject reasons.
        prequal_top=[asdict(p) for p in prequal[: cfg.prequal_top_n]],
        quality_ranked=[asdict(q) for q in quality],
        active_basket=list(active),
        sentiment_calls=sentiment_calls,
        note=(
            f"Funnel complete in {time.time()-t0:.1f}s. "
            f"Universe={len(universe)} → prequal≤{cfg.prequal_top_n} "
            f"(min ${cfg.min_quote_volume_24h_usd:,.0f}/24h) → quality pass → "
            f"contenders={len(contenders)}. {deep_note}. "
            "Shadow only — does not mutate basket."
        ),
    )

    if write:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LATEST_JSON.write_text(json.dumps(asdict(report), indent=2) + "\n")
        # Compact stage ledger for retro "why not" (names + scores + reject reasons).
        # Keep bounded so jsonl stays greppable — not full universe.
        quality_fail = [
            {
                "product_id": q.product_id,
                "quality_score": q.quality_score,
                "pass_gate": q.pass_gate,
                "reason": q.reason,
                "mom_3d": round(q.mom_3d, 6),
                "vol_accel": round(q.vol_accel, 4),
                "vol_expand": round(q.vol_expand, 4),
                "prequal_energy": q.prequal_energy,
            }
            for q in quality
            if not q.pass_gate
        ][:25]
        quality_pass = [
            {
                "product_id": q.product_id,
                "quality_score": q.quality_score,
                "reason": q.reason,
                "mom_3d": round(q.mom_3d, 6),
                "vol_accel": round(q.vol_accel, 4),
                "prequal_energy": q.prequal_energy,
            }
            for q in quality
            if q.pass_gate
        ][:20]
        prequal_slim = [
            {
                "product_id": p.product_id,
                "energy": p.energy,
                "rank_energy": p.rank_energy,
                "ret_24h": round(p.ret_24h, 6),
                "volume_quote_usd": round(p.volume_quote_usd, 2),
            }
            for p in prequal[: cfg.prequal_top_n]
        ]
        with open(JSONL, "a") as f:
            f.write(
                json.dumps(
                    {
                        "ts": report.timestamp,
                        "schema": "pair_discovery_run_v2",
                        "universe_n": report.universe_n,
                        "prequal_n": report.prequal_n,
                        "quality_n": report.quality_n,
                        "contenders": [
                            c["product_id"] for c in report.contenders
                        ],
                        "contenders_detail": [
                            {
                                "product_id": c["product_id"],
                                "quality_score": c.get("quality_score"),
                                "prequal_energy": c.get("prequal_energy"),
                                "promote_eligible": c.get("promote_eligible"),
                                "ret_24h": c.get("ret_24h"),
                                "mom_3d": c.get("mom_3d"),
                                "reasons": c.get("reasons") or [],
                            }
                            for c in report.contenders
                        ],
                        "prequal_top": prequal_slim,
                        "quality_pass": quality_pass,
                        "quality_fail": quality_fail,
                        "active_basket": list(active),
                        "cfg_min_quote_volume_24h_usd": cfg.min_quote_volume_24h_usd,
                        "cfg_prequal_top_n": cfg.prequal_top_n,
                        "cfg_min_quality_score": cfg.min_quality_score,
                        "cfg_contender_top_n": cfg.contender_top_n,
                        "sentiment_calls": report.sentiment_calls,
                    }
                )
                + "\n"
            )
        CONTENDERS_JSON.write_text(
            json.dumps(
                {
                    "ts": report.timestamp,
                    "contenders": report.contenders,
                    "promote_eligible": [
                        c["product_id"]
                        for c in report.contenders
                        if c.get("promote_eligible")
                    ],
                    "note": "Feed to pool_cycling as discovery candidates (shadow).",
                },
                indent=2,
            )
            + "\n"
        )

    return report


def report_plain_english(report: DiscoveryReport) -> str:
    lines = [
        f"Pair discovery (shadow) @ {report.timestamp}",
        f"Universe: {report.universe_n} USD products → "
        f"prequal shortlist: {report.prequal_n} → "
        f"quality pass: {report.quality_n} → "
        f"contenders: {len(report.contenders)}",
        f"Sentiment API calls this run: {report.sentiment_calls}",
        "",
    ]
    if not report.contenders:
        lines.append("No promote-eligible contenders this run.")
    else:
        lines.append("Contenders (high-energy, quality-gated, not yet in basket unless noted):")
        for c in report.contenders:
            flag = "PROMOTE?" if c.get("promote_eligible") else "in-basket"
            lines.append(
                f"  • {c['product_id']} [{flag}] q={c['quality_score']:.3f} "
                f"e={c['prequal_energy']:.3f} mom3d={c['mom_3d']:.1%} "
                f"vol24h≈${c['volume_quote_usd']:,.0f}"
            )
            lines.append(f"      {'; '.join(c.get('reasons') or [])}")
    lines.append("")
    lines.append(report.note)
    if report.prequal_top[:5]:
        lines.append("")
        lines.append("Top prequal energy (stage1, free stats):")
        for p in report.prequal_top[:5]:
            lines.append(
                f"  {p['rank_energy']}. {p['product_id']} e={p['energy']:.3f} "
                f"ret24h={p['ret_24h']:.1%} rng={p['range_pct']:.1%} "
                f"vol≈${p['volume_quote_usd']:,.0f}"
            )
    return "\n".join(lines)


def load_discovery_contender_ids(path: Path = CONTENDERS_JSON) -> List[str]:
    """Helper for pool_cycling to pull latest promote-eligible IDs."""
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
        ids = raw.get("promote_eligible") or [
            c["product_id"]
            for c in (raw.get("contenders") or [])
            if c.get("promote_eligible")
        ]
        return [str(x) for x in ids]
    except Exception:
        return []
