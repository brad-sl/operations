#!/usr/bin/env python3
"""Isolation: SL anchor must not use dead prior-cycle lot prices."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.stop_loss_coordinator import StopLossCoordinator


def test_rejects_stale_high_entry_vs_mark():
    slm = MagicMock()
    c = StopLossCoordinator(slm, exchange_client=MagicMock(), config={})
    # Simulate RAVE: stale Aug-12 entry 0.3135, mark 0.2767 after fresh buy
    px = c._get_original_entry(
        "RAVE-USD",
        {"entry_price": 0.3135, "current_price": 0.2767, "amount": 1223.3},
    )
    assert px == 0.0 or px * 0.97 < 0.2767, f"stale high entry accepted: {px}"
    print("reject stale high entry OK", px)


def test_accepts_fresh_buy_below_mark():
    slm = MagicMock()
    c = StopLossCoordinator(slm, exchange_client=MagicMock(), config={})
    px = c._get_original_entry(
        "LINK-USD",
        {"entry_price": 10.5, "current_price": 11.4, "amount": 100},
    )
    assert abs(px - 10.5) < 1e-9, px
    print("accept healthy entry OK", px)


def test_ledger_open_buy_skips_after_sell(monkeypatch_trades=None):
    slm = MagicMock()
    c = StopLossCoordinator(slm, exchange_client=MagicMock(), config={})

    class FakeLedger:
        def get_recent_trades(self, limit=400):
            return [
                {"timestamp": "2026-08-23T04:07:00Z", "pair": "RAVE-USD", "side": "SELL",
                 "reason": "stop_loss_exchange", "entry_price": 0.28},
                {"timestamp": "2026-08-23T04:00:00Z", "pair": "RAVE-USD", "side": "BUY",
                 "entry_price": 0.2769},
                {"timestamp": "2026-08-12T04:00:00Z", "pair": "RAVE-USD", "side": "BUY",
                 "entry_price": 0.3135},
            ]

    import phase6.core.stop_loss_coordinator as mod

    # Patch TradeLedger used inside method
    import phase6.core.trade_ledger as tl

    orig = tl.TradeLedger
    tl.TradeLedger = FakeLedger  # type: ignore
    try:
        px = c._latest_ledger_open_buy_entry("RAVE-USD")
        assert px == 0.0, f"expected flat after SELL, got {px}"
        print("ledger flat after SELL OK")
    finally:
        tl.TradeLedger = orig


if __name__ == "__main__":
    test_rejects_stale_high_entry_vs_mark()
    test_accepts_fresh_buy_below_mark()
    test_ledger_open_buy_skips_after_sell()
    print("test_isolation_sl_stale_anchor PASS")
