#!/usr/bin/env python3
"""Membership heightened-potential boundary (optimize bag — not deploy-ready).

Spec: docs/research/MEMBERSHIP_HEIGHTENED_POTENTIAL_BOUNDARY.md

Frozen intent (Brad 2026-08-19):
  - Optimize fixed bag via 1:1 swap, do not expand.
  - Inbound needs heightened *potential* (structural seat quality).
  - Does NOT require RSI/sentiment buy-today (deploy is a separate layer).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

# --- frozen defaults (spec) ---
STICKY_CORE: frozenset = frozenset({"BTC-USD", "ETH-USD"})
MIN_QUOTE_VOL_24H = 1_500_000.0
MIN_POTENTIAL_SCORE = 0.35
MIN_DELTA = 0.05
MIN_MOM_7D_ALT = 0.02  # +2% if 3d mom not non-negative
PUMP_RET_24H_ABS = 0.80
ANTI_PUMP_RET_24H = 0.15
ANTI_PUMP_RET_3D = 0.25
ANTI_PUMP_RUNUP_3D = 0.35
FLAT_HELD_USD = 40.0
REQUIRE_DEPLOY_READY_FOR_MEMBERSHIP = False  # FROZEN


@dataclass
class MembershipSwapVerdict:
    """Boundary verdict for a proposed 1:1 bag optimization."""

    ok: bool
    optimize_bag: bool = True
    require_deploy_ready: bool = REQUIRE_DEPLOY_READY_FOR_MEMBERSHIP
    inbound_ok: bool = False
    outbound_ok: bool = False
    delta_ok: bool = False
    bag_ok: bool = False
    inbound_potential: Optional[float] = None
    outbound_potential: Optional[float] = None
    delta: Optional[float] = None
    layer_failed: Optional[str] = None  # M0|M1|M2|M3
    reasons: List[str] = field(default_factory=list)
    add: str = ""
    remove: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _f(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def composite_potential_from_features(
    *,
    quality_score: Optional[float] = None,
    arm_score: Optional[float] = None,
    mom_3d: Optional[float] = None,
    mom_7d: Optional[float] = None,
    vol_expand: Optional[float] = None,
    energy: Optional[float] = None,
) -> Optional[float]:
    """Seat-quality scalar in ~[0,1+] when possible.

    Prefer discovery quality_score; else arm_score mapped softly; else feature blend.
    """
    q = _f(quality_score)
    if q is not None:
        return q
    a = _f(arm_score)
    if a is not None:
        # arm scores are heterogeneous; keep raw for delta, clamp display-ish
        return a
    m3 = _f(mom_3d) or 0.0
    m7 = _f(mom_7d) or 0.0
    ve = _f(vol_expand) or 1.0
    en = _f(energy) or 0.0
    # rough unnormalized blend → still usable for delta within same method
    return round(0.4 * max(m3, 0.0) * 10 + 0.3 * max(m7, 0.0) * 10 + 0.2 * min(ve, 5.0) / 5.0 + 0.1 * en, 4)


def inbound_heightened_potential(
    *,
    add: str,
    active: Sequence[str],
    potential_score: Optional[float],
    quote_vol_24h: Optional[float] = None,
    ret_24h: Optional[float] = None,
    mom_3d: Optional[float] = None,
    mom_7d: Optional[float] = None,
    runup_3d: Optional[float] = None,
    discovery_upside_ok: Optional[bool] = None,
    min_potential: float = MIN_POTENTIAL_SCORE,
    min_quote_vol: float = MIN_QUOTE_VOL_24H,
    skip_score_floor: bool = False,
) -> tuple[bool, List[str], Optional[float]]:
    """M1: structural seat quality — never RSI/sent."""
    reasons: List[str] = []
    add = str(add or "")
    if not add:
        return False, ["no_add"], None
    if add in set(active):
        return False, ["already_active"], potential_score

    vol = _f(quote_vol_24h)
    if vol is not None and vol < min_quote_vol:
        reasons.append("thin_liquidity")

    r24 = _f(ret_24h)
    if r24 is not None and abs(r24) > PUMP_RET_24H_ABS:
        reasons.append("pump_brake")
    # anti-pump extension (membership still avoids melt-up seats)
    m3 = _f(mom_3d)
    run = _f(runup_3d)
    if r24 is not None and r24 > ANTI_PUMP_RET_24H:
        reasons.append("extended_24h")
    if m3 is not None and m3 > ANTI_PUMP_RET_3D:
        reasons.append("extended_3d")
    if run is not None and run > ANTI_PUMP_RUNUP_3D:
        reasons.append("extended_runup")

    score = _f(potential_score)
    if score is None and not skip_score_floor:
        reasons.append("no_potential_score")
    elif score is not None and not skip_score_floor and score < min_potential:
        # arm scores may be outside 0-1; only apply floor when score looks like quality [0,1.5]
        if 0.0 <= score <= 1.5 and score < min_potential:
            reasons.append("low_potential")

    # upside structure
    m7 = _f(mom_7d)
    upside = False
    if discovery_upside_ok is True:
        upside = True
    if m3 is not None and m3 >= 0:
        upside = True
    if m7 is not None and m7 >= MIN_MOM_7D_ALT:
        upside = True
    if r24 is not None and r24 >= 0 and (m3 is None or m3 >= -0.02):
        upside = True
    if not upside:
        reasons.append("no_upside_structure")

    ok = not reasons
    return ok, reasons, score


def outbound_weak_seat(
    *,
    remove: str,
    active: Sequence[str],
    sticky: Optional[Set[str]] = None,
    held_usd: Optional[float] = None,
    protect_held_hard: bool = False,
    flat_held_usd: float = FLAT_HELD_USD,
) -> tuple[bool, List[str]]:
    """M2: fair eject from fixed bag."""
    reasons: List[str] = []
    remove = str(remove or "")
    sticky = sticky or set(STICKY_CORE)
    if not remove:
        return False, ["no_remove"]
    if remove in sticky:
        return False, ["sticky_core"]
    if remove not in set(active):
        return False, ["not_active"]
    h = _f(held_usd)
    if h is not None and h >= flat_held_usd:
        if protect_held_hard:
            reasons.append("protect_held")
        else:
            reasons.append("held_soft_prefer_flat")  # soft — does not fail alone
    # soft reason doesn't fail
    hard = [r for r in reasons if r != "held_soft_prefer_flat"]
    return len(hard) == 0, reasons


def potential_delta_ok(
    inbound_potential: Optional[float],
    outbound_potential: Optional[float],
    *,
    min_delta: float = MIN_DELTA,
    precomputed_delta: Optional[float] = None,
) -> tuple[bool, List[str], Optional[float]]:
    """M3: ADD seat clearly better than REMOVE seat."""
    if precomputed_delta is not None:
        d = float(precomputed_delta)
        if d >= min_delta or d > 0:  # arm Δ>0 accepted; min_delta for score units
            # If arm uses large scores, >0 is enough; for 0-1 quality use min_delta
            if abs(d) > 2:  # arm-scale
                ok = d > 0
            else:
                ok = d >= min_delta
            return ok, ([] if ok else ["delta_too_small"]), d
    inn = _f(inbound_potential)
    out = _f(outbound_potential)
    if inn is None or out is None:
        return False, ["delta_missing_scores"], None
    d = inn - out
    # scale-aware margin
    if abs(inn) > 2 or abs(out) > 2:
        ok = d > 0
    else:
        ok = d >= min_delta
    return ok, ([] if ok else ["delta_too_small"]), d


def evaluate_membership_swap(
    *,
    add: str,
    remove: str,
    active: Sequence[str],
    inbound_potential: Optional[float] = None,
    outbound_potential: Optional[float] = None,
    precomputed_delta: Optional[float] = None,
    quote_vol_24h: Optional[float] = None,
    ret_24h: Optional[float] = None,
    mom_3d: Optional[float] = None,
    mom_7d: Optional[float] = None,
    runup_3d: Optional[float] = None,
    discovery_upside_ok: Optional[bool] = None,
    held_usd_remove: Optional[float] = None,
    sticky: Optional[Set[str]] = None,
    protect_held_hard: bool = False,
    skip_inbound_score_floor: bool = False,
    min_delta: float = MIN_DELTA,
) -> MembershipSwapVerdict:
    """Full M0–M3 membership boundary. Deploy-ready is never required."""
    reasons: List[str] = []
    active_l = list(active)

    # M0 bag
    bag_ok = True
    if not add or not remove:
        bag_ok = False
        reasons.append("bag_missing_leg")
    if add == remove:
        bag_ok = False
        reasons.append("bag_same_pair")
    if add in active_l and remove in active_l and add != remove:
        # swapping two actives is not optimize-in from outside — reject for this path
        bag_ok = False
        reasons.append("bag_not_outside_in")
    if remove not in active_l:
        bag_ok = False
        reasons.append("bag_remove_not_active")
    if add in active_l:
        bag_ok = False
        reasons.append("bag_expand_or_already_in")

    if not bag_ok:
        return MembershipSwapVerdict(
            ok=False,
            bag_ok=False,
            layer_failed="M0",
            reasons=reasons,
            add=add,
            remove=remove,
            require_deploy_ready=REQUIRE_DEPLOY_READY_FOR_MEMBERSHIP,
        )

    in_ok, in_reasons, in_score = inbound_heightened_potential(
        add=add,
        active=active_l,
        potential_score=inbound_potential,
        quote_vol_24h=quote_vol_24h,
        ret_24h=ret_24h,
        mom_3d=mom_3d,
        mom_7d=mom_7d,
        runup_3d=runup_3d,
        discovery_upside_ok=discovery_upside_ok,
        skip_score_floor=skip_inbound_score_floor,
    )
    reasons.extend([f"M1:{r}" for r in in_reasons])
    if not in_ok:
        return MembershipSwapVerdict(
            ok=False,
            bag_ok=True,
            inbound_ok=False,
            inbound_potential=in_score if in_score is not None else inbound_potential,
            outbound_potential=outbound_potential,
            layer_failed="M1",
            reasons=reasons,
            add=add,
            remove=remove,
        )

    out_ok, out_reasons = outbound_weak_seat(
        remove=remove,
        active=active_l,
        sticky=sticky,
        held_usd=held_usd_remove,
        protect_held_hard=protect_held_hard,
    )
    reasons.extend([f"M2:{r}" for r in out_reasons])
    if not out_ok:
        return MembershipSwapVerdict(
            ok=False,
            bag_ok=True,
            inbound_ok=True,
            outbound_ok=False,
            inbound_potential=inbound_potential,
            outbound_potential=outbound_potential,
            layer_failed="M2",
            reasons=reasons,
            add=add,
            remove=remove,
        )

    d_ok, d_reasons, delta = potential_delta_ok(
        inbound_potential if inbound_potential is not None else in_score,
        outbound_potential,
        min_delta=min_delta,
        precomputed_delta=precomputed_delta,
    )
    reasons.extend([f"M3:{r}" for r in d_reasons])
    if not d_ok:
        return MembershipSwapVerdict(
            ok=False,
            bag_ok=True,
            inbound_ok=True,
            outbound_ok=True,
            delta_ok=False,
            inbound_potential=inbound_potential if inbound_potential is not None else in_score,
            outbound_potential=outbound_potential,
            delta=delta,
            layer_failed="M3",
            reasons=reasons,
            add=add,
            remove=remove,
        )

    reasons.append("membership_potential_ok")
    reasons.append("deploy_ready_not_required")
    return MembershipSwapVerdict(
        ok=True,
        bag_ok=True,
        inbound_ok=True,
        outbound_ok=True,
        delta_ok=True,
        inbound_potential=inbound_potential if inbound_potential is not None else in_score,
        outbound_potential=outbound_potential,
        delta=delta,
        layer_failed=None,
        reasons=reasons,
        add=add,
        remove=remove,
        require_deploy_ready=REQUIRE_DEPLOY_READY_FOR_MEMBERSHIP,
    )
