"""NEEDLE-01: capped USDC→USD top-up so a deploy door can fire.

USDC is a temporary yield bank, not a permanent vault. Convert only the
shortfall vs powder reserve, never dump remaining USDC. Native Convert 403
on this consumer book — usdc_convert hops USDT.

Never sells crypto. Max unwind per cycle is hard-capped.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from phase6.core.phase6_runner import Phase6Runner

logger = logging.getLogger(__name__)

MAX_UNWIND_PER_CYCLE = 150.0
MIN_ACTION_USD = 25.0


@dataclass
class ClipUnwindPlan:
    action: str = "hold"  # hold | unwind
    reason: str = ""
    usd: float = 0.0
    usdc: float = 0.0
    target_usd_reserve: float = 0.0
    shortfall: float = 0.0
    unwind_usd: float = 0.0
    cap_usd: float = MAX_UNWIND_PER_CYCLE

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def plan_clip_unwind(
    *,
    usd: float,
    usdc: float,
    target_usd_reserve: float,
    park_signal: bool = False,
    bear: bool = False,
    max_unwind: float = MAX_UNWIND_PER_CYCLE,
    min_action: float = MIN_ACTION_USD,
) -> ClipUnwindPlan:
    """Pure decision. Dump-all is impossible: unwind ≤ min(shortfall, usdc, cap)."""
    usd = float(usd or 0.0)
    usdc = float(usdc or 0.0)
    target = float(target_usd_reserve or 0.0)
    cap = max(0.0, float(max_unwind))
    plan = ClipUnwindPlan(
        usd=usd,
        usdc=usdc,
        target_usd_reserve=target,
        cap_usd=cap,
        shortfall=max(0.0, target - usd),
    )
    if park_signal or bear:
        plan.reason = "park_or_bear_keep_usdc"
        return plan
    if plan.shortfall < float(min_action):
        plan.reason = "usd_covers_reserve"
        return plan
    if usdc < float(min_action):
        plan.reason = "usdc_below_min_action"
        return plan
    unwind = min(plan.shortfall, usdc, cap)
    if unwind < float(min_action):
        plan.reason = "unwind_below_min_action"
        return plan
    plan.action = "unwind"
    plan.unwind_usd = round(unwind, 2)
    plan.reason = "usd_short_of_wave_reserve"
    return plan


def maybe_cycle_clip_unwind(runner: "Phase6Runner") -> Dict[str, Any]:
    """Live/shadow cycle hook. Shadow records intent; live converts via USDT hop."""
    from phase6.core.powder_balancer import compute_target_usd_reserve, compute_wave_need, powder_balancer_cfg
    from phase6.core.usdc_park_executor import _portfolio_snapshot

    out: Dict[str, Any] = {
        "ok": True,
        "ts": datetime.now(timezone.utc).isoformat(),
        "skipped": True,
    }
    park_cfg: Dict[str, Any] = {}
    try:
        from phase6.core.trader_account_config import live_usdc_park_settings

        acct = getattr(runner, "account_id", None) or "default"
        park_cfg = live_usdc_park_settings(acct) or {}
    except Exception:
        park_cfg = {}

    snap = _portfolio_snapshot(runner)
    wave = compute_wave_need(getattr(runner, "config_dict", None) or {})
    pcfg = powder_balancer_cfg(park_cfg)
    target = compute_target_usd_reserve(wave, pcfg)

    regime = ""
    park_signal = False
    try:
        st = getattr(runner, "regime_cash_status", None) or {}
        if isinstance(st, dict):
            regime = str(st.get("regime") or st.get("label") or "")
            park_signal = bool(st.get("park_signal") or st.get("usdc_park"))
    except Exception:
        pass
    bear = "bear" in regime.lower() or "usdc_park" in regime.lower()

    plan = plan_clip_unwind(
        usd=float(snap.get("usd") or 0.0),
        usdc=float(snap.get("usdc") or 0.0),
        target_usd_reserve=float(target),
        park_signal=park_signal,
        bear=bear,
    )
    out["plan"] = plan.to_dict()
    out["reason"] = plan.reason
    if plan.action != "unwind":
        return out

    mode = str(getattr(runner, "mode", "") or "")
    if mode != "live":
        out["shadow_intent"] = True
        out["would_unwind_usd"] = plan.unwind_usd
        logger.info("[NEEDLE-01] shadow unwind $%.0f reason=%s", plan.unwind_usd, plan.reason)
        return out

    try:
        from phase6.core.usdc_convert import convert_via_runner

        trade = convert_via_runner(runner, direction="usdc_to_usd", amount=plan.unwind_usd)
        out["trade"] = trade
        out["ok"] = bool((trade or {}).get("success"))
        out["skipped"] = False
        logger.info(
            "[NEEDLE-01] live unwind $%.0f ok=%s reason=%s",
            plan.unwind_usd,
            out["ok"],
            plan.reason,
        )
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)
        logger.exception("[NEEDLE-01] unwind failed")
    return out
