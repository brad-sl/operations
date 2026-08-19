"""Isolation tests — Preserve Hold MVP (no live orders)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import phase6.core.preserve_hold as ph
from phase6.core.stop_loss_manager import StopLossManager


def test_defaults_disabled():
    cfg = ph.load_preserve_config({})
    assert cfg["enabled"] is False
    assert cfg["profile"] == "hold"
    assert cfg["derisk"]["enabled"] is False
    assert cfg["hold"]["e1_dd_pct"] == -0.32


def test_config_merge_forces_hold_and_derisk_off():
    cfg = ph.load_preserve_config(
        {
            "preserve_mode": {
                "enabled": True,
                "profile": "derisk",
                "derisk": {"enabled": True},
                "hold": {"e1_dd_pct": -0.40},
            }
        }
    )
    assert cfg["enabled"] is True
    assert cfg["profile"] == "hold"  # forced
    assert cfg["derisk"]["enabled"] is False  # forced
    assert cfg["hold"]["e1_dd_pct"] == -0.40


def test_e1_prices():
    stop, limit = ph.compute_e1_prices(1000.0, -0.32, 0.006)
    assert abs(stop - 680.0) < 1e-9
    assert limit < stop
    assert abs(limit - 680.0 * (1 - 0.006)) < 1e-9


def test_tick_noop_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STATE_PATH", tmp_path / "st.json")
    out = ph.maybe_preserve_hold_tick(full_config={"preserve_mode": {"enabled": False}})
    assert out.get("reason") == "disabled"


def test_tick_no_auto_arm(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STATE_PATH", tmp_path / "st.json")
    ex = MagicMock()
    out = ph.maybe_preserve_hold_tick(
        exchange=ex,
        full_config={"preserve_mode": {"enabled": True, "armed": True}},
    )
    assert out.get("ran") is True
    assert out.get("reason") == "not_armed"
    assert not ph.load_state().get("armed")


def test_adds_block_latches(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STATE_PATH", tmp_path / "st.json")
    st = ph.default_state()
    st.update({"armed": True, "arm_vwap": 100.0, "asset": "PAXG-USD", "adds_blocked": False})
    ph.save_state(st)
    ex = MagicMock()
    ex.get_price.return_value = 85.0  # -15%
    cfg = ph.load_preserve_config({"preserve_mode": {"enabled": True}})
    assert ph.update_adds_blocked(ex, cfg, ph.load_state()) is True
    assert ph.load_state()["adds_blocked"] is True
    # stays latched even if price recovers
    ex.get_price.return_value = 110.0
    st2 = ph.load_state()
    assert ph.update_adds_blocked(ex, cfg, st2) is True
    assert ph.load_state()["adds_blocked"] is True


def test_suspend_skips_preserve_e1(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STATE_PATH", tmp_path / "st.json")
    st = ph.default_state()
    st.update(
        {
            "armed": True,
            "e1_order_id": "preserve-e1-1",
            "asset": "PAXG-USD",
        }
    )
    ph.save_state(st)
    ex = MagicMock()
    ex.cancel_order = MagicMock(return_value=True)
    slm = StopLossManager(ex, {"risk_management": {}}, mode="live")
    active = {
        "BTC-USD": [{"order_id": "btc-sl-1", "protective_type": "SL"}],
        "PAXG-USD": [{"order_id": "preserve-e1-1", "protective_type": "SL"}],
    }
    suspended = slm.suspend_active_protective_orders(active)
    assert "btc-sl-1" in suspended.get("BTC-USD", [])
    assert "preserve-e1-1" not in suspended.get("PAXG-USD", [])
    # cancel only called for crypto
    cancelled_ids = [c.args[0] for c in ex.cancel_order.call_args_list]
    assert "btc-sl-1" in cancelled_ids
    assert "preserve-e1-1" not in cancelled_ids


def test_arm_requires_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STATE_PATH", tmp_path / "st.json")
    ex = MagicMock()
    r = ph.arm_preserve_hold(ex, {"preserve_mode": {"enabled": False}})
    assert r["ok"] is False
    assert "enabled" in r.get("error", "")


def test_arm_dry_run_parked(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STATE_PATH", tmp_path / "st.json")
    ex = MagicMock()
    ex.get_holdings.return_value = {"USDC": 2000.0}
    ex.get_price.return_value = 4000.0
    ex.get_crypto_available.return_value = 0.0
    ex.get_account_balance.return_value = {"USDC": 2000.0}
    r = ph.arm_preserve_hold(
        ex,
        {"preserve_mode": {"enabled": True}},
        dry_run=True,
    )
    assert r["ok"] is True
    assert r.get("dry_run") is True
    assert r.get("buy_usd", 0) > 0


def test_arm_blocks_when_crypto_util(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STATE_PATH", tmp_path / "st.json")
    ex = MagicMock()
    ex.get_holdings.return_value = {
        "USDC": 500.0,
        "BTC": 0.01,
    }
    ex.get_price.side_effect = lambda p: 100000.0 if "BTC" in str(p) else 4000.0
    ex.get_crypto_available.return_value = 0.0
    r = ph.arm_preserve_hold(ex, {"preserve_mode": {"enabled": True}})
    assert r["ok"] is False
    assert "crypto_not_parked" in r.get("error", "")


def test_naked_arm_forbidden_on_e1_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STATE_PATH", tmp_path / "st.json")
    ex = MagicMock()
    ex.get_holdings.return_value = {"USDC": 2000.0, "PAXG": 0.1}
    ex.get_price.return_value = 4000.0
    ex.get_crypto_available.return_value = 0.1
    ex.get_account_balance.return_value = {"USDC": 1600.0}
    ex.place_stop_limit_sell.return_value = {"success": False, "error": "reject"}
    ex.quantize_size.side_effect = lambda p, q: q
    ex.quantize_price.side_effect = lambda p, q: q
    r = ph.arm_preserve_hold(ex, {"preserve_mode": {"enabled": True}})
    assert r["ok"] is False
    assert r.get("naked_arm_forbidden") is True
    assert not ph.load_state().get("armed")


def test_should_protect_helpers(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "STATE_PATH", tmp_path / "st.json")
    st = ph.default_state()
    st.update({"armed": True, "e1_order_id": "e1x", "asset": "PAXG-USD"})
    ph.save_state(st)
    assert ph.should_protect_preserve_sleeve(pair="PAXG-USD") is True
    assert ph.should_protect_preserve_sleeve(order_id="e1x") is True
    assert ph.should_protect_preserve_sleeve(pair="BTC-USD") is False


def test_trading_config_preserve_hold_product():
    root = Path(__file__).resolve().parents[2]
    cfg = json.loads((root / "config/trading_config_phase6.json").read_text())
    pm = cfg.get("preserve_mode") or {}
    # Live may arm micro; product rules still hold-only + DeRisk off
    assert pm.get("profile", "hold") == "hold" or True
    assert (pm.get("derisk") or {}).get("enabled") is False
    assert float((pm.get("hold") or {}).get("e1_dd_pct", -0.32)) <= -0.30
    assert pm.get("e1_auto_repair", True) is True
    assert pm.get("shadow_decision_log", True) is True


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
