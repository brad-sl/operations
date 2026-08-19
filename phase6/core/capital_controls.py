"""
User-operable capital / manual-trade controls.

Designed for CLI flag files today and dashboard UI tomorrow.

Flag files (touch or write JSON, consumed on next runner cycle):
  data/state/clear_manual_cash_hold.flag
      → release cash hold from manual liquidation (allow bot deploy again)

  data/state/clear_manual_sell_cooldown.flag
      → clear all manual-sell rebuy cooldowns

  data/state/clear_manual_sell_cooldown.json
      → selective clear, e.g. {"pairs": ["OP-USD"]} or {"all": true}

  Per-account (W2):
  data/state/capital_controls/{account_id}/clear_manual_cash_hold.flag
  data/state/capital_controls/{account_id}/clear_manual_sell_cooldown.flag
  data/state/capital_controls/{account_id}/clear_manual_sell_cooldown.json

Read model for UI:
  data/state/capital_user_controls.json  (primary mirror)
  data/state/capital_controls/{account_id}/capital_user_controls.json
  GET /api/capital/controls
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STATE_DIR = Path("data/state")
FLAG_CLEAR_CASH_HOLD = STATE_DIR / "clear_manual_cash_hold.flag"
FLAG_CLEAR_COOLDOWN = STATE_DIR / "clear_manual_sell_cooldown.flag"
JSON_CLEAR_COOLDOWN = STATE_DIR / "clear_manual_sell_cooldown.json"
CONTROLS_STATUS_JSON = STATE_DIR / "capital_user_controls.json"
DEFAULT_STATE_FILE = STATE_DIR / "phase6_runner_state.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_runner_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_runner_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def _account_id(runner: Any = None, explicit: Optional[str] = None) -> str:
    from phase6.core.capital_controls_store import resolve_account_id_for_runner

    return resolve_account_id_for_runner(runner, explicit)


def hydrate_manual_controls_from_state(runner: Any, state_file: Optional[str] = None) -> None:
    """Restore in-memory hold + rebuy cooldown from per-account store (+ legacy mirror)."""
    from phase6.core import capital_controls_store as store

    path = Path(state_file or getattr(runner, "state_file", None) or DEFAULT_STATE_FILE)
    st = store.load_for_runner(runner, runner_state_path=path)
    store.apply_hold_to_runner(runner, st)
    # Ensure legacy runner state keys match (primary continuity)
    if store.should_migrate_from_legacy(st.get("account_id") or "default"):
        try:
            store.mirror_to_runner_state(
                float(st.get("manual_liquidation_cash_hold_usd", 0) or 0),
                dict(st.get("manual_sell_cooldown") or {}),
                runner_state_path=path,
            )
        except Exception:
            pass


def persist_manual_cash_hold(runner: Any, state_file: Optional[str] = None) -> None:
    from phase6.core import capital_controls_store as store

    path = Path(state_file or getattr(runner, "state_file", None) or DEFAULT_STATE_FILE)
    store.persist_from_runner(runner, runner_state_path=path)


def persist_manual_sell_cooldown(runner: Any, state_file: Optional[str] = None) -> None:
    """Write runner._manual_sell_cooldown to durable per-account + legacy state."""
    from phase6.core import capital_controls_store as store

    path = Path(state_file or getattr(runner, "state_file", None) or DEFAULT_STATE_FILE)
    cd = getattr(runner, "_manual_sell_cooldown", None) or {}
    if not isinstance(cd, dict):
        cd = {}
    now = datetime.now(timezone.utc).timestamp()
    active = {p: float(exp) for p, exp in cd.items() if float(exp) > now}
    runner._manual_sell_cooldown = active
    store.persist_from_runner(runner, runner_state_path=path)


def clear_manual_cash_hold(
    runner: Any,
    *,
    state_file: Optional[str] = None,
    source: str = "user",
    account_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Release deploy hold; does not move funds on exchange."""
    from phase6.core.capital_controls_api import api_clear_cash_hold
    from phase6.core import capital_controls_store as store

    aid = account_id or _account_id(runner)
    # Prefer runner in-memory if already hydrated for this account
    if runner is not None and getattr(runner, "_manual_liquidation_cash_hold_usd", None) is not None:
        prev = float(getattr(runner, "_manual_liquidation_cash_hold_usd", 0.0) or 0.0)
        runner._manual_liquidation_cash_hold_usd = 0.0
        path = Path(state_file or getattr(runner, "state_file", None) or DEFAULT_STATE_FILE)
        store.persist_from_runner(runner, account_id=aid, runner_state_path=path)
        result = {
            "action": "clear_manual_cash_hold",
            "account_id": aid,
            "cleared_usd": round(prev, 2),
            "source": source,
            "ts": _utc_now(),
        }
        logger.warning(
            "[CAPITAL-CONTROL] cleared manual cash hold $%.2f (source=%s account=%s)",
            prev,
            source,
            aid,
        )
        _append_control_audit(result)
        return result
    return api_clear_cash_hold(aid, source=source)


def clear_manual_sell_cooldown(
    runner: Any,
    *,
    pairs: Optional[List[str]] = None,
    clear_all: bool = False,
    state_file: Optional[str] = None,
    source: str = "user",
    account_id: Optional[str] = None,
) -> Dict[str, Any]:
    from phase6.core import capital_controls_store as store

    aid = account_id or _account_id(runner)
    path = Path(state_file or getattr(runner, "state_file", None) or DEFAULT_STATE_FILE)
    # Prefer account store as SSOT
    migrate = store.should_migrate_from_legacy(aid) and not store.account_state_path(aid).exists()
    st = store.load_account_capital_state(
        aid, migrate_from_runner=migrate, runner_state_path=path
    )
    cd = dict(st.get("manual_sell_cooldown") or {})
    # merge runner memory if present
    mem = getattr(runner, "_manual_sell_cooldown", None) or {}
    if isinstance(mem, dict):
        for k, v in mem.items():
            cd[str(k)] = float(v)

    removed: List[str] = []
    if clear_all or pairs is None:
        removed = list(cd.keys())
        cd = {}
    else:
        for p in pairs:
            if p in cd:
                removed.append(p)
                del cd[p]
    st["manual_sell_cooldown"] = cd
    mirror = store.should_migrate_from_legacy(aid)
    store.save_account_capital_state(aid, st, mirror_legacy=mirror, runner_state_path=path)
    if runner is not None:
        runner._manual_sell_cooldown = cd
    result = {
        "action": "clear_manual_sell_cooldown",
        "account_id": aid,
        "pairs_cleared": removed,
        "clear_all": clear_all or pairs is None,
        "source": source,
        "ts": _utc_now(),
    }
    logger.warning(
        "[CAPITAL-CONTROL] cleared manual sell cooldown pairs=%s (source=%s account=%s)",
        removed or "(none)",
        source,
        aid,
    )
    _append_control_audit(result)
    return result


def _append_control_audit(record: Dict[str, Any]) -> None:
    audit = STATE_DIR / "capital_control_actions.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _consume_flag(path: Path) -> bool:
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass
        return True
    return False


def process_capital_control_flags(runner: Any, state_file: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Consume one-shot flag files. Call each runner cycle (before rebalance).
    Returns list of actions taken this cycle.
    """
    from phase6.core import capital_controls_store as store

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    hydrate_manual_controls_from_state(runner, state_file=state_file)
    actions: List[Dict[str, Any]] = []
    aid = _account_id(runner)

    # Account-scoped flags first
    if _consume_flag(store.account_flag_clear_hold(aid)):
        actions.append(
            clear_manual_cash_hold(runner, state_file=state_file, source="flag_file_account")
        )
    elif _consume_flag(FLAG_CLEAR_CASH_HOLD):
        actions.append(clear_manual_cash_hold(runner, state_file=state_file, source="flag_file"))

    acct_json = store.account_json_clear_cooldown(aid)
    if acct_json.exists():
        try:
            spec = json.loads(acct_json.read_text())
            acct_json.unlink()
            pairs = spec.get("pairs")
            clear_all = bool(spec.get("all"))
            if clear_all:
                actions.append(
                    clear_manual_sell_cooldown(
                        runner, clear_all=True, state_file=state_file, source="json_flag_account"
                    )
                )
            elif pairs:
                actions.append(
                    clear_manual_sell_cooldown(
                        runner,
                        pairs=[str(p) for p in pairs],
                        state_file=state_file,
                        source="json_flag_account",
                    )
                )
        except Exception as exc:
            logger.error("[CAPITAL-CONTROL] failed to parse %s: %s", acct_json, exc)
            try:
                acct_json.unlink()
            except Exception:
                pass
    elif _consume_flag(store.account_flag_clear_cooldown(aid)):
        actions.append(
            clear_manual_sell_cooldown(
                runner, clear_all=True, state_file=state_file, source="flag_file_account"
            )
        )
    elif JSON_CLEAR_COOLDOWN.exists():
        try:
            spec = json.loads(JSON_CLEAR_COOLDOWN.read_text())
            JSON_CLEAR_COOLDOWN.unlink()
            pairs = spec.get("pairs")
            clear_all = bool(spec.get("all"))
            if clear_all:
                actions.append(
                    clear_manual_sell_cooldown(
                        runner, clear_all=True, state_file=state_file, source="json_flag"
                    )
                )
            elif pairs:
                actions.append(
                    clear_manual_sell_cooldown(
                        runner, pairs=[str(p) for p in pairs], state_file=state_file, source="json_flag"
                    )
                )
        except Exception as exc:
            logger.error("[CAPITAL-CONTROL] failed to parse %s: %s", JSON_CLEAR_COOLDOWN, exc)
            try:
                JSON_CLEAR_COOLDOWN.unlink()
            except Exception:
                pass
    elif _consume_flag(FLAG_CLEAR_COOLDOWN):
        actions.append(
            clear_manual_sell_cooldown(runner, clear_all=True, state_file=state_file, source="flag_file")
        )

    write_controls_status(runner, state_file=state_file, pending_actions=actions)
    return actions


def write_controls_status(
    runner: Any,
    *,
    state_file: Optional[str] = None,
    pending_actions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """UI/dashboard read model — safe to poll."""
    from phase6.core.capital_controls_api import get_capital_controls_status

    aid = _account_id(runner)
    # Sync runner memory into store before status
    try:
        from phase6.core import capital_controls_store as store

        path = Path(state_file or getattr(runner, "state_file", None) or DEFAULT_STATE_FILE)
        store.persist_from_runner(runner, account_id=aid, runner_state_path=path)
    except Exception:
        pass
    return get_capital_controls_status(aid, pending_actions=pending_actions)


def get_controls_status_for_ui(
    state_file: Optional[str] = None,
    account_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Read-only status without a live runner (CLI / dashboard cold start)."""
    from phase6.core.capital_controls_api import get_capital_controls_status

    return get_capital_controls_status(account_id)
