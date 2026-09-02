#!/usr/bin/env python3
"""
Run-phase deploy gate (P0).

Block / haircut NEW buys when the pair is already mid/late run
(extension → exhaustion → distribution). Prefer ignition / early trend.

Principle (with RSI-primary):
  - Structure + run *context* first.
  - Sentiment must not open a late-run seat.

See: docs/research/RUN_PHASE_DEPLOY_GATE_2026-08-24.md
"""
from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Phase ints — higher = later in run
PHASE_BASE = 0
PHASE_IGNITION = 1
PHASE_TREND = 2
PHASE_EXTENSION = 3
PHASE_EXHAUSTION = 4
PHASE_DISTRIBUTION = 5

PHASE_NAME = {
    0: "base",
    1: "ignition",
    2: "trend",
    3: "extension",
    4: "exhaustion",
    5: "distribution",
}

DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    # Extension thresholds (either trips phase ≥3)
    "ext_from_low_10d": 0.15,  # +15% off 10d low = late enough to stop NEW full seats
    "ext_from_low_20d": 0.25,
    "ext_rsi": 70.0,
    "ext_rsi_min_from_low_10d": 0.12,
    "ext_days_since_ignition": 8,
    # Exhaustion
    "exhaust_rsi": 80.0,
    "exhaust_min_from_low_10d": 0.10,
    "exhaust_from_low_10d": 0.32,
    "climax_vol_ratio": 1.8,
    # Distribution: off peak while still extended
    "dist_off_peak_pct": 0.03,  # ≥3% below recent high
    "dist_peak_lookback": 5,
    "dist_min_from_low_10d": 0.15,
    # Ignition detection
    "ignition_vol_ratio": 1.5,
    "ignition_lookback": 20,
    # Deploy policy (P0: hard block late phases for NEW buys)
    "block_new_phase_ge": 3,  # block phase 3,4,5 new seats
    "phase_size_frac": {
        "0": 1.0,
        "1": 1.0,
        "2": 1.0,
        "3": 0.0,  # P0 block
        "4": 0.0,
        "5": 0.0,
    },
    # Adds into existing stack in late phase
    "allow_add_phase_ge": False,
    "add_phase_ge_size_frac": 0.0,
    "min_holding_usd_for_add": 25.0,
    "min_move_usd": 50.0,
    # Candle fetch
    "candle_granularity_sec": 86400,
    "candle_limit": 40,
    "fail_open_on_missing_candles": False,  # fail closed for safety when enabled
}

AUDIT_PATH = Path("data/state/run_phase_deploy_audit.jsonl")
UA = {"User-Agent": "Mozilla/5.0 (compatible; phase6-run-phase/1.0)"}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_run_phase_config(config_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out = json.loads(json.dumps(DEFAULTS))
    cfg = config_dict or {}
    block = cfg.get("run_phase_deploy") if isinstance(cfg, dict) else None
    if not isinstance(block, dict):
        gs = cfg.get("global_settings") if isinstance(cfg, dict) else None
        if isinstance(gs, dict) and isinstance(gs.get("run_phase_deploy"), dict):
            block = gs["run_phase_deploy"]
    if isinstance(block, dict):
        for k, v in block.items():
            if k == "phase_size_frac" and isinstance(v, dict):
                out["phase_size_frac"].update({str(kk): vv for kk, vv in v.items()})
            else:
                out[k] = v
    return out


# ---------------------------------------------------------------------------
# Candle helpers
# ---------------------------------------------------------------------------


def normalize_candles(raw: Sequence[Any]) -> List[Dict[str, float]]:
    """
    Normalize to ascending list of {t,o,h,l,c,v}.
    Accepts Coinbase REST [t,l,h,o,c,v] or dict rows.
    """
    rows: List[Dict[str, float]] = []
    for c in raw or []:
        if isinstance(c, dict):
            rows.append(
                {
                    "t": _f(c.get("t") or c.get("time") or c.get("start")),
                    "o": _f(c.get("o") or c.get("open")),
                    "h": _f(c.get("h") or c.get("high")),
                    "l": _f(c.get("l") or c.get("low")),
                    "c": _f(c.get("c") or c.get("close")),
                    "v": _f(c.get("v") or c.get("volume")),
                }
            )
        elif isinstance(c, (list, tuple)) and len(c) >= 6:
            t, l, h, o, cl, v = c[0], c[1], c[2], c[3], c[4], c[5]
            rows.append(
                {"t": _f(t), "o": _f(o), "h": _f(h), "l": _f(l), "c": _f(cl), "v": _f(v)}
            )
    rows = [r for r in rows if r["c"] > 0]
    rows.sort(key=lambda r: r["t"])
    return rows


def fetch_daily_candles_public(pair: str, limit: int = 40) -> List[Dict[str, float]]:
    """Coinbase Exchange public candles (daily)."""
    url = f"https://api.exchange.coinbase.com/products/{pair}/candles?granularity=86400"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode())
    rows = normalize_candles(data)
    if limit and len(rows) > limit:
        rows = rows[-limit:]
    return rows


def candles_from_closes(closes: Sequence[float], vols: Optional[Sequence[float]] = None) -> List[Dict[str, float]]:
    """Weak fallback when only close series exists (no true OHLC)."""
    rows = []
    for i, c in enumerate(closes):
        cv = _f(c)
        if cv <= 0:
            continue
        v = _f(vols[i], 0.0) if vols and i < len(vols) else 0.0
        rows.append({"t": float(i), "o": cv, "h": cv, "l": cv, "c": cv, "v": v})
    return rows


def rsi_wilder(closes: Sequence[float], n: int = 14) -> Optional[float]:
    """Wilder RSI; needs n+1 closes minimum."""
    if len(closes) < n + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    # seed with SMA of first n changes
    avg_g = sum(gains[:n]) / n
    avg_l = sum(losses[:n]) / n
    for i in range(n, len(gains)):
        avg_g = (avg_g * (n - 1) + gains[i]) / n
        avg_l = (avg_l * (n - 1) + losses[i]) / n
    if avg_l <= 1e-12:
        return 100.0 if avg_g > 0 else 50.0
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1.0 + rs))


def _vol_ratio_at(vols: Sequence[float], i: int, look: int = 20) -> Optional[float]:
    if i < 1:
        return None
    window = [vols[j] for j in range(max(0, i - look), i) if vols[j] > 0]
    if not window:
        return None
    avg = sum(window) / len(window)
    if avg <= 0:
        return None
    return vols[i] / avg


def find_ignition_index(candles: List[Dict[str, float]], cfg: Dict[str, Any]) -> Optional[int]:
    """
    First bar in lookback where volume expands and close breaks recent range high.
    """
    if len(candles) < 12:
        return None
    vol_thr = _f(cfg.get("ignition_vol_ratio"), 1.5)
    look = int(cfg.get("ignition_lookback") or 20)
    vols = [c["v"] for c in candles]
    n = len(candles)
    start = max(10, n - look - 1)
    for i in range(start, n):
        vr = _vol_ratio_at(vols, i, 20)
        if vr is None or vr < vol_thr:
            continue
        # breakout: close >= max high of prior 10 bars
        prior_h = max(candles[j]["h"] for j in range(max(0, i - 10), i))
        if candles[i]["c"] >= prior_h * 0.998:
            return i
    return None


@dataclass
class RunPhaseSnapshot:
    pair: str
    phase: int
    phase_name: str
    daily_rsi: Optional[float] = None
    pct_from_low_10d: Optional[float] = None
    pct_from_low_20d: Optional[float] = None
    vol_ratio: Optional[float] = None
    days_since_ignition: Optional[int] = None
    off_peak_pct: Optional[float] = None
    close: Optional[float] = None
    notes: List[str] = field(default_factory=list)
    as_of_t: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_run_phase(
    candles: Sequence[Any],
    *,
    pair: str = "",
    cfg: Optional[Dict[str, Any]] = None,
    as_of_index: Optional[int] = None,
) -> RunPhaseSnapshot:
    """
    Classify run phase from daily (or higher-TF) OHLCV.

    as_of_index: inclusive end index for CF (default last bar).
    """
    c = cfg or DEFAULTS
    rows = normalize_candles(candles)
    if as_of_index is not None:
        rows = rows[: as_of_index + 1]
    if len(rows) < 16:
        return RunPhaseSnapshot(
            pair=pair,
            phase=PHASE_BASE,
            phase_name=PHASE_NAME[PHASE_BASE],
            notes=["insufficient_candles"],
        )

    closes = [r["c"] for r in rows]
    highs = [r["h"] for r in rows]
    lows = [r["l"] for r in rows]
    vols = [r["v"] for r in rows]
    i = len(rows) - 1
    close = closes[i]
    rsi = rsi_wilder(closes, 14)
    vol_r = _vol_ratio_at(vols, i, 20)

    low10 = min(lows[max(0, i - 9) : i + 1])
    low20 = min(lows[max(0, i - 19) : i + 1])
    pct10 = (close / low10 - 1.0) if low10 > 0 else 0.0
    pct20 = (close / low20 - 1.0) if low20 > 0 else 0.0

    peak_lb = int(c.get("dist_peak_lookback") or 5)
    peak = max(highs[max(0, i - peak_lb) : i + 1])
    off_peak = (peak - close) / peak if peak > 0 else 0.0

    ign_i = find_ignition_index(rows, c)
    days_ign = (i - ign_i) if ign_i is not None else None

    notes: List[str] = []
    phase = PHASE_BASE

    ext_floor = _f(c.get("ext_from_low_10d"), 0.20)
    ext_rsi = _f(c.get("ext_rsi"), 70.0)
    # RSI-only extension is too aggressive on short climbs — require price extension too
    rsi_ext_min_pct = _f(c.get("ext_rsi_min_from_low_10d"), 0.12)

    # --- Exhaustion (4) ---
    # High RSI alone is not enough; need extension *context*.
    exhaust = False
    exhaust_rsi = _f(c.get("exhaust_rsi"), 80.0)
    min_ext_for_rsi_exhaust = _f(
        c.get("exhaust_min_from_low_10d"), max(0.10, ext_floor * 0.5)
    )
    if (
        rsi is not None
        and rsi >= exhaust_rsi
        and pct10 >= min_ext_for_rsi_exhaust
    ):
        exhaust = True
        notes.append(f"rsi>={exhaust_rsi}+ext")
    if pct10 >= _f(c.get("exhaust_from_low_10d"), 0.32) and (
        vol_r is not None and vol_r >= _f(c.get("climax_vol_ratio"), 1.8)
    ):
        exhaust = True
        notes.append("climax_ext+vol")
    if (
        rsi is not None
        and rsi >= 75.0
        and pct10 >= ext_floor
        and vol_r is not None
        and vol_r >= _f(c.get("climax_vol_ratio"), 1.8)
    ):
        exhaust = True
        notes.append("rsi75+ext+climax_vol")

    # --- Distribution (5) ---
    dist = False
    if (
        off_peak >= _f(c.get("dist_off_peak_pct"), 0.03)
        and pct10 >= _f(c.get("dist_min_from_low_10d"), 0.15)
        and (rsi is None or rsi >= 60.0)
    ):
        # Prefer distribution when we've already extended and rolled off highs
        if exhaust or pct10 >= ext_floor:
            dist = True
            notes.append(f"off_peak={off_peak:.3f}")

    # --- Extension (3) ---
    ext = False
    if pct10 >= ext_floor:
        ext = True
        notes.append(f"from_low_10d={pct10:.3f}")
    if pct20 >= _f(c.get("ext_from_low_20d"), 0.28):
        ext = True
        notes.append(f"from_low_20d={pct20:.3f}")
    if rsi is not None and rsi >= ext_rsi and pct10 >= rsi_ext_min_pct:
        ext = True
        notes.append(f"rsi_ext={rsi:.1f}+pct10")
    if days_ign is not None and days_ign >= int(c.get("ext_days_since_ignition") or 8):
        if pct10 >= 0.12:  # only if still meaningfully up
            ext = True
            notes.append(f"days_since_ignition={days_ign}")

    # Priority: distribution > exhaustion > extension > trend/ignition/base
    if dist:
        phase = PHASE_DISTRIBUTION
    elif exhaust:
        phase = PHASE_EXHAUSTION
    elif ext:
        phase = PHASE_EXTENSION
    else:
        # Ignition / trend / base
        recently_ignited = days_ign is not None and days_ign <= 3
        vol_ok = vol_r is not None and vol_r >= _f(c.get("ignition_vol_ratio"), 1.5)
        rsi_mid = rsi is not None and 48.0 <= rsi <= 68.0
        rsi_trend = rsi is not None and 55.0 <= rsi < ext_rsi
        mom3 = (close / closes[i - 3] - 1.0) if i >= 3 else 0.0

        if recently_ignited and (vol_ok or rsi_mid) and pct10 < ext_floor:
            phase = PHASE_IGNITION
            notes.append("ignition_window")
        elif rsi_trend and mom3 > 0 and pct10 >= 0.03:
            phase = PHASE_TREND
            notes.append("trend")
        elif vol_ok and rsi is not None and rsi >= 50 and mom3 > 0 and pct10 < 0.12:
            phase = PHASE_IGNITION
            notes.append("vol_ignition_like")
        else:
            phase = PHASE_BASE
            notes.append("base_or_chop")

    return RunPhaseSnapshot(
        pair=pair,
        phase=phase,
        phase_name=PHASE_NAME.get(phase, str(phase)),
        daily_rsi=rsi,
        pct_from_low_10d=pct10,
        pct_from_low_20d=pct20,
        vol_ratio=vol_r,
        days_since_ignition=days_ign,
        off_peak_pct=off_peak,
        close=close,
        notes=notes,
        as_of_t=rows[i]["t"],
    )


@dataclass
class RunPhaseGateResult:
    pair: str
    original_usd: float
    final_usd: float
    dropped: bool
    phase: int
    phase_name: str
    size_frac: float
    blocked: bool
    snapshot: Optional[Dict[str, Any]] = None
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def size_frac_for_phase(phase: int, cfg: Dict[str, Any], *, is_add: bool) -> float:
    fracs = cfg.get("phase_size_frac") or {}
    frac = _f(fracs.get(str(phase), fracs.get(phase, 1.0)), 1.0)
    block_ge = int(cfg.get("block_new_phase_ge") or 99)
    if not is_add and phase >= block_ge:
        return 0.0
    if is_add and phase >= block_ge:
        if not cfg.get("allow_add_phase_ge", False):
            return _f(cfg.get("add_phase_ge_size_frac"), 0.0)
    return max(0.0, min(1.0, frac))


def apply_run_phase_buy_gate(
    pair: str,
    proposed_usd: float,
    snapshot: RunPhaseSnapshot,
    *,
    current_pair_usd: float = 0.0,
    cfg: Optional[Dict[str, Any]] = None,
) -> RunPhaseGateResult:
    """Apply phase size policy to a proposed BUY notional."""
    c = cfg or DEFAULTS
    usd0 = max(0.0, _f(proposed_usd, 0.0))
    min_move = _f(c.get("min_move_usd"), 50.0)
    holding = _f(current_pair_usd, 0.0)
    is_add = holding >= _f(c.get("min_holding_usd_for_add"), 25.0)
    frac = size_frac_for_phase(snapshot.phase, c, is_add=is_add)
    notes = list(snapshot.notes)
    notes.append(f"phase={snapshot.phase_name}")
    if is_add:
        notes.append("is_add")
    usd = usd0 * frac
    blocked = frac <= 1e-12
    if blocked:
        notes.append("blocked_late_run" if not is_add else "blocked_late_run_add")
    dropped = usd < min_move - 1e-9 or blocked
    if dropped:
        usd = 0.0
    elif frac < 1.0 - 1e-12:
        notes.append(f"phase_haircut×{frac:.2f}")

    return RunPhaseGateResult(
        pair=pair,
        original_usd=usd0,
        final_usd=usd,
        dropped=dropped,
        phase=snapshot.phase,
        phase_name=snapshot.phase_name,
        size_frac=frac,
        blocked=blocked,
        snapshot=snapshot.as_dict(),
        notes=notes,
    )


def resolve_candles_for_pair(
    pair: str,
    *,
    candles_by_pair: Optional[Dict[str, Sequence[Any]]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, float]]:
    c = cfg or DEFAULTS
    if candles_by_pair and pair in candles_by_pair:
        return normalize_candles(candles_by_pair[pair])
    # public daily
    try:
        return fetch_daily_candles_public(pair, limit=int(c.get("candle_limit") or 40))
    except Exception as e:
        logger.warning("[RUN-PHASE] candle fetch failed %s: %s", pair, e)
    # price_history closes fallback
    try:
        ph = json.loads(Path("data/state/price_history.json").read_text())
        hist = (ph.get("history") or {}).get(pair) or []
        if hist:
            return candles_from_closes(hist)
    except Exception:
        pass
    return []


def apply_run_phase_to_actions(
    actions: Sequence[Dict[str, Any]],
    *,
    positions_usd: Optional[Dict[str, float]] = None,
    candles_by_pair: Optional[Dict[str, Sequence[Any]]] = None,
    snapshots: Optional[Dict[str, RunPhaseSnapshot]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[RunPhaseGateResult]]:
    c = cfg or DEFAULTS
    if not c.get("enabled", True):
        return [dict(a) for a in actions], []

    pos = {str(k): _f(v) for k, v in (positions_usd or {}).items()}
    out: List[Dict[str, Any]] = []
    results: List[RunPhaseGateResult] = []
    snap_cache: Dict[str, RunPhaseSnapshot] = dict(snapshots or {})

    for a in actions:
        action = str(a.get("action") or a.get("side") or "").upper()
        pair = str(a.get("pair") or "")
        if action != "BUY" or not pair:
            out.append(dict(a))
            continue

        proposed = _f(a.get("usd") if a.get("usd") is not None else a.get("usd_amount"), 0.0)
        if pair not in snap_cache:
            candles = resolve_candles_for_pair(pair, candles_by_pair=candles_by_pair, cfg=c)
            if not candles:
                if c.get("fail_open_on_missing_candles", False):
                    out.append(dict(a))
                    continue
                # fail closed
                gr = RunPhaseGateResult(
                    pair=pair,
                    original_usd=proposed,
                    final_usd=0.0,
                    dropped=True,
                    phase=PHASE_BASE,
                    phase_name="unknown",
                    size_frac=0.0,
                    blocked=True,
                    notes=["no_candles_fail_closed"],
                )
                results.append(gr)
                logger.info("[RUN-PHASE] drop BUY %s — no candles (fail closed)", pair)
                continue
            snap_cache[pair] = classify_run_phase(candles, pair=pair, cfg=c)

        snap = snap_cache[pair]
        gr = apply_run_phase_buy_gate(
            pair,
            proposed,
            snap,
            current_pair_usd=pos.get(pair, 0.0),
            cfg=c,
        )
        # quality_tryout thaw A: week-1 tryout pairs already passed RSI≤55 + eng_sent floor.
        # Late-run hard block would freeze the only allowed path during soft_down recovery.
        # Brad GO C 2026-09-01: pass tryout allowlist through with full proposed size.
        if gr.dropped or gr.final_usd <= 0:
            try:
                from phase6.core.regime_cash_policy import (
                    _recovery_rec,
                    recovery_quality_tryout_cfg,
                )
                import json as _json
                from pathlib import Path as _Path

                pol = {}
                try:
                    pol = _json.loads(
                        _Path("config/regime_cash_policy.json").read_text(encoding="utf-8")
                    )
                except Exception:
                    pol = {}
                rec = _recovery_rec(pol) or {}
                mode = str((rec or {}).get("new_alt_policy") or "")
                if mode.startswith("quality_tryout"):
                    qt = recovery_quality_tryout_cfg(rec if isinstance(rec, dict) else {})
                    try_set = {
                        str(x).upper().replace("_", "-")
                        for x in (qt.get("tryout_pairs") or set())
                    }
                    pu = str(pair).upper().replace("_", "-")
                    if pu in try_set:
                        gr = RunPhaseGateResult(
                            pair=pair,
                            original_usd=proposed,
                            final_usd=proposed,
                            dropped=False,
                            phase=gr.phase,
                            phase_name=gr.phase_name,
                            size_frac=1.0,
                            blocked=False,
                            snapshot=gr.snapshot,
                            notes=list(gr.notes)
                            + ["quality_tryout_late_run_pass", "brad_go_c_20260901"],
                        )
                        logger.info(
                            "[RUN-PHASE] quality_tryout PASS BUY %s $%.2f (was phase=%s)",
                            pair,
                            proposed,
                            snap.phase_name,
                        )
            except Exception as _qt_e:
                logger.debug("[RUN-PHASE] quality_tryout pass check skipped: %s", _qt_e)
        results.append(gr)
        if gr.dropped or gr.final_usd <= 0:
            logger.info(
                "[RUN-PHASE] drop BUY %s $%.2f phase=%s (%s)",
                pair,
                proposed,
                gr.phase_name,
                ";".join(gr.notes),
            )
            continue

        na = dict(a)
        na["usd"] = gr.final_usd
        if "usd_amount" in na:
            na["usd_amount"] = gr.final_usd
        na["run_phase"] = gr.phase
        na["run_phase_name"] = gr.phase_name
        na["run_phase_gate"] = gr.as_dict()
        tag = f"run_phase:{gr.phase_name}"
        prev = str(na.get("reason") or "")
        na["reason"] = f"{prev}|{tag}" if prev else tag
        if gr.final_usd + 1e-6 < proposed:
            na["run_phase_clipped_from"] = proposed
            logger.info(
                "[RUN-PHASE] clip BUY %s $%.2f → $%.2f phase=%s",
                pair,
                proposed,
                gr.final_usd,
                gr.phase_name,
            )
        out.append(na)

    return out, results


def filter_trade_plan_run_phase_deploy(
    runner: Any,
    plan: Any,
    *,
    candles_by_pair: Optional[Dict[str, Sequence[Any]]] = None,
    positions_usd: Optional[Dict[str, float]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Rebalance-path filter: drop/haircut BUY actions in late run phases.
    """
    if plan is None or not getattr(plan, "actions", None):
        return plan

    cfg_dict = cfg or getattr(runner, "config_dict", None) or {}
    c = load_run_phase_config(cfg_dict if isinstance(cfg_dict, dict) else {})
    if not c.get("enabled", True):
        return plan

    pos: Dict[str, float] = {}
    if positions_usd is not None:
        pos = {str(k): _f(v) for k, v in positions_usd.items()}
    else:
        try:
            live_p = Path("data/state/phase6_live_state.json")
            if live_p.exists():
                live = json.loads(live_p.read_text())
                for row in live.get("positions") or []:
                    if isinstance(row, dict) and row.get("pair"):
                        pos[str(row["pair"])] = _f(row.get("value_usd"), 0.0)
        except Exception:
            pass

    new_actions, results = apply_run_phase_to_actions(
        list(plan.actions),
        positions_usd=pos,
        candles_by_pair=candles_by_pair,
        cfg=c,
    )
    plan.actions = new_actions
    blocked = [r for r in results if r.dropped or r.blocked]
    if blocked:
        extra = f"run_phase_blocks={len(blocked)}"
        prev = getattr(plan, "notes", "") or ""
        plan.notes = f"{prev}; {extra}" if prev else extra
        try:
            AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_PATH.open("a") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": _utcnow(),
                            "results": [r.as_dict() for r in results],
                        }
                    )
                    + "\n"
                )
        except Exception as e:
            logger.debug("run_phase audit failed: %s", e)
    return plan
