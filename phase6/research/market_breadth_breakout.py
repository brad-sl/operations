#!/usr/bin/env python3
"""Market breadth / multi-pair momentum helpers — research + paper shadow only.

See:
  docs/research/MARKET_BREADTH_MOMENTUM_BREAKOUT_RESEARCH.md
  docs/research/CASH_RERISK_AFTER_ROTATION_SHADOW_RULE.md

No live orders. Pure functions + light IO helpers for case studies.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# Liquid set for breadth B1 (majors / high-value; not full discovery universe)
DEFAULT_BREADTH_UNIVERSE: Tuple[str, ...] = (
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "XRP-USD",
    "LINK-USD",
    "AVAX-USD",
    "DOGE-USD",
    "ADA-USD",
)

DEFAULT_RET_24H_MIN = 0.03  # +3%
DEFAULT_BREADTH_K = 4
DEFAULT_CASH_FRAC_MIN = 0.60
DEFAULT_BEAR_BTC_30D = -0.10  # fraction
DEFAULT_PAPER_SLEEVE_USD = 75.0


@dataclass
class BreadthSnapshot:
    """One evaluation of multi-pair participation."""

    ret_by_pair: Dict[str, float]
    green_pairs: List[str]
    breadth_count: int
    breadth_k: int
    ret_min: float
    breadth_on: bool
    median_ret: Optional[float]
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CashReriskFire:
    """Paper would-fire decision for cash re-risk shadow rule."""

    fire: bool
    reasons: List[str] = field(default_factory=list)
    cash_frac: Optional[float] = None
    breadth_on: bool = False
    bear_veto: bool = False
    unblocked_targets: List[str] = field(default_factory=list)
    paper_sleeve_usd: float = 0.0
    paper_targets: List[str] = field(default_factory=list)
    tag: str = "none"  # fire | breadth_only | cash_idle_no_breadth | bear | blocked | none

    def to_dict(self) -> dict:
        return asdict(self)


def pct_returns(rets: Mapping[str, float]) -> Dict[str, float]:
    """Normalize map values to float fractions (0.05 = +5%). Accepts percent if |x|>1.5."""
    out: Dict[str, float] = {}
    for k, v in rets.items():
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if abs(x) > 1.5:  # likely percent points
            x = x / 100.0
        out[str(k)] = x
    return out


def breadth_from_returns(
    ret_by_pair: Mapping[str, float],
    *,
    universe: Sequence[str] = DEFAULT_BREADTH_UNIVERSE,
    ret_min: float = DEFAULT_RET_24H_MIN,
    k: int = DEFAULT_BREADTH_K,
) -> BreadthSnapshot:
    """B1: count names in universe with ret >= ret_min."""
    rets = pct_returns(ret_by_pair)
    scored = {p: rets[p] for p in universe if p in rets}
    green = sorted([p for p, r in scored.items() if r >= ret_min])
    vals = list(scored.values())
    med = sorted(vals)[len(vals) // 2] if vals else None
    on = len(green) >= int(k)
    note = (
        f"green={len(green)}/{len(universe)} (have_data={len(scored)}) "
        f"threshold={ret_min:.2%} k={k} → {'ON' if on else 'OFF'}"
    )
    return BreadthSnapshot(
        ret_by_pair=dict(scored),
        green_pairs=green,
        breadth_count=len(green),
        breadth_k=int(k),
        ret_min=float(ret_min),
        breadth_on=on,
        median_ret=med,
        note=note,
    )


def cash_fraction(cash_usd: float, total_usd: float) -> Optional[float]:
    try:
        c = float(cash_usd)
        t = float(total_usd)
    except (TypeError, ValueError):
        return None
    if t <= 0:
        return None
    return max(0.0, min(1.0, c / t))


def evaluate_cash_rerisk(
    *,
    cash_usd: float,
    total_usd: float,
    breadth: BreadthSnapshot,
    btc_ret_30d: Optional[float] = None,
    buy_blocked: Optional[Iterable[str]] = None,
    in_basket: Optional[Sequence[str]] = None,
    preferred_targets: Optional[Sequence[str]] = None,
    cash_frac_min: float = DEFAULT_CASH_FRAC_MIN,
    paper_sleeve_usd: float = DEFAULT_PAPER_SLEEVE_USD,
    bear_btc_30d: float = DEFAULT_BEAR_BTC_30D,
    coil_recent: bool = False,
    allow_coil_expansion_alt: bool = True,
) -> CashReriskFire:
    """Paper shadow decision — no side effects.

    M2 alt: if cash-heavy and breadth OFF but coil_recent + allow_coil_expansion_alt,
    do **not** auto-fire (coil alone ≠ expansion). Fire still requires breadth ON.
    Tag `coil_ready_wait_breadth` when coiled + cash-heavy for logger context.
    When breadth ON after coil, tag becomes `fire_coil_expansion` for analysis.
    """
    blocked = {str(p) for p in (buy_blocked or [])}
    basket = list(in_basket or DEFAULT_BREADTH_UNIVERSE)
    cf = cash_fraction(cash_usd, total_usd)
    reasons: List[str] = []

    # bear veto (fraction or percent)
    bear = False
    if btc_ret_30d is not None:
        r = float(btc_ret_30d)
        if abs(r) > 1.5:
            r = r / 100.0
        bear = r <= float(bear_btc_30d)
    if bear:
        return CashReriskFire(
            fire=False,
            reasons=["bear_veto_btc_30d"],
            cash_frac=cf,
            breadth_on=breadth.breadth_on,
            bear_veto=True,
            tag="bear",
        )

    if cf is None:
        return CashReriskFire(
            fire=False,
            reasons=["bad_nav"],
            breadth_on=breadth.breadth_on,
            tag="none",
        )

    cash_heavy = cf >= float(cash_frac_min)
    if breadth.breadth_on and not cash_heavy:
        return CashReriskFire(
            fire=False,
            reasons=[f"breadth_on_but_cash_frac={cf:.2f}<{cash_frac_min}"],
            cash_frac=cf,
            breadth_on=True,
            tag="breadth_only",
        )
    if cash_heavy and not breadth.breadth_on:
        tag = "cash_idle_no_breadth"
        rs = [
            f"cash_heavy_frac={cf:.2f}",
            f"breadth_off count={breadth.breadth_count}<{breadth.breadth_k}",
        ]
        if coil_recent and allow_coil_expansion_alt:
            tag = "coil_ready_wait_breadth"
            rs.append("coil_recent_wait_for_breadth_expansion")
        return CashReriskFire(
            fire=False,
            reasons=rs,
            cash_frac=cf,
            breadth_on=False,
            tag=tag,
        )
    if not cash_heavy and not breadth.breadth_on:
        return CashReriskFire(
            fire=False,
            reasons=["no_cash_idle_no_breadth"],
            cash_frac=cf,
            breadth_on=False,
            tag="none",
        )

    # both cash heavy + breadth ON
    reasons.append(f"cash_frac={cf:.2f}>={cash_frac_min}")
    reasons.append(breadth.note)
    fire_tag = "fire_coil_expansion" if coil_recent else "fire"
    if coil_recent:
        reasons.append("coil_then_breadth_expansion")

    # targets: preferred ∩ basket, unblocked; else green ∩ basket unblocked
    pref = list(preferred_targets or ("BTC-USD", "ETH-USD", "SOL-USD", "LINK-USD"))
    unblocked = [p for p in basket if p not in blocked]
    if not unblocked:
        return CashReriskFire(
            fire=False,
            reasons=reasons + ["all_basket_buy_blocked"],
            cash_frac=cf,
            breadth_on=True,
            unblocked_targets=[],
            tag="blocked",
        )

    ordered: List[str] = []
    for p in pref:
        if p in unblocked and p not in ordered:
            ordered.append(p)
    for p in breadth.green_pairs:
        if p in unblocked and p not in ordered:
            ordered.append(p)
    for p in unblocked:
        if p not in ordered:
            ordered.append(p)
    targets = ordered[:2]
    sleeve = min(float(paper_sleeve_usd), max(0.0, 0.25 * float(cash_usd)))
    reasons.append(f"paper_targets={targets} sleeve=${sleeve:.2f}")

    return CashReriskFire(
        fire=True,
        reasons=reasons,
        cash_frac=cf,
        breadth_on=True,
        bear_veto=False,
        unblocked_targets=unblocked,
        paper_sleeve_usd=round(sleeve, 2),
        paper_targets=targets,
        tag=fire_tag,
    )


# Back-compat alias
evaluate_cash_rerisk_shadow = evaluate_cash_rerisk
