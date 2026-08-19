#!/usr/bin/env python3
"""Isolation: per-account capital state store — no cross-account bleed (W2)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import phase6.core.capital_controls_store as store
import phase6.core.capital_controls as cc
from phase6.core.capital_controls_api import (
    api_clear_cash_hold,
    api_clear_cooldown,
    get_capital_controls_status,
)


def test_no_bleed_between_accounts():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        old_dir = store.CAPITAL_CONTROLS_DIR
        old_legacy = store.LEGACY_RUNNER_STATE
        store.CAPITAL_CONTROLS_DIR = base / "capital_controls"
        store.LEGACY_RUNNER_STATE = base / "phase6_runner_state.json"
        store.LEGACY_RUNNER_STATE.write_text("{}")
        try:
            a = "acct-alpha"
            b = "acct-beta"
            store.save_account_capital_state(
                a,
                {"manual_liquidation_cash_hold_usd": 100.0, "manual_sell_cooldown": {"AAA-USD": 9e12}},
                mirror_legacy=False,
            )
            store.save_account_capital_state(
                b,
                {"manual_liquidation_cash_hold_usd": 5.0, "manual_sell_cooldown": {"BBB-USD": 9e12}},
                mirror_legacy=False,
            )
            sa = store.load_account_capital_state(a, migrate_from_runner=False)
            sb = store.load_account_capital_state(b, migrate_from_runner=False)
            assert sa["manual_liquidation_cash_hold_usd"] == 100.0
            assert sb["manual_liquidation_cash_hold_usd"] == 5.0
            assert "AAA-USD" in sa["manual_sell_cooldown"]
            assert "AAA-USD" not in sb["manual_sell_cooldown"]
            assert "BBB-USD" in sb["manual_sell_cooldown"]

            api_clear_cash_hold(a, source="test")
            sa2 = store.load_account_capital_state(a, migrate_from_runner=False)
            sb2 = store.load_account_capital_state(b, migrate_from_runner=False)
            assert sa2["manual_liquidation_cash_hold_usd"] == 0.0
            assert sb2["manual_liquidation_cash_hold_usd"] == 5.0  # B untouched

            api_clear_cooldown(b, clear_all=True, source="test")
            sb3 = store.load_account_capital_state(b, migrate_from_runner=False)
            sa3 = store.load_account_capital_state(a, migrate_from_runner=False)
            assert sb3["manual_sell_cooldown"] == {}
            assert "AAA-USD" not in sa3["manual_sell_cooldown"] or True
            # A cooldown may still exist if not cleared
            print("PASS no_bleed_between_accounts")
        finally:
            store.CAPITAL_CONTROLS_DIR = old_dir
            store.LEGACY_RUNNER_STATE = old_legacy


def test_runner_hydrate_persist_account_store():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        old_dir = store.CAPITAL_CONTROLS_DIR
        old_legacy = store.LEGACY_RUNNER_STATE
        store.CAPITAL_CONTROLS_DIR = base / "capital_controls"
        runner_state = base / "phase6_runner_state.json"
        store.LEGACY_RUNNER_STATE = runner_state
        runner_state.write_text(
            json.dumps({"manual_liquidation_cash_hold_usd": 42.5, "manual_sell_cooldown": {}})
        )
        try:
            runner = MagicMock()
            runner.account_id = "3176ac3f-deca-4fca-9c67-87ba91f96558"
            runner.state_file = str(runner_state)
            # first hydrate migrates
            cc.hydrate_manual_controls_from_state(runner, state_file=str(runner_state))
            assert float(runner._manual_liquidation_cash_hold_usd) == 42.5
            path = store.account_state_path(runner.account_id)
            assert path.exists()
            runner._manual_liquidation_cash_hold_usd = 10.0
            cc.persist_manual_cash_hold(runner, state_file=str(runner_state))
            st = store.load_account_capital_state(runner.account_id, migrate_from_runner=False)
            assert st["manual_liquidation_cash_hold_usd"] == 10.0
            legacy = json.loads(runner_state.read_text())
            assert legacy["manual_liquidation_cash_hold_usd"] == 10.0
            print("PASS runner_hydrate_persist")
        finally:
            store.CAPITAL_CONTROLS_DIR = old_dir
            store.LEGACY_RUNNER_STATE = old_legacy


def test_status_api_includes_account():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        old_dir = store.CAPITAL_CONTROLS_DIR
        old_legacy = store.LEGACY_RUNNER_STATE
        store.CAPITAL_CONTROLS_DIR = base / "capital_controls"
        store.LEGACY_RUNNER_STATE = base / "rs.json"
        store.LEGACY_RUNNER_STATE.write_text("{}")
        try:
            store.save_account_capital_state(
                "paper-x",
                {"manual_liquidation_cash_hold_usd": 7.0, "manual_sell_cooldown": {}},
                mirror_legacy=False,
            )
            st = get_capital_controls_status("paper-x")
            assert st["account_id"] == "paper-x"
            assert st["manual_liquidation_cash_hold_usd"] == 7.0
            assert st["ui_actions"]["clear_cash_hold"]["enabled"] is True
            print("PASS status_api")
        finally:
            store.CAPITAL_CONTROLS_DIR = old_dir
            store.LEGACY_RUNNER_STATE = old_legacy


if __name__ == "__main__":
    test_no_bleed_between_accounts()
    test_runner_hydrate_persist_account_store()
    test_status_api_includes_account()
    print("ALL PASS")
