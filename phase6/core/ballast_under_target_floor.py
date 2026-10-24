#!/usr/bin/env python3
"""
§C1/C2 Ballast under-target floor.

Pure helper: would_allow_under_target_step(...)
- Floor step when ordinary max_add cannot fund a real move:
  max_add == 0 (collapsed) OR 0 < max_add < min_useful (residual stub, Brad GO A 2026-10-23)
- Skip if held >= 0.35 * target_w * equity
- Guard: pair/role, stop_attached, not_over, upnl >= -0.06
- step_usd = min(max_step, flat_cap, max(0, target_val - held))
- already_has_max_add only when max_add >= min_useful (default $25 min_move)

live_apply: when True + no kill file, matrix may inject step into max_add.
Money still only moves via rebalance/add-risk consumers of max_add.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from phase6.core.paths import CONFIG_DIR, STATE_DIR

logger = logging.getLogger(__name__)

CONFIG_PATH = CONFIG_DIR / "ballast_under_target_floor.json"
KILL_PATH = STATE_DIR / "ballast_under_target_floor_KILL"
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
    "min_useful_max_add_usd": 25.0,
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


def kill_file_on(path: Optional[Path] = None) -> bool:
    p = path or KILL_PATH
    try:
        return p.is_file()
    except Exception:
        return False


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


def is_live_apply(cfg: Optional[Dict[str, Any]] = None) -> bool:
    """True only when config live_apply AND no kill file."""
    c = cfg or load_config()
    if kill_file_on():
        return False
    return bool(c.get("live_apply")) and not bool(c.get("shadow_only", False) and not c.get("live_apply"))


def effective_live_apply(cfg: Optional[Dict[str, Any]] = None) -> bool:
    """Strict: live_apply true, shadow_only false, no kill."""
    c = cfg or load_config()
    if kill_file_on():
        return False
    if not bool(c.get("live_apply")):
        return False
    # If live_apply true, ignore stale shadow_only pin
    return True


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
    min_useful_max_add_usd: Optional[float] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return {allow: bool, step_usd: float, reasons: list, shadow/live flags}.

    Floor opens when ordinary max_add is collapsed (0) OR a residual stub below
    min_useful_max_add_usd (same idea as add-risk min_move — default $25). A
    positive-but-useless max_add must not block the ballast step (Brad GO A
    2026-10-23). Useful room (max_add >= min_useful) still means already_has_max_add.
    """
    c = cfg or load_config()
    live = effective_live_apply(c)
    pn = _norm_pair(pair)
    out: Dict[str, Any] = {
        "pair": pn,
        "role": role,
        "allow": False,
        "step_usd": 0.0,
        "reasons": [],
        "shadow": not live,
        "live_apply": live,
        "kill_file": kill_file_on(),
    }

    pairs = c.get("pairs_allow", DEFAULT_CFG["pairs_allow"])
    roles = c.get("roles_allow", DEFAULT_CFG["roles_allow"])
    max_step = _f(c.get("max_step_usd", 75))
    min_held_pct = _f(c.get("min_held_pct_of_target_to_skip", 0.35))
    forbid_upnl = _f(c.get("forbid_if_open_upnl_pct_lt", -0.06))
    require_stop = bool(c.get("require_stop_attached", True))
    require_not_over = bool(c.get("require_not_over_target", True))
    if min_useful_max_add_usd is not None:
        min_useful = _f(min_useful_max_add_usd, 25.0)
    else:
        min_useful = _f(c.get("min_useful_max_add_usd", DEFAULT_CFG["min_useful_max_add_usd"]), 25.0)
    out["min_useful_max_add_usd"] = round(min_useful, 4)

    # Useful ordinary room already funds a real move — do not double-inject floor.
    # Residual stubs (0 < max_add < min_useful) are treated as collapsed for floor.
    if _f(max_add_usd) + 1e-9 >= min_useful:
        out["reasons"].append("already_has_max_add")
        return out
    if _f(max_add_usd) > 0:
        out["residual_max_add_usd"] = round(_f(max_add_usd), 4)

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

    if target_val > 0 and (held / target_val) >= min_held_pct:
        out["reasons"].append("min_held_pct_skip")
        return out

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


def apply_floor_to_max_add(
    *,
    pair: str,
    role: str,
    held_usd: float,
    equity_usd: float,
    target_w: float,
    max_add_usd: Optional[float],
    open_upnl_pct: float = 0.0,
    stop_attached: bool = True,
    flat_cap_usd: Optional[float] = None,
    min_useful_max_add_usd: Optional[float] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    If live_apply and floor allows, return max(max_add, step).
    Always returns diagnostic; only mutates when live.
    Residual max_add below min_useful is overridden by the floor step (GO A).
    """
    c = cfg or load_config()
    live = effective_live_apply(c)
    raw = max_add_usd
    max_f = _f(max_add_usd, 0.0) if max_add_usd is not None else 0.0
    # empty bag / flat_no_stack → treat collapsed
    if max_add_usd is None and _f(held_usd) < 1.0:
        max_f = 0.0

    would = would_allow_under_target_step(
        pair=pair,
        role=role,
        held_usd=held_usd,
        equity_usd=equity_usd,
        target_w=target_w,
        max_add_usd=max_f,
        open_upnl_pct=open_upnl_pct,
        stop_attached=stop_attached,
        flat_cap_usd=flat_cap_usd,
        min_useful_max_add_usd=min_useful_max_add_usd,
        cfg=c,
    )
    out: Dict[str, Any] = {
        "pair": would.get("pair"),
        "live_apply": live,
        "would": would,
        "max_add_before": raw,
        "max_add_after": raw,
        "injected": False,
        "step_usd": would.get("step_usd") or 0.0,
    }
    if live and would.get("allow") and _f(would.get("step_usd")) > 0:
        step = _f(would.get("step_usd"))
        after = max(max_f, step)
        out["max_add_after"] = round(after, 4)
        out["injected"] = True
    return out


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
    """Pure call site helper. Returns the would_ dict."""
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
