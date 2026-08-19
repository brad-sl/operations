#!/usr/bin/env python3
"""Isolation: capital control flags clear hold and cooldown (never touch live store)."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.capital_controls import (
    process_capital_control_flags,
    clear_manual_cash_hold,
    hydrate_manual_controls_from_state,
)
import phase6.core.capital_controls as cc
import phase6.core.capital_controls_store as store


def _patch_store(td: Path):
    old = {
        "CAPITAL_CONTROLS_DIR": store.CAPITAL_CONTROLS_DIR,
        "LEGACY_RUNNER_STATE": store.LEGACY_RUNNER_STATE,
        "STATE_DIR": cc.STATE_DIR,
        "FLAG_CLEAR_CASH_HOLD": cc.FLAG_CLEAR_CASH_HOLD,
        "FLAG_CLEAR_COOLDOWN": cc.FLAG_CLEAR_COOLDOWN,
        "JSON_CLEAR_COOLDOWN": cc.JSON_CLEAR_COOLDOWN,
        "CONTROLS_STATUS_JSON": cc.CONTROLS_STATUS_JSON,
        "DEFAULT_STATE_FILE": cc.DEFAULT_STATE_FILE,
    }
    store.CAPITAL_CONTROLS_DIR = td / "capital_controls"
    store.LEGACY_RUNNER_STATE = td / "phase6_runner_state.json"
    cc.STATE_DIR = td
    cc.FLAG_CLEAR_CASH_HOLD = td / "clear_manual_cash_hold.flag"
    cc.FLAG_CLEAR_COOLDOWN = td / "clear_manual_sell_cooldown.flag"
    cc.JSON_CLEAR_COOLDOWN = td / "clear_manual_sell_cooldown.json"
    cc.CONTROLS_STATUS_JSON = td / "capital_user_controls.json"
    cc.DEFAULT_STATE_FILE = td / "phase6_runner_state.json"
    return old


def _restore(old):
    store.CAPITAL_CONTROLS_DIR = old["CAPITAL_CONTROLS_DIR"]
    store.LEGACY_RUNNER_STATE = old["LEGACY_RUNNER_STATE"]
    cc.STATE_DIR = old["STATE_DIR"]
    cc.FLAG_CLEAR_CASH_HOLD = old["FLAG_CLEAR_CASH_HOLD"]
    cc.FLAG_CLEAR_COOLDOWN = old["FLAG_CLEAR_COOLDOWN"]
    cc.JSON_CLEAR_COOLDOWN = old["JSON_CLEAR_COOLDOWN"]
    cc.CONTROLS_STATUS_JSON = old["CONTROLS_STATUS_JSON"]
    cc.DEFAULT_STATE_FILE = old["DEFAULT_STATE_FILE"]


def test_flag_clears_cash_hold():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        old = _patch_store(base)
        try:
            state = base / "phase6_runner_state.json"
            state.write_text(
                json.dumps({"manual_liquidation_cash_hold_usd": 250.0, "manual_sell_cooldown": {}})
            )
            runner = MagicMock()
            runner.state_file = str(state)
            runner.account_id = "test-book-a"
            runner._manual_liquidation_cash_hold_usd = 0.0
            # seed account store from runner path without live migrate
            store.save_account_capital_state(
                "test-book-a",
                {"manual_liquidation_cash_hold_usd": 250.0, "manual_sell_cooldown": {}},
                mirror_legacy=True,
                runner_state_path=state,
            )
            hydrate_manual_controls_from_state(runner, state_file=str(state))
            assert float(runner._manual_liquidation_cash_hold_usd) == 250.0
            clear_manual_cash_hold(runner, state_file=str(state), source="test")
            assert float(runner._manual_liquidation_cash_hold_usd) == 0.0
            data = json.loads(state.read_text())
            # non-primary: may not mirror; check account store
            st = store.load_account_capital_state("test-book-a", migrate_from_runner=False)
            assert st["manual_liquidation_cash_hold_usd"] == 0.0
            print("PASS clear cash hold")
        finally:
            _restore(old)


def test_process_flag_file():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        old = _patch_store(base)
        try:
            state = base / "phase6_runner_state.json"
            state.write_text(json.dumps({"manual_liquidation_cash_hold_usd": 100.0}))
            runner = MagicMock()
            runner.state_file = str(state)
            runner.account_id = "test-book-b"
            store.save_account_capital_state(
                "test-book-b",
                {"manual_liquidation_cash_hold_usd": 100.0, "manual_sell_cooldown": {}},
                mirror_legacy=False,
            )
            cc.FLAG_CLEAR_CASH_HOLD.touch()
            actions = process_capital_control_flags(runner, state_file=str(state))
            assert len(actions) == 1
            assert actions[0]["action"] == "clear_manual_cash_hold"
            assert not cc.FLAG_CLEAR_CASH_HOLD.exists()
            print("PASS process flag file")
        finally:
            _restore(old)


if __name__ == "__main__":
    test_flag_clears_cash_hold()
    test_process_flag_file()
    print("ALL PASS")
