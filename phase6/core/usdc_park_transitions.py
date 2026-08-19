"""
USDC park toggle transitions: off→on, on→off, park→market redeploy.

Operational state: data/state/usdc_park/<account>_transitions.json
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from phase6.core.paths import PROJECT_ROOT
from phase6.core.trader_account_config import live_usdc_park_settings
from phase6.core.usdc_park_executor import (
    PARK_STATE_DIR,
    _portfolio_snapshot,
    _save_park_state,
    execute_usdc_park_cycle,
    park_signal_active,
)

if TYPE_CHECKING:
    from phase6.core.phase6_runner import Phase6Runner

logger = logging.getLogger(__name__)

PHASE_STANDDOWN = "standdown_only"
PHASE_ARMED = "armed"
PHASE_PARKED = "parked"
PHASE_REDEPLOY = "redeploy_unwind"


def _transition_path(account_id: str) -> Path:
    PARK_STATE_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in account_id)[:128]
    return PARK_STATE_DIR / f"{safe}_transitions.json"


def load_transition_state(account_id: str) -> Dict[str, Any]:
    path = _transition_path(account_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_transition_state(account_id: str, state: Dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _transition_path(account_id).write_text(
        json.dumps(state, indent=2) + "\n", encoding="utf-8"
    )


def deploy_signal_active(config_dict: Dict[str, Any]) -> bool:
    """Regime/overlay wants alt deploy (not USDC park)."""
    if park_signal_active(config_dict):
        return False
    gs = config_dict.get("global_settings") or {}
    cap = float(gs.get("rebalance_cap_usd", 0) or 0)
    if cap > 0:
        return True
    shadow = config_dict.get("_analyst_shadow") or {}
    if shadow.get("scenario_id") and shadow.get("scenario_id") != "usdc_hold":
        return True
    return False


def record_toggle_change(account_id: str, enabled: bool) -> Dict[str, Any]:
    """Call when trader flips live_usdc_park in config (CLI or manual edit)."""
    state = load_transition_state(account_id)
    prev = bool(state.get("toggle_enabled"))
    state["toggle_enabled"] = enabled
    event = None
    if enabled and not prev:
        event = "off_to_on"
        state["operational_phase"] = PHASE_ARMED
        state["off_to_on_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("[USDC-PARK] transition off→on account=%s (armed)", account_id)
    elif not enabled and prev:
        event = "on_to_off"
        state["operational_phase"] = PHASE_STANDDOWN
        state["on_to_off_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("[USDC-PARK] transition on→off account=%s (standdown_only)", account_id)
    if event:
        state["last_transition"] = event
        state["last_transition_at"] = datetime.now(timezone.utc).isoformat()
    save_transition_state(account_id, state)
    return {"event": event, "state": state}


@dataclass
class TransitionRebalancePlan:
    """What daily rebalance should do for USDC park layer."""

    account_id: str
    run_park: bool = False
    park_summary: Optional[Dict[str, Any]] = None
    run_redeploy_unwind: bool = False
    unwind_summary: Optional[Dict[str, Any]] = None
    transition_note: Optional[str] = None
    operational_phase: str = PHASE_STANDDOWN


def execute_redeploy_unwind_usdc(
    runner: "Phase6Runner",
    park_cfg: Dict[str, Any],
    *,
    account_id: str,
) -> Dict[str, Any]:
    """
    Park→deploy: sell USDC for USD so ARCH-4 / legacy rebalance can deploy alts.
    """
    snap = _portfolio_snapshot(runner)
    target_pct = float(park_cfg.get("redeploy_target_usdc_pct", 0.05))
    min_deploy = float(park_cfg.get("redeploy_min_usd_for_deploy_usd", 80.0))
    nav = snap["nav"]
    if nav <= 0 or snap["usdc"] <= 0:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_usdc_to_unwind",
            "snap": snap,
        }
    excess_usdc = max(0.0, snap["usdc"] - nav * target_pct)
    if excess_usdc < min_deploy:
        return {
            "ok": True,
            "skipped": True,
            "reason": "excess_usdc_below_min",
            "excess_usdc": round(excess_usdc, 2),
        }
    pair = str(park_cfg.get("usdc_product_id", "USDC-USD"))
    try:
        if getattr(runner, "use_platform_executor", False) and getattr(
            runner, "trade_executor", None
        ):
            result = runner.trade_executor.execute_sell(pair, excess_usdc)
        else:
            result = runner.order_executor.execute_sell(pair, excess_usdc)
    except Exception as e:
        result = {"success": False, "error": str(e)}
    runner.portfolio.refresh()
    snap2 = _portfolio_snapshot(runner)
    out = {
        "ok": bool(result.get("success")),
        "reason": "regime_redeploy_unwind",
        "account_id": account_id,
        "unwind_usdc_usd": round(excess_usdc, 2),
        "sell": result,
        "usdc_pct_before": round(snap["usdc_pct"], 4),
        "usdc_pct_after": round(snap2["usdc_pct"], 4),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _save_park_state(account_id, {**out, "phase": PHASE_REDEPLOY})
    logger.info(
        "[USDC-PARK] redeploy unwind $%s USDC ok=%s",
        excess_usdc,
        result.get("success"),
    )
    return out


def plan_usdc_park_for_daily_rebalance(runner: "Phase6Runner") -> TransitionRebalancePlan:
    """
    Evaluate toggle + regime signals and return park / unwind / neither.
    Updates transition state file each call.
    """
    from phase6.core.param_audit import resolve_account_id_from_exchange

    account_id = getattr(runner, "account_id", None) or resolve_account_id_from_exchange(
        runner.exchange
    )
    runner.account_id = account_id
    park_cfg = live_usdc_park_settings(account_id)
    enabled = bool(park_cfg.get("enabled"))
    park_sig = park_signal_active(runner.config_dict)
    deploy_sig = deploy_signal_active(runner.config_dict)

    state = load_transition_state(account_id)
    if "toggle_enabled" not in state:
        state["toggle_enabled"] = enabled
        state["operational_phase"] = PHASE_STANDDOWN if not enabled else PHASE_ARMED
    prev_toggle = bool(state.get("toggle_enabled"))
    prev_park_sig = bool(state.get("last_park_signal"))
    phase = str(state.get("operational_phase") or PHASE_STANDDOWN)

    note = None
    if "toggle_enabled" in state and enabled != prev_toggle:
        rec = record_toggle_change(account_id, enabled)
        note = rec.get("event")
        state = load_transition_state(account_id)
        phase = str(state.get("operational_phase") or phase)

    plan = TransitionRebalancePlan(account_id=account_id, operational_phase=phase)
    plan.transition_note = note

    state["toggle_enabled"] = enabled
    state["last_park_signal"] = park_sig
    state["last_deploy_signal"] = deploy_sig
    shadow = runner.config_dict.get("_analyst_shadow") or {}
    state["last_regime"] = (shadow.get("regime_policy") or {}).get("current_regime")

    if not enabled:
        state["operational_phase"] = PHASE_STANDDOWN
        save_transition_state(account_id, state)
        plan.operational_phase = PHASE_STANDDOWN
        return plan

    # Toggle ON
    regime_flip_to_deploy = prev_park_sig and deploy_sig and not park_sig

    if deploy_sig and (phase == PHASE_PARKED or regime_flip_to_deploy):
        state["operational_phase"] = PHASE_REDEPLOY
        state["last_transition"] = "park_to_redeploy"
        state["park_to_redeploy_at"] = datetime.now(timezone.utc).isoformat()
        save_transition_state(account_id, state)
        plan.run_redeploy_unwind = True
        plan.operational_phase = PHASE_REDEPLOY
        plan.transition_note = plan.transition_note or "park_to_redeploy"
        plan.unwind_summary = execute_redeploy_unwind_usdc(
            runner, park_cfg, account_id=account_id
        )
        if plan.unwind_summary.get("ok"):
            state["operational_phase"] = PHASE_ARMED
            save_transition_state(account_id, state)
        return plan

    if park_sig:
        state["operational_phase"] = PHASE_PARKED
        save_transition_state(account_id, state)
        plan.run_park = True
        plan.operational_phase = PHASE_PARKED
        plan.park_summary = execute_usdc_park_cycle(
            runner, park_cfg, account_id=account_id, reason="regime_usdc_park"
        )
        return plan

    state["operational_phase"] = PHASE_ARMED
    save_transition_state(account_id, state)
    plan.operational_phase = PHASE_ARMED
    return plan


def maybe_run_usdc_park_on_rebalance(runner: "Phase6Runner") -> Optional[Dict[str, Any]]:
    """Backward-compatible: park-only early exit (coordinator uses plan_usdc_park_for_daily_rebalance)."""
    plan = plan_usdc_park_for_daily_rebalance(runner)
    if plan.run_redeploy_unwind:
        return None
    if plan.run_park:
        return plan.park_summary
    return None


def get_transition_status(account_id: str) -> Dict[str, Any]:
    state = load_transition_state(account_id)
    park_cfg = live_usdc_park_settings(account_id)
    return {
        "account_id": account_id,
        "toggle_enabled": park_cfg.get("enabled"),
        "operational_phase": state.get("operational_phase", PHASE_STANDDOWN),
        "last_transition": state.get("last_transition"),
        "last_transition_at": state.get("last_transition_at"),
        "last_regime": state.get("last_regime"),
        "last_park_signal": state.get("last_park_signal"),
        "state_file": str(_transition_path(account_id)),
    }