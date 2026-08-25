#!/usr/bin/env python3
"""
Run lifecycle P1/P2 — structure-confirmed ignition scout + dual-peak exit shadow.

P1 Ignition scout: surface early-run (phase 1–2) entries with RSI *paired* to
structure (SMA trend + Fib zone), not RSI alone.

P2 Dual-peak exit: shadow scale-out when price stall/failed-high *and*
sentiment fade (or climax) coincide — before we only had price TP or deep sent.

See:
  docs/research/RUN_LIFECYCLE_P1_P2_2026-08-24.md
  docs/research/RUN_PHASE_DEPLOY_GATE_2026-08-24.md
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.core.run_phase_deploy import (
    PHASE_BASE,
    PHASE_DISTRIBUTION,
    PHASE_EXHAUSTION,
    PHASE_EXTENSION,
    PHASE_IGNITION,
    PHASE_NAME,
    PHASE_TREND,
    classify_run_phase,
    fetch_daily_candles_public,
    normalize_candles,
    resolve_candles_for_pair,
    rsi_wilder,
    load_run_phase_config,
)

logger = logging.getLogger(__name__)

SCOUT_BOARD_PATH = Path("data/state/ignition_scout_board.json")
SCOUT_AUDIT_PATH = Path("data/state/ignition_scout_audit.jsonl")
DUAL_PEAK_EVENTS_PATH = Path("data/state/dual_peak_exit_shadow_events.jsonl")
DUAL_PEAK_NOTIFY_PATH = Path("data/state/dual_peak_notify_dedupe.json")
DUAL_PEAK_LIVE_EXITS_PATH = Path("data/state/dual_peak_live_exits.jsonl")
ENTRY_LOTS_PATH = Path("data/state/entry_driver_lots.json")

DEFAULTS_P1: Dict[str, Any] = {
    "enabled": True,
    "mode": "shadow",  # shadow | propose (append BUY on rebalance) | off
    "min_score": 0.55,
    "max_proposals": 4,
    # Equity-based seat (CF lifecycle_deployed) — not timid 5%
    "deploy_frac": 0.18,
    "max_open_seats": 4,  # non-ballast concurrent bags
    "proposal_usd_cap": 500.0,  # hard ceiling; pair weight still binds
    "proposal_usd_floor": 100.0,
    "require_structure_ok": True,
    "allow_phases": [1, 2],  # ignition + early trend only
    "sentiment_boost_min": 0.05,
    "sentiment_boost_weight": 0.12,
    "notify_telegram": True,
    "ballast_pairs": ["PAXG-USD", "PAXG-USDC", "USDC-USD"],
}

DEFAULTS_STRUCTURE: Dict[str, Any] = {
    "sma_fast": 20,
    "sma_slow": 50,
    "rsi_band_low": 45.0,
    "rsi_band_high": 68.0,
    "fib_zone_low": 0.382,
    "fib_zone_high": 0.618,
    "fib_extension_late": 1.0,  # at/above swing high = late for NEW
    "min_swing_pct": 0.06,  # swing must be meaningful
}

DEFAULTS_P2: Dict[str, Any] = {
    "enabled": True,
    "mode": "shadow",  # shadow | live | off
    "mfe_stall_bars": 2,  # daily bars without new high while still green
    "failed_high_off_peak": 0.03,
    "min_peak_return": 0.02,  # only dual-peak trim if had some MFE
    "sent_fade_delta": 0.30,  # slightly tighter than pure fade 0.40 for dual
    "sent_fade_floor": 0.20,
    "climax_vol_ratio": 1.8,
    "extension_partial_frac": 0.33,  # phase≥3 partial — take meat before dump
    "dual_trim_frac": 0.50,
    "min_position_usd": 25.0,
    "tp_arm_pct": 0.04,  # if past TP arm, live TP owns it
    "notify_telegram": True,
    "notify_dedupe_hours": 6.0,
    # Persist while phase≤trend AND sent not faded (metrics + sent agree)
    "hold_while_metrics_and_sent_agree": True,
    # Extension partial: live when mode=live (structure late even if sent hot)
    "extension_partial_live": True,
    "extension_partial_shadow": True,
    "live_min_trim_usd": 40.0,
    "live_max_trims_per_tick": 2,
    "ballast_pairs": ["PAXG-USD", "PAXG-USDC"],
}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_lifecycle_config(config_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merge trading_config run_lifecycle over defaults."""
    out = {
        "structure": json.loads(json.dumps(DEFAULTS_STRUCTURE)),
        "ignition_scout": json.loads(json.dumps(DEFAULTS_P1)),
        "dual_peak_exit": json.loads(json.dumps(DEFAULTS_P2)),
    }
    cfg = config_dict or {}
    block = cfg.get("run_lifecycle") if isinstance(cfg, dict) else None
    if not isinstance(block, dict):
        return out
    if isinstance(block.get("structure"), dict):
        out["structure"].update(block["structure"])
    if isinstance(block.get("ignition_scout"), dict):
        out["ignition_scout"].update(block["ignition_scout"])
    if isinstance(block.get("dual_peak_exit"), dict):
        out["dual_peak_exit"].update(block["dual_peak_exit"])
    return out


# ---------------------------------------------------------------------------
# Structure confirm — pair RSI with MA + Fib (not RSI in isolation)
# ---------------------------------------------------------------------------


def sma(values: Sequence[float], n: int) -> Optional[float]:
    if n <= 0 or len(values) < n:
        return None
    window = values[-n:]
    return sum(window) / n


def find_swing(
    highs: Sequence[float], lows: Sequence[float], lookback: int = 20
) -> Tuple[Optional[float], Optional[float], Optional[int], Optional[int]]:
    """
    Simple swing: lowest low and highest high in lookback.
    Returns (swing_low, swing_high, low_idx, high_idx) relative to slice start.
    """
    if len(highs) < 5 or len(lows) < 5:
        return None, None, None, None
    start = max(0, len(highs) - lookback)
    h_slice = list(highs[start:])
    l_slice = list(lows[start:])
    li = min(range(len(l_slice)), key=lambda i: l_slice[i])
    # high after low preferred for up-swing
    hi_candidates = list(range(li, len(h_slice))) or list(range(len(h_slice)))
    hi = max(hi_candidates, key=lambda i: h_slice[i])
    return l_slice[li], h_slice[hi], start + li, start + hi


@dataclass
class StructureSnapshot:
    pair: str
    sma_fast: Optional[float]
    sma_slow: Optional[float]
    price: float
    above_sma_fast: bool
    above_sma_slow: bool
    sma_fast_rising: bool
    swing_low: Optional[float]
    swing_high: Optional[float]
    fib_pos: Optional[float]  # 0 at swing_low, 1 at swing_high, >1 extension
    in_fib_pullback_zone: bool
    at_or_past_extension: bool
    structure_ok_for_entry: bool
    structure_late: bool
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_structure(
    candles: Sequence[Any],
    *,
    pair: str = "",
    cfg: Optional[Dict[str, Any]] = None,
    as_of_index: Optional[int] = None,
) -> StructureSnapshot:
    """
    MA + Fib structure alongside price.

    Entry-friendly structure (structure_ok_for_entry):
      - Price reclaiming/holding above rising SMA fast, OR
      - Pullback into Fib 38.2–61.8 of up-swing with SMA fast not collapsing
    Late structure (structure_late):
      - Fib pos ≥ 1.0 (at/through swing high extension) with stretched run
    """
    c = cfg or DEFAULTS_STRUCTURE
    rows = normalize_candles(candles)
    if as_of_index is not None:
        rows = rows[: as_of_index + 1]
    notes: List[str] = []
    if len(rows) < 25:
        px = rows[-1]["c"] if rows else 0.0
        return StructureSnapshot(
            pair=pair,
            sma_fast=None,
            sma_slow=None,
            price=px,
            above_sma_fast=False,
            above_sma_slow=False,
            sma_fast_rising=False,
            swing_low=None,
            swing_high=None,
            fib_pos=None,
            in_fib_pullback_zone=False,
            at_or_past_extension=False,
            structure_ok_for_entry=False,
            structure_late=False,
            notes=["insufficient_bars"],
        )

    closes = [r["c"] for r in rows]
    highs = [r["h"] for r in rows]
    lows = [r["l"] for r in rows]
    price = closes[-1]
    n_fast = int(c.get("sma_fast") or 20)
    n_slow = int(c.get("sma_slow") or 50)
    sf = sma(closes, n_fast)
    ss = sma(closes, n_slow)
    sf_prev = sma(closes[:-1], n_fast) if len(closes) > n_fast else None
    rising = bool(sf is not None and sf_prev is not None and sf >= sf_prev)
    above_f = bool(sf is not None and price >= sf)
    above_s = bool(ss is not None and price >= ss)

    sl, sh, _, _ = find_swing(highs, lows, lookback=20)
    fib_pos = None
    in_zone = False
    past_ext = False
    min_swing = _f(c.get("min_swing_pct"), 0.06)
    if sl and sh and sh > sl * (1.0 + min_swing):
        span = sh - sl
        fib_pos = (price - sl) / span if span > 0 else None
        zlo = _f(c.get("fib_zone_low"), 0.382)
        zhi = _f(c.get("fib_zone_high"), 0.618)
        if fib_pos is not None:
            in_zone = zlo <= fib_pos <= zhi
            past_ext = fib_pos >= _f(c.get("fib_extension_late"), 1.0)
            notes.append(f"fib_pos={fib_pos:.3f}")
    else:
        notes.append("swing_too_small_or_missing")

    # Structure OK for early entry
    ok = False
    if above_f and rising and not past_ext:
        ok = True
        notes.append("above_rising_sma_fast")
    if in_zone and (above_f or rising) and not past_ext:
        ok = True
        notes.append("fib_pullback_zone")
    # soft: above both MAs early trend
    if above_f and above_s and not past_ext and rising:
        ok = True
        notes.append("above_dual_ma")

    late = bool(past_ext)
    if late:
        notes.append("fib_extension_late")

    return StructureSnapshot(
        pair=pair,
        sma_fast=sf,
        sma_slow=ss,
        price=price,
        above_sma_fast=above_f,
        above_sma_slow=above_s,
        sma_fast_rising=rising,
        swing_low=sl,
        swing_high=sh,
        fib_pos=fib_pos,
        in_fib_pullback_zone=in_zone,
        at_or_past_extension=past_ext,
        structure_ok_for_entry=ok,
        structure_late=late,
        notes=notes,
    )


def rsi_structure_entry_score(
    *,
    daily_rsi: Optional[float],
    structure: StructureSnapshot,
    run_phase: int,
    sentiment: float = 0.0,
    cfg_structure: Optional[Dict[str, Any]] = None,
    cfg_scout: Optional[Dict[str, Any]] = None,
) -> Tuple[float, str]:
    """
    Composite entry score: RSI band × structure × phase × small sent reinforce.
    Returns (score 0-1, reason).
    """
    sc = cfg_structure or DEFAULTS_STRUCTURE
    p1 = cfg_scout or DEFAULTS_P1
    parts: List[str] = []
    score = 0.0

    # Phase gate
    allow = set(int(x) for x in (p1.get("allow_phases") or [1, 2]))
    if run_phase not in allow:
        return 0.0, f"phase_blocked={PHASE_NAME.get(run_phase, run_phase)}"

    # RSI component (band, not isolation)
    rsi = daily_rsi
    rlo = _f(sc.get("rsi_band_low"), 45.0)
    rhi = _f(sc.get("rsi_band_high"), 68.0)
    if rsi is None:
        return 0.0, "no_rsi"
    if rlo <= rsi <= rhi:
        # peak mid-band ~55-58
        peak = 56.0
        dist = abs(rsi - peak) / max(1.0, (rhi - rlo) / 2)
        rsi_comp = max(0.0, 1.0 - dist) * 0.40
        parts.append(f"rsi_band={rsi:.1f}")
    elif 40 <= rsi < rlo:
        rsi_comp = 0.15  # early turn
        parts.append(f"rsi_early={rsi:.1f}")
    else:
        rsi_comp = 0.0
        parts.append(f"rsi_out={rsi:.1f}")
        if rsi > rhi:
            return 0.0, "rsi_too_high_without_structure_pass"

    score += rsi_comp

    # Structure component (required if configured)
    if structure.structure_late:
        return 0.0, "structure_late_fib_ext|" + "|".join(structure.notes)
    if structure.structure_ok_for_entry:
        score += 0.40
        parts.append("structure_ok")
    elif p1.get("require_structure_ok", True):
        return 0.0, "structure_not_ok|" + "|".join(structure.notes)
    else:
        score += 0.10
        parts.append("structure_weak")

    # Phase quality
    if run_phase == PHASE_IGNITION:
        score += 0.15
        parts.append("phase=ignition")
    elif run_phase == PHASE_TREND:
        score += 0.10
        parts.append("phase=trend")

    # Sentiment reinforce only (small)
    sent = _f(sentiment, 0.0)
    smin = _f(p1.get("sentiment_boost_min"), 0.05)
    sw = _f(p1.get("sentiment_boost_weight"), 0.12)
    if sent >= smin:
        score += min(sw, sw * (sent / 0.5))
        parts.append(f"sent_boost={sent:.2f}")

    score = max(0.0, min(1.0, score))
    return round(score, 3), "|".join(parts)


# ---------------------------------------------------------------------------
# P1 — Ignition scout
# ---------------------------------------------------------------------------


@dataclass
class IgnitionCandidate:
    pair: str
    score: float
    phase: int
    phase_name: str
    daily_rsi: Optional[float]
    sentiment: float
    structure_ok: bool
    reason: str
    proposal_usd: float
    snapshot_phase: Dict[str, Any] = field(default_factory=dict)
    snapshot_structure: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def score_pair_ignition(
    pair: str,
    candles: Sequence[Any],
    *,
    sentiment: float = 0.0,
    cfg_all: Optional[Dict[str, Any]] = None,
    as_of_index: Optional[int] = None,
) -> IgnitionCandidate:
    life = cfg_all or load_lifecycle_config()
    p1 = life["ignition_scout"]
    st_cfg = life["structure"]
    # run phase uses run_phase_deploy defaults via classify
    snap = classify_run_phase(candles, pair=pair, as_of_index=as_of_index)
    structure = classify_structure(
        candles, pair=pair, cfg=st_cfg, as_of_index=as_of_index
    )
    score, reason = rsi_structure_entry_score(
        daily_rsi=snap.daily_rsi,
        structure=structure,
        run_phase=snap.phase,
        sentiment=sentiment,
        cfg_structure=st_cfg,
        cfg_scout=p1,
    )
    prop = 0.0
    if score >= _f(p1.get("min_score"), 0.55):
        # Placeholder; apply_ignition sizes from live equity * deploy_frac
        prop = _f(p1.get("proposal_usd_cap"), 500.0)
    return IgnitionCandidate(
        pair=pair,
        score=score,
        phase=snap.phase,
        phase_name=snap.phase_name,
        daily_rsi=snap.daily_rsi,
        sentiment=_f(sentiment),
        structure_ok=structure.structure_ok_for_entry,
        reason=reason,
        proposal_usd=prop,
        snapshot_phase=snap.as_dict(),
        snapshot_structure=structure.as_dict(),
    )


def _live_equity_and_positions(
    config_dict: Optional[Dict[str, Any]] = None,
) -> Tuple[float, float, Dict[str, float], List[str]]:
    """Return equity, cash, positions_usd, held_pairs (non-dust)."""
    eq = cash = 0.0
    pos: Dict[str, float] = {}
    held: List[str] = []
    try:
        live_p = Path("data/state/phase6_live_state.json")
        if live_p.exists():
            live = json.loads(live_p.read_text())
            eq = _f(live.get("total_usd") or live.get("equity_usd"), 0.0)
            cash = _f(live.get("cash_usd"), 0.0)
            for row in live.get("positions") or []:
                if not isinstance(row, dict) or not row.get("pair"):
                    continue
                p = str(row["pair"])
                v = _f(row.get("value_usd"), 0.0)
                pos[p] = v
                if v >= 25.0:
                    held.append(p)
    except Exception:
        pass
    if eq <= 0:
        eq = cash + sum(pos.values())
    return eq, cash, pos, held


def ignition_ticket_usd(
    *,
    equity_usd: float,
    free_cash_usd: float,
    current_pair_usd: float = 0.0,
    cfg_p1: Optional[Dict[str, Any]] = None,
    max_pair_weight: float = 0.30,
) -> float:
    """Size one ignition seat: deploy_frac * equity, pair room, cash, floor/cap."""
    p1 = cfg_p1 or DEFAULTS_P1
    eq = max(0.0, _f(equity_usd, 0.0))
    cash = max(0.0, _f(free_cash_usd, 0.0))
    frac = max(0.05, min(0.30, _f(p1.get("deploy_frac"), 0.18)))
    cap = _f(p1.get("proposal_usd_cap"), 500.0)
    floor = _f(p1.get("proposal_usd_floor"), 100.0)
    ticket = eq * frac if eq > 0 else _f(p1.get("proposal_usd_cap"), 150.0)
    ticket = min(ticket, cap)
    # pair weight room
    w = max(0.0, min(1.0, max_pair_weight))
    if eq > 0 and w > 0:
        room = max(0.0, w * eq - max(0.0, current_pair_usd))
        ticket = min(ticket, room)
    # don't spend more than half free cash on one seat
    if cash > 0:
        ticket = min(ticket, cash * 0.50)
    if ticket < floor:
        return 0.0 if ticket < 50 else ticket
    return round(ticket, 2)


def run_ignition_scout(
    universe: Sequence[str],
    *,
    config_dict: Optional[Dict[str, Any]] = None,
    sentiment_by_pair: Optional[Dict[str, float]] = None,
    candles_by_pair: Optional[Dict[str, Sequence[Any]]] = None,
    held_pairs: Optional[Sequence[str]] = None,
    write_board: bool = True,
) -> Dict[str, Any]:
    """
    Scan universe for ignition/early-trend structure-confirmed entries.
    Shadow by default — writes board JSON; propose mode used by rebalance filter.
    """
    life = load_lifecycle_config(config_dict)
    p1 = life["ignition_scout"]
    if not p1.get("enabled", True) or str(p1.get("mode") or "shadow").lower() in (
        "off",
        "disabled",
        "0",
        "false",
    ):
        return {"enabled": False, "candidates": [], "ts": _utcnow()}

    sent_map = sentiment_by_pair or {}
    held = set(held_pairs or [])
    cands: List[IgnitionCandidate] = []

    for pair in universe:
        try:
            if candles_by_pair and pair in candles_by_pair:
                candles = normalize_candles(candles_by_pair[pair])
            else:
                candles = resolve_candles_for_pair(pair, cfg=load_run_phase_config(config_dict))
            if len(candles) < 25:
                continue
            cand = score_pair_ignition(
                pair,
                candles,
                sentiment=_f(sent_map.get(pair), 0.0),
                cfg_all=life,
            )
            # de-prioritize already held for *new seat* scout (still list)
            if pair in held:
                cand.reason = (cand.reason + "|already_held").strip("|")
            cands.append(cand)
        except Exception as e:
            logger.debug("ignition scout skip %s: %s", pair, e)

    cands.sort(key=lambda x: x.score, reverse=True)
    min_s = _f(p1.get("min_score"), 0.55)
    hits = [c for c in cands if c.score >= min_s and c.pair not in held]
    max_n = int(p1.get("max_proposals") or 3)
    top = hits[:max_n]

    board = {
        "ts": _utcnow(),
        "mode": p1.get("mode"),
        "min_score": min_s,
        "top": [c.as_dict() for c in top],
        "all_scored": [
            {
                "pair": c.pair,
                "score": c.score,
                "phase": c.phase_name,
                "rsi": c.daily_rsi,
                "structure_ok": c.structure_ok,
                "reason": c.reason,
            }
            for c in cands[:30]
        ],
        "note": "P1 scout — structure+RSI+phase; sentiment reinforce only. P0 still blocks late runs.",
    }
    if write_board:
        try:
            SCOUT_BOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
            SCOUT_BOARD_PATH.write_text(json.dumps(board, indent=2))
            with SCOUT_AUDIT_PATH.open("a") as f:
                f.write(json.dumps({"ts": board["ts"], "top": board["top"]}) + "\n")
        except Exception as e:
            logger.debug("scout board write failed: %s", e)
    return board


def apply_ignition_proposals_to_plan(
    runner: Any,
    plan: Any,
    *,
    config_dict: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    If mode=propose: append BUY actions for top scout hits not already in plan.
    Sized at deploy_frac * equity (CF lifecycle_deployed spirit).
    Call after run-phase; re-apply RSI-primary + run-phase after this.
    """
    if plan is None:
        return plan
    cfg = config_dict or getattr(runner, "config_dict", {}) or {}
    life = load_lifecycle_config(cfg)
    p1 = life["ignition_scout"]
    if str(p1.get("mode") or "shadow").lower() != "propose":
        return plan
    if not p1.get("enabled", True):
        return plan

    pool = []
    try:
        pool = list(
            (cfg.get("phase_6_specific") or {}).get("opportunity_pool")
            or (cfg.get("global_settings") or {}).get("pairs")
            or []
        )
    except Exception:
        pool = []
    if not pool:
        return plan

    sent = {}
    try:
        from phase6.core.sentiment_scorer import load_sentiment_scores

        sent = load_sentiment_scores(universe=pool) or {}
    except Exception:
        pass

    eq, cash, pos, held = _live_equity_and_positions(cfg)
    ballast = {str(x) for x in (p1.get("ballast_pairs") or [])}
    non_ballast = [p for p in held if p not in ballast]
    max_seats = int(p1.get("max_open_seats") or 4)
    seats_left = max(0, max_seats - len(non_ballast))
    if seats_left <= 0:
        logger.info("[IGNITION-SCOUT] max_open_seats=%s reached — no new proposals", max_seats)
        return plan

    # pair weight from rsi_primary if present
    max_pw = 0.30
    try:
        max_pw = float((cfg.get("rsi_primary_deploy") or {}).get("max_pair_weight") or 0.30)
    except Exception:
        pass

    board = run_ignition_scout(
        pool, config_dict=cfg, sentiment_by_pair=sent, held_pairs=held, write_board=True
    )
    existing = {
        str(a.get("pair"))
        for a in (plan.actions or [])
        if str(a.get("action") or a.get("side") or "").upper() == "BUY"
    }
    actions = list(plan.actions or [])
    added = 0
    remaining_cash = cash
    for row in board.get("top") or []:
        if added >= seats_left:
            break
        if added >= int(p1.get("max_proposals") or 4):
            break
        pair = row.get("pair")
        if not pair or pair in existing or pair in held:
            continue
        if not row.get("structure_ok", True) and p1.get("require_structure_ok", True):
            continue
        usd = ignition_ticket_usd(
            equity_usd=eq,
            free_cash_usd=remaining_cash,
            current_pair_usd=pos.get(str(pair), 0.0),
            cfg_p1=p1,
            max_pair_weight=max_pw,
        )
        # score-scale slightly: top score full, borderline 0.75x
        sc = _f(row.get("score"), 0.0)
        if sc < 0.70:
            usd = round(usd * 0.75, 2)
        if usd < 50:
            continue
        actions.append(
            {
                "pair": pair,
                "action": "BUY",
                "usd": usd,
                "reason": (
                    f"ignition_scout:{row.get('reason')}|score={row.get('score')}"
                    f"|deploy_frac={p1.get('deploy_frac')}"
                ),
                "entry_rsi": row.get("daily_rsi"),
                "entry_sentiment": row.get("sentiment"),
                "run_phase": row.get("phase"),
                "run_phase_name": row.get("phase_name"),
                "structure_ok": row.get("structure_ok"),
                "ignition_scout": True,
                "entry_drivers": ["rsi_structure", "run_ignition"],
            }
        )
        existing.add(pair)
        remaining_cash = max(0.0, remaining_cash - usd)
        added += 1
    if added:
        plan.actions = actions
        prev = getattr(plan, "notes", "") or ""
        extra = f"ignition_proposals={added}"
        plan.notes = f"{prev}; {extra}" if prev else extra
        logger.info(
            "[IGNITION-SCOUT] added %d BUY proposals mode=propose eq=%.0f cash=%.0f",
            added,
            eq,
            cash,
        )
    return plan


# ---------------------------------------------------------------------------
# P2 — Dual-peak exit shadow
# ---------------------------------------------------------------------------


@dataclass
class DualPeakEvent:
    pair: str
    kind: str  # dual_peak | extension_partial | sent_fade_only
    would_trim_usd: float
    would_trim_frac: float
    entry_price: float
    current_price: float
    peak_return: float
    off_peak_pct: float
    entry_sentiment: float
    current_sentiment: float
    sent_fade: float
    phase_name: str
    reasons: List[str]
    mode: str
    shadow: bool = True

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["ts"] = _utcnow()
        return d


def _load_lots(path: Path = ENTRY_LOTS_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return list(data.get("lots") or [])
    except Exception:
        return []
    return []


def evaluate_dual_peak_exits(
    *,
    lots: Sequence[Dict[str, Any]],
    current_sentiment: Dict[str, float],
    current_prices: Dict[str, float],
    positions_usd: Dict[str, float],
    candles_by_pair: Optional[Dict[str, Sequence[Any]]] = None,
    cfg_p2: Optional[Dict[str, Any]] = None,
    cfg_phase: Optional[Dict[str, Any]] = None,
) -> List[DualPeakEvent]:
    """
    Pure P2 evaluation. No orders.

    Dual-peak: (price stall OR failed high OR climax/extension) AND
               (sentiment faded from entry OR sent floor)
    Also emits extension_partial shadow when phase≥3 and green enough.
    """
    c = cfg_p2 or DEFAULTS_P2
    if not c.get("enabled", True):
        return []
    mode = str(c.get("mode") or "shadow").lower()
    if mode in ("off", "disabled", "false", "0"):
        return []

    events: List[DualPeakEvent] = []
    min_pos = _f(c.get("min_position_usd"), 25.0)
    arm = _f(c.get("tp_arm_pct"), 0.04)
    fade_d = _f(c.get("sent_fade_delta"), 0.30)
    fade_f = _f(c.get("sent_fade_floor"), 0.20)
    off_thr = _f(c.get("failed_high_off_peak"), 0.03)
    min_peak = _f(c.get("min_peak_return"), 0.02)
    dual_frac = max(0.0, min(1.0, _f(c.get("dual_trim_frac"), 0.50)))
    ext_frac = max(0.0, min(1.0, _f(c.get("extension_partial_frac"), 0.33)))

    for lot in lots:
        if not lot.get("open", True):
            continue
        pair = str(lot.get("pair") or "")
        if not pair:
            continue
        pos = _f(positions_usd.get(pair), _f(lot.get("usd"), 0.0))
        if pos < min_pos:
            continue
        entry_px = _f(lot.get("entry_price"), 0.0)
        cur_px = _f(current_prices.get(pair), 0.0)
        if entry_px <= 0 or cur_px <= 0:
            continue
        peak_ret = (cur_px / entry_px) - 1.0
        # track lot peak if stored
        lot_peak = _f(lot.get("peak_price"), 0.0)
        if lot_peak > 0:
            peak_ret = max(peak_ret, (lot_peak / entry_px) - 1.0)
            off_peak = (lot_peak - cur_px) / lot_peak if lot_peak > 0 else 0.0
        else:
            off_peak = 0.0

        # skip if TP zone already owns exit
        if peak_ret >= arm - 1e-12 and off_peak < off_thr:
            continue

        entry_sent = _f(lot.get("entry_sentiment"), _f(lot.get("entry_sent_peak"), 0.0))
        # peak sentiment if tracked
        entry_sent = max(entry_sent, _f(lot.get("entry_sent_peak"), entry_sent))
        cur_sent = _f(current_sentiment.get(pair), 0.0)
        sent_fade = entry_sent - cur_sent
        sent_hit = sent_fade >= fade_d - 1e-12 or cur_sent <= fade_f + 1e-12

        # candles → phase + failed high + stall
        candles = []
        if candles_by_pair and pair in candles_by_pair:
            candles = normalize_candles(candles_by_pair[pair])
        else:
            try:
                candles = fetch_daily_candles_public(pair, limit=40)
            except Exception:
                candles = []

        phase_name = "unknown"
        phase = PHASE_BASE
        failed_high = False
        stall = False
        climax = False
        if candles:
            snap = classify_run_phase(candles, pair=pair, cfg=cfg_phase)
            phase = snap.phase
            phase_name = snap.phase_name
            if snap.off_peak_pct is not None and snap.off_peak_pct >= off_thr:
                failed_high = True
                off_peak = max(off_peak, snap.off_peak_pct)
            if snap.vol_ratio is not None and snap.vol_ratio >= _f(c.get("climax_vol_ratio"), 1.8):
                if phase >= PHASE_EXTENSION:
                    climax = True
            # stall: last N closes no new high while peak_ret > 0
            n_stall = int(c.get("mfe_stall_bars") or 2)
            if len(candles) >= n_stall + 1 and peak_ret >= min_peak:
                recent_h = [x["h"] for x in candles[-(n_stall + 1) :]]
                if recent_h[-1] <= max(recent_h[:-1]) + 1e-12:
                    # and not making progress on close
                    if candles[-1]["c"] <= max(x["c"] for x in candles[-(n_stall + 1) : -1]) + 1e-12:
                        stall = True

        price_hit = failed_high or stall or climax or phase >= PHASE_DISTRIBUTION
        reasons: List[str] = []
        if failed_high:
            reasons.append(f"failed_high_off={off_peak:.3f}")
        if stall:
            reasons.append("mfe_stall")
        if climax:
            reasons.append("climax_vol")
        if phase >= PHASE_EXTENSION:
            reasons.append(f"phase={phase_name}")
        if sent_hit:
            reasons.append(f"sent_fade={sent_fade:.3f}|cur={cur_sent:.3f}")

        # HOLD while metrics (early/mid structure) AND sentiment still agree
        metrics_early = phase <= PHASE_TREND and not failed_high and not climax
        metrics_and_sent_agree = metrics_early and (not sent_hit)
        if c.get("hold_while_metrics_and_sent_agree", True) and metrics_and_sent_agree:
            continue

        is_live = mode == "live"

        # Dual peak: price rolling AND sent fading → scale before dump
        if price_hit and sent_hit and peak_ret >= min_peak * 0.5:
            events.append(
                DualPeakEvent(
                    pair=pair,
                    kind="dual_peak",
                    would_trim_usd=round(pos * dual_frac, 4),
                    would_trim_frac=dual_frac,
                    entry_price=entry_px,
                    current_price=cur_px,
                    peak_return=round(peak_ret, 4),
                    off_peak_pct=round(off_peak, 4),
                    entry_sentiment=entry_sent,
                    current_sentiment=cur_sent,
                    sent_fade=round(sent_fade, 4),
                    phase_name=phase_name,
                    reasons=reasons,
                    mode=mode,
                    shadow=(not is_live),
                )
            )
            continue

        # Extension partial: structure late — take meat even if sent still hot
        ext_ok = phase >= PHASE_EXTENSION and peak_ret >= min_peak
        if ext_ok and (
            (is_live and c.get("extension_partial_live", True))
            or ((not is_live) and c.get("extension_partial_shadow", True))
        ):
            events.append(
                DualPeakEvent(
                    pair=pair,
                    kind="extension_partial",
                    would_trim_usd=round(pos * ext_frac, 4),
                    would_trim_frac=ext_frac,
                    entry_price=entry_px,
                    current_price=cur_px,
                    peak_return=round(peak_ret, 4),
                    off_peak_pct=round(off_peak, 4),
                    entry_sentiment=entry_sent,
                    current_sentiment=cur_sent,
                    sent_fade=round(sent_fade, 4),
                    phase_name=phase_name,
                    reasons=reasons or [f"phase={phase_name}"],
                    mode=mode,
                    shadow=(not is_live),
                )
            )

    return events


def reattach_sl_after_lifecycle_trim(
    exchange: Any,
    pair: str,
    *,
    entry_price: float,
    remaining_qty_hint: float = 0.0,
    config_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    After a lifecycle partial market sell: cancel open stops for pair, wait for
    free size, re-attach SL on remaining bag using lot entry as anchor.

    One pair at a time (caller already serializes trims). Does not bulk-race.
    """
    out: Dict[str, Any] = {
        "pair": pair,
        "ok": False,
        "action": "reattach",
        "entry_price": entry_price,
        "size": 0.0,
    }
    if exchange is None or not pair:
        out["error"] = "no_exchange_or_pair"
        return out
    try:
        import time as _time

        from phase6.core.config_loader import ConfigLoader
        from phase6.core.sl_preflight import (
            cancel_open_stops_for_pair,
            poll_available_after_cancel,
            resolve_sl_attach_size,
        )
        from phase6.core.stop_loss_manager import StopLossManager

        cfg = config_dict
        if not cfg:
            try:
                cfg = ConfigLoader()._config
            except Exception:
                cfg = json.loads(Path("config/trading_config_phase6.json").read_text())

        # 1) Release size held by old stop
        try:
            released = cancel_open_stops_for_pair(exchange, pair)
            out["cancelled"] = released
        except Exception as ce:
            out["cancel_error"] = str(ce)[:160]
            released = None

        try:
            poll_available_after_cancel(exchange, pair, timeout=4.0)
        except Exception:
            _time.sleep(0.8)

        # 2) Resolve remaining free size (prefer exchange balance)
        hint = max(0.0, _f(remaining_qty_hint, 0.0))
        size, meta = resolve_sl_attach_size(exchange, pair, hint if hint > 0 else 1e9)
        out["resolve_meta"] = {k: meta.get(k) for k in list(meta or {})[:12]} if isinstance(meta, dict) else {}
        if size <= 0 and hint > 0:
            size = hint
            try:
                if hasattr(exchange, "quantize_size"):
                    size = float(exchange.quantize_size(pair, size))
            except Exception:
                pass
        out["size"] = float(size or 0.0)
        if size <= 0:
            out["error"] = "no_remaining_size"
            out["ok"] = True  # nothing to protect — not a hard failure
            out["action"] = "skip_empty"
            return out

        anchor = _f(entry_price, 0.0)
        if anchor <= 0:
            try:
                anchor = _f(exchange.get_price(pair), 0.0)
            except Exception:
                anchor = 0.0
        if anchor <= 0:
            out["error"] = "no_entry_anchor"
            return out
        out["entry_price"] = anchor

        slm = StopLossManager(exchange, cfg if isinstance(cfg, dict) else {}, mode="live")
        ok = bool(
            slm.attach_stop_loss(
                pair,
                anchor,
                float(size),
                fresh_buy=False,
            )
        )
        out["ok"] = ok
        if not ok:
            out["error"] = "attach_stop_loss_returned_false"
        else:
            logger.info(
                "[LIFECYCLE-EXIT] SL reattached %s size=%.8f anchor=%.6f",
                pair,
                size,
                anchor,
            )
        return out
    except Exception as e:
        out["error"] = str(e)[:200]
        logger.error("[LIFECYCLE-EXIT] SL reattach exception %s: %s", pair, e)
        return out


def apply_lifecycle_exits_live(
    *,
    config_dict: Optional[Dict[str, Any]] = None,
    exchange: Any = None,
    dry_run: bool = False,
    notify: bool = True,
) -> Dict[str, Any]:
    """
    Execute dual_peak / extension_partial trims when dual_peak_exit.mode=live.
    Uses market sells via exchange.place_market_sell (same path as live TP).
    """
    cfg = config_dict or {}
    if not cfg:
        try:
            cfg = json.loads(Path("config/trading_config_phase6.json").read_text())
        except Exception:
            cfg = {}
    life = load_lifecycle_config(cfg)
    p2 = life["dual_peak_exit"]
    mode = str(p2.get("mode") or "shadow").lower()
    out: Dict[str, Any] = {
        "ts": _utcnow(),
        "mode": mode,
        "dry_run": dry_run,
        "events": [],
        "executed": [],
        "skipped": [],
    }
    if mode != "live" and not dry_run:
        out["note"] = "dual_peak_exit.mode != live — no sells"
        # still run shadow path for board
        out["events"] = run_dual_peak_exit_shadow(config_dict=cfg, notify=notify)
        return out

    # Evaluate with live mode semantics
    p2_eval = dict(p2)
    p2_eval["mode"] = "live"
    lots = [x for x in _load_lots(ENTRY_LOTS_PATH) if x.get("open", True)]
    if not lots:
        out["note"] = "no open entry lots"
        return out

    pairs = [str(x["pair"]) for x in lots if x.get("pair")]
    ballast = {str(x) for x in (p2.get("ballast_pairs") or [])}
    try:
        from phase6.core.sentiment_scorer import load_sentiment_scores

        sent = load_sentiment_scores(universe=pairs) or {}
    except Exception:
        sent = {}

    prices: Dict[str, float] = {}
    positions: Dict[str, float] = {}
    qty_by_pair: Dict[str, float] = {}
    try:
        live_p = Path("data/state/phase6_live_state.json")
        if live_p.exists():
            live = json.loads(live_p.read_text())
            try:
                from phase6.core.position_qty import qty_map_from_live_state, position_qty

                qty_by_pair = qty_map_from_live_state(live)
            except Exception:
                qty_by_pair = {}
            for row in live.get("positions") or []:
                if isinstance(row, dict) and row.get("pair"):
                    p = str(row["pair"])
                    positions[p] = _f(row.get("value_usd"), 0.0)
                    prices[p] = _f(row.get("current_price"), 0.0)
                    if p not in qty_by_pair:
                        try:
                            from phase6.core.position_qty import position_qty

                            qty_by_pair[p] = position_qty(row, 0.0)
                        except Exception:
                            qty_by_pair[p] = _f(
                                row.get("quantity") or row.get("qty") or row.get("amount"),
                                0.0,
                            )
    except Exception:
        pass

    # peak updates (same as shadow)
    try:
        run_dual_peak_exit_shadow(config_dict=cfg, notify=False)
        lots = [x for x in _load_lots(ENTRY_LOTS_PATH) if x.get("open", True)]
    except Exception:
        pass

    phase_cfg = load_run_phase_config(cfg)
    events = evaluate_dual_peak_exits(
        lots=lots,
        current_sentiment=sent,
        current_prices=prices,
        positions_usd=positions,
        cfg_p2=p2_eval,
        cfg_phase=phase_cfg,
    )
    out["events"] = [e.as_dict() for e in events]

    if not events:
        return out

    min_trim = _f(p2.get("live_min_trim_usd"), 40.0)
    max_n = int(p2.get("live_max_trims_per_tick") or 2)

    # Prefer dual_peak over extension_partial
    ordered = sorted(events, key=lambda e: 0 if e.kind == "dual_peak" else 1)
    seen = set()
    to_do = []
    for ev in ordered:
        if ev.pair in seen or ev.pair in ballast:
            continue
        if ev.would_trim_usd < min_trim:
            continue
        seen.add(ev.pair)
        to_do.append(ev)
        if len(to_do) >= max_n:
            break

    if dry_run or (mode != "live"):
        out["skipped"] = [
            {"pair": e.pair, "kind": e.kind, "usd": e.would_trim_usd, "reason": "dry_run_or_not_live"}
            for e in to_do
        ]
        if notify and out["events"] and p2.get("notify_telegram", True):
            _notify_dual_peak(out["events"], dedupe_hours=_f(p2.get("notify_dedupe_hours"), 6.0))
        return out

    if exchange is None:
        try:
            from phase6.core.exchange_client import CoinbaseExchangeClient

            exchange = CoinbaseExchangeClient(mode="live")
        except Exception as e:
            out["error"] = f"no_exchange: {e}"
            return out

    for ev in to_do:
        pair = ev.pair
        px = _f(prices.get(pair), ev.current_price)
        qty_full = _f(qty_by_pair.get(pair), 0.0)
        if qty_full <= 0 and px > 0:
            qty_full = positions.get(pair, 0.0) / px
        qty = qty_full * ev.would_trim_frac
        try:
            if hasattr(exchange, "quantize_size"):
                qty = float(exchange.quantize_size(pair, qty))
        except Exception:
            qty = round(qty, 8)
        if qty <= 0:
            out["skipped"].append({"pair": pair, "reason": "zero_qty"})
            continue
        try:
            result = exchange.place_market_sell(pair, qty) or {}
        except Exception as se:
            out["skipped"].append({"pair": pair, "error": str(se)[:200]})
            logger.error("[LIFECYCLE-EXIT] sell exception %s: %s", pair, se)
            continue
        ok = bool(result.get("success"))
        oid = result.get("order_id")
        row = {
            "ts": _utcnow(),
            "pair": pair,
            "kind": ev.kind,
            "success": ok,
            "order_id": oid,
            "qty": qty,
            "would_trim_frac": ev.would_trim_frac,
            "phase_name": ev.phase_name,
            "reasons": ev.reasons,
            "signal_source": f"lifecycle_{ev.kind}",
        }
        if not ok:
            row["error"] = result.get("error")
            out["skipped"].append(row)
            continue
        exit_px = px
        filled = qty
        if oid and hasattr(exchange, "get_order_fill_details"):
            try:
                import time as _time

                _time.sleep(0.5)
                fill = exchange.get_order_fill_details(oid) or {}
                if _f(fill.get("average_filled_price")) > 0:
                    exit_px = _f(fill["average_filled_price"])
                if _f(fill.get("filled_size")) > 0:
                    filled = _f(fill["filled_size"])
            except Exception:
                pass
        row["exit_price"] = exit_px
        row["filled_qty"] = filled
        # ledger
        try:
            from phase6.core.trade_ledger import TradeLedger

            led = TradeLedger()
            led.log_trade(
                {
                    "pair": pair,
                    "side": "SELL",
                    "action": "SELL",
                    "qty": filled,
                    "exit_price": exit_px,
                    "order_id": oid,
                    "reason": f"lifecycle_{ev.kind}:{'|'.join(ev.reasons)}",
                    "signal_source": f"lifecycle_{ev.kind}",
                    "success": True,
                }
            )
        except Exception as le:
            row["ledger_error"] = str(le)[:120]
        # close/reduce entry lot
        entry_anchor = ev.entry_price
        try:
            all_lots = _load_lots(ENTRY_LOTS_PATH)
            for lot in all_lots:
                if str(lot.get("pair")) == pair and lot.get("open", True):
                    entry_anchor = _f(lot.get("entry_price"), entry_anchor) or entry_anchor
                    if ev.would_trim_frac >= 0.99:
                        lot["open"] = False
                        lot["closed_at"] = _utcnow()
                        lot["close_reason"] = ev.kind
                    else:
                        lot["partial_trim_frac"] = _f(lot.get("partial_trim_frac"), 0.0) + ev.would_trim_frac
                        lot["last_trim_kind"] = ev.kind
                        lot["last_trim_at"] = _utcnow()
            ENTRY_LOTS_PATH.write_text(
                json.dumps({"updated": _utcnow(), "lots": all_lots}, indent=2)
            )
        except Exception:
            pass
        # SL reattach remaining bag (one pair at a time — no bulk race)
        rem_hint = max(0.0, qty_full - filled)
        if rem_hint > 1e-12 and ev.would_trim_frac < 0.99:
            sl_info = reattach_sl_after_lifecycle_trim(
                exchange,
                pair,
                entry_price=entry_anchor if entry_anchor > 0 else exit_px,
                remaining_qty_hint=rem_hint,
                config_dict=cfg,
            )
            row["sl_reattach"] = sl_info
            if not sl_info.get("ok"):
                logger.warning(
                    "[LIFECYCLE-EXIT] SL reattach failed %s: %s",
                    pair,
                    sl_info.get("error") or sl_info,
                )
        elif ev.would_trim_frac >= 0.99:
            # Full exit — cancel leftover protective orders for pair
            try:
                from phase6.core.sl_preflight import cancel_open_stops_for_pair

                cancel_open_stops_for_pair(exchange, pair)
                row["sl_reattach"] = {"ok": True, "action": "cancelled_full_exit"}
            except Exception as ce:
                row["sl_reattach"] = {"ok": False, "error": f"cancel_full: {ce}"[:160]}
        out["executed"].append(row)
        logger.info(
            "[LIFECYCLE-EXIT] LIVE %s %s qty=%.6f oid=%s sl=%s",
            ev.kind,
            pair,
            filled,
            oid,
            (row.get("sl_reattach") or {}).get("ok"),
        )
        try:
            DUAL_PEAK_LIVE_EXITS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with DUAL_PEAK_LIVE_EXITS_PATH.open("a") as f:
                f.write(json.dumps(row, default=str) + "\n")
        except Exception:
            pass

    if notify and (out["executed"] or out["events"]) and p2.get("notify_telegram", True):
        note_rows = out["executed"] or out["events"]
        _notify_dual_peak(
            [
                {
                    "pair": r.get("pair"),
                    "kind": r.get("kind"),
                    "would_trim_usd": r.get("qty"),
                    "would_trim_frac": r.get("would_trim_frac"),
                    "phase_name": r.get("phase_name"),
                    "reasons": r.get("reasons") or [],
                    "mode": "live",
                    "shadow": False,
                    "ts": r.get("ts") or _utcnow(),
                }
                for r in note_rows
            ],
            dedupe_hours=_f(p2.get("notify_dedupe_hours"), 6.0),
        )
    return out


def run_dual_peak_exit_shadow(
    *,
    config_dict: Optional[Dict[str, Any]] = None,
    notify: bool = False,
    lots_path: Path = ENTRY_LOTS_PATH,
    events_path: Path = DUAL_PEAK_EVENTS_PATH,
) -> List[Dict[str, Any]]:
    life = load_lifecycle_config(config_dict)
    p2 = life["dual_peak_exit"]
    lots = [x for x in _load_lots(lots_path) if x.get("open", True)]
    if not lots:
        return []

    pairs = [str(x["pair"]) for x in lots if x.get("pair")]
    try:
        from phase6.core.sentiment_scorer import load_sentiment_scores

        sent = load_sentiment_scores(universe=pairs) or {}
    except Exception:
        sent = {}

    prices: Dict[str, float] = {}
    positions: Dict[str, float] = {}
    try:
        live_p = Path("data/state/phase6_live_state.json")
        if live_p.exists():
            live = json.loads(live_p.read_text())
            for row in live.get("positions") or []:
                if isinstance(row, dict) and row.get("pair"):
                    p = str(row["pair"])
                    positions[p] = _f(row.get("value_usd"), 0.0)
                    prices[p] = _f(row.get("current_price"), 0.0)
    except Exception:
        pass

    # update peak_price on lots (best-effort persistence)
    try:
        changed = False
        all_lots = _load_lots(lots_path)
        for lot in all_lots:
            if not lot.get("open", True):
                continue
            p = str(lot.get("pair") or "")
            px = _f(prices.get(p), 0.0)
            if px <= 0:
                continue
            prev = _f(lot.get("peak_price"), 0.0)
            if px > prev:
                lot["peak_price"] = px
                changed = True
            # track sent peak
            cs = _f(sent.get(p), 0.0)
            prev_s = _f(lot.get("entry_sent_peak"), _f(lot.get("entry_sentiment"), 0.0))
            if cs > prev_s:
                lot["entry_sent_peak"] = cs
                changed = True
        if changed:
            lots_path.parent.mkdir(parents=True, exist_ok=True)
            lots_path.write_text(
                json.dumps({"updated": _utcnow(), "lots": all_lots}, indent=2)
            )
            lots = [x for x in all_lots if x.get("open", True)]
    except Exception:
        pass

    phase_cfg = load_run_phase_config(config_dict)
    events = evaluate_dual_peak_exits(
        lots=lots,
        current_sentiment=sent,
        current_prices=prices,
        positions_usd=positions,
        cfg_p2=p2,
        cfg_phase=phase_cfg,
    )
    out: List[Dict[str, Any]] = []
    if events:
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with events_path.open("a") as f:
            for ev in events:
                row = ev.as_dict()
                f.write(json.dumps(row) + "\n")
                out.append(row)
                logger.info(
                    "[DUAL-PEAK-%s] %s %s would_trim=$%.2f (%.0f%%) peak_r=%.2f%% phase=%s %s",
                    "SHADOW" if ev.shadow else "TAG",
                    ev.kind,
                    ev.pair,
                    ev.would_trim_usd,
                    ev.would_trim_frac * 100,
                    ev.peak_return * 100,
                    ev.phase_name,
                    "|".join(ev.reasons),
                )

    if notify and out and p2.get("notify_telegram", True):
        _notify_dual_peak(out, dedupe_hours=_f(p2.get("notify_dedupe_hours"), 6.0))
    return out


def _notify_dual_peak(rows: List[Dict[str, Any]], dedupe_hours: float = 6.0) -> None:
    try:
        dedupe = {}
        if DUAL_PEAK_NOTIFY_PATH.exists():
            dedupe = json.loads(DUAL_PEAK_NOTIFY_PATH.read_text())
    except Exception:
        dedupe = {}
    now = datetime.now(timezone.utc)
    to_send = []
    for r in rows:
        key = f"{r.get('pair')}:{r.get('kind')}"
        last = dedupe.get(key)
        if last:
            try:
                prev = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                if (now - prev).total_seconds() < dedupe_hours * 3600:
                    continue
            except Exception:
                pass
        to_send.append(r)
        dedupe[key] = now.isoformat()
    if not to_send:
        return
    try:
        DUAL_PEAK_NOTIFY_PATH.parent.mkdir(parents=True, exist_ok=True)
        DUAL_PEAK_NOTIFY_PATH.write_text(json.dumps(dedupe, indent=2))
    except Exception:
        pass
    lines = ["📉 Dual-peak / extension SHADOW (no live sell)"]
    for r in to_send:
        lines.append(
            f"• {r.get('kind')} {r['pair']}: would_trim ${r['would_trim_usd']:.0f} "
            f"({r['would_trim_frac']*100:.0f}%) peak_r={r['peak_return']*100:.1f}% "
            f"phase={r.get('phase_name')} sent {r.get('entry_sentiment'):.2f}→{r.get('current_sentiment'):.2f}"
        )
    msg = "\n".join(lines)
    try:
        from phase6.core.telegram_notifier import send_telegram_message  # type: ignore

        send_telegram_message(msg)
    except Exception:
        logger.warning("[DUAL-PEAK] notify skipped. msg=\n%s", msg)


def enrich_entry_lot_lifecycle(
    lot: Dict[str, Any],
    *,
    candles: Optional[Sequence[Any]] = None,
    config_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Add run_phase_at_entry, structure, swing refs onto a lot dict."""
    pair = str(lot.get("pair") or "")
    if not pair:
        return lot
    try:
        cdl = normalize_candles(candles) if candles else fetch_daily_candles_public(pair, limit=40)
        snap = classify_run_phase(cdl, pair=pair)
        st = classify_structure(cdl, pair=pair, cfg=load_lifecycle_config(config_dict)["structure"])
        lot["run_phase_at_entry"] = snap.phase
        lot["run_phase_name_at_entry"] = snap.phase_name
        lot["swing_low_ref"] = st.swing_low
        lot["swing_high_ref"] = st.swing_high
        lot["structure_at_entry"] = {
            "ok": st.structure_ok_for_entry,
            "fib_pos": st.fib_pos,
            "above_sma_fast": st.above_sma_fast,
        }
        lot["entry_sent_peak"] = _f(lot.get("entry_sent_peak"), _f(lot.get("entry_sentiment"), 0.0))
        lot["peak_price"] = max(_f(lot.get("peak_price"), 0.0), _f(lot.get("entry_price"), 0.0))
    except Exception as e:
        lot["lifecycle_enrich_error"] = str(e)
    return lot
