#!/usr/bin/env python3
"""Isolation: per-account capital_controls policy (personalized settings W1)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import phase6.core.trader_account_config as tac
from phase6.core.runner_capital_events import _runner_capital_settings


def _write_accounts(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_defaults_and_account_override():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "trader_accounts.json"
        _write_accounts(
            p,
            {
                "defaults": {
                    "capital_controls": {
                        "manual_sell_hold_cash": True,
                        "manual_sell_block_rebuy_hours": 48,
                        "stop_loss_exchange_hold_cash": True,
                        "stop_loss_exchange_block_rebuy_hours": 72,
                    }
                },
                "accounts": {
                    "acct-a": {
                        "capital_controls": {
                            "manual_sell_hold_cash": False,
                            "manual_sell_block_rebuy_hours": 12,
                        }
                    },
                    "acct-b": {
                        "capital_controls": {
                            "stop_loss_exchange_hold_cash": False,
                            "stop_loss_exchange_block_rebuy_hours": 24,
                        }
                    },
                },
            },
        )
        old = tac.TRADER_ACCOUNTS_PATH
        tac.TRADER_ACCOUNTS_PATH = p
        try:
            a = tac.capital_controls_settings("acct-a")
            assert a["manual_sell_hold_cash"] is False
            assert a["manual_sell_block_rebuy_hours"] == 12.0
            # inherited from defaults
            assert a["stop_loss_exchange_hold_cash"] is True
            assert a["stop_loss_exchange_block_rebuy_hours"] == 72.0

            b = tac.capital_controls_settings("acct-b")
            assert b["manual_sell_hold_cash"] is True
            assert b["stop_loss_exchange_hold_cash"] is False
            assert b["stop_loss_exchange_block_rebuy_hours"] == 24.0

            # no bleed: A still false hold
            a2 = tac.capital_controls_settings("acct-a")
            assert a2["manual_sell_hold_cash"] is False
            print("PASS defaults_and_account_override")
        finally:
            tac.TRADER_ACCOUNTS_PATH = old


def test_runner_settings_overlay_beats_global_settings():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "trader_accounts.json"
        _write_accounts(
            p,
            {
                "defaults": {
                    "capital_controls": {
                        "manual_sell_hold_cash": True,
                        "manual_sell_block_rebuy_hours": 48,
                        "stop_loss_exchange_hold_cash": True,
                        "stop_loss_exchange_block_rebuy_hours": 72,
                    }
                },
                "accounts": {
                    "paper-uuid": {
                        "capital_controls": {
                            "manual_sell_hold_cash": False,
                            "stop_loss_exchange_block_rebuy_hours": 6,
                        }
                    }
                },
            },
        )
        old = tac.TRADER_ACCOUNTS_PATH
        tac.TRADER_ACCOUNTS_PATH = p
        try:
            runner = MagicMock()
            runner.account_id = "paper-uuid"
            runner.config_dict = {
                "global_settings": {
                    "capital_event_manual_sell_hold_cash": True,
                    "capital_event_manual_sell_block_rebuy_hours": 48,
                    "capital_event_stop_loss_exchange_hold_cash": True,
                    "capital_event_stop_loss_exchange_block_rebuy_hours": 72,
                    "capital_event_force_rebalance": False,
                }
            }
            s = _runner_capital_settings(runner)
            assert s["manual_sell_hold_cash"] is False
            assert s["stop_loss_exchange_block_rebuy_hours"] == 6.0
            assert s["capital_controls_account_id"] == "paper-uuid"
            assert s["force_rebalance"] is False  # still from global
            print("PASS runner_settings_overlay")
        finally:
            tac.TRADER_ACCOUNTS_PATH = old


def test_missing_file_safe_defaults():
    with tempfile.TemporaryDirectory() as td:
        old = tac.TRADER_ACCOUNTS_PATH
        tac.TRADER_ACCOUNTS_PATH = Path(td) / "missing.json"
        try:
            d = tac.capital_controls_settings("nobody")
            assert d["manual_sell_hold_cash"] is True
            assert d["stop_loss_exchange_block_rebuy_hours"] == 72.0
            print("PASS missing_file_safe_defaults")
        finally:
            tac.TRADER_ACCOUNTS_PATH = old


if __name__ == "__main__":
    test_defaults_and_account_override()
    test_runner_settings_overlay_beats_global_settings()
    test_missing_file_safe_defaults()
    print("ALL PASS")
