"""Per-trader / per-account configuration (Coinbase portfolio scope)."""
from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from phase6.core.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

TRADER_ACCOUNTS_PATH = PROJECT_ROOT / "config/trader_accounts.json"

# Spec FEAT-TRADER-PERSONALIZED-SETTINGS — policy defaults (amount held is state, not config).
# Match primary live repair book (trading_config_phase6 capital_event_* ) so W1 is behavior-neutral.
DEFAULT_CAPITAL_CONTROLS: Dict[str, Any] = {
    "manual_sell_hold_cash": True,
    "manual_sell_block_rebuy_hours": 48.0,
    "stop_loss_exchange_hold_cash": True,
    "stop_loss_exchange_block_rebuy_hours": 72.0,
    "manual_sell_cancel_stops": True,
    "ui_show_hold_banner": True,
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_trader_accounts_file() -> Dict[str, Any]:
    if not TRADER_ACCOUNTS_PATH.exists():
        return {"defaults": {}, "accounts": {}}
    try:
        return json.loads(TRADER_ACCOUNTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("trader_accounts.json unreadable: %s", e)
        return {"defaults": {}, "accounts": {}}


def resolve_account_config(account_id: str) -> Dict[str, Any]:
    """Merge defaults + account-specific trader options."""
    raw = load_trader_accounts_file()
    defaults = raw.get("defaults") or {}
    accounts = raw.get("accounts") or {}
    acct = accounts.get(account_id) or accounts.get("default") or {}
    merged = _deep_merge(defaults, acct)
    merged["account_id"] = account_id
    return merged


def resolve_runner_account_id(runner: Any = None) -> str:
    """Best-effort Coinbase portfolio / trader account id for policy lookup."""

    def _clean(v: Any) -> Optional[str]:
        if v is None or isinstance(v, bool):
            return None
        if not isinstance(v, (str, int, float)):
            return None
        s = str(v).strip()
        if not s or s.startswith("<MagicMock"):
            return None
        return s

    if runner is not None:
        for attr in (
            "portfolio_uuid",
            "coinbase_portfolio_uuid",
            "account_id",
            "trader_account_id",
        ):
            s = _clean(getattr(runner, attr, None))
            if not s:
                continue
            if s == "brad-primary":
                # legacy label — prefer env / portfolio uuid below
                break
            return s
    env = (
        os.environ.get("COINBASE_PORTFOLIO_UUID")
        or os.environ.get("PHASE6_ACCOUNT_ID")
        or os.environ.get("TRADER_ACCOUNT_ID")
    )
    if env and str(env).strip():
        return str(env).strip()
    if runner is not None:
        s = _clean(getattr(runner, "account_id", None))
        if s:
            return s
    return "default"


def capital_controls_settings(account_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Per-account capital *policy* (not current hold $).

    See docs/features/TRADER_PERSONALIZED_SETTINGS_SPEC.md §3.
    Missing keys fall back to DEFAULT_CAPITAL_CONTROLS.
    """
    aid = (account_id or "default").strip() or "default"
    cfg = resolve_account_config(aid)
    raw = dict(cfg.get("capital_controls") or {})
    out = dict(DEFAULT_CAPITAL_CONTROLS)
    for k, default in DEFAULT_CAPITAL_CONTROLS.items():
        if k not in raw:
            continue
        v = raw[k]
        if isinstance(default, bool):
            out[k] = bool(v)
        elif isinstance(default, float):
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = default
        else:
            out[k] = v
    out["account_id"] = aid
    out["source"] = "trader_accounts.capital_controls"
    return out


def capital_controls_for_runner(runner: Any = None) -> Dict[str, Any]:
    return capital_controls_settings(resolve_runner_account_id(runner))


def live_usdc_park_settings(account_id: str) -> Dict[str, Any]:
    cfg = resolve_account_config(account_id)
    park = dict(cfg.get("live_usdc_park") or {})
    park.setdefault("enabled", False)
    park.setdefault("target_usdc_pct", 0.92)
    park.setdefault("min_usd_reserve_usd", 50.0)
    park.setdefault("usdc_product_id", "USDC-USD")
    park.setdefault("min_sell_usd", 15.0)
    park.setdefault("skip_if_usdc_pct_above", 0.88)
    return park


def set_live_usdc_park_enabled(account_id: str, enabled: bool) -> Dict[str, Any]:
    """Persist toggle for one account (creates entry if missing)."""
    raw = load_trader_accounts_file()
    accounts = raw.setdefault("accounts", {})
    entry = accounts.setdefault(account_id, {"trader_id": "default"})
    park = entry.setdefault("live_usdc_park", {})
    park["enabled"] = bool(enabled)
    TRADER_ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRADER_ACCOUNTS_PATH.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    from phase6.core.usdc_park_transitions import record_toggle_change

    record_toggle_change(account_id, bool(enabled))
    return live_usdc_park_settings(account_id)