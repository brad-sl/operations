#!/usr/bin/env python3
"""Isolation: FIFO must apply SELL qty even without exit_price (B)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.position_cost_basis import average_cost_from_trades, _fifo_layers_from_trades


def test_sell_without_exit_price_reduces_layers() -> None:
    """Operator trim style: qty + entry_price, no exit_price — still reduces inventory."""
    trades = [
        {
            "timestamp": "2026-08-20T00:00:00Z",
            "side": "BUY",
            "qty": 164.59,
            "entry_price": 11.60,
            "pair": "LINK-USD",
        },
        {
            "timestamp": "2026-08-24T00:00:00Z",
            "side": "SELL",
            "qty": 32.34,
            "entry_price": 11.57,  # no exit_price — historic bug skipped this
            "pair": "LINK-USD",
        },
    ]
    layers, _ = _fifo_layers_from_trades(trades)
    open_qty = sum(q for q, _ in layers)
    assert abs(open_qty - (164.59 - 32.34)) < 0.02, open_qty


def test_flat_ledger_with_exchange_qty_refuses_last_buy() -> None:
    trades = [
        {
            "timestamp": "2026-08-01T00:00:00Z",
            "side": "BUY",
            "qty": 10.0,
            "entry_price": 11.0,
        },
        {
            "timestamp": "2026-08-02T00:00:00Z",
            "side": "SELL",
            "qty": 10.0,
            "exit_price": 11.5,
        },
    ]
    px, basis = average_cost_from_trades(trades, expected_qty=5.92)
    assert px is None, (px, basis)
    assert basis in ("ledger_flat_exchange_open", "flat_or_unknown", "unknown"), basis
    assert "last_buy" not in basis


def test_qty_mismatch_refuses_invented_last_buy() -> None:
    """Ghost layers ≫ exchange qty must not return last_buy_* as open-lot truth."""
    trades = [
        {
            "timestamp": "2026-08-01T00:00:00Z",
            "side": "BUY",
            "qty": 40.0,
            "entry_price": 11.641,
        },
        # missing sells leave phantom inventory; exchange only holds 5.92 of a *new* buy
        # that never hit the ledger
    ]
    px, basis = average_cost_from_trades(trades, expected_qty=5.92)
    # May return lifo slice for dash soft estimate OR refuse — live TP must not trust lifo.
    # Hard rule: never last_buy_flat / last_buy_ledger_drift when expected_qty set.
    assert basis not in ("last_buy_flat", "last_buy_ledger_drift"), (px, basis)


def test_matched_avg_cost_ok() -> None:
    trades = [
        {
            "timestamp": "2026-09-07T00:00:00Z",
            "side": "BUY",
            "qty": 5.92,
            "entry_price": 12.658,
            "average_filled_price": 12.658,
        }
    ]
    px, basis = average_cost_from_trades(trades, expected_qty=5.92)
    assert px is not None and abs(px - 12.658) < 1e-6
    assert basis == "ledger_avg_cost"


def test_fresh_lot_amid_ghost_layers_trusted() -> None:
    """Newest layer qty matches exchange bag → ledger_avg_cost even if older ghosts remain."""
    trades = [
        {
            "timestamp": "2026-08-01T00:00:00Z",
            "side": "BUY",
            "qty": 40.0,
            "entry_price": 11.641,
        },
        {
            "timestamp": "2026-08-24T00:00:00Z",
            "side": "SELL",
            "qty": 32.34,
            "entry_price": 11.57,
        },
        {
            "timestamp": "2026-09-07T21:01:00Z",
            "side": "BUY",
            "qty": 5.92,
            "average_filled_price": 12.658,
        },
    ]
    px, basis = average_cost_from_trades(trades, expected_qty=5.92)
    assert px is not None and abs(px - 12.658) < 1e-6, (px, basis)
    assert basis == "ledger_avg_cost", basis


def test_dual_peak_remainder_full_cover_promotes_trusted() -> None:
    """After half-trim, exchange qty fully covered by open layers → trusted avg (not forever LIFO)."""
    trades = [
        {"timestamp": "2026-09-26T18:51:00Z", "side": "BUY", "qty": 1.76, "entry_price": 14.159},
        {"timestamp": "2026-09-27T04:01:00Z", "side": "BUY", "qty": 4.46, "entry_price": 14.097},
        {
            "timestamp": "2026-09-27T15:50:00Z",
            "side": "SELL",
            "qty": 3.11,
            "exit_price": 14.097,
        },
    ]
    px, basis = average_cost_from_trades(trades, expected_qty=3.11)
    assert px is not None, (px, basis)
    assert basis == "ledger_avg_cost", basis
    # FIFO remainder after selling 3.11 from first layers lands on 3.11 @ 14.097
    # (or LIFO blend if only cover-slice path). Either is trusted math — not soft LIFO tag.
    assert abs(px - 14.097) < 1e-4 or abs(px - (1.35 * 14.097 + 1.76 * 14.159) / 3.11) < 1e-4, (
        px,
        basis,
    )

def test_incomplete_lifo_cover_stays_untrusted_tag() -> None:
    """Partial layer cover must not promote — soft LIFO only."""
    trades = [
        {"timestamp": "2026-09-01T00:00:00Z", "side": "BUY", "qty": 1.0, "entry_price": 10.0},
    ]
    px, basis = average_cost_from_trades(trades, expected_qty=5.0)
    # 1.0 covers only 20% of 5.0 → incomplete
    assert basis in ("ledger_lifo_exchange_qty", "ledger_exchange_qty_mismatch"), basis
    if basis == "ledger_lifo_exchange_qty":
        assert px is not None


if __name__ == "__main__":
    test_sell_without_exit_price_reduces_layers()
    test_flat_ledger_with_exchange_qty_refuses_last_buy()
    test_qty_mismatch_refuses_invented_last_buy()
    test_matched_avg_cost_ok()
    test_fresh_lot_amid_ghost_layers_trusted()
    test_dual_peak_remainder_full_cover_promotes_trusted()
    test_incomplete_lifo_cover_stays_untrusted_tag()
    print("position cost basis sell qty isolation PASS")
