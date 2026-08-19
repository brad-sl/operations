#!/usr/bin/env python3
"""Isolation: position cost basis matches current-lot logic (not lifetime buy average)."""
import json
from pathlib import Path

from phase6.core.position_cost_basis import (
    average_cost_for_pair,
    average_cost_from_trades,
    enrich_position_unrealized,
)
from phase6.core.trade_ledger import TradeLedger


def test_eth_last_buy_when_ledger_drift():
    ledger = TradeLedger()
    entry, basis = average_cost_for_pair(
        ledger, "ETH-USD", expected_qty=0.05004178
    )
    assert entry is not None
    assert basis in (
        "last_buy_ledger_drift",
        "ledger_avg_cost",
        "ledger_lifo_exchange_qty",
        "last_buy_flat",
    )
    # Must not be the old broken lifetime average ~2281
    assert entry < 2100, f"entry still inflated: {entry} ({basis})"
    assert 1700 < entry < 1900, f"expected ~1795 lot, got {entry}"


def test_enrich_eth_position():
    ledger = TradeLedger()
    pos = {
        "pair": "ETH-USD",
        "amount": 0.05004178,
        "current_price": 1738.89,
        "entry_price": 2281.27,
        "unrealized_pnl_pct": -0.2378,
    }
    out = enrich_position_unrealized(pos, ledger)
    assert out["entry_price"] < 2100
    assert out["unrealized_pnl_pct"] > -0.10
    assert "unrealized_pnl_usd" in out


def test_sell_uses_exit_price():
    trades = [
        {"timestamp": "2026-06-01T00:00:00", "side": "BUY", "qty": 0.1, "entry_price": 2000.0},
        {"timestamp": "2026-06-02T00:00:00", "side": "SELL", "qty": 0.1, "exit_price": 1900.0},
        {"timestamp": "2026-07-11T00:00:00", "side": "BUY", "qty": 0.05, "entry_price": 1795.0},
    ]
    entry, basis = average_cost_from_trades(trades, expected_qty=0.05)
    assert entry == 1795.0
    assert basis == "ledger_avg_cost"


def test_btc_open_book_not_lifetime_buy_avg():
    """Live BTC bag must not use lifetime BUY average (~43k) when current lot is ~63k."""
    ledger = TradeLedger()
    live_path = Path("data/state/phase6_live_state.json")
    if not live_path.exists():
        print("SKIP: no live_state for BTC audit")
        return
    live = json.loads(live_path.read_text())
    btc = next((p for p in (live.get("positions") or []) if p.get("pair") == "BTC-USD"), None)
    if not btc or float(btc.get("amount") or 0) <= 0:
        print("SKIP: no BTC position")
        return
    amt = float(btc["amount"])
    entry, basis = average_cost_for_pair(ledger, "BTC-USD", expected_qty=amt)
    assert entry is not None
    # Lifetime buy-only avg historically ~43k; current lots ~62–65k
    assert entry > 55000, f"BTC entry still looks lifetime-low: {entry} ({basis})"
    assert entry < 80000, f"BTC entry absurdly high: {entry} ({basis})"
    assert basis in (
        "ledger_lifo_exchange_qty",
        "ledger_avg_cost",
        "last_buy_ledger_drift",
        "last_buy_flat",
    )
    # Enrich must overwrite lying state entry
    out = enrich_position_unrealized(
        {
            "pair": "BTC-USD",
            "amount": amt,
            "current_price": float(btc.get("current_price") or 65000),
            "entry_price": 43264.0,
            "unrealized_pnl_pct": 0.49,
        },
        ledger,
    )
    assert out["entry_price"] > 55000
    assert out["unrealized_pnl_pct"] < 0.15, out
    print(f"BTC OK entry={out['entry_price']} r={out['unrealized_pnl_pct']} basis={out.get('entry_basis')}")


if __name__ == "__main__":
    test_eth_last_buy_when_ledger_drift()
    test_enrich_eth_position()
    test_sell_uses_exit_price()
    test_btc_open_book_not_lifetime_buy_avg()
    print("OK")