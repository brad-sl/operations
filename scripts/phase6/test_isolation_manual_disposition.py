#!/usr/bin/env python3
"""Isolation: manual sell / swap disposition detection."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.portfolio_disposition import detect_manual_disposition


def test_liquidation_op_to_usd():
    prev = {"OP-USD": 400.0, "LINK-USD": 280.0}
    cur = {"OP-USD": 0.0, "LINK-USD": 280.0}
    d = detect_manual_disposition(prev, cur, delta_cash=395.0, delta_holdings=-400.0, delta_total=-5.0)
    assert d and d["event_type"] == "manual_liquidation_to_cash"
    assert "OP-USD" in d["pairs_sold"]
    print("PASS liquidation OP->USD")


def test_crypto_swap():
    prev = {"OP-USD": 400.0, "LINK-USD": 100.0}
    cur = {"OP-USD": 50.0, "LINK-USD": 450.0}
    d = detect_manual_disposition(prev, cur, delta_cash=0.0, delta_holdings=0.0, delta_total=0.0)
    assert d and d["event_type"] == "manual_crypto_swap"
    assert "OP-USD" in d["pairs_sold"] and "LINK-USD" in d["pairs_bought"]
    print("PASS crypto swap")


def test_not_deposit_misclass():
    # Same NAV shift as manual sell — external classifier returns 0; disposition catches it
    prev = {"OP-USD": 300.0}
    cur = {"OP-USD": 0.0}
    d = detect_manual_disposition(prev, cur, delta_cash=298.0, delta_holdings=-300.0, delta_total=-2.0)
    assert d["event_type"] == "manual_liquidation_to_cash"
    print("PASS not confused with deposit path")


if __name__ == "__main__":
    test_liquidation_op_to_usd()
    test_crypto_swap()
    test_not_deposit_misclass()
    print("ALL PASS")