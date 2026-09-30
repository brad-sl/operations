"""NEEDLE-05: core vs tryout size split (flag default OFF).

Live apply of 40–55% core is a separate Brad GO. This module is the
shadow sizer + min_move contract so $25 tryouts are not dropped.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class SizeSplitPlan:
    enabled: bool
    tryout_usd: float
    min_move_usd: float
    tryout_passes_min_move: bool
    core_target_pct_lo: float
    core_target_pct_hi: float
    equity_usd: float
    core_plan_usd: float
    max_deployable_usd: float
    note: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def plan_size_split(
    *,
    equity_usd: float,
    min_move_usd: float = 25.0,
    tryout_usd: float = 25.0,
    max_deployable_usd: float = 1000.0,
    enabled: bool = False,
    core_pct_lo: float = 0.40,
    core_pct_hi: float = 0.55,
) -> SizeSplitPlan:
    eq = max(0.0, float(equity_usd or 0.0))
    mm = float(min_move_usd)
    tryout = float(tryout_usd)
    # Core envelope is a *plan*, not a live order. Cap vs max_deployable.
    mid = 0.5 * (float(core_pct_lo) + float(core_pct_hi))
    core_usd = min(eq * mid, float(max_deployable_usd))
    return SizeSplitPlan(
        enabled=bool(enabled),
        tryout_usd=tryout,
        min_move_usd=mm,
        tryout_passes_min_move=tryout + 1e-9 >= mm,
        core_target_pct_lo=float(core_pct_lo),
        core_target_pct_hi=float(core_pct_hi),
        equity_usd=eq,
        core_plan_usd=round(core_usd, 2),
        max_deployable_usd=float(max_deployable_usd),
        note=(
            "FLAG OFF — do not size live to 40–55%. "
            "Core plan is hundreds; tryout $25 must clear min_move."
            if not enabled
            else "FLAG ON — still requires Brad GO before live clip."
        ),
    )


def from_config(config_dict: Optional[Dict[str, Any]], equity_usd: float) -> SizeSplitPlan:
    cfg = config_dict or {}
    gs = cfg.get("global_settings") or {}
    alloc = gs.get("allocator") or {}
    n05 = cfg.get("needle05_size_split") or gs.get("needle05_size_split") or {}
    return plan_size_split(
        equity_usd=equity_usd,
        min_move_usd=float(alloc.get("min_move_usd") or 25.0),
        tryout_usd=float((n05.get("tryout_usd") if isinstance(n05, dict) else None) or 25.0),
        max_deployable_usd=float(gs.get("max_deployable_usd") or 1000.0),
        enabled=bool(n05.get("enabled")) if isinstance(n05, dict) else False,
    )
