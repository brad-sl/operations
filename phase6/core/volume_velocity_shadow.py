#!/usr/bin/env python3
"""
Volume-velocity shadow arm — early RVOL nominator for swap-evaluation research.

Job (Brad 2026-08-21)
---------------------
Nominate coins that are *starting to trade* (relative volume / velocity) into a
**shadow evaluation queue**. Track:

  1) Do they ever meet existing selection / discovery / membership gates?
  2) How do they perform on their own even if *never* selected for the basket?

Never mutates config. Never places orders. No sentiment spend.

Primary metric: RVOL = recent volume / mean of prior N periods (own history).
Optional multi-TF: 1h RVOL + 1d RVOL. Coil flag: high RVOL + modest |return|.

Vol/MCap deferred (no reliable free mcap on Coinbase public path).
"""
from __future__ import annotations

import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import requests

from phase6.core.paths import PROJECT_ROOT, load_trading_basket
from phase6.core.pair_discovery import (
    EXCLUDE_BASES,
    EXCLUDE_IDS_EXACT,
)

PUBLIC = "https://api.exchange.coinbase.com"
UA = {"User-Agent": "phase6-volume-velocity-shadow/1.0 (research; no orders)"}

STATE_DIR = PROJECT_ROOT / "data" / "state"
LATEST = STATE_DIR / "volume_velocity_shadow_latest.json"
TRACKS = STATE_DIR / "volume_velocity_tracks.json"
EVENTS = STATE_DIR / "volume_velocity_events.jsonl"
NOMINATIONS = STATE_DIR / "volume_velocity_nominations.jsonl"
MD_REPORT = PROJECT_ROOT / "reports" / "VOLUME_VELOCITY_SHADOW_LATEST.md"

HORIZONS_H = (6, 24, 72, 168)  # 6h, 1d, 3d, 7d


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _utc_now()).astimezone(timezone.utc).isoformat()


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    return s


@dataclass
class VelocityConfig:
    # Universe / cost control
    min_quote_volume_24h_usd: float = 150_000.0  # lower than discovery — catch early
    max_quote_volume_24h_usd: float = 80_000_000.0  # skip mega-liquid always-on tape for "early"
    always_include_top_n: int = 15  # still watch majors for context
    max_stats_workers: int = 14
    candle_workers: int = 8
    # How many names get 1h candles each run (plus open tracks)
    candle_scan_top_n: int = 80
    # Prefer mid-tier: mix top liquid + mid volume band (wake-ups live here)
    mid_band_low_usd: float = 200_000.0
    mid_band_high_usd: float = 15_000_000.0
    mid_band_scan_n: int = 50
    # RVOL (completed hour + 3h burst — last bar is usually incomplete)
    rvol_lookback_bars: int = 20  # prior bars for mean
    rvol_1h_min: float = 1.75  # completed 1h bar
    rvol_burst_3h_min: float = 2.0  # primary "starting to trade" flag
    rvol_1d_min: float = 1.5  # daily bar RVOL softer
    require_dual_tf: bool = False  # if True need 1h AND 1d
    # Prefer waking-up vs already exploded
    max_abs_ret_24h_for_early: float = 0.35  # |ret| above = chase, still log as hot
    coil_abs_ret_24h: float = 0.08  # high RVOL + |ret|<this = coil
    # Tracking
    max_open_tracks: int = 40
    track_ttl_days: int = 14
    equal_notional_usd: float = 100.0  # paper sleeve for performance
    # Pump brake (still nominate to "hot" bucket, not early)
    pump_ret_24h_abs: float = 0.80
    sleep_s: float = 0.06


@dataclass
class Nomination:
    pair: str
    ts: str
    last_px: float
    vol_quote_24h: float
    ret_24h: float
    rvol_1h: float
    rvol_1d: Optional[float]
    vol_accel_24h: Optional[float]
    bucket: str  # early_coil | early_trend | hot_chase | dual_tf
    reasons: List[str] = field(default_factory=list)
    in_active_basket: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

def list_usd_products(sess: requests.Session) -> List[str]:
    r = sess.get(f"{PUBLIC}/products", timeout=30)
    r.raise_for_status()
    out: List[str] = []
    for p in r.json() or []:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "")
        if not pid.endswith("-USD"):
            continue
        if pid in EXCLUDE_IDS_EXACT:
            continue
        base = pid.split("-")[0]
        if base in EXCLUDE_BASES:
            continue
        if p.get("status") not in (None, "online"):
            if str(p.get("status")).lower() not in ("online",):
                continue
        if p.get("trading_disabled") is True:
            continue
        out.append(pid)
    return sorted(set(out))


def fetch_stats(pid: str, sess: requests.Session, timeout: float = 12.0) -> Dict[str, Any]:
    out: Dict[str, Any] = {"product_id": pid, "ok": False}
    try:
        r = sess.get(f"{PUBLIC}/products/{pid}/stats", timeout=timeout)
        if r.status_code != 200:
            out["error"] = f"stats {r.status_code}"
            return out
        sd = r.json()
        last = _f(sd.get("last"))
        open_ = _f(sd.get("open"))
        high = _f(sd.get("high"))
        low = _f(sd.get("low"))
        vol = _f(sd.get("volume"))
        mid = (high + low) / 2.0 if high and low else last
        out.update(
            {
                "ok": True,
                "last": last,
                "open_24h": open_,
                "volume_base_24h": vol,
                "volume_quote_24h_est": vol * mid if mid else 0.0,
                "ret_24h": ((last - open_) / open_) if open_ else None,
            }
        )
    except Exception as e:
        out["error"] = str(e)[:160]
    return out


def fetch_candles_1h(pid: str, n_bars: int, sess: requests.Session) -> List[list]:
    """Newest-last candles: [time, low, high, open, close, volume]."""
    end = _utc_now()
    start = end - timedelta(hours=n_bars + 5)
    params = {
        "granularity": 3600,
        "start": start.isoformat().replace("+00:00", "Z"),
        "end": end.isoformat().replace("+00:00", "Z"),
    }
    try:
        r = sess.get(f"{PUBLIC}/products/{pid}/candles", params=params, timeout=25)
        if r.status_code != 200:
            return []
        rows = sorted(r.json() or [], key=lambda x: x[0])
        return rows[-n_bars:] if len(rows) > n_bars else rows
    except Exception:
        return []


def rvol_from_vols(vols: Sequence[float], lookback: int, *, use_last: bool = True) -> Optional[float]:
    """RVOL of a bar vs mean of prior `lookback` bars.

    use_last=False → penultimate bar (prefer for incomplete current hour).
    """
    if use_last:
        if len(vols) < lookback + 1:
            return None
        last = float(vols[-1])
        prior = [float(v) for v in vols[-(lookback + 1) : -1]]
    else:
        if len(vols) < lookback + 2:
            return None
        last = float(vols[-2])
        prior = [float(v) for v in vols[-(lookback + 2) : -2]]
    mean_p = sum(prior) / len(prior) if prior else 0.0
    if mean_p <= 0:
        return None
    return last / mean_p


def rvol_burst_nh(vols: Sequence[float], n_hours: int, lookback_hours: int) -> Optional[float]:
    """Sum of last n_hours vol / (n_hours × mean hourly vol of prior lookback_hours)."""
    need = n_hours + lookback_hours
    if len(vols) < need:
        return None
    # drop incomplete last bar if present — use through penultimate as end of burst
    series = list(vols[:-1]) if len(vols) >= need + 1 else list(vols)
    if len(series) < need:
        return None
    burst = sum(float(v) for v in series[-n_hours:])
    prior = [float(v) for v in series[-(n_hours + lookback_hours) : -n_hours]]
    mean_p = sum(prior) / len(prior) if prior else 0.0
    if mean_p <= 0:
        return None
    return (burst / n_hours) / mean_p

def daily_vols_from_hourly(candles: Sequence[list]) -> List[float]:
    """Aggregate hourly volume into UTC day buckets (oldest→newest)."""
    by_day: Dict[str, float] = {}
    for c in candles:
        ts = datetime.fromtimestamp(int(c[0]), tz=timezone.utc)
        key = ts.strftime("%Y-%m-%d")
        by_day[key] = by_day.get(key, 0.0) + float(c[5] or 0)
    keys = sorted(by_day)
    return [by_day[k] for k in keys]


def vol_accel_24h(candles: Sequence[list]) -> Optional[float]:
    if len(candles) < 48:
        return None
    vols = [float(c[5] or 0) for c in candles]
    rec = sum(vols[-24:])
    pri = sum(vols[-48:-24]) or 1e-12
    return min(rec / pri, 20.0)


def price_at_or_after(candles: Sequence[list], ts: datetime) -> Optional[float]:
    t = int(ts.timestamp())
    for c in candles:
        if int(c[0]) >= t:
            return float(c[4])
    return float(candles[-1][4]) if candles else None


def price_now(candles: Sequence[list]) -> Optional[float]:
    return float(candles[-1][4]) if candles else None


# ---------------------------------------------------------------------------
# Gate probes (existing stack — shadow read-only)
# ---------------------------------------------------------------------------

def load_discovery_snapshot() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "contender_ids": set(),
        "quality_by_pair": {},
        "promote_eligible": set(),
        "pipeline_as_of": None,
    }
    cpath = STATE_DIR / "pair_discovery_contenders.json"
    if cpath.exists():
        try:
            data = json.loads(cpath.read_text(encoding="utf-8"))
            rows = data if isinstance(data, list) else data.get("contenders") or data.get("rows") or []
            for r in rows:
                if not isinstance(r, dict):
                    continue
                pid = r.get("product_id") or r.get("pair")
                if not pid:
                    continue
                out["contender_ids"].add(pid)
                out["quality_by_pair"][pid] = r
                if r.get("promote_eligible") or r.get("pass_gate"):
                    out["promote_eligible"].add(pid)
        except Exception:
            pass
    dpath = STATE_DIR / "discovery_pipeline_latest.json"
    if dpath.exists():
        try:
            d = json.loads(dpath.read_text(encoding="utf-8"))
            out["pipeline_as_of"] = d.get("as_of") or d.get("ts")
            for r in d.get("contenders") or []:
                if isinstance(r, dict) and r.get("product_id"):
                    out["contender_ids"].add(r["product_id"])
                    if r.get("promote_eligible"):
                        out["promote_eligible"].add(r["product_id"])
        except Exception:
            pass
    # latest discovery quality list
    lpath = STATE_DIR / "pair_discovery_latest.json"
    if lpath.exists():
        try:
            d = json.loads(lpath.read_text(encoding="utf-8"))
            for r in d.get("quality") or d.get("quality_rows") or []:
                if isinstance(r, dict) and r.get("product_id"):
                    out["quality_by_pair"][r["product_id"]] = {
                        **out["quality_by_pair"].get(r["product_id"], {}),
                        **r,
                    }
                    if r.get("pass_gate"):
                        out["contender_ids"].add(r["product_id"])
        except Exception:
            pass
    return out


def load_pool_proposal_adds() -> Set[str]:
    """Pairs that cycler has proposed as ADD (shadow)."""
    adds: Set[str] = set()
    for path in (
        STATE_DIR / "pool_cycling_proposed_pairs.json",
        STATE_DIR / "pool_cycling_latest.json",
    ):
        if not path.exists():
            continue
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if path.name == "pool_cycling_proposed_pairs.json":
            for a in d.get("add") or d.get("adds") or []:
                adds.add(str(a))
            if d.get("add_pair"):
                adds.add(str(d["add_pair"]))
        swaps = d.get("swaps") or d.get("proposals") or []
        for s in swaps:
            if isinstance(s, dict):
                a = s.get("add") or s.get("add_pair") or s.get("in")
                if a:
                    adds.add(str(a))
    # jsonl tail
    jpath = STATE_DIR / "pool_cycling_proposals.jsonl"
    if jpath.exists():
        try:
            lines = jpath.read_text(encoding="utf-8", errors="replace").splitlines()[-50:]
            for L in lines:
                try:
                    o = json.loads(L)
                except Exception:
                    continue
                a = o.get("add") or o.get("add_pair")
                if a:
                    adds.add(str(a))
                for s in o.get("swaps") or []:
                    if isinstance(s, dict) and s.get("add"):
                        adds.add(str(s["add"]))
        except Exception:
            pass
    return adds


def synthetic_gate_check(
    *,
    pair: str,
    ret_24h: Optional[float],
    mom_3d: Optional[float],
    mom_7d: Optional[float],
    rvol_1h: float,
    vol_quote_24h: float,
    quality_row: Optional[Dict[str, Any]],
    in_contenders: bool,
    promote_eligible: bool,
    proposed_add: bool,
    cfg: VelocityConfig,
) -> Dict[str, Any]:
    """Lightweight mirror of why current stack might reject early velocity names."""
    fails: List[str] = []
    passes: List[str] = []

    if vol_quote_24h >= 2_000_000:
        passes.append("discovery_liq_floor_2m")
    else:
        fails.append(f"below_discovery_liq_floor({vol_quote_24h:,.0f}<2e6)")

    if vol_quote_24h >= 1_500_000:
        passes.append("membership_liq_floor_1.5m")
    else:
        fails.append(f"below_membership_liq({vol_quote_24h:,.0f}<1.5e6)")

    if ret_24h is not None and abs(ret_24h) > cfg.pump_ret_24h_abs:
        fails.append("pump_brake_ret24")
    else:
        passes.append("not_hyper_pump")

    # Discovery often wants quality score + mom
    q = quality_row or {}
    qs = q.get("quality_score")
    if qs is not None:
        if float(qs) >= 0.35:
            passes.append(f"quality_score>={float(qs):.2f}")
        else:
            fails.append(f"quality_score_low({float(qs):.2f})")
    else:
        fails.append("no_discovery_quality_row")

    if q.get("pass_gate") or promote_eligible:
        passes.append("discovery_pass_or_promote")
    elif in_contenders:
        passes.append("on_contender_list")
        fails.append("contender_but_not_promote")
    else:
        fails.append("not_in_discovery_contenders")

    if proposed_add:
        passes.append("pool_cycler_proposed_add")
    else:
        fails.append("never_pool_cycler_add")

    # Hypothesis lane: high RVOL + thin discovery fit
    low_qualified = (
        rvol_1h >= cfg.rvol_1h_min
        and (qs is None or float(qs) < 0.35 or not (q.get("pass_gate") or promote_eligible))
    )
    return {
        "passes": passes,
        "fails": fails,
        "in_contenders": in_contenders,
        "promote_eligible": promote_eligible,
        "proposed_add": proposed_add,
        "quality_score": qs,
        "low_qualified_high_velocity": low_qualified,
        "would_clear_legacy_funnel": bool(
            promote_eligible or (q.get("pass_gate") and vol_quote_24h >= 2_000_000)
        ),
    }


# ---------------------------------------------------------------------------
# Tracks + performance
# ---------------------------------------------------------------------------

def load_tracks() -> Dict[str, Any]:
    if TRACKS.exists():
        try:
            return json.loads(TRACKS.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"schema": "volume_velocity_tracks_v1", "open": {}, "closed": []}


def save_tracks(data: Dict[str, Any]) -> None:
    TRACKS.parent.mkdir(parents=True, exist_ok=True)
    TRACKS.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def update_track_performance(
    track: Dict[str, Any],
    candles: Sequence[list],
    now: datetime,
) -> None:
    entry_ts = datetime.fromisoformat(str(track["nominated_at"]).replace("Z", "+00:00"))
    entry_px = _f(track.get("entry_px"))
    if entry_px <= 0:
        px0 = price_at_or_after(candles, entry_ts)
        if px0:
            track["entry_px"] = px0
            entry_px = px0
    if entry_px <= 0:
        return
    mark = price_now(candles)
    if not mark:
        return
    track["mark_px"] = mark
    track["mark_r"] = (mark / entry_px) - 1.0
    track["updated_at"] = _iso(now)
    rets = track.setdefault("forward_ret", {})
    for h in HORIZONS_H:
        key = f"{h}h"
        if key in rets and rets[key] is not None:
            continue
        target = entry_ts + timedelta(hours=h)
        if now < target:
            continue
        px = price_at_or_after(candles, target)
        if px and entry_px:
            rets[key] = (px / entry_px) - 1.0
    # max favorable / adverse excursion from hourly highs/lows after entry
    t0 = int(entry_ts.timestamp())
    mfe = track.get("mfe")
    mae = track.get("mae")
    for c in candles:
        if int(c[0]) < t0:
            continue
        hi, lo = float(c[2]), float(c[1])
        if entry_px > 0:
            up = (hi / entry_px) - 1.0
            dn = (lo / entry_px) - 1.0
            mfe = up if mfe is None else max(mfe, up)
            mae = dn if mae is None else min(mae, dn)
    track["mfe"] = mfe
    track["mae"] = mae
    # paper PnL on equal notional
    notion = _f(track.get("notional_usd"), 100.0)
    track["paper_pnl_usd"] = notion * track["mark_r"]


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run_volume_velocity_shadow(cfg: Optional[VelocityConfig] = None) -> Dict[str, Any]:
    cfg = cfg or VelocityConfig()
    now = _utc_now()
    sess = _session()
    active = set(load_trading_basket() or [])

    products = list_usd_products(sess)
    # stats fan-out
    stats_rows: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=cfg.max_stats_workers) as ex:
        futs = {ex.submit(fetch_stats, pid, sess): pid for pid in products}
        for fut in as_completed(futs):
            row = fut.result()
            if row.get("ok") and _f(row.get("volume_quote_24h_est")) >= cfg.min_quote_volume_24h_usd:
                stats_rows.append(row)
            time.sleep(cfg.sleep_s / max(cfg.max_stats_workers, 1))

    stats_rows.sort(key=lambda r: _f(r.get("volume_quote_24h_est")), reverse=True)
    disc = load_discovery_snapshot()
    proposed_adds = load_pool_proposal_adds()

    tracks_doc = load_tracks()
    open_tracks: Dict[str, Any] = dict(tracks_doc.get("open") or {})
    # expire old
    ttl = timedelta(days=cfg.track_ttl_days)
    closed = list(tracks_doc.get("closed") or [])
    for pid, tr in list(open_tracks.items()):
        try:
            t0 = datetime.fromisoformat(str(tr["nominated_at"]).replace("Z", "+00:00"))
            if now - t0 > ttl:
                tr["status"] = "expired"
                tr["closed_at"] = _iso(now)
                closed.append(tr)
                del open_tracks[pid]
        except Exception:
            pass

    # Scan mix: top liquid (context) + mid-band (where quiet→loud shows up)
    top = [r["product_id"] for r in stats_rows[: cfg.always_include_top_n]]
    mid = [
        r["product_id"]
        for r in stats_rows
        if cfg.mid_band_low_usd <= _f(r.get("volume_quote_24h_est")) <= cfg.mid_band_high_usd
    ][: cfg.mid_band_scan_n]
    # also a slice of remaining top-N by vol for coverage
    rest = [r["product_id"] for r in stats_rows[: cfg.candle_scan_top_n]]
    scan_set: List[str] = []
    for pid in top + mid + rest + list(open_tracks.keys()):
        if pid not in scan_set:
            scan_set.append(pid)
    scan_set = scan_set[: max(cfg.candle_scan_top_n, cfg.always_include_top_n + cfg.mid_band_scan_n)]
    # candle + RVOL
    need_bars = max(cfg.rvol_lookback_bars + 5, 72) + 24  # room for daily agg
    candle_cache: Dict[str, List[list]] = {}
    metrics: Dict[str, Dict[str, Any]] = {}

    def one(pid: str) -> Tuple[str, List[list], Dict[str, Any]]:
        s2 = _session()
        candles = fetch_candles_1h(pid, need_bars + 48, s2)
        time.sleep(cfg.sleep_s)
        vols = [float(c[5] or 0) for c in candles] if candles else []
        # Completed hour RVOL (skip incomplete forming bar)
        r1h = rvol_from_vols(vols, cfg.rvol_lookback_bars, use_last=False) if vols else None
        r1h_raw = rvol_from_vols(vols, cfg.rvol_lookback_bars, use_last=True) if vols else None
        r3h = rvol_burst_nh(vols, 3, cfg.rvol_lookback_bars) if vols else None
        dvols = daily_vols_from_hourly(candles) if candles else []
        r1d = (
            rvol_from_vols(dvols, min(10, max(3, len(dvols) - 1)), use_last=True)
            if len(dvols) >= 5
            else None
        )
        va = vol_accel_24h(candles) if candles else None
        # 3d/7d mom from hourly closes
        closes = [float(c[4]) for c in candles] if candles else []
        mom_3d = mom_7d = None
        if len(closes) >= 72:
            mom_3d = closes[-1] / closes[-72] - 1.0
        if len(closes) >= 168:
            mom_7d = closes[-1] / closes[-168] - 1.0
        elif len(closes) >= 2:
            mom_7d = closes[-1] / closes[0] - 1.0
        return pid, candles, {
            "rvol_1h": r1h,
            "rvol_1h_forming": r1h_raw,
            "rvol_burst_3h": r3h,
            "rvol_1d": r1d,
            "vol_accel_24h": va,
            "mom_3d": mom_3d,
            "mom_7d": mom_7d,
            "last_px": closes[-1] if closes else None,
            "n_candles": len(candles),
        }
    with ThreadPoolExecutor(max_workers=cfg.candle_workers) as ex:
        futs = [ex.submit(one, pid) for pid in scan_set]
        for fut in as_completed(futs):
            try:
                pid, candles, m = fut.result()
            except Exception:
                continue
            candle_cache[pid] = candles
            metrics[pid] = m

    stats_by = {r["product_id"]: r for r in stats_rows}
    nominations: List[Nomination] = []

    for pid, m in metrics.items():
        r1h = m.get("rvol_1h")
        r3h = m.get("rvol_burst_3h")
        r1d = m.get("rvol_1d")
        hit_1h = r1h is not None and r1h >= cfg.rvol_1h_min
        hit_3h = r3h is not None and r3h >= cfg.rvol_burst_3h_min
        hit_1d = r1d is not None and r1d >= cfg.rvol_1d_min
        if not (hit_1h or hit_3h or (hit_1d and r1h and r1h >= 1.25)):
            continue
        if cfg.require_dual_tf and not (hit_1h and hit_1d):
            continue

        st = stats_by.get(pid) or {}
        vq = _f(st.get("volume_quote_24h_est"))
        # Optional mega-cap skip unless dual-TF or already tracked
        if (
            vq > cfg.max_quote_volume_24h_usd
            and pid not in open_tracks
            and not (hit_1h and hit_3h)
        ):
            continue

        ret24 = st.get("ret_24h")
        if ret24 is None and m.get("mom_3d") is not None:
            ret24 = m.get("mom_3d")  # weak fallback
        ret24 = _f(ret24, 0.0) if ret24 is not None else None

        reasons = []
        if r1h is not None:
            reasons.append(f"rvol_1h_done={r1h:.2f}")
        if r3h is not None:
            reasons.append(f"rvol_burst_3h={r3h:.2f}")
        if r1d is not None:
            reasons.append(f"rvol_1d={r1d:.2f}")
        if m.get("vol_accel_24h") is not None:
            reasons.append(f"vol_accel={m['vol_accel_24h']:.2f}")

        # Score for sort: prefer burst
        score_r = max(float(r3h or 0), float(r1h or 0), float(r1d or 0) * 0.8)

        abs_ret = abs(ret24) if ret24 is not None else 0.0
        if abs_ret >= cfg.pump_ret_24h_abs:
            bucket = "hot_chase"
            reasons.append("hyper_move")
        elif abs_ret <= cfg.coil_abs_ret_24h and (hit_1h or hit_3h):
            bucket = "early_coil"
            reasons.append("coil_volume")
        elif abs_ret <= cfg.max_abs_ret_24h_for_early:
            bucket = "early_trend"
        else:
            bucket = "hot_chase"
            reasons.append("extended_ret")

        if hit_1h and hit_1d:
            reasons.append("dual_tf_rvol")
            if bucket.startswith("early"):
                bucket = "dual_tf"

        nom = Nomination(
            pair=pid,
            ts=_iso(now),
            last_px=_f(m.get("last_px") or st.get("last")),
            vol_quote_24h=vq,
            ret_24h=_f(ret24) if ret24 is not None else 0.0,
            rvol_1h=float(score_r),  # primary score surface
            rvol_1d=float(r1d) if r1d is not None else None,
            vol_accel_24h=float(m["vol_accel_24h"]) if m.get("vol_accel_24h") is not None else None,
            bucket=bucket,
            reasons=reasons,
            in_active_basket=pid in active,
        )
        # stash detail on reasons already; also keep true 1h in track via reasons
        nominations.append(nom)
    # Prefer early buckets in sort
    bucket_rank = {"early_coil": 0, "dual_tf": 1, "early_trend": 2, "hot_chase": 3}
    nominations.sort(key=lambda n: (bucket_rank.get(n.bucket, 9), -n.rvol_1h))

    # Open / refresh tracks for nominations not in active (still track active for science)
    for nom in nominations:
        pid = nom.pair
        qrow = disc["quality_by_pair"].get(pid)
        gate = synthetic_gate_check(
            pair=pid,
            ret_24h=nom.ret_24h,
            mom_3d=(metrics.get(pid) or {}).get("mom_3d"),
            mom_7d=(metrics.get(pid) or {}).get("mom_7d"),
            rvol_1h=nom.rvol_1h,
            vol_quote_24h=nom.vol_quote_24h,
            quality_row=qrow,
            in_contenders=pid in disc["contender_ids"],
            promote_eligible=pid in disc["promote_eligible"],
            proposed_add=pid in proposed_adds,
            cfg=cfg,
        )
        if pid not in open_tracks:
            if len(open_tracks) >= cfg.max_open_tracks and nom.bucket == "hot_chase":
                continue
            if len(open_tracks) >= cfg.max_open_tracks:
                # drop weakest hot_chase by rvol
                victims = [
                    (k, v)
                    for k, v in open_tracks.items()
                    if v.get("bucket") == "hot_chase"
                ]
                if victims:
                    victims.sort(key=lambda kv: _f(kv[1].get("rvol_1h")))
                    del open_tracks[victims[0][0]]
                elif len(open_tracks) >= cfg.max_open_tracks:
                    continue
            open_tracks[pid] = {
                "pair": pid,
                "nominated_at": nom.ts,
                "entry_px": nom.last_px,
                "notional_usd": cfg.equal_notional_usd,
                "bucket": nom.bucket,
                "rvol_1h_at_nom": nom.rvol_1h,
                "rvol_1d_at_nom": nom.rvol_1d,
                "ret_24h_at_nom": nom.ret_24h,
                "vol_quote_24h_at_nom": nom.vol_quote_24h,
                "in_active_at_nom": nom.in_active_basket,
                "status": "open",
                "gate_first": gate,
                "gate_ever_promote": bool(gate.get("promote_eligible")),
                "gate_ever_contender": bool(gate.get("in_contenders")),
                "gate_ever_cycler_add": bool(gate.get("proposed_add")),
                "low_qualified_high_velocity": bool(gate.get("low_qualified_high_velocity")),
            }
            append_jsonl(NOMINATIONS, {**nom.to_dict(), "gate": gate})
        else:
            tr = open_tracks[pid]
            tr["last_seen_rvol_1h"] = nom.rvol_1h
            tr["last_bucket"] = nom.bucket
            tr["gate_latest"] = gate
            if gate.get("promote_eligible"):
                tr["gate_ever_promote"] = True
            if gate.get("in_contenders"):
                tr["gate_ever_contender"] = True
            if gate.get("proposed_add"):
                tr["gate_ever_cycler_add"] = True
            if gate.get("low_qualified_high_velocity"):
                tr["low_qualified_high_velocity"] = True

    # Update performance for all open tracks
    for pid, tr in open_tracks.items():
        candles = candle_cache.get(pid)
        if candles is None:
            candles = fetch_candles_1h(pid, need_bars + 48, sess)
            candle_cache[pid] = candles
        if candles:
            update_track_performance(tr, candles, now)
        # refresh gates even if not re-nominated this run
        qrow = disc["quality_by_pair"].get(pid)
        st = stats_by.get(pid) or {}
        m = metrics.get(pid) or {}
        gate = synthetic_gate_check(
            pair=pid,
            ret_24h=_f(st.get("ret_24h"), tr.get("ret_24h_at_nom")),
            mom_3d=m.get("mom_3d"),
            mom_7d=m.get("mom_7d"),
            rvol_1h=_f(tr.get("last_seen_rvol_1h"), tr.get("rvol_1h_at_nom")),
            vol_quote_24h=_f(st.get("volume_quote_24h_est"), tr.get("vol_quote_24h_at_nom")),
            quality_row=qrow,
            in_contenders=pid in disc["contender_ids"],
            promote_eligible=pid in disc["promote_eligible"],
            proposed_add=pid in proposed_adds,
            cfg=cfg,
        )
        tr["gate_latest"] = gate
        if gate.get("promote_eligible"):
            tr["gate_ever_promote"] = True
        if gate.get("in_contenders"):
            tr["gate_ever_contender"] = True
        if gate.get("proposed_add"):
            tr["gate_ever_cycler_add"] = True

    tracks_doc["open"] = open_tracks
    tracks_doc["closed"] = closed[-200:]
    tracks_doc["updated_at"] = _iso(now)
    save_tracks(tracks_doc)

    # Summary stats
    open_list = list(open_tracks.values())
    lqhv = [t for t in open_list if t.get("low_qualified_high_velocity")]
    ever_promote = [t for t in open_list if t.get("gate_ever_promote")]
    never_selected = [
        t
        for t in open_list
        if not t.get("gate_ever_promote") and not t.get("gate_ever_cycler_add")
    ]

    def mean_ret(tracks: List[Dict[str, Any]], key: str = "mark_r") -> Optional[float]:
        xs = [_f(t.get(key)) for t in tracks if t.get(key) is not None]
        # mark_r always set maybe 0
        xs = [ _f(t.get("mark_r")) for t in tracks if t.get("mark_px") ]
        return sum(xs) / len(xs) if xs else None

    def hit_rate(tracks: List[Dict[str, Any]]) -> Optional[float]:
        xs = [_f(t.get("mark_r")) for t in tracks if t.get("mark_px")]
        if not xs:
            return None
        return sum(1 for x in xs if x > 0) / len(xs)

    summary = {
        "schema": "volume_velocity_shadow_latest_v1",
        "as_of": _iso(now),
        "live_orders": False,
        "config": asdict(cfg),
        "universe_stats_ok": len(stats_rows),
        "candles_scanned": len(metrics),
        "nominations_this_run": len(nominations),
        "nominations": [n.to_dict() for n in nominations[:25]],
        "open_tracks": len(open_list),
        "open_by_bucket": _count_by(open_list, "bucket"),
        "low_qualified_high_velocity_n": len(lqhv),
        "ever_promote_eligible_n": len(ever_promote),
        "never_selected_n": len(never_selected),
        "perf_all_open": {
            "n": len(open_list),
            "mean_mark_r": mean_ret(open_list),
            "hit_rate": hit_rate(open_list),
            "mean_mfe": _mean([t.get("mfe") for t in open_list]),
            "mean_mae": _mean([t.get("mae") for t in open_list]),
        },
        "perf_lqhv": {
            "n": len(lqhv),
            "mean_mark_r": mean_ret(lqhv),
            "hit_rate": hit_rate(lqhv),
            "mean_mfe": _mean([t.get("mfe") for t in lqhv]),
        },
        "perf_never_selected": {
            "n": len(never_selected),
            "mean_mark_r": mean_ret(never_selected),
            "hit_rate": hit_rate(never_selected),
            "mean_mfe": _mean([t.get("mfe") for t in never_selected]),
        },
        "perf_ever_promote": {
            "n": len(ever_promote),
            "mean_mark_r": mean_ret(ever_promote),
            "hit_rate": hit_rate(ever_promote),
        },
        "top_open": sorted(
            open_list,
            key=lambda t: _f(t.get("mark_r")),
            reverse=True,
        )[:12],
        "hypothesis": (
            "RVOL nominates early movers into evaluate queue. "
            "LQHV = high velocity but fails legacy discovery/promote gates — "
            "track if they outperform selected names (different filter set)."
        ),
    }

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    append_jsonl(
        EVENTS,
        {
            "ts": summary["as_of"],
            "n_nom": summary["nominations_this_run"],
            "n_open": summary["open_tracks"],
            "lqhv": summary["low_qualified_high_velocity_n"],
            "mean_r_all": summary["perf_all_open"]["mean_mark_r"],
            "mean_r_lqhv": summary["perf_lqhv"]["mean_mark_r"],
            "mean_r_never": summary["perf_never_selected"]["mean_mark_r"],
        },
    )
    MD_REPORT.parent.mkdir(parents=True, exist_ok=True)
    MD_REPORT.write_text(_to_md(summary), encoding="utf-8")
    return summary


def _count_by(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        k = str(r.get(key) or "?")
        out[k] = out.get(k, 0) + 1
    return out


def _mean(xs: Sequence[Any]) -> Optional[float]:
    vals = [_f(x) for x in xs if x is not None]
    # distinguish missing vs zero
    vals2 = []
    for x in xs:
        if x is None:
            continue
        try:
            vals2.append(float(x))
        except (TypeError, ValueError):
            continue
    return sum(vals2) / len(vals2) if vals2 else None


def _pct(x: Optional[float]) -> str:
    if x is None:
        return "—"
    return f"{100.0 * float(x):+.2f}%"


def _to_md(s: Dict[str, Any]) -> str:
    lines = [
        f"# Volume velocity shadow — {str(s.get('as_of'))[:19]}",
        "",
        "**Live orders: false** · RVOL nominator → evaluate queue research",
        "",
        f"- Stats universe: {s.get('universe_stats_ok')} · candles scanned: {s.get('candles_scanned')}",
        f"- Nominations this run: **{s.get('nominations_this_run')}**",
        f"- Open tracks: **{s.get('open_tracks')}** · by bucket: {s.get('open_by_bucket')}",
        f"- LQHV (high velocity, weak legacy gates): **{s.get('low_qualified_high_velocity_n')}**",
        f"- Ever promote-eligible: {s.get('ever_promote_eligible_n')} · never selected: {s.get('never_selected_n')}",
        "",
        "## Paper performance (equal $100 from nomination)",
        f"- All open: mean mark {_pct((s.get('perf_all_open') or {}).get('mean_mark_r'))} · hit {(s.get('perf_all_open') or {}).get('hit_rate')}",
        f"- LQHV: mean mark {_pct((s.get('perf_lqhv') or {}).get('mean_mark_r'))} · hit {(s.get('perf_lqhv') or {}).get('hit_rate')} · mean MFE {_pct((s.get('perf_lqhv') or {}).get('mean_mfe'))}",
        f"- Never selected: mean mark {_pct((s.get('perf_never_selected') or {}).get('mean_mark_r'))} · hit {(s.get('perf_never_selected') or {}).get('hit_rate')}",
        f"- Ever promote: mean mark {_pct((s.get('perf_ever_promote') or {}).get('mean_mark_r'))}",
        "",
        "## Top open by mark_r",
    ]
    for t in s.get("top_open") or []:
        lines.append(
            f"- {t.get('pair')} [{t.get('bucket')}] r={_pct(t.get('mark_r'))} "
            f"MFE={_pct(t.get('mfe'))} rvol0={t.get('rvol_1h_at_nom')} "
            f"promote_ever={t.get('gate_ever_promote')} lqhv={t.get('low_qualified_high_velocity')}"
        )
    lines.extend(
        [
            "",
            "## Hypothesis",
            str(s.get("hypothesis") or ""),
            "",
            "Artifacts: `data/state/volume_velocity_shadow_latest.json`, "
            "`volume_velocity_tracks.json`, `volume_velocity_nominations.jsonl`",
            "",
        ]
    )
    return "\n".join(lines)


def telegram_summary(s: Dict[str, Any]) -> str:
    """Short body for cron; empty if nothing interesting (optional quiet)."""
    n = int(s.get("nominations_this_run") or 0)
    open_n = int(s.get("open_tracks") or 0)
    if n == 0 and open_n == 0:
        return ""
    pa = s.get("perf_all_open") or {}
    pl = s.get("perf_lqhv") or {}
    pn = s.get("perf_never_selected") or {}
    tops = s.get("nominations") or []
    top_s = ", ".join(
        f"{t.get('pair')} {t.get('bucket')} RVOL{float(t.get('rvol_1h') or 0):.1f}"
        for t in tops[:5]
    )
    return (
        f"VELOCITY shadow · noms {n} · open tracks {open_n}\n"
        f"LQHV {s.get('low_qualified_high_velocity_n')} · ever promote {s.get('ever_promote_eligible_n')} · never sel {s.get('never_selected_n')}\n"
        f"Paper mean r: all {_pct(pa.get('mean_mark_r'))} · LQHV {_pct(pl.get('mean_mark_r'))} · never {_pct(pn.get('mean_mark_r'))}\n"
        f"Top: {top_s or '—'}\n"
        f"Live: OFF · report reports/VOLUME_VELOCITY_SHADOW_LATEST.md"
    )


if __name__ == "__main__":
    import pprint

    pprint.pp(run_volume_velocity_shadow())
