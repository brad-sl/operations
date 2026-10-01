"""
Phase 6 Core Package

This package contains the canonical implementation of the Phase 6 trading system.
All modules here are considered the single source of truth for Phase 6.

Do not modify files in scripts/phase6/ or root-level Phase 6 files without first
migrating changes here.
"""

from .allocation_engine import (
    compute_inverse_vol_allocations,
    plan_static_allocations,
    rebalance_plan,
)
from .stop_loss_manager import StopLossManager
from .sl_risk_scorer import get_all_sl_risks, get_sl_risk

# Lazy import for Phase6Runner to avoid pulling heavy deps (e.g. requests)
# into every `import phase6.core.*` (shadows, tests, etc). Use direct
# `from phase6.core.phase6_runner import Phase6Runner` or `from phase6.core import Phase6Runner`
# for full runner.
def __getattr__(name: str):
    if name == "Phase6Runner":
        from .phase6_runner import Phase6Runner as _Phase6Runner
        return _Phase6Runner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "Phase6Runner",
    "compute_inverse_vol_allocations",
    "plan_static_allocations",
    "rebalance_plan",
    "StopLossManager",
    "get_all_sl_risks",
    "get_sl_risk",
]
