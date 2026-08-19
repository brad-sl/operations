#!/usr/bin/env python3
"""
Stoch %K as entry-time predictor of subsequent stop-loss (offline, real data only).

Joins trades/phase6_trades.jsonl buys → entry RSI/Stoch (on-fill or history)
→ forward SL label on same pair. Exit-time Stoch is reported only as trailing
baseline (known reverse-causality trap).

No live config writes.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
TRADES_JSONL = ROOT / "trades" / "phase6_trades.jsonl"
HISTORY_JSONL = ROOT / "data" / "state" / "rsi_indicator_history.jsonl"
DEFAULT_TRIAL_START = "2026-07-21T21:54:57.262723+00:00"


def parse_ts(s: Any) -> Optional[datetime]:
    if s is None:
        return None
    if isinstance(s, datetime):
        dt = s
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    if not isinstance(s, str) or not s.strip():
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _f(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def iter_jsonl(path: Path) -> Iterable[dict]:
    if not path.exists():
        return
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def is_buy(row: dict) -> bool:
    side = str(row.get("side") or "").lower()
    reason = str(row.get("reason") or row.get("exit_reason") or "").lower()
    if "stop_loss" in reason:
        return False
    if side == "buy":
        return True
    if "buy" in reason and "sell" not in reason:
        return True
    return False


def is_sl(row: dict) -> bool:
    reason = str(row.get("reason") or row.get("exit_reason") or "").lower()
    return "stop_loss" in reason


def load_trades(path: Path = TRADES_JSONL) -> List[dict]:
    out: List[dict] = []
    for r in iter_jsonl(path):
        ts = parse_ts(r.get("timestamp"))
        if ts is None:
            continue
        r = dict(r)
        r["_ts"] = ts
        r["_pair"] = r.get("pair") or r.get("product_id")
        if not r["_pair"]:
            continue
        out.append(r)
    out.sort(key=lambda x: x["_ts"])
    return out


def load_history(path: Path = HISTORY_JSONL) -> List[Tuple[datetime, Dict[str, dict]]]:
    hist: List[Tuple[datetime, Dict[str, dict]]] = []
    for row in iter_jsonl(path):
        ts = parse_ts(row.get("timestamp") or row.get("run_timestamp"))
        if ts is None:
            continue
        pairs = row.get("pairs") or {}
        if not isinstance(pairs, dict):
            continue
        clean: Dict[str, dict] = {}
        for p, ent in pairs.items():
            if isinstance(ent, dict):
                clean[p] = ent
        hist.append((ts, clean))
    hist.sort(key=lambda x: x[0])
    return hist


def nearest_history_ind(
    hist: Sequence[Tuple[datetime, Dict[str, dict]]],
    pair: str,
    ts: datetime,
    max_before_min: float = 90.0,
    max_after_min: float = 10.0,
) -> Tuple[Optional[dict], Optional[datetime], Optional[float]]:
    """Prefer last snapshot at/before ts; allow small after-skew."""
    best_ent: Optional[dict] = None
    best_ts: Optional[datetime] = None
    best_pen: Optional[float] = None
    lo = ts - timedelta(minutes=max_before_min)
    hi = ts + timedelta(minutes=max_after_min)
    for hts, pairs in hist:
        if hts < lo:
            continue
        if hts > hi:
            break
        ent = pairs.get(pair)
        if not isinstance(ent, dict):
            continue
        if ent.get("stoch_k") is None and ent.get("rsi") is None:
            continue
        lag_s = (hts - ts).total_seconds()
        # Prefer before/equal; penalize future snapshots.
        pen = abs(lag_s) + (0.0 if lag_s <= 0 else 50_000.0)
        if best_pen is None or pen < best_pen:
            best_pen = pen
            best_ent = ent
            best_ts = hts
    if best_ent is None:
        return None, None, None
    lag = (best_ts - ts).total_seconds() if best_ts else None
    return best_ent, best_ts, lag


def resolve_entry_indicators(
    buy: dict,
    hist: Sequence[Tuple[datetime, Dict[str, dict]]],
) -> dict:
    on = buy.get("indicators_at_trade") or {}
    if isinstance(on, dict) and (on.get("stoch_k") is not None or on.get("rsi") is not None):
        return {
            "rsi": _f(on.get("rsi")),
            "stoch_k": _f(on.get("stoch_k")),
            "stoch_d": _f(on.get("stoch_d")),
            "source": "indicators_at_trade",
            "ind_ts": parse_ts(on.get("cache_timestamp") or on.get("timestamp")),
            "lag_s": 0.0,
        }
    ent, hts, lag = nearest_history_ind(hist, buy["_pair"], buy["_ts"])
    if ent is None:
        return {
            "rsi": None,
            "stoch_k": None,
            "stoch_d": None,
            "source": "missing",
            "ind_ts": None,
            "lag_s": None,
        }
    return {
        "rsi": _f(ent.get("rsi")),
        "stoch_k": _f(ent.get("stoch_k")),
        "stoch_d": _f(ent.get("stoch_d")),
        "source": "history_join",
        "ind_ts": hts,
        "lag_s": lag,
    }


@dataclass
class BuyEpisode:
    pair: str
    entry_ts: str
    entry_price: Optional[float]
    reason: str
    rsi: Optional[float]
    stoch_k: Optional[float]
    stoch_d: Optional[float]
    ind_source: str
    ind_lag_s: Optional[float]
    hit_sl_3d: bool
    hit_sl_7d: bool
    hit_sl_14d: bool
    hours_to_sl: Optional[float]
    sl_ts: Optional[str]
    exit_stoch_k: Optional[float]
    exit_rsi: Optional[float]
    next_event: Optional[str] = None


def build_buy_episodes(
    trades: Sequence[dict],
    hist: Sequence[Tuple[datetime, Dict[str, dict]]],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    horizons_days: Sequence[int] = (3, 7, 14),
) -> List[BuyEpisode]:
    """Each buy → entry ind → first SL on pair within horizons (forward-looking)."""
    buys = [t for t in trades if is_buy(t)]
    sls = [t for t in trades if is_sl(t)]
    sl_by_pair: Dict[str, List[dict]] = defaultdict(list)
    for s in sls:
        sl_by_pair[s["_pair"]].append(s)

    episodes: List[BuyEpisode] = []
    for b in buys:
        if start and b["_ts"] < start:
            continue
        if end and b["_ts"] > end:
            continue
        ind = resolve_entry_indicators(b, hist)
        hit = {d: False for d in horizons_days}
        hours_to_sl: Optional[float] = None
        sl_ts: Optional[str] = None
        exit_sk = None
        exit_rsi = None
        first_sl = None
        for s in sl_by_pair.get(b["_pair"], []):
            if s["_ts"] <= b["_ts"]:
                continue
            dt_h = (s["_ts"] - b["_ts"]).total_seconds() / 3600.0
            if first_sl is None:
                first_sl = s
                hours_to_sl = dt_h
                sl_ts = s["_ts"].isoformat()
                sind = s.get("indicators_at_trade") or {}
                if isinstance(sind, dict):
                    exit_sk = _f(sind.get("stoch_k"))
                    exit_rsi = _f(sind.get("rsi"))
            for d in horizons_days:
                if dt_h <= d * 24:
                    hit[d] = True
            # once past max horizon, stop
            if dt_h > max(horizons_days) * 24:
                break

        episodes.append(
            BuyEpisode(
                pair=b["_pair"],
                entry_ts=b["_ts"].isoformat(),
                entry_price=_f(b.get("entry_price") or b.get("price")),
                reason=str(b.get("reason") or b.get("side") or ""),
                rsi=ind["rsi"],
                stoch_k=ind["stoch_k"],
                stoch_d=ind["stoch_d"],
                ind_source=ind["source"],
                ind_lag_s=ind["lag_s"],
                hit_sl_3d=hit.get(3, False),
                hit_sl_7d=hit.get(7, False),
                hit_sl_14d=hit.get(14, False),
                hours_to_sl=hours_to_sl,
                sl_ts=sl_ts,
                exit_stoch_k=exit_sk,
                exit_rsi=exit_rsi,
            )
        )
    return episodes


def rate(xs: Sequence[bool]) -> Optional[float]:
    if not xs:
        return None
    return sum(1 for x in xs if x) / len(xs)


def wilson_ci(successes: int, n: int, z: float = 1.96) -> Tuple[Optional[float], Optional[float]]:
    if n <= 0:
        return None, None
    p = successes / n
    denom = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    lo = (centre - margin) / denom
    hi = (centre + margin) / denom
    return max(0.0, lo), min(1.0, hi)


def bucket_stats(episodes: Sequence[BuyEpisode], mask: Sequence[bool], horizon: str) -> dict:
    sub = [e for e, m in zip(episodes, mask) if m]
    hits = [getattr(e, horizon) for e in sub]
    s = sum(1 for h in hits if h)
    n = len(hits)
    lo, hi = wilson_ci(s, n)
    return {
        "n": n,
        "sl_hits": s,
        "sl_rate": (s / n) if n else None,
        "wilson_lo": lo,
        "wilson_hi": hi,
    }


def compare_threshold(
    episodes: Sequence[BuyEpisode],
    *,
    attr: str,
    thr: float,
    horizon: str = "hit_sl_7d",
    require_not_none: bool = True,
) -> dict:
    low_mask = []
    high_mask = []
    for e in episodes:
        v = getattr(e, attr)
        if v is None and require_not_none:
            low_mask.append(False)
            high_mask.append(False)
            continue
        if v is None:
            low_mask.append(False)
            high_mask.append(False)
            continue
        low_mask.append(v < thr)
        high_mask.append(v >= thr)
    low = bucket_stats(episodes, low_mask, horizon)
    high = bucket_stats(episodes, high_mask, horizon)
    lift = None
    if low["sl_rate"] is not None and high["sl_rate"] not in (None, 0):
        lift = low["sl_rate"] / high["sl_rate"]
    elif low["sl_rate"] is not None and high["sl_rate"] == 0 and low["sl_rate"] > 0:
        lift = float("inf")
    return {
        "attr": attr,
        "threshold": thr,
        "horizon": horizon,
        "low": low,
        "high": high,
        "lift_low_over_high": lift,
        "rule": f"{attr} < {thr} vs >={thr}",
    }


def rsi_controlled_stoch(
    episodes: Sequence[BuyEpisode],
    *,
    stoch_thr: float = 30.0,
    rsi_lo: float = 40.0,
    rsi_hi: float = 60.0,
    horizon: str = "hit_sl_7d",
) -> dict:
    """Stoch split only where RSI is mid — tests additive info."""
    mid = [e for e in episodes if e.rsi is not None and rsi_lo <= e.rsi <= rsi_hi and e.stoch_k is not None]
    low_m = [e.stoch_k < stoch_thr for e in mid]
    # rebuild as full-length masks relative to mid list via bucket on mid only
    low_eps = [e for e in mid if e.stoch_k is not None and float(e.stoch_k) < stoch_thr]
    high_eps = [e for e in mid if e.stoch_k is not None and float(e.stoch_k) >= stoch_thr]
    def br(eps):
        hits = [getattr(e, horizon) for e in eps]
        s = sum(1 for h in hits if h)
        n = len(hits)
        lo, hi = wilson_ci(s, n)
        return {"n": n, "sl_hits": s, "sl_rate": (s / n) if n else None, "wilson_lo": lo, "wilson_hi": hi}
    low, high = br(low_eps), br(high_eps)
    lift = None
    if low["sl_rate"] is not None and high["sl_rate"] not in (None, 0):
        lift = low["sl_rate"] / high["sl_rate"]
    return {
        "rsi_band": [rsi_lo, rsi_hi],
        "stoch_thr": stoch_thr,
        "horizon": horizon,
        "n_mid_rsi": len(mid),
        "low_stoch": low,
        "high_stoch": high,
        "lift": lift,
        "note": "Additive test: Stoch split inside RSI-neutral band only",
    }


def trailing_exit_baseline(episodes: Sequence[BuyEpisode], thr: float = 30.0) -> dict:
    """Among episodes that hit SL, distribution of exit stoch (trailing / reverse-causality)."""
    hit = [e for e in episodes if e.hit_sl_14d and e.exit_stoch_k is not None]
    ks = [e.exit_stoch_k for e in hit if e.exit_stoch_k is not None]
    if not ks:
        return {"n": 0}
    return {
        "n": len(ks),
        "mean": statistics.mean(ks),
        "median": statistics.median(ks),
        "pct_lt_thr": sum(1 for k in ks if k < thr) / len(ks),
        "threshold": thr,
        "caveat": "Exit Stoch is trailing — expected low after adverse move; not proof of entry utility.",
    }


def entry_vs_exit_on_sl_hits(episodes: Sequence[BuyEpisode], thr: float = 30.0) -> dict:
    hit = [
        e
        for e in episodes
        if e.hit_sl_14d and e.stoch_k is not None
    ]
    entry_low = sum(1 for e in hit if e.stoch_k is not None and float(e.stoch_k) < thr)
    with_exit = [e for e in hit if e.exit_stoch_k is not None]
    exit_low = sum(1 for e in with_exit if e.exit_stoch_k is not None and float(e.exit_stoch_k) < thr)
    return {
        "sl_hits_with_entry_stoch": len(hit),
        "entry_stoch_lt_thr": entry_low,
        "entry_pct_lt_thr": (entry_low / len(hit)) if hit else None,
        "sl_hits_with_exit_stoch": len(with_exit),
        "exit_stoch_lt_thr": exit_low,
        "exit_pct_lt_thr": (exit_low / len(with_exit)) if with_exit else None,
        "threshold": thr,
        "interpretation": (
            "If exit_pct >> entry_pct, Stoch is mostly trailing the loss path. "
            "If entry_pct elevated vs non-SL baseline, possible leading signal."
        ),
    }


def recommend(analysis: dict) -> Tuple[str, List[str], str]:
    """
    Enums:
      no_utility_drop | weak_keep_observe | scoped_shadow_sl_risk | extend_collect
    """
    caveats: List[str] = []
    primary = analysis.get("primary_7d_stoch30") or {}
    low = primary.get("low") or {}
    high = primary.get("high") or {}
    n_low = low.get("n") or 0
    n_high = high.get("n") or 0
    n = n_low + n_high
    lift = primary.get("lift_low_over_high")
    add = analysis.get("rsi_controlled") or {}
    add_lift = add.get("lift")
    entry_exit = analysis.get("entry_vs_exit") or {}
    entry_pct = entry_exit.get("entry_pct_lt_thr")
    exit_pct = entry_exit.get("exit_pct_lt_thr")

    if n < 12:
        caveats.append(f"thin labeled buys with entry Stoch (n={n}) — do not ship live knobs")
        return (
            "extend_collect",
            caveats
            + [
                "Need more buys with entry tags OR longer window after Stoch instrumentation.",
                "Allocator stays plain RSI; no live SL change.",
            ],
            "Sample too small for utility call.",
        )

    # Clear trailing-only pattern
    trailing_dom = (
        exit_pct is not None
        and entry_pct is not None
        and exit_pct >= 0.7
        and entry_pct <= 0.45
        and (lift is None or lift < 1.25)
    )
    if trailing_dom and (add_lift is None or add_lift < 1.2):
        caveats.append("Exit Stoch much hotter than entry Stoch on SL paths — reverse-causality dominates")
        return (
            "no_utility_drop",
            caveats
            + [
                "Stoch remains useful as risk *label/narrative* at stress, not as entry SL predictor.",
                "No scoped shadow SL threshold experiment.",
            ],
            "No leading utility vs reverse-causality / weak lift.",
        )

    # Inverted primary (low Stoch *safer* on this tape) kills promote/shadow.
    if lift is not None and lift < 0.9 and n_low >= 5 and n_high >= 5:
        caveats.append(
            f"Primary entry Stoch lift inverted ({lift:.2f}x) — low Stoch cohort did not SL more"
        )
        if add_lift is not None and add_lift >= 1.25 and (add.get("low_stoch") or {}).get("n", 0) < 8:
            caveats.append(
                "RSI-neutral Stoch lift ignored: additive low-bucket n too small to override inverted primary"
            )
        return (
            "no_utility_drop",
            caveats
            + [
                "Trailing exit Stoch can still look hot; that is not entry prediction utility.",
                "Keep Stoch on scorer narrative only; no SL threshold experiment.",
            ],
            "No leading SL utility — entry low-Stoch did not predict more stops.",
        )

    strong = (
        lift is not None
        and lift >= 1.5
        and n_low >= 5
        and n_high >= 5
        and (low.get("sl_rate") or 0) >= 0.25
        and (add_lift is None or add_lift >= 1.2 or (add.get("n_mid_rsi") or 0) < 6)
    )
    if strong:
        caveats.append("Still offline/shadow only — multi-lot pair matching is coarse")
        return (
            "scoped_shadow_sl_risk",
            caveats
            + [
                f"Entry Stoch<{primary.get('threshold')} shows lift≈{lift:.2f}x on {primary.get('horizon')}.",
                "Next: log-only shadow at arm; no Coinbase SL % change without Brad go.",
            ],
            "Entry Stoch shows usable SL lift — shadow experiment warranted.",
        )

    add_n_low = (add.get("low_stoch") or {}).get("n") or 0
    mild = lift is not None and lift >= 1.15 and n >= 12
    mild_add = (
        add_lift is not None
        and add_lift >= 1.25
        and add_n_low >= 8
        and (lift is None or lift >= 0.9)
    )
    if mild or mild_add:
        caveats.append("Signal mild or sample still thin — keep collecting")
        return (
            "weak_keep_observe",
            caveats
            + [
                "Possible sensitivity edge; not strong enough for live or aggressive shadow sizing.",
                "Re-run at Stoch final + more tagged buys.",
            ],
            "Weak/possible leading signal — observe, don't promote.",
        )

    caveats.append("Lift not material after entry-time framing")
    return (
        "no_utility_drop",
        caveats
        + [
            "Higher sensitivity ≠ reliable SL predictor ahead of the move.",
            "Keep Stoch on scorer narrative; do not gate entries or SL distance.",
        ],
        "No material entry-time SL prediction utility.",
    )


def run_analysis(
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    trades_path: Path = TRADES_JSONL,
    history_path: Path = HISTORY_JSONL,
) -> dict:
    trades = load_trades(trades_path)
    hist = load_history(history_path)
    if start is None:
        start = parse_ts(DEFAULT_TRIAL_START)
    if end is None:
        end = datetime.now(timezone.utc)

    episodes = build_buy_episodes(trades, hist, start=start, end=end)
    with_sk = [e for e in episodes if e.stoch_k is not None]
    with_rsi = [e for e in episodes if e.rsi is not None]

    primary = compare_threshold(with_sk, attr="stoch_k", thr=30.0, horizon="hit_sl_7d")
    stoch20 = compare_threshold(with_sk, attr="stoch_k", thr=20.0, horizon="hit_sl_7d")
    stoch30_14 = compare_threshold(with_sk, attr="stoch_k", thr=30.0, horizon="hit_sl_14d")
    stoch30_3 = compare_threshold(with_sk, attr="stoch_k", thr=30.0, horizon="hit_sl_3d")
    rsi35 = compare_threshold(with_rsi, attr="rsi", thr=35.0, horizon="hit_sl_7d")
    rsi_ctrl = rsi_controlled_stoch(with_sk, stoch_thr=30.0, horizon="hit_sl_7d")
    trailing = trailing_exit_baseline(with_sk, thr=30.0)
    entry_exit = entry_vs_exit_on_sl_hits(with_sk, thr=30.0)

    # coverage
    src_counts: Dict[str, int] = defaultdict(int)
    for e in episodes:
        src_counts[e.ind_source] += 1

    analysis = {
        "window": {"start": start.isoformat() if start else None, "end": end.isoformat()},
        "n_buys": len(episodes),
        "n_with_entry_stoch": len(with_sk),
        "n_with_entry_rsi": len(with_rsi),
        "ind_source_counts": dict(src_counts),
        "base_sl_rate_7d": rate([e.hit_sl_7d for e in with_sk]),
        "base_sl_rate_14d": rate([e.hit_sl_14d for e in with_sk]),
        "primary_7d_stoch30": primary,
        "stoch20_7d": stoch20,
        "stoch30_3d": stoch30_3,
        "stoch30_14d": stoch30_14,
        "rsi35_7d": rsi35,
        "rsi_controlled": rsi_ctrl,
        "trailing_exit": trailing,
        "entry_vs_exit": entry_exit,
        "episodes": [asdict(e) for e in episodes],
    }
    enum, caveats, plain = recommend(analysis)
    analysis["recommendation"] = {
        "enum": enum,
        "plain_english": plain,
        "caveats": caveats,
        "go_live_sl_change": False,
        "go_allocator_change": False,
        "go_shadow": enum == "scoped_shadow_sl_risk",
    }
    return analysis


def render_markdown(analysis: dict, trial_id: str) -> str:
    rec = analysis["recommendation"]
    p = analysis.get("primary_7d_stoch30") or {}
    lines = [
        f"# Stoch → SL predictor — offline report",
        "",
        f"**Trial:** `{trial_id}`  ",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}  ",
        f"**Window:** `{analysis['window']['start']}` → `{analysis['window']['end']}`  ",
        f"**Recommendation:** **{rec['enum']}**  ",
        f"**Plain English:** {rec['plain_english']}  ",
        "",
        "## Hypothesis",
        "",
        "Low Stoch %K **at buy/arm** predicts higher stop-loss rate within 3–14d, "
        "beyond plain RSI — i.e. leading risk signal, not only trailing label after the drop.",
        "",
        "## Method",
        "",
        "- Real fills: `trades/phase6_trades.jsonl`",
        "- Entry indicators: `indicators_at_trade` else nearest `rsi_indicator_history.jsonl` (≤90m before / 10m after)",
        "- Label: first `stop_loss*` on **same pair** after buy within horizon",
        "- Controls: RSI&lt;35 split; RSI-neutral band Stoch split (additive test)",
        "- Trailing check: exit Stoch on SL hits vs entry Stoch",
        "- **Non-goals:** live SL %, allocator, Stoch param search",
        "",
        "## Coverage",
        "",
        f"- Buys in window: **{analysis['n_buys']}**",
        f"- With entry Stoch: **{analysis['n_with_entry_stoch']}** | RSI: **{analysis['n_with_entry_rsi']}**",
        f"- Ind sources: `{analysis['ind_source_counts']}`",
        f"- Base SL rate (entry-Stoch cohort): 7d **{_pct(analysis.get('base_sl_rate_7d'))}** | 14d **{_pct(analysis.get('base_sl_rate_14d'))}**",
        "",
        "## Primary test — entry Stoch %K &lt; 30 vs ≥ 30 (7d SL)",
        "",
        _fmt_compare(p),
        "",
        "### Also",
        "",
        f"- Stoch&lt;20 @7d: {_fmt_compare_inline(analysis.get('stoch20_7d'))}",
        f"- Stoch&lt;30 @3d: {_fmt_compare_inline(analysis.get('stoch30_3d'))}",
        f"- Stoch&lt;30 @14d: {_fmt_compare_inline(analysis.get('stoch30_14d'))}",
        f"- RSI&lt;35 @7d (control): {_fmt_compare_inline(analysis.get('rsi35_7d'))}",
        "",
        "## Additive test (RSI 40–60 only)",
        "",
        f"`{json.dumps(analysis.get('rsi_controlled'), indent=2)}`",
        "",
        "## Trailing vs leading",
        "",
        f"- Exit baseline: `{analysis.get('trailing_exit')}`",
        f"- Entry vs exit on SL hits: `{analysis.get('entry_vs_exit')}`",
        "",
        "## Caveats",
        "",
    ]
    for c in rec.get("caveats") or []:
        lines.append(f"- {c}")
    lines += [
        "- Multi-lot / partial exits: pair-level forward SL is coarse (may over-attribute).",
        "- Buys that opened before Stoch instrumentation often lack true entry Stoch (history join helps only post-history).",
        "- Small n → wide Wilson intervals; do not overfit thresholds.",
        "",
        "## Decision gates",
        "",
        f"- Live SL change: **{rec.get('go_live_sl_change')}**",
        f"- Allocator change: **{rec.get('go_allocator_change')}**",
        f"- Shadow SL-risk log: **{rec.get('go_shadow')}**",
        "",
        "## Honest assessment",
        "",
        "Stoch is more sensitive than RSI (more extremes, more disagreements). Sensitivity can mean "
        "**earlier stress labeling** and **stronger trailing confirmation** without being a clean "
        "**direction/entry filter**. This report scores *entry-time SL prediction only*.",
        "",
    ]
    return "\n".join(lines)


def _pct(x: Optional[float]) -> str:
    if x is None:
        return "n/a"
    return f"{100 * x:.1f}%"


def _fmt_compare(p: dict) -> str:
    if not p:
        return "_no data_"
    low, high = p.get("low") or {}, p.get("high") or {}
    return (
        f"- Rule: `{p.get('rule')}`\n"
        f"- Low bucket: n={low.get('n')} hits={low.get('sl_hits')} rate={_pct(low.get('sl_rate'))} "
        f"CI=[{_pct(low.get('wilson_lo'))}, {_pct(low.get('wilson_hi'))}]\n"
        f"- High bucket: n={high.get('n')} hits={high.get('sl_hits')} rate={_pct(high.get('sl_rate'))} "
        f"CI=[{_pct(high.get('wilson_lo'))}, {_pct(high.get('wilson_hi'))}]\n"
        f"- Lift (low/high): **{p.get('lift_low_over_high')}**"
    )


def _fmt_compare_inline(p: Optional[dict]) -> str:
    if not p:
        return "n/a"
    low, high = p.get("low") or {}, p.get("high") or {}
    return (
        f"low n={low.get('n')} rate={_pct(low.get('sl_rate'))} | "
        f"high n={high.get('n')} rate={_pct(high.get('sl_rate'))} | lift={p.get('lift_low_over_high')}"
    )
