#!/usr/bin/env python3
"""Isolation: SL residual dust sweep gates + orphan listing (no live orders)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phase6.core.sl_dust_sweep import (
    list_orphan_dust_from_live_state,
    load_dust_sweep_config,
    residual_is_sweepable,
    sweep_residual_after_stop,
    market_sell_full_available,
)


def test_gate_matches_link_residual():
    # Real case: 142.62 filled, ~2.92 residual (~2%), ~$23
    ok, reason = residual_is_sweepable(
        residual_qty=2.92,
        residual_usd=23.35,
        filled_qty=142.62,
        max_usd=50.0,
        min_usd=0.5,
        max_frac_of_fill=0.06,
    )
    assert ok and reason == "ok", (ok, reason)

    # Too large leftover (half the bag) must NOT auto-sweep — frac gate
    ok2, reason2 = residual_is_sweepable(
        residual_qty=70.0,
        residual_usd=40.0,  # under USD cap so frac gate is the blocker
        filled_qty=142.62,
        max_usd=50.0,
        min_usd=0.5,
        max_frac_of_fill=0.06,
    )
    assert not ok2 and "frac_of_fill" in reason2, (ok2, reason2)

    # Above USD cap
    ok3, reason3 = residual_is_sweepable(
        residual_qty=2.0,
        residual_usd=80.0,
        filled_qty=100.0,
        max_usd=50.0,
    )
    assert not ok3 and reason3 == "above_max_usd"
    print("[GATE] LINK-class residual OK; large leftover blocked")


def test_config_defaults():
    cfg = load_dust_sweep_config(
        {
            "risk_management": {
                "dust_sweep_after_sl": True,
                "dust_sweep_max_usd": 50,
            }
        }
    )
    assert cfg["enabled"] is True
    assert cfg["max_usd"] == 50.0
    print("[CONFIG] load_dust_sweep_config OK")


def test_list_orphan_from_fixture():
    payload = {
        "positions": [
            {"pair": "LINK-USD", "amount": 2.92, "value_usd": 23.35},
            {"pair": "ADA-USD", "amount": 0.0001, "value_usd": 0.00002},
            {"pair": "SOL-USD", "amount": 3.0, "value_usd": 220.0},
            {"pair": "USD-USD", "amount": 100, "value_usd": 100},
        ]
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "live.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        dust = list_orphan_dust_from_live_state(max_usd=50.0, min_usd=0.0, live_state_path=p)
        pairs = {d["pair"] for d in dust}
        assert "LINK-USD" in pairs
        assert "ADA-USD" in pairs
        assert "SOL-USD" not in pairs
        assert "USD-USD" not in pairs
    print("[LIST] orphan dust listing OK")


class _Ex:
    def __init__(self, avail=2.92, price=8.0):
        self.avail = avail
        self.price = price
        self.sells = []

    def get_crypto_available(self, asset):
        return self.avail

    def get_holdings_verified(self):
        return {"positions": {"LINK": self.avail}, "verified": True}

    def get_price(self, pair):
        return self.price

    def quantize_size(self, pair, size):
        return float(f"{float(size):.4f}")

    def place_market_sell(self, product_id, size):
        self.sells.append((product_id, size))
        return {"success": True, "order_id": "dust-test-1", "size": size}

    def get_order_fill_details(self, oid):
        return {"average_filled_price": self.price, "filled_size": self.avail}

    # stubs so protected_market_exit cancel path does not AttributeError in dry runs
    def get_open_stop_orders(self, pair):
        return []

    def get_open_orders(self, pair):
        return []

    def cancel_order(self, oid):
        return True


def test_sweep_residual_after_stop_dry_and_live_mock():
    ex = _Ex()
    dry = sweep_residual_after_stop(
        ex,
        "LINK-USD",
        filled_qty=142.62,
        parent_sl_order_id="parent-sl",
        dry_run=True,
        config={"risk_management": {"dust_sweep_after_sl": True, "dust_sweep_max_usd": 50}},
    )
    assert dry.get("success") and not dry.get("skipped"), dry
    assert ex.sells == []

    import phase6.core.sl_dust_sweep as mod

    real_ledger = mod._ledger_dust_sell
    mod._ledger_dust_sell = lambda *a, **k: None  # isolation: no live ledger write
    try:
        live = sweep_residual_after_stop(
            ex,
            "LINK-USD",
            filled_qty=142.62,
            parent_sl_order_id="parent-sl",
            dry_run=False,
            config={"risk_management": {"dust_sweep_after_sl": True, "dust_sweep_max_usd": 50}},
        )
    finally:
        mod._ledger_dust_sell = real_ledger
    assert live.get("success") and not live.get("skipped"), live
    assert ex.sells and ex.sells[0][0] == "LINK-USD"
    assert abs(ex.sells[0][1] - 2.92) < 1e-6
    print("[SWEEP] residual_after_stop mock OK")


def test_market_sell_zero_skip():
    ex = _Ex(avail=0.0)
    r = market_sell_full_available(ex, "LINK-USD", dry_run=False, settle_wait_s=0.0)
    assert r.get("skipped") and "zero" in str(r.get("skip_reason") or "").lower(), (r.get("skip_reason"), r)
    print("[SWEEP] zero residual skip OK")


if __name__ == "__main__":
    test_gate_matches_link_residual()
    test_config_defaults()
    test_list_orphan_from_fixture()
    test_sweep_residual_after_stop_dry_and_live_mock()
    test_market_sell_zero_skip()
    print("[SL DUST SWEEP ISOLATION] PASSED")
