#!/usr/bin/env python3
"""
Fractional Kelly as a risk-budget layer (research-only).

Not an entry signal. Full Kelly is never a live default.
Maps edge (p, b) → risk fraction f → loss-at-stop notional, then clamps
to deploy / regime util / reserve / max position envelopes.

Real ledger estimation and path compares live in run_kelly_sizing_test.py.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional


def kelly_fraction(p: float, b: float) -> float:
    """
    Full Kelly fraction for a single independent bet.

    f* = p - (1-p)/b = (b*p - q)/b
    p = win rate in (0,1], b = avg_win/avg_loss > 0 (payoff ratio).
    Returns 0 when edge is non-positive or inputs invalid.
    """
    if b is None or p is None:
        return 0.0
    try:
        p = float(p)
        b = float(b)
    except (TypeError, ValueError):
        return 0.0
    if b <= 0 or p < 0 or p > 1:
        return 0.0
    q = 1.0 - p
    f = p - (q / b)
    if f <= 0:
        return 0.0
    return float(f)


def fractional_kelly(p: float, b: float, frac: float = 0.5) -> float:
    """frac * full Kelly (e.g. half-Kelly). frac<=0 → 0; clamps frac to [0,1] for safety."""
    if frac is None:
        frac = 0.5
    try:
        frac = float(frac)
    except (TypeError, ValueError):
        frac = 0.5
    if frac <= 0:
        return 0.0
    if frac > 1.0:
        frac = 1.0
    return kelly_fraction(p, b) * frac


def risk_budget_to_notional(f: float, equity: float, sl_pct: float) -> float:
    """
    Convert risk fraction f (capital lost if SL hits) to position notional.

    position_usd ≈ (f * equity) / sl_pct
    """
    try:
        f = float(f)
        equity = float(equity)
        sl_pct = float(sl_pct)
    except (TypeError, ValueError):
        return 0.0
    if f <= 0 or equity <= 0 or sl_pct <= 0:
        return 0.0
    return (f * equity) / sl_pct


@dataclass(frozen=True)
class EnvelopeClampResult:
    position_usd: float
    raw_position_usd: float
    f_requested: float
    f_effective: float
    binding_constraint: str
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def clamp_to_envelopes(
    position_usd: float,
    *,
    equity: float,
    f_requested: float = 0.0,
    deploy_pct: float = 0.72,
    regime_target_max_util_pct: float = 0.65,
    min_reserve_usd: float = 50.0,
    max_position_usd: Optional[float] = None,
    rebalance_cap_usd: Optional[float] = None,
    cash_usd: Optional[float] = None,
    already_deployed_usd: float = 0.0,
) -> EnvelopeClampResult:
    """
    Clamp a Kelly-derived notional inside live-style envelopes.

    Order of binding checks (first tightest after sequential mins):
      raw → max_position → rebalance_cap → deploy budget → regime util headroom → reserve.
    Never exceeds remaining deployable after reserve / util.
    """
    try:
        raw = max(0.0, float(position_usd))
        equity = float(equity)
        deploy_pct = float(deploy_pct)
        util = float(regime_target_max_util_pct)
        reserve = max(0.0, float(min_reserve_usd))
        deployed = max(0.0, float(already_deployed_usd))
        f_req = max(0.0, float(f_requested))
    except (TypeError, ValueError):
        return EnvelopeClampResult(
            position_usd=0.0,
            raw_position_usd=0.0,
            f_requested=0.0,
            f_effective=0.0,
            binding_constraint="invalid_inputs",
            details={},
        )

    if equity <= 0:
        return EnvelopeClampResult(
            position_usd=0.0,
            raw_position_usd=raw,
            f_requested=f_req,
            f_effective=0.0,
            binding_constraint="non_positive_equity",
            details={"equity": equity},
        )

    cash = float(cash_usd) if cash_usd is not None else max(0.0, equity - deployed)
    # Deploy budget on equity (legacy knob) and cash available after reserve
    deploy_budget = max(0.0, equity * deploy_pct - deployed)
    util_budget = max(0.0, equity * util - deployed)
    reserve_room = max(0.0, cash - reserve)
    # Cannot deploy more than cash after reserve
    cash_budget = reserve_room

    caps = {
        "raw": raw,
        "deploy_pct_budget": deploy_budget,
        "regime_util_budget": util_budget,
        "reserve_cash_room": cash_budget,
    }
    if max_position_usd is not None and float(max_position_usd) > 0:
        caps["max_position_usd"] = float(max_position_usd)
    if rebalance_cap_usd is not None and float(rebalance_cap_usd) > 0:
        caps["rebalance_cap_usd"] = float(rebalance_cap_usd)

    # Binding = minimum positive-or-zero cap name
    binding = "raw"
    final = raw
    for name, cap in caps.items():
        if name == "raw":
            continue
        if cap < final:
            final = max(0.0, cap)
            binding = name

    # Effective risk fraction if this position were taken at given equity (needs sl later externally)
    f_eff = f_req
    if raw > 0 and f_req > 0:
        f_eff = f_req * (final / raw) if raw > 0 else 0.0

    return EnvelopeClampResult(
        position_usd=float(final),
        raw_position_usd=float(raw),
        f_requested=float(f_req),
        f_effective=float(max(0.0, f_eff)),
        binding_constraint=binding if final < raw - 1e-12 else "none",
        details={
            "equity": equity,
            "cash_usd": cash,
            "already_deployed_usd": deployed,
            "deploy_pct": deploy_pct,
            "regime_target_max_util_pct": util,
            "min_reserve_usd": reserve,
            "caps": {k: round(v, 6) for k, v in caps.items()},
        },
    )


def map_risk_fraction_to_deploy_pct(
    f_risk: float,
    sl_pct: float,
    *,
    haircut: float = 1.0,
    deploy_cap: float = 0.95,
) -> float:
    """
    Rough map: if risk_usd = f * equity and position ≈ risk/sl, then
    single-name full-book notional fraction ≈ f/sl. Multi-asset concurrent books
    should pass haircut < 1 (e.g. 0.5) so deploy_pct is not overstated.

    deploy_pct_candidate = min(deploy_cap, haircut * f_risk / sl_pct)
    """
    try:
        f_risk = float(f_risk)
        sl_pct = float(sl_pct)
        haircut = float(haircut)
        deploy_cap = float(deploy_cap)
    except (TypeError, ValueError):
        return 0.0
    if f_risk <= 0 or sl_pct <= 0 or haircut <= 0:
        return 0.0
    return float(min(deploy_cap, max(0.0, haircut * f_risk / sl_pct)))


def estimate_edge_from_returns(
    returns: list[float],
) -> Dict[str, Any]:
    """
    From a list of per-trade returns r = pnl/entry_notional (real trades only).
    p = P(r>0), b = mean(win r) / mean(|loss r|).
    """
    rets = [float(x) for x in returns if x is not None]
    n = len(rets)
    if n == 0:
        return {
            "n": 0,
            "p": None,
            "b": None,
            "f_full": 0.0,
            "insufficient": True,
            "reason": "no_returns",
        }
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    p = len(wins) / n
    if not wins or not losses:
        return {
            "n": n,
            "n_wins": len(wins),
            "n_losses": len(losses),
            "p": p,
            "b": None,
            "mean_win_r": (sum(wins) / len(wins)) if wins else None,
            "mean_loss_r": (sum(losses) / len(losses)) if losses else None,
            "f_full": 0.0,
            "insufficient": True,
            "reason": "need_both_wins_and_losses",
        }
    mean_w = sum(wins) / len(wins)
    mean_l = abs(sum(losses) / len(losses))
    b = mean_w / mean_l if mean_l > 0 else None
    f = kelly_fraction(p, b) if b else 0.0
    return {
        "n": n,
        "n_wins": len(wins),
        "n_losses": len(losses),
        "p": round(p, 6),
        "b": round(b, 6) if b is not None else None,
        "mean_win_r": round(mean_w, 6),
        "mean_loss_r": round(sum(losses) / len(losses), 6),
        "f_full": round(f, 6),
        "f_half": round(f * 0.5, 6),
        "f_quarter": round(f * 0.25, 6),
        "insufficient": False,
        "reason": None,
    }


def apply_trade_to_equity(
    equity: float,
    trade_return: float,
    f_risk: float,
    sl_pct: float,
    envelopes: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    One-step sequential bet: size from f_risk, apply realized trade_return on notional.
    envelopes forwarded to clamp_to_envelopes (equity-only book, deployed=0).
    """
    equity = float(equity)
    if equity <= 0:
        return {"equity": 0.0, "pnl": 0.0, "position_usd": 0.0, "binding": "dead"}
    raw = risk_budget_to_notional(f_risk, equity, sl_pct)
    env = dict(envelopes or {})
    clamped = clamp_to_envelopes(
        raw,
        equity=equity,
        f_requested=f_risk,
        deploy_pct=float(env.get("deploy_pct", 0.95)),
        regime_target_max_util_pct=float(env.get("regime_target_max_util_pct", 0.95)),
        min_reserve_usd=float(env.get("min_reserve_usd", 0.0)),
        max_position_usd=env.get("max_position_usd"),
        rebalance_cap_usd=env.get("rebalance_cap_usd"),
        cash_usd=env.get("cash_usd", equity),
        already_deployed_usd=float(env.get("already_deployed_usd", 0.0)),
    )
    pos = clamped.position_usd
    pnl = pos * float(trade_return)
    new_eq = equity + pnl
    return {
        "equity_before": equity,
        "equity_after": new_eq,
        "pnl": pnl,
        "position_usd": pos,
        "raw_position_usd": clamped.raw_position_usd,
        "binding": clamped.binding_constraint,
        "f_risk": f_risk,
        "trade_return": trade_return,
    }
