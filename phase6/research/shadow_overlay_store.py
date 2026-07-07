"""
ANALYST-OPT R4: Shadow trial overlay persistence + git-versioned snapshots.
"""
from __future__ import annotations

import json
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from phase6.core.paths import PROJECT_ROOT
from phase6.research.scenario_knobs import ScenarioKnobs

STATE_PATH = PROJECT_ROOT / "data/state/analyst_shadow_overlay.json"
OVERLAY_DIR = PROJECT_ROOT / "config/shadow_overlays"
BASE_CONFIG = PROJECT_ROOT / "config/trading_config_phase6.json"


def load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"active": False, "history": []}
    with open(STATE_PATH) as f:
        return json.load(f)


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _snapshot_to_git(proposal_id: str, payload: Dict[str, Any]) -> str:
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    path = OVERLAY_DIR / f"{proposal_id}.json"
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return str(path.relative_to(PROJECT_ROOT))


def activate_overlay(
    proposal: Dict[str, Any],
    scenario: Dict[str, Any],
    pack: Optional[Dict[str, Any]],
    *,
    predicted_metrics: Dict[str, Any],
    baseline_equity_usd: float,
    enable_regime_policy: bool = False,
    mode: str = "shadow",
) -> Dict[str, Any]:
    knobs = ScenarioKnobs.from_scenario(scenario, pack)
    proposal_id = proposal["id"]
    state = load_state()
    if state.get("active"):
        raise RuntimeError(
            f"Shadow overlay already active ({state.get('proposal_id')}). Roll back first."
        )

    payload = {
        "active": True,
        "mode": mode,
        "proposal_id": proposal_id,
        "source_run_id": proposal.get("source_run_id"),
        "scenario_id": proposal.get("scenario_id") or scenario.get("id"),
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_equity_usd": round(float(baseline_equity_usd), 2),
        "predicted": predicted_metrics,
        "knobs": knobs.to_arch4_params(),
        "live_overlay": knobs.to_live_config_overlay(),
        "gap_flags": knobs.gap_flags(),
        "regime_policy": {
            "enabled": enable_regime_policy,
            "map_path": "config/regime_knob_map.json",
            "current_regime": None,
            "last_regime_change_at": None,
        },
    }
    snap = _snapshot_to_git(proposal_id, payload)
    payload["config_snapshot_path"] = snap

    if BASE_CONFIG.exists():
        shutil.copy2(BASE_CONFIG, OVERLAY_DIR / f"{proposal_id}_base_config.json")

    state = {
        "active": True,
        **payload,
        "history": (state.get("history") or [])[-20:],
    }
    save_state(state)
    return state


def rollback_overlay(reason: str, *, breach: bool = False) -> Dict[str, Any]:
    state = load_state()
    if not state.get("active"):
        return {"rolled_back": False, "reason": "no active overlay"}

    entry = {
        "proposal_id": state.get("proposal_id"),
        "rolled_back_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "monitor_breach": breach,
    }
    hist = state.get("history") or []
    hist.append(entry)

    new_state = {"active": False, "history": hist[-30:], "last_rollback": entry}
    save_state(new_state)
    return {"rolled_back": True, **entry}