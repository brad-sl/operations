#!/usr/bin/env python3
"""
§C1 Ballast under-target floor (shadow only).

Pure helper: would_allow_under_target_step(...)
- Floor step ONLY when max_add_usd == 0 (collapsed)
- Skip if held >= 0.35 * target_w * equity
- Guard: pair/role, stop_attached, not_over, upnl >= -0.06
- step_usd = min(max_step, flat_cap, max(0, target_val - held))
- live_apply: false always for this module (shadow)

No money movement. Measure only.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from phase6.core.paths import CONFIG_DIR

logger = logging.getLogger(__name__)

CONFIG_PATH = CONFIG_DIR / "ballast_under_target_floor.json"
SCHEMA = "ballast_under_target_floor_v1"

DEFAULT_CFG: Dict[str, Any] = {
    "schema": SCHEMA,
    "live_apply": False,
    "pairs_allow": ["BTC-USD", "ETH-USD"],
    "roles_allow": ["ballast_core"],
    "max_step_usd": 75,
    "respect_flat_rebalance_cap": True,
    "min_held_pct_of_target_to_skip": 0.35,
    "require_stop_attached": True,
    "require_not_over_target": True,
    "forbid_if_open_upnl_pct_lt": -0.06,
    "default_flat_cap_usd": 75,
    "shadow_only": True,
}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def _norm_pair(pair: str) -> str:
    p = str(pair or "").strip().upper().replace("_", "-")
    if not p:
        return ""
    if "-" not in p:
        p = f"{p}-USD"
    return p


def load_config() -> Dict[str, Any]:
    try:
        if CONFIG_PATH.is_file():
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg = DEFAULT_CFG.copy()
                cfg.update(raw)
                return cfg
    except Exception as e:
        logger.warning("ballast_under_target_floor config load failed: %s", e)
    return DEFAULT_CFG.copy()


def would_allow_under_target_step(
    *,
    pair: str,
    role: str,
    held_usd: float,
    equity_usd: float,
    target_w: float,
    max_add_usd: float,
    open_upnl_pct: float,
    stop_attached: bool,
    flat_cap_usd: Optional[float] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return {allow: bool, step_usd: float, reasons: list, shadow: true}."""
    c = cfg or load_config()
    pn = _norm_pair(pair)
    out: Dict[str, Any] = {
        "pair": pn,
        "role": role,
        "allow": False,
        "step_usd": 0.0,
        "reasons": [],
        "shadow": True,
        "live_apply": False,  # enforced
    }

    pairs = c.get("pairs_allow", DEFAULT_CFG["pairs_allow"])
    roles = c.get("roles_allow", DEFAULT_CFG["roles_allow"])
    max_step = _f(c.get("max_step_usd", 75))
    min_held_pct = _f(c.get("min_held_pct_of_target_to_skip", 0.35))
    forbid_upnl = _f(c.get("forbid_if_open_upnl_pct_lt", -0.06))
    require_stop = bool(c.get("require_stop_attached", True))
    require_not_over = bool(c.get("require_not_over_target", True))

    if max_add_usd > 0:
        out["reasons"].append("already_has_max_add")
        return out

    if pn not in pairs:
        out["reasons"].append("pair_not_allowed")
        return out
    if role not in roles:
        out["reasons"].append("role_not_ballast")
        return out

    held = _f(held_usd)
    eq = max(_f(equity_usd), 1.0)
    tw = _f(target_w)
    target_val = tw * eq
    gap = max(0.0, target_val - held)

    # Guards before "enough held" skip so over-target / stop / upnl stay explicit
    if require_not_over and held > target_val + 1e-9:
        out["reasons"].append("over_target")
        return out

    if require_stop and not stop_attached:
        out["reasons"].append("stop_required")
        return out

    upnl = _f(open_upnl_pct)
    if upnl < forbid_upnl:
        out["reasons"].append("upnl_below_forbid")
        return out

    # Already near band (held ≥ min_held_pct of target) — floor not needed
    if target_val > 0 and (held / target_val) >= min_held_pct:
        out["reasons"].append("min_held_pct_skip")
        return out

    # flat cap
    fcap = (
        _f(flat_cap_usd)
        if flat_cap_usd is not None
        else _f(c.get("default_flat_cap_usd", 75))
    )
    step = min(max_step, fcap, gap)

    out["allow"] = step > 0
    out["step_usd"] = round(step, 2)
    out["target_val"] = round(target_val, 2)
    out["gap"] = round(gap, 2)
    if not out["allow"]:
        out["reasons"].append("zero_step")
    return out


# Optional pure helper for future matrix wire (no side effects)
def would_under_target_floor_for_membership(
    pair: str,
    role: str,
    held_usd: float,
    equity_usd: float,
    target_w: float,
    max_add_usd: float = 0.0,
    open_upnl_pct: float = 0.0,
    stop_attached: bool = True,
    flat_cap_usd: Optional[float] = None,
) -> Dict[str, Any]:
    """Pure call site helper. Returns the would_ dict. No money change."""
    return would_allow_under_target_step(
        pair=pair,
        role=role,
        held_usd=held_usd,
        equity_usd=equity_usd,
        target_w=target_w,
        max_add_usd=max_add_usd,
        open_upnl_pct=open_upnl_pct,
        stop_attached=stop_attached,
        flat_cap_usd=flat_cap_usd,
    )


if __name__ == "__main__":
    # quick smoke
    print(load_config())
    print(
        would_allow_under_target_step(
            pair="BTC-USD",
            role="ballast_core",
            held_usd=55,
            equity_usd=2260,
            target_w=0.18,
            max_add_usd=0,
            open_upnl_pct=-0.02,
            stop_attached=True,
            flat_cap_usd=75,
        )
    )
