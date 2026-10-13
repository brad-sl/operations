#!/usr/bin/env python3
"""
§D1 Flat deploy priority (shadow only).

Pure helper: would_prefer_ballast_before_shell(...)
- Applies in regime flat or transition
- deploy_cap e.g. 75
- If BTC or ETH held < 0.35 * target*eq AND not late_run_blocked for that leg
  → prefer_ballast=True, reserve=min(deploy_cap, gap_to_35pct)
- If late_run blocked on both → shells_ok=True (allow new tryout)
- Otherwise prefer=False, reserve=0

Shadow measure only. No live_apply. No orders.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from phase6.core.paths import CONFIG_DIR

logger = logging.getLogger(__name__)

CONFIG_PATH = CONFIG_DIR / "flat_deploy_priority.json"
SCHEMA = "flat_deploy_priority_v1"

DEFAULT_CFG: Dict[str, Any] = {
    "schema": SCHEMA,
    "live_apply": False,
    "flat_regimes": ["flat", "transition"],
    "deploy_cap_usd": 75,
    "min_held_pct": 0.35,
    "reserve_before_shell": True,
    "shadow_only": True,
    "late_run_block_allows_shell": True,
}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def load_config() -> Dict[str, Any]:
    try:
        if CONFIG_PATH.is_file():
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg = DEFAULT_CFG.copy()
                cfg.update(raw)
                return cfg
    except Exception as e:
        logger.warning("flat_deploy_priority config load failed: %s", e)
    return DEFAULT_CFG.copy()


def would_prefer_ballast_before_shell(
    *,
    regime: str,
    deploy_cap_usd: float,
    btc_held: float,
    eth_held: float,
    equity: float,
    target_w_btc: float,
    target_w_eth: float,
    btc_late_run_blocked: bool,
    eth_late_run_blocked: bool,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return {would_prefer_ballast: bool, reserve_usd: float, reasons: list, shells_ok: bool, shadow: true}"""
    c = cfg or load_config()
    out: Dict[str, Any] = {
        "regime": str(regime or "").lower(),
        "would_prefer_ballast": False,
        "reserve_usd": 0.0,
        "reasons": [],
        "shells_ok": True,
        "shadow": True,
        "live_apply": False,
    }

    flat_regimes = c.get("flat_regimes", DEFAULT_CFG["flat_regimes"])
    min_pct = _f(c.get("min_held_pct", 0.35))
    dcap = _f(deploy_cap_usd or c.get("deploy_cap_usd", 75))

    reg = out["regime"]
    if reg not in flat_regimes:
        out["reasons"].append("not_flat_or_transition")
        out["shells_ok"] = True
        return out

    eq = max(_f(equity), 1.0)
    btc_t = _f(target_w_btc) * eq
    eth_t = _f(target_w_eth) * eq
    btc_held_f = _f(btc_held)
    eth_held_f = _f(eth_held)

    btc_gap_to_min = max(0.0, (min_pct * btc_t) - btc_held_f)
    eth_gap_to_min = max(0.0, (min_pct * eth_t) - eth_held_f)

    btc_needs = btc_gap_to_min > 1.0 and not btc_late_run_blocked
    eth_needs = eth_gap_to_min > 1.0 and not eth_late_run_blocked

    if btc_needs or eth_needs:
        out["would_prefer_ballast"] = True
        gap = max(btc_gap_to_min, eth_gap_to_min)
        reserve = min(dcap, gap)
        out["reserve_usd"] = round(reserve, 2)
        out["shells_ok"] = False  # hold for ballast first
        out["reasons"].append("under_target_ballast_gap")
        if btc_needs:
            out["reasons"].append("btc_needs_floor")
        if eth_needs:
            out["reasons"].append("eth_needs_floor")
    else:
        out["would_prefer_ballast"] = False
        out["reserve_usd"] = 0.0
        if btc_held_f >= (min_pct * btc_t) and eth_held_f >= (min_pct * eth_t):
            out["reasons"].append("both_sufficiently_held")
        else:
            out["reasons"].append("no_gap_or_blocked")

    # late run blocks allow shells even if gaps
    if btc_late_run_blocked and eth_late_run_blocked:
        out["shells_ok"] = True
        out["reasons"].append("late_run_blocked")
        if out["would_prefer_ballast"]:
            # still prefer but allow shell if both blocked? per spec test: shells_ok_true
            out["reasons"].append("shells_forced_by_late_block")

    return out


if __name__ == "__main__":
    print(load_config())
    print(would_prefer_ballast_before_shell(
        regime="flat", deploy_cap_usd=75, btc_held=20, eth_held=0,
        equity=2500, target_w_btc=0.18, target_w_eth=0.12,
        btc_late_run_blocked=False, eth_late_run_blocked=False
    ))
