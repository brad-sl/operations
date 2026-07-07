"""
Apply ANALYST-OPT shadow overlay + optional regime-adaptive knob swap to runner config dict.

Does not write trading_config_phase6.json on disk — in-memory merge only (safe rollback).
"""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from phase6.core.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

OVERLAY_STATE = PROJECT_ROOT / "data/state/analyst_shadow_overlay.json"


def _set_nested(d: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = d
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value


def load_overlay_state() -> Dict[str, Any]:
    if not OVERLAY_STATE.exists():
        return {"active": False}
    with open(OVERLAY_STATE) as f:
        return json.load(f)


def apply_regime_knobs(overlay: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """If regime policy enabled, pick scenario knobs for detected regime."""
    policy = overlay.get("regime_policy") or {}
    if not policy.get("enabled"):
        return overlay

    from phase6.research.regime_detector import detect_regime

    det = detect_regime()
    regime = det.get("regime", "unknown")
    config.setdefault("_analyst_shadow", {})["_regime_detection"] = det

    map_path = PROJECT_ROOT / policy.get("map_path", "config/regime_knob_map.json")
    if not map_path.exists():
        return overlay

    with open(map_path) as f:
        knob_map = json.load(f)
    entry = (knob_map.get("regimes") or {}).get(regime)
    if not entry:
        return overlay

    prev = overlay.get("regime_policy", {}).get("current_regime")
    if prev and prev != regime:
        logger.info("[shadow] regime shift %s -> %s; swapping knobs", prev, regime)
        overlay = deepcopy(overlay)
        overlay.setdefault("regime_policy", {})["current_regime"] = regime
        overlay["regime_policy"]["last_regime_change_at"] = det.get("as_of")
        if entry.get("live_overlay"):
            overlay["live_overlay"] = entry["live_overlay"]
        if entry.get("arch4_params"):
            overlay["knobs"] = {**(overlay.get("knobs") or {}), **entry["arch4_params"]}
        overlay["scenario_id"] = entry.get("scenario_id", overlay.get("scenario_id"))
    elif not prev:
        overlay = deepcopy(overlay)
        overlay.setdefault("regime_policy", {})["current_regime"] = regime

    return overlay


def _persist_regime_if_changed(before: Dict[str, Any], after: Dict[str, Any]) -> None:
    bp = (before.get("regime_policy") or {}).get("current_regime")
    ap = (after.get("regime_policy") or {}).get("current_regime")
    if ap and ap != bp:
        merged = {**before, **{k: after[k] for k in ("regime_policy", "live_overlay", "knobs", "scenario_id") if k in after}}
        merged["active"] = True
        try:
            with open(OVERLAY_STATE, "w") as f:
                json.dump(merged, f, indent=2)
        except OSError as e:
            logger.warning("failed to persist regime swap: %s", e)


def apply_analyst_overlays(config: Dict[str, Any]) -> Dict[str, Any]:
    state = load_overlay_state()
    if not state.get("active"):
        return config

    cfg = deepcopy(config)
    overlay = apply_regime_knobs(state, cfg)
    _persist_regime_if_changed(state, overlay)

    for key, val in (overlay.get("live_overlay") or {}).items():
        _set_nested(cfg, key, val)

    meta = overlay.get("knobs") or {}
    cfg.setdefault("_analyst_shadow", {})
    cfg["_analyst_shadow"].update(
        {
            "active": True,
            "proposal_id": overlay.get("proposal_id"),
            "source_run_id": overlay.get("source_run_id"),
            "scenario_id": overlay.get("scenario_id"),
            "mode": overlay.get("mode", "shadow"),
            "allocator_strategy": meta.get("use_rotation", True) and "rotation" or "rebalance",
            "arch4_params": meta,
        }
    )
    if overlay.get("regime_policy", {}).get("enabled"):
        cfg["_analyst_shadow"]["regime_policy"] = overlay["regime_policy"]

    return cfg


def shadow_params_from_overlay() -> Dict[str, Any]:
    """IDEALOOP-005 compatible shadow_params for runner."""
    state = load_overlay_state()
    if not state.get("active"):
        return {}
    knobs = state.get("knobs") or {}
    return {
        "analyst_shadow": True,
        "scenario_id": state.get("scenario_id"),
        "proposal_id": state.get("proposal_id"),
        "rebalance_cap_usd": (state.get("live_overlay") or {}).get(
            "global_settings.rebalance_cap_usd"
        ),
        "use_rotation": knobs.get("use_rotation", True),
    }