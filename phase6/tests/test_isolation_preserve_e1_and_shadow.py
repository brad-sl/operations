#!/usr/bin/env python3
"""Isolation: E1 health + park ballast shadow decision (no live orders)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import phase6.core.preserve_hold as ph
from phase6.core.park_ballast_shadow import (
    build_park_ballast_decision,
    evaluate_keep_hold,
    is_deploy_open,
    is_parked,
)


def test_inspect_e1_exact(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STATE_PATH", tmp_path / "st.json")
    monkeypatch.setattr(ph, "E1_ALERT_PATH", tmp_path / "alert.json")
    st = ph.default_state()
    st.update(
        {
            "armed": True,
            "asset": "PAXG-USD",
            "arm_vwap": 4000.0,
            "e1_order_id": "e1-exact",
        }
    )
    ph.save_state(st)
    ex = MagicMock()
    ex.get_open_stop_orders.return_value = [
        {"order_id": "e1-exact", "product_id": "PAXG-USD"}
    ]
    ex.get_crypto_available.return_value = 0.01
    ex.get_account_balance.return_value = 0.01
    # _holding_qty path
    if not hasattr(ex, "get_holdings"):
        ex.get_holdings.return_value = {"PAXG": 0.01}

    cfg = ph.load_preserve_config({"preserve_mode": {"enabled": True}})
    # patch holding
    monkeypatch.setattr(ph, "_holding_qty", lambda *a, **k: (0.01, 0.01))
    h = ph.inspect_e1_health(ex, cfg, st)
    assert h["e1_open"] is True
    assert h["naked"] is False
    assert h["match_mode"] == "exact_id"


def test_inspect_e1_naked_triggers_repair(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STATE_PATH", tmp_path / "st.json")
    monkeypatch.setattr(ph, "STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(ph, "E1_ALERT_PATH", tmp_path / "alert.json")
    monkeypatch.setattr(ph, "SLEEVE_LOG_PATH", tmp_path / "sleeve.jsonl")
    st = ph.default_state()
    st.update(
        {
            "armed": True,
            "asset": "PAXG-USD",
            "arm_vwap": 4000.0,
            "e1_order_id": "missing-id",
            "arm_qty": 0.02,
        }
    )
    ph.save_state(st)
    ex = MagicMock()
    ex.get_open_stop_orders.return_value = []
    ex.shadow_mode = True
    ex.get_price.return_value = 4000.0
    ex.quantize_size.side_effect = lambda p, q: q
    ex.quantize_price.side_effect = lambda p, q: q
    monkeypatch.setattr(ph, "_holding_qty", lambda *a, **k: (0.02, 0.02))
    monkeypatch.setattr(
        ph,
        "place_e1_stop",
        lambda *a, **k: {"success": True, "order_id": "repaired-1"},
    )
    cfg = ph.load_preserve_config(
        {"preserve_mode": {"enabled": True, "e1_auto_repair": True}}
    )
    h = ph.inspect_e1_health(ex, cfg, st)
    assert h["naked"] is True
    r = ph.repair_e1_if_missing(ex, cfg, ph.load_state())
    assert r.get("repaired") is True
    assert ph.load_state().get("e1_order_id") == "repaired-1"


def test_inspect_id_drift_sync(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STATE_PATH", tmp_path / "st.json")
    monkeypatch.setattr(ph, "E1_ALERT_PATH", tmp_path / "alert.json")
    st = ph.default_state()
    st.update({"armed": True, "asset": "PAXG-USD", "arm_vwap": 4000.0, "e1_order_id": "old"})
    ph.save_state(st)
    ex = MagicMock()
    ex.get_open_stop_orders.return_value = [
        {"order_id": "new-stop", "product_id": "PAXG-USD"}
    ]
    monkeypatch.setattr(ph, "_holding_qty", lambda *a, **k: (0.02, 0.02))
    cfg = ph.load_preserve_config({"preserve_mode": {"enabled": True}})
    h = ph.inspect_e1_health(ex, cfg, st)
    assert h["e1_open"] is True
    assert h.get("id_drift") is True
    r = ph.repair_e1_if_missing(ex, cfg, ph.load_state())
    assert r.get("reason") == "e1_present_id_synced"
    assert ph.load_state()["e1_order_id"] == "new-stop"


def test_status_naked_badge(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STATE_PATH", tmp_path / "st.json")
    st = ph.default_state()
    st.update({"armed": True, "soak_micro": True, "arm_vwap": 1.0})
    ph.save_state(st)
    health = {"e1_open": False, "naked": True, "reason": "naked_armed_inventory"}
    snap = ph.status_snapshot(
        {"preserve_mode": {"enabled": True, "micro_live": True}},
        e1_health=health,
    )
    assert snap["badge"] == "NAKED"
    assert snap["e1_naked"] is True


def test_keep_hold_eval():
    k = evaluate_keep_hold(
        ret_vs_arm=0.01,
        paxg_30d_pct=12.0,
        btc_30d_pct=2.0,
        basket_30d_pct=1.0,
        margin_pp=5.0,
    )
    assert k["eligible"] is True
    k2 = evaluate_keep_hold(
        ret_vs_arm=-0.01,
        paxg_30d_pct=-1.0,
        btc_30d_pct=2.0,
        basket_30d_pct=1.0,
    )
    assert k2["eligible"] is False


def test_shadow_decision_no_orders(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STATE_PATH", tmp_path / "st.json")
    # park regime file
    regime = tmp_path / "regime.json"
    regime.write_text(
        json.dumps(
            {
                "regime": "flat",
                "strategy_mode": "deploy",
                "allow_new_buys": True,
                "btc_return_pct": 0.3,
            }
        )
    )
    import phase6.core.park_ballast_shadow as sh

    monkeypatch.setattr(sh, "REGIME_STATUS", regime)
    monkeypatch.setattr(sh, "LIVE_STATE", tmp_path / "live.json")
    (tmp_path / "live.json").write_text(
        json.dumps({"total_usd": 2500, "cash_usd": 2000, "positions": []})
    )
    st = ph.default_state()
    st.update(
        {
            "armed": True,
            "soak_micro": True,
            "arm_vwap": 4000.0,
            "e1_order_id": "x",
        }
    )
    ph.save_state(st)
    dec = build_park_ballast_decision(
        preserve_cfg=ph.load_preserve_config({"preserve_mode": {"enabled": True, "micro_live": True}}),
        state=st,
        e1_health={"e1_open": True, "naked": False, "reason": "e1_present"},
        sleeve_row={"preserve_usd": 74.0, "ret_vs_arm": -0.002, "price": 3990.0},
    )
    assert dec["orders"] is False
    assert dec["would"]["scale_to_full_20pct"] is False
    # deploy open + armed + not keep => trim default
    assert dec["would"]["trim_default_on_deploy"] is True
    assert dec["recommended_action"] == "TRIM_DEFAULT_TO_A"


def test_park_helpers():
    assert is_parked({"strategy_mode": "usdc_park", "allow_new_buys": False})
    assert is_deploy_open({"strategy_mode": "deploy", "allow_new_buys": True, "regime": "flat"})


def main() -> int:
    # run without pytest if needed
    import tempfile
    from unittest.mock import MagicMock

    class MP:
        def __init__(self):
            self._stack = []

        def setattr(self, obj, name, val):
            old = getattr(obj, name)
            self._stack.append((obj, name, old))
            setattr(obj, name, val)

        def undo(self):
            for obj, name, old in reversed(self._stack):
                setattr(obj, name, old)

    failures = 0
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        mp = MP()
        try:
            test_inspect_e1_exact(td_path, mp)
            print("PASS exact")
        except Exception as e:
            print("FAIL exact", e)
            failures += 1
        finally:
            mp.undo()

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        mp = MP()
        try:
            test_inspect_e1_naked_triggers_repair(td_path, mp)
            print("PASS naked repair")
        except Exception as e:
            print("FAIL naked repair", e)
            failures += 1
        finally:
            mp.undo()

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        mp = MP()
        try:
            test_inspect_id_drift_sync(td_path, mp)
            print("PASS id drift")
        except Exception as e:
            print("FAIL id drift", e)
            failures += 1
        finally:
            mp.undo()

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        mp = MP()
        try:
            test_status_naked_badge(td_path, mp)
            print("PASS naked badge")
        except Exception as e:
            print("FAIL naked badge", e)
            failures += 1
        finally:
            mp.undo()

    try:
        test_keep_hold_eval()
        print("PASS keep_hold")
    except Exception as e:
        print("FAIL keep_hold", e)
        failures += 1

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        mp = MP()
        try:
            test_shadow_decision_no_orders(td_path, mp)
            print("PASS shadow")
        except Exception as e:
            print("FAIL shadow", e)
            failures += 1
        finally:
            mp.undo()

    try:
        test_park_helpers()
        print("PASS park helpers")
    except Exception as e:
        print("FAIL park helpers", e)
        failures += 1

    # existing preserve tests that still apply
    try:
        test_defaults = __import__("importlib").import_module("phase6.tests.test_isolation_preserve_hold")
        # skip config defaults_off if live config enabled
        print("legacy module importable")
    except Exception as e:
        print("legacy import", e)

    if failures:
        print(f"FAILED {failures}")
        return 1
    print("PASS test_isolation_preserve_e1_and_shadow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
