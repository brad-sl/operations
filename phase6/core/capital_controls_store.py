"""
Per-account capital controls **state** store (hold $ + rebuy cooldown map).

W2 FEAT-TRADER-PERSONALIZED-SETTINGS:
  Policy  → config/trader_accounts.json capital_controls (W1)
  State   → data/state/capital_controls/{account_id}/state.json (this module)
  Legacy  → still mirrors hold/cooldown into phase6_runner_state.json for primary book

Account A state never shares a file with account B.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from phase6.core.paths import STATE_DIR, sanitize_account_id

logger = logging.getLogger(__name__)

CAPITAL_CONTROLS_DIR = STATE_DIR / "capital_controls"
LEGACY_RUNNER_STATE = STATE_DIR / "phase6_runner_state.json"
SCHEMA_VERSION = 1
PRIMARY_UUID = "3176ac3f-deca-4fca-9c67-87ba91f96558"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def account_dir(account_id: str) -> Path:
    d = CAPITAL_CONTROLS_DIR / sanitize_account_id(account_id or "default")
    d.mkdir(parents=True, exist_ok=True)
    return d


def account_state_path(account_id: str) -> Path:
    return account_dir(account_id) / "state.json"


def account_status_path(account_id: str) -> Path:
    return account_dir(account_id) / "capital_user_controls.json"


def account_flag_clear_hold(account_id: str) -> Path:
    return account_dir(account_id) / "clear_manual_cash_hold.flag"


def account_flag_clear_cooldown(account_id: str) -> Path:
    return account_dir(account_id) / "clear_manual_sell_cooldown.flag"


def account_json_clear_cooldown(account_id: str) -> Path:
    return account_dir(account_id) / "clear_manual_sell_cooldown.json"


def empty_state(account_id: str) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "account_id": account_id,
        "manual_liquidation_cash_hold_usd": 0.0,
        "manual_sell_cooldown": {},
        "updated_at": _utc_now(),
    }


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _prune_cooldown(cd: Any) -> Dict[str, float]:
    if not isinstance(cd, dict):
        return {}
    now = datetime.now(timezone.utc).timestamp()
    out: Dict[str, float] = {}
    for p, exp in cd.items():
        try:
            e = float(exp)
        except (TypeError, ValueError):
            continue
        if e > now:
            out[str(p)] = e
    return out


def load_legacy_runner_hold_cooldown(
    runner_state_path: Optional[Path] = None,
) -> Tuple[float, Dict[str, float]]:
    path = Path(runner_state_path or LEGACY_RUNNER_STATE)
    data = _load_json(path)
    hold = float(data.get("manual_liquidation_cash_hold_usd", 0.0) or 0.0)
    cd = _prune_cooldown(data.get("manual_sell_cooldown") or {})
    return hold, cd


def mirror_to_runner_state(
    hold_usd: float,
    cooldown: Dict[str, float],
    runner_state_path: Optional[Path] = None,
) -> None:
    """Keep primary single-book keys in phase6_runner_state.json (compat)."""
    path = Path(runner_state_path or LEGACY_RUNNER_STATE)
    state = _load_json(path)
    state["manual_liquidation_cash_hold_usd"] = round(float(hold_usd or 0.0), 2)
    state["manual_sell_cooldown"] = _prune_cooldown(cooldown)
    _save_json(path, state)


def primary_account_id() -> str:
    env = (
        os.environ.get("COINBASE_PORTFOLIO_UUID")
        or os.environ.get("PHASE6_ACCOUNT_ID")
        or os.environ.get("TRADER_ACCOUNT_ID")
        or ""
    ).strip()
    if env:
        return env
    return PRIMARY_UUID


def should_migrate_from_legacy(account_id: str) -> bool:
    """Migrate/mirror legacy runner state only for the primary book ids."""
    aid = (account_id or "default").strip() or "default"
    env = (
        os.environ.get("COINBASE_PORTFOLIO_UUID")
        or os.environ.get("PHASE6_ACCOUNT_ID")
        or os.environ.get("TRADER_ACCOUNT_ID")
        or ""
    ).strip()
    if aid == PRIMARY_UUID:
        return True
    if env and aid == env:
        return True
    if aid == "brad-primary":
        return True
    # Bare "default" only when no portfolio env is set (dev/paper single-book)
    if aid == "default" and not env:
        return True
    return False


def save_account_capital_state(
    account_id: str,
    state: Dict[str, Any],
    *,
    mirror_legacy: bool = True,
    runner_state_path: Optional[Path] = None,
) -> Dict[str, Any]:
    aid = (account_id or "default").strip() or "default"
    hold = round(float(state.get("manual_liquidation_cash_hold_usd", 0.0) or 0.0), 2)
    cd = _prune_cooldown(state.get("manual_sell_cooldown") or {})
    out = {
        "schema_version": SCHEMA_VERSION,
        "account_id": aid,
        "manual_liquidation_cash_hold_usd": hold,
        "manual_sell_cooldown": cd,
        "updated_at": _utc_now(),
    }
    if state.get("migrated_from"):
        out["migrated_from"] = state["migrated_from"]
    _save_json(account_state_path(aid), out)
    if mirror_legacy and should_migrate_from_legacy(aid):
        try:
            path = Path(runner_state_path) if runner_state_path else LEGACY_RUNNER_STATE
            mirror_to_runner_state(hold, cd, runner_state_path=path)
        except Exception as exc:
            logger.warning("[CAPITAL-STORE] legacy mirror failed: %s", exc)
    return out


def load_account_capital_state(
    account_id: str,
    *,
    migrate_from_runner: bool = True,
    runner_state_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Load per-account hold/cooldown. If store missing and migrate_from_runner,
    seed once from legacy runner state (primary book continuity).
    """
    aid = (account_id or "default").strip() or "default"
    path = account_state_path(aid)
    if path.exists():
        data = _load_json(path)
        st = empty_state(aid)
        st["manual_liquidation_cash_hold_usd"] = round(
            float(data.get("manual_liquidation_cash_hold_usd", 0.0) or 0.0), 2
        )
        st["manual_sell_cooldown"] = _prune_cooldown(data.get("manual_sell_cooldown") or {})
        st["updated_at"] = data.get("updated_at") or _utc_now()
        st["schema_version"] = int(data.get("schema_version") or SCHEMA_VERSION)
        if st["manual_sell_cooldown"] != (data.get("manual_sell_cooldown") or {}):
            save_account_capital_state(aid, st, mirror_legacy=False)
        return st

    st = empty_state(aid)
    if migrate_from_runner:
        hold, cd = load_legacy_runner_hold_cooldown(runner_state_path)
        st["manual_liquidation_cash_hold_usd"] = round(hold, 2)
        st["manual_sell_cooldown"] = cd
        st["updated_at"] = _utc_now()
        st["migrated_from"] = str(runner_state_path or LEGACY_RUNNER_STATE)
        save_account_capital_state(aid, st, mirror_legacy=False)
        logger.info(
            "[CAPITAL-STORE] migrated hold=$%.2f cooldown_n=%d → %s",
            hold,
            len(cd),
            path,
        )
    return st


def resolve_account_id_for_runner(runner: Any = None, explicit: Optional[str] = None) -> str:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    try:
        from phase6.core.trader_account_config import resolve_runner_account_id

        aid = resolve_runner_account_id(runner)
        if aid and aid != "default":
            return aid
    except Exception:
        pass
    # Prefer env / primary UUID over bare default for live book
    env = (
        os.environ.get("COINBASE_PORTFOLIO_UUID")
        or os.environ.get("PHASE6_ACCOUNT_ID")
        or os.environ.get("TRADER_ACCOUNT_ID")
        or ""
    ).strip()
    if env:
        return env
    if runner is not None:
        try:
            from phase6.core.trader_account_config import resolve_runner_account_id as r

            return r(runner)
        except Exception:
            pass
    return primary_account_id()


def load_for_runner(
    runner: Any = None,
    *,
    account_id: Optional[str] = None,
    runner_state_path: Optional[Path] = None,
) -> Dict[str, Any]:
    aid = resolve_account_id_for_runner(runner, account_id)
    path = Path(
        runner_state_path
        or getattr(runner, "state_file", None)
        or LEGACY_RUNNER_STATE
    )
    migrate = should_migrate_from_legacy(aid) and not account_state_path(aid).exists()
    return load_account_capital_state(
        aid,
        migrate_from_runner=migrate,
        runner_state_path=path,
    )


def apply_hold_to_runner(runner: Any, state: Dict[str, Any]) -> None:
    runner._manual_liquidation_cash_hold_usd = float(
        state.get("manual_liquidation_cash_hold_usd", 0.0) or 0.0
    )
    runner._manual_sell_cooldown = dict(state.get("manual_sell_cooldown") or {})
    try:
        cur = getattr(runner, "account_id", None)
        if not cur or not isinstance(cur, str):
            runner.account_id = state.get("account_id")
    except Exception:
        pass


def persist_from_runner(
    runner: Any,
    *,
    account_id: Optional[str] = None,
    runner_state_path: Optional[Path] = None,
) -> Dict[str, Any]:
    aid = resolve_account_id_for_runner(runner, account_id)
    try:
        hold = float(getattr(runner, "_manual_liquidation_cash_hold_usd", 0.0) or 0.0)
    except (TypeError, ValueError):
        hold = 0.0
    cd = getattr(runner, "_manual_sell_cooldown", None) or {}
    if not isinstance(cd, dict):
        cd = {}
    st = {
        "manual_liquidation_cash_hold_usd": hold,
        "manual_sell_cooldown": cd,
    }
    path = Path(
        runner_state_path
        or getattr(runner, "state_file", None)
        or LEGACY_RUNNER_STATE
    )
    return save_account_capital_state(
        aid, st, mirror_legacy=should_migrate_from_legacy(aid), runner_state_path=path
    )
