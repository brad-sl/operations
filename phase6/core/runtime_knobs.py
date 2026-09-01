"""Runtime knobs: single place live paths read trading config.

Hardcodes in coordinators have repeatedly defeated SL%, post-SL blocks, and
cap experiments. Prefer these helpers everywhere an auto-BUY / allocate path
needs a number.

Defaults here match *intended* live policy in trading_config_phase6.json
(not historical leftover 12% / 24h / $200).
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping, Optional


# Intended live defaults when a key is missing (must match product policy).
DEFAULT_STOP_LOSS_PCT = 0.03
DEFAULT_REBALANCE_CAP_USD = 150.0
DEFAULT_MIN_RESERVE_USD = 50.0
DEFAULT_MIN_MOVE_USD = 50.0
DEFAULT_MIN_SCORE_DELTA = 0.05
DEFAULT_ALLOCATOR_COOLDOWN_HOURS = 6.0
DEFAULT_DD_THRESHOLD_PCT = 0.08
DEFAULT_MAX_PAIRS = 5
DEFAULT_DEPLOY_MIN_RSI = 30.0
DEFAULT_STOP_BLOCK_REBUY_HOURS = 72.0
DEFAULT_MANUAL_BLOCK_REBUY_HOURS = 48.0


def _as_dict(cfg: Any) -> Dict[str, Any]:
    if cfg is None:
        return {}
    if isinstance(cfg, Mapping):
        return dict(cfg)
    return {}


def _gs(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    return _as_dict(cfg.get("global_settings"))


def _rm(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    return _as_dict(cfg.get("risk_management"))


def _alloc_section(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    """Optional nested knobs: global_settings.allocator or top-level allocator."""
    gs = _gs(cfg)
    nested = gs.get("allocator")
    if isinstance(nested, Mapping):
        return dict(nested)
    top = cfg.get("allocator")
    if isinstance(top, Mapping):
        return dict(top)
    return {}


def stop_loss_pct(config_dict: Optional[Mapping[str, Any]] = None) -> float:
    """Exchange-aligned stop fraction (e.g. 0.03 = 3%)."""
    cfg = _as_dict(config_dict)
    rm = _rm(cfg)
    raw = rm.get("stop_loss_pct", rm.get("sl_base_pct", DEFAULT_STOP_LOSS_PCT))
    try:
        v = float(raw)
    except (TypeError, ValueError):
        v = DEFAULT_STOP_LOSS_PCT
    # Guard absurd values (legacy 12% as fraction is ok; 12 as percent is not)
    if v > 1.0:
        v = v / 100.0
    if v <= 0 or v > 0.5:
        return DEFAULT_STOP_LOSS_PCT
    return v


def rebalance_cap_usd(config_dict: Optional[Mapping[str, Any]] = None) -> float:
    cfg = _as_dict(config_dict)
    gs = _gs(cfg)
    try:
        return float(gs.get("rebalance_cap_usd", DEFAULT_REBALANCE_CAP_USD))
    except (TypeError, ValueError):
        return DEFAULT_REBALANCE_CAP_USD


def min_reserve_usd(config_dict: Optional[Mapping[str, Any]] = None) -> float:
    cfg = _as_dict(config_dict)
    wr = _as_dict(cfg.get("withdrawal_reserve"))
    rm = _rm(cfg)
    raw = wr.get("min_reserve_usd", rm.get("min_reserve_usd", DEFAULT_MIN_RESERVE_USD))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return DEFAULT_MIN_RESERVE_USD


def deploy_min_rsi(config_dict: Optional[Mapping[str, Any]] = None) -> float:
    cfg = _as_dict(config_dict)
    gs = _gs(cfg)
    alloc = _alloc_section(cfg)
    raw = alloc.get("deploy_min_rsi", gs.get("deploy_min_rsi", DEFAULT_DEPLOY_MIN_RSI))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return DEFAULT_DEPLOY_MIN_RSI


def stop_loss_block_rebuy_hours(config_dict: Optional[Mapping[str, Any]] = None) -> float:
    """Fallback only — live path should prefer capital_controls overlay."""
    cfg = _as_dict(config_dict)
    gs = _gs(cfg)
    raw = gs.get(
        "capital_event_stop_loss_exchange_block_rebuy_hours",
        DEFAULT_STOP_BLOCK_REBUY_HOURS,
    )
    try:
        return float(raw)
    except (TypeError, ValueError):
        return DEFAULT_STOP_BLOCK_REBUY_HOURS


def allocator_kwargs(config_dict: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Kwargs for ``create_allocator(..., **allocator_kwargs(cfg))``."""
    cfg = _as_dict(config_dict)
    gs = _gs(cfg)
    alloc = _alloc_section(cfg)

    def _f(key: str, default: float, *alt_keys: str) -> float:
        for k in (key,) + alt_keys:
            if k in alloc and alloc[k] is not None:
                try:
                    return float(alloc[k])
                except (TypeError, ValueError):
                    pass
            if k in gs and gs[k] is not None:
                try:
                    return float(gs[k])
                except (TypeError, ValueError):
                    pass
        return float(default)

    def _i(key: str, default: int) -> int:
        try:
            return int(_f(key, float(default)))
        except (TypeError, ValueError):
            return default

    return {
        "min_move_usd": _f("min_move_usd", DEFAULT_MIN_MOVE_USD, "allocator_min_move_usd"),
        "min_score_delta": _f(
            "min_score_delta", DEFAULT_MIN_SCORE_DELTA, "allocator_min_score_delta"
        ),
        "stop_loss_pct": stop_loss_pct(cfg),
        "cooldown_hours": _f(
            "cooldown_hours", DEFAULT_ALLOCATOR_COOLDOWN_HOURS, "allocator_cooldown_hours"
        ),
        "dd_threshold_pct": _f(
            "dd_threshold_pct", DEFAULT_DD_THRESHOLD_PCT, "allocator_dd_threshold_pct"
        ),
        "max_pairs": _i("max_pairs", DEFAULT_MAX_PAIRS),
    }


def config_dict_from_runner(runner: Any) -> Dict[str, Any]:
    return _as_dict(getattr(runner, "config_dict", None))


def limit_first_policy(config_dict: Optional[Mapping[str, Any]] = None):
    """Limit-first buy policy. Default enabled=False (market IOC path)."""
    from phase6.core.limit_first_buy import policy_from_config

    return policy_from_config(_as_dict(config_dict))


def limit_first_enabled(config_dict: Optional[Mapping[str, Any]] = None) -> bool:
    return bool(limit_first_policy(config_dict).enabled)


def create_allocator_from_config(
    strategy: str = "rotation",
    config_dict: Optional[Mapping[str, Any]] = None,
    **overrides: Any,
):
    """create_allocator with config-backed knobs; overrides win."""
    from phase6.core.allocator import create_allocator

    kw = allocator_kwargs(config_dict)
    kw.update(overrides)
    return create_allocator(strategy, **kw)
