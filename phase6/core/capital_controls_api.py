"""
Capital controls service API (no HTTP). Dashboard + CLI call these.

Endpoints (served by serve_dashboard.py):
  GET  /api/capital/controls?account_id=
  POST /api/capital/clear-cash-hold   body: {account_id?, source?}
  POST /api/capital/clear-cooldown   body: {account_id?, all?, pairs?, source?}
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from phase6.core import capital_controls_store as store
from phase6.core.capital_controls import (
    FLAG_CLEAR_CASH_HOLD,
    FLAG_CLEAR_COOLDOWN,
    JSON_CLEAR_COOLDOWN,
    _append_control_audit,
)
from phase6.core.paths import STATE_DIR
from phase6.core.trader_account_config import capital_controls_settings

logger = logging.getLogger(__name__)

LEGACY_STATUS = STATE_DIR / "capital_user_controls.json"


def _default_aid(account_id: Optional[str] = None) -> str:
    from phase6.core.capital_controls_store import primary_account_id

    return (account_id or primary_account_id()).strip() or primary_account_id()



def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _ShimRunner:
    def __init__(self, account_id: str, state_file: Optional[str] = None):
        self.account_id = account_id
        self.state_file = state_file or str(store.LEGACY_RUNNER_STATE)
        self._manual_liquidation_cash_hold_usd = 0.0
        self._manual_sell_cooldown: Dict[str, float] = {}


def get_capital_controls_status(
    account_id: Optional[str] = None,
    *,
    pending_actions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    from phase6.core.capital_controls_store import primary_account_id

    aid = (account_id or primary_account_id()).strip() or primary_account_id()
    migrate = store.should_migrate_from_legacy(aid) and not store.account_state_path(aid).exists()
    st = store.load_account_capital_state(aid, migrate_from_runner=migrate)
    hold = float(st.get("manual_liquidation_cash_hold_usd", 0.0) or 0.0)
    cd = st.get("manual_sell_cooldown") or {}
    now = datetime.now(timezone.utc).timestamp()
    active_cd: Dict[str, str] = {}
    for pair, exp in (cd.items() if isinstance(cd, dict) else []):
        try:
            if float(exp) > now:
                active_cd[str(pair)] = datetime.fromtimestamp(
                    float(exp), tz=timezone.utc
                ).isoformat()
        except (TypeError, ValueError):
            continue

    try:
        policy = capital_controls_settings(aid)
    except Exception:
        policy = {}

    status = {
        "schema_version": 2,
        "account_id": aid,
        "updated_at": _utc_now(),
        "manual_liquidation_cash_hold_usd": round(hold, 2),
        "manual_sell_cooldown_active": active_cd,
        "capital_controls_policy": policy,
        "state_path": str(store.account_state_path(aid)),
        "flag_files": {
            "clear_manual_cash_hold": str(store.account_flag_clear_hold(aid)),
            "clear_manual_sell_cooldown_all": str(store.account_flag_clear_cooldown(aid)),
            "clear_manual_sell_cooldown_selective": str(store.account_json_clear_cooldown(aid)),
            "legacy_clear_manual_cash_hold": str(FLAG_CLEAR_CASH_HOLD),
        },
        "ui_actions": {
            "clear_cash_hold": {
                "enabled": hold > 0,
                "label": "Release cash hold (allow deployment)",
                "api_path": "/api/capital/clear-cash-hold",
                "api_action": "clear_manual_cash_hold",
                "method": "POST",
            },
            "clear_rebuy_cooldown_all": {
                "enabled": len(active_cd) > 0,
                "label": "Clear all manual-sell rebuy blocks",
                "api_path": "/api/capital/clear-cooldown",
                "api_action": "clear_manual_sell_cooldown",
                "method": "POST",
                "params": {"all": True},
            },
            "clear_rebuy_cooldown_pair": {
                "enabled": len(active_cd) > 0,
                "label": "Clear rebuy block for selected pair(s)",
                "api_path": "/api/capital/clear-cooldown",
                "api_action": "clear_manual_sell_cooldown",
                "method": "POST",
                "params": {"pairs": ["<PAIR-USD>"]},
            },
        },
        "recent_control_actions": pending_actions or [],
    }

    # Persist per-account + legacy primary mirror of status
    try:
        p = store.account_status_path(aid)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        if store.should_migrate_from_legacy(aid):
            LEGACY_STATUS.parent.mkdir(parents=True, exist_ok=True)
            LEGACY_STATUS.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        logger.debug("status write skip: %s", exc)
    return status


def api_clear_cash_hold(
    account_id: Optional[str] = None,
    *,
    source: str = "api",
) -> Dict[str, Any]:
    aid = _default_aid(account_id)
    migrate = store.should_migrate_from_legacy(aid) and not store.account_state_path(aid).exists()
    st = store.load_account_capital_state(aid, migrate_from_runner=migrate)
    prev = float(st.get("manual_liquidation_cash_hold_usd", 0.0) or 0.0)
    st["manual_liquidation_cash_hold_usd"] = 0.0
    mirror = store.should_migrate_from_legacy(aid)
    store.save_account_capital_state(aid, st, mirror_legacy=mirror)
    result = {
        "action": "clear_manual_cash_hold",
        "account_id": aid,
        "cleared_usd": round(prev, 2),
        "source": source,
        "ts": _utc_now(),
    }
    logger.warning(
        "[CAPITAL-CONTROL] cleared manual cash hold $%.2f account=%s source=%s",
        prev,
        aid,
        source,
    )
    _append_control_audit(result)
    get_capital_controls_status(aid, pending_actions=[result])
    return result


def api_clear_cooldown(
    account_id: Optional[str] = None,
    *,
    pairs: Optional[List[str]] = None,
    clear_all: bool = False,
    source: str = "api",
) -> Dict[str, Any]:
    aid = _default_aid(account_id)
    migrate = store.should_migrate_from_legacy(aid) and not store.account_state_path(aid).exists()
    st = store.load_account_capital_state(aid, migrate_from_runner=migrate)
    cd = dict(st.get("manual_sell_cooldown") or {})
    removed: List[str] = []
    if clear_all or not pairs:
        removed = list(cd.keys())
        cd = {}
    else:
        for p in pairs:
            if p in cd:
                removed.append(p)
                del cd[p]
    st["manual_sell_cooldown"] = cd
    mirror = store.should_migrate_from_legacy(aid)
    store.save_account_capital_state(aid, st, mirror_legacy=mirror)
    result = {
        "action": "clear_manual_sell_cooldown",
        "account_id": aid,
        "pairs_cleared": removed,
        "clear_all": clear_all or not pairs,
        "source": source,
        "ts": _utc_now(),
    }
    logger.warning(
        "[CAPITAL-CONTROL] cleared cooldown pairs=%s account=%s source=%s",
        removed or "(none)",
        aid,
        source,
    )
    _append_control_audit(result)
    get_capital_controls_status(aid, pending_actions=[result])
    return result


def api_request_clear_cash_hold(account_id: Optional[str] = None) -> Dict[str, Any]:
    """Touch flag consumed by runner next cycle (account-scoped + legacy for primary)."""
    aid = _default_aid(account_id)
    f = store.account_flag_clear_hold(aid)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.touch()
    if store.should_migrate_from_legacy(aid):
        FLAG_CLEAR_CASH_HOLD.parent.mkdir(parents=True, exist_ok=True)
        FLAG_CLEAR_CASH_HOLD.touch()
    return {"ok": True, "flag": str(f), "account_id": aid}


def api_request_clear_cooldown(
    account_id: Optional[str] = None,
    *,
    pairs: Optional[List[str]] = None,
    clear_all: bool = False,
) -> Dict[str, Any]:
    aid = _default_aid(account_id)
    if clear_all or not pairs:
        f = store.account_flag_clear_cooldown(aid)
        f.touch()
        if store.should_migrate_from_legacy(aid):
            FLAG_CLEAR_COOLDOWN.touch()
        return {"ok": True, "flag": str(f), "account_id": aid, "all": True}
    j = store.account_json_clear_cooldown(aid)
    j.write_text(json.dumps({"pairs": list(pairs)}), encoding="utf-8")
    if store.should_migrate_from_legacy(aid):
        JSON_CLEAR_COOLDOWN.write_text(json.dumps({"pairs": list(pairs)}), encoding="utf-8")
    return {"ok": True, "json": str(j), "account_id": aid, "pairs": list(pairs)}
