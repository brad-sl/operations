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
    # Classic large-bag residual (~2% of fill, under residual max) OK
    ok, reason = residual_is_sweepable(
        residual_qty=2.92,
        residual_usd=23.35,
        filled_qty=142.62,
        max_usd=25.0,
        min_usd=0.5,
        max_frac_of_fill=0.06,
    )
    assert ok and reason == "ok", (ok, reason)

    # Too large leftover (half the bag) must NOT auto-sweep — frac gate
    ok2, reason2 = residual_is_sweepable(
        residual_qty=70.0,
        residual_usd=20.0,  # under USD residual cap so frac gate is the blocker
        filled_qty=142.62,
        max_usd=25.0,
        min_usd=0.5,
        max_frac_of_fill=0.06,
    )
    assert not ok2 and "frac_of_fill" in reason2, (ok2, reason2)

    # Full tryout bag must be blocked by orphan USD cap at $5
    ok3, reason3 = residual_is_sweepable(
        residual_qty=2.04,
        residual_usd=25.0,
        filled_qty=0.0,
        max_usd=5.0,
    )
    assert not ok3 and reason3 == "above_max_usd", (ok3, reason3)

    # Above residual USD cap
    ok4, reason4 = residual_is_sweepable(
        residual_qty=2.0,
        residual_usd=80.0,
        filled_qty=100.0,
        max_usd=25.0,
    )
    assert not ok4 and reason4 == "above_max_usd"
    print("[GATE] residual OK; tryout-size + large leftover blocked")


def test_config_defaults():
    cfg = load_dust_sweep_config(
        {
            "risk_management": {
                "dust_sweep_after_sl": True,
                "dust_sweep_max_usd": 25,
                "dust_sweep_orphan_max_usd": 5,
            }
        }
    )
    assert cfg["enabled"] is True
    assert cfg["max_usd"] == 25.0
    assert cfg["orphan_max_usd"] == 5.0
    # Default orphan tighter than residual
    bare = load_dust_sweep_config({})
    assert bare["orphan_max_usd"] <= bare["max_usd"]
    print("[CONFIG] load_dust_sweep_config OK")


def test_list_orphan_from_fixture():
    payload = {
        "positions": [
            {"pair": "LINK-USD", "amount": 2.92, "value_usd": 23.35},  # tryout — not orphan dust
            {"pair": "ADA-USD", "amount": 0.0001, "value_usd": 0.00002},
            {"pair": "SOL-USD", "amount": 3.0, "value_usd": 220.0},
            {"pair": "USD-USD", "amount": 100, "value_usd": 100},
            {"pair": "ZEC-USD", "amount": 0.01, "value_usd": 3.5},  # residual dust
        ]
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "live.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        dust = list_orphan_dust_from_live_state(max_usd=5.0, min_usd=0.0, live_state_path=p)
        pairs = {d["pair"] for d in dust}
        assert "LINK-USD" not in pairs  # $23 tryout must not be orphan-dust listed
        assert "ZEC-USD" in pairs
        assert "ADA-USD" in pairs
        assert "SOL-USD" not in pairs
        assert "USD-USD" not in pairs
    print("[LIST] orphan dust listing OK")


def test_sweep_orphan_refuses_full_tryout_bag():
    """2026-09-23 LINK: $25 bag must never market-sell as dust_sweep_orphan."""
    from phase6.core.sl_dust_sweep import sweep_orphan_dust

    class _BagEx:
        def get_crypto_available(self, asset):
            return 2.04

        def get_holdings_verified(self):
            return {
                "positions": {
                    "LINK": {"available": 0.05, "hold": 1.99, "amount": 2.04}
                },
                "verified": True,
            }

        def get_price(self, pair):
            return 12.28

        def get_open_stop_orders(self, pair):
            return []  # simulate stop already cancelled / lag

        def get_open_orders(self, pair):
            return []

        def place_market_sell(self, *a, **k):
            raise AssertionError("must not sell full tryout as dust")

    with patch(
        "phase6.core.sl_dust_sweep.list_orphan_dust_from_live_state",
        return_value=[{"pair": "LINK-USD", "amount": 2.04, "value_usd": 25.06}],
    ):
        out = sweep_orphan_dust(
            _BagEx(),
            dry_run=False,
            max_usd=5.0,
            skip_if_open_stop=True,
        )
    results = out.get("results") or []
    assert results, out
    assert results[0].get("skipped") is True, results[0]
    assert results[0].get("skip_reason") in {
        "above_max_usd_full_bag",
        "held_under_stop_not_dust",
        "above_max_usd",
    }, results[0]
    print("[ORPHAN] full tryout bag refused OK")


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
        config={"risk_management": {"dust_sweep_after_sl": True, "dust_sweep_max_usd": 25}},
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
            config={"risk_management": {"dust_sweep_after_sl": True, "dust_sweep_max_usd": 25}},
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
    test_sweep_orphan_refuses_full_tryout_bag()
    test_sweep_residual_after_stop_dry_and_live_mock()
    test_market_sell_zero_skip()
    print("[SL DUST SWEEP ISOLATION] PASSED")
