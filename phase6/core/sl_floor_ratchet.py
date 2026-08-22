"""
SL floor ratchet after large mark-vs-entry spread / multi-bagger adds.

Pure policy: never loosen stop. Raises protective floor when open multiple
and/or projected add gap is too wide (P6-SL-RATCHET-AFTER-ADDS).

See docs/research/SL_FLOOR_RATCHET_AFTER_ADDS.md
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "multiple_soft": 1.5,
    "multiple_hard": 2.0,
    "lock_frac_soft": 0.35,
    "lock_frac_hard": 0.50,
    "be_buffer_pct": 0.005,
    "add_gap_max": 0.20,
    "min_raise_pct": 0.001,
    "stop_loss_pct": 0.03,
}


@dataclass
class RatchetDecision:
    applied: bool
    old_stop: float
    new_stop: float
    calc_base_out: float
    reasons: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def raised(self) -> bool:
        return self.applied and self.new_stop > self.old_stop + 1e-12


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def load_ratchet_settings(risk_management: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rm = risk_management or {}
    cfg = dict(_DEFAULTS)
    block = rm.get("sl_ratchet") if isinstance(rm.get("sl_ratchet"), dict) else {}
    cfg.update({k: v for k, v in block.items() if v is not None})
    if "sl_ratchet_enabled" in rm:
        cfg["enabled"] = bool(rm.get("sl_ratchet_enabled"))
    if rm.get("stop_loss_pct") is not None:
        cfg["stop_loss_pct"] = _f(rm.get("stop_loss_pct"), cfg["stop_loss_pct"])
    return cfg


def open_multiple(mark: float, entry: float) -> Optional[float]:
    e = _f(entry)
    m = _f(mark)
    if e <= 0 or m <= 0:
        return None
    return m / e


def profit_lock_floor(entry: float, mark: float, lock_frac: float, be_buffer_pct: float) -> float:
    """Price floor that locks `lock_frac` of the open run from entry → mark."""
    e = _f(entry)
    m = _f(mark)
    if e <= 0 or m <= e:
        return 0.0
    locked = e + max(0.0, min(1.0, lock_frac)) * (m - e)
    # slight buffer under lock level so stop isn't glued to mark noise
    return locked * (1.0 - max(0.0, be_buffer_pct))


def compute_ratchet_stop(
    *,
    entry: float,
    mark: float,
    proposed_stop: float,
    existing_stop: Optional[float] = None,
    add_price: Optional[float] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> RatchetDecision:
    """
    Return stop that is max(proposed, existing, ratchet floors). Never below proposed if
    ratchet disabled; never loosens vs existing_stop when provided.
    """
    cfg = dict(_DEFAULTS)
    if settings:
        cfg.update(settings)

    prop = _f(proposed_stop)
    entry_f = _f(entry)
    mark_f = _f(mark)
    existing = _f(existing_stop) if existing_stop is not None else 0.0
    floor = prop
    reasons: List[str] = []
    detail: Dict[str, Any] = {
        "entry": entry_f,
        "mark": mark_f,
        "proposed_stop": prop,
        "existing_stop": existing or None,
        "enabled": bool(cfg.get("enabled", True)),
    }

    if not cfg.get("enabled", True):
        out = max(prop, existing) if existing > 0 else prop
        return RatchetDecision(
            applied=False,
            old_stop=prop,
            new_stop=out,
            calc_base_out=out / max(1e-12, 1.0 - _f(cfg.get("stop_loss_pct"), 0.03))
            if out > 0
            else entry_f,
            reasons=["disabled"],
            detail=detail,
        )

    mult = open_multiple(mark_f, entry_f)
    detail["multiple"] = round(mult, 6) if mult is not None else None

    if mult is not None and mark_f > entry_f > 0:
        soft_m = _f(cfg.get("multiple_soft"), 1.5)
        hard_m = _f(cfg.get("multiple_hard"), 2.0)
        if mult >= hard_m:
            lf = _f(cfg.get("lock_frac_hard"), 0.50)
            fl = profit_lock_floor(entry_f, mark_f, lf, _f(cfg.get("be_buffer_pct"), 0.005))
            if fl > floor:
                floor = fl
                reasons.append(f"hard_multiple>={hard_m:g} lock={lf:g}")
        elif mult >= soft_m:
            lf = _f(cfg.get("lock_frac_soft"), 0.35)
            fl = profit_lock_floor(entry_f, mark_f, lf, _f(cfg.get("be_buffer_pct"), 0.005))
            # also at least breakeven+buffer once soft multiple hit
            be = entry_f * (1.0 + _f(cfg.get("be_buffer_pct"), 0.005))
            fl = max(fl, be)
            if fl > floor:
                floor = fl
                reasons.append(f"soft_multiple>={soft_m:g} lock={lf:g}")

    # Add gap: if adding at add_price with current floor leaves huge air pocket, raise floor
    add_px = _f(add_price) if add_price is not None else 0.0
    gap_max = _f(cfg.get("add_gap_max"), 0.20)
    if add_px > 0 and floor > 0:
        gap = (add_px - floor) / add_px
        detail["add_gap_at_floor"] = round(gap, 6)
        if gap > gap_max:
            # raise floor so gap == gap_max: floor = add_px * (1 - gap_max)
            target = add_px * (1.0 - gap_max)
            if target > floor:
                floor = target
                reasons.append(f"add_gap>{gap_max:g}")

    # Open-book air pocket: large multiple-ish runner with stop far under mark
    # (covers post-add bags even when reattach is not tagged fresh_buy)
    pocket_mult_min = _f(cfg.get("air_pocket_multiple_min"), 1.25)
    if mark_f > 0 and floor > 0 and mult is not None and mult >= pocket_mult_min:
        gap_m = (mark_f - floor) / mark_f
        detail["mark_gap_at_floor"] = round(gap_m, 6)
        if gap_m > gap_max:
            target = mark_f * (1.0 - gap_max)
            if target > floor:
                floor = target
                reasons.append(f"air_pocket_gap>{gap_max:g}")

    # Never loosen vs existing live stop
    if existing > 0:
        floor = max(floor, existing)

    # Never place stop at/above mark
    if mark_f > 0 and floor >= mark_f:
        floor = mark_f * (1.0 - max(_f(cfg.get("stop_loss_pct"), 0.03), 0.005))
        reasons.append("clamped_below_mark")

    min_raise = _f(cfg.get("min_raise_pct"), 0.001)
    raised = floor > prop * (1.0 + min_raise) or (existing > 0 and floor > prop + 1e-12 and floor >= existing)
    # applied if we improved vs pure proposed genesis stop
    applied = floor > prop + max(prop * min_raise, 1e-12)

    if applied:
        reasons = reasons or ["raised"]
    else:
        reasons = reasons or ["no_raise"]
        floor = max(prop, existing) if existing > 0 else prop

    # Implied calc_base for % SL logging: stop / (1 - sl_pct)
    slp = _f(cfg.get("stop_loss_pct"), 0.03)
    calc_out = floor / (1.0 - slp) if slp < 0.999 and floor > 0 else entry_f
    detail["lock_floor"] = round(floor, 8)
    detail["reasons"] = list(reasons)

    return RatchetDecision(
        applied=applied,
        old_stop=prop,
        new_stop=floor,
        calc_base_out=calc_out,
        reasons=reasons,
        detail=detail,
    )


def apply_ratchet_to_stop_bundle(
    *,
    pair: str,
    entry: float,
    mark: float,
    proposed_stop: float,
    proposed_limit: float,
    existing_stop: Optional[float] = None,
    add_price: Optional[float] = None,
    risk_management: Optional[Dict[str, Any]] = None,
) -> tuple[float, float, RatchetDecision]:
    """Adjust stop/limit upward only. Limit stays ~0.5% under stop when raised."""
    settings = load_ratchet_settings(risk_management)
    dec = compute_ratchet_stop(
        entry=entry,
        mark=mark,
        proposed_stop=proposed_stop,
        existing_stop=existing_stop,
        add_price=add_price,
        settings=settings,
    )
    stop = dec.new_stop
    if dec.raised or dec.applied:
        limit = min(proposed_limit, stop * 0.995) if proposed_limit > 0 else stop * 0.995
        if limit >= stop:
            limit = stop * 0.995
        logger.info(
            "[SL-RATCHET] %s stop $%.6f → $%.6f reasons=%s multiple=%s",
            pair,
            dec.old_stop,
            stop,
            dec.reasons,
            (dec.detail or {}).get("multiple"),
        )
    else:
        limit = proposed_limit
        stop = proposed_stop if not existing_stop else max(proposed_stop, _f(existing_stop))
    return stop, limit, dec
