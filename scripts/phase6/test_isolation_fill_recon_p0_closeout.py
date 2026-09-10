#!/usr/bin/env python3
"""Isolation: A3 limit-first attribution + A4 flat ghost close + A2 bag_id field."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestFillReconP0Closeout(unittest.TestCase):
    def test_is_coinbase_trading_bot_accepts_phase6_client_id(self) -> None:
        from phase6.core.exchange_fill_reconciler import is_coinbase_trading_bot_order

        self.assertTrue(
            is_coinbase_trading_bot_order(
                {
                    "order_data_source": "ORDER_DATA_SOURCE_TRADING_PROXY",
                    "side": "BUY",
                }
            )
        )
        self.assertTrue(
            is_coinbase_trading_bot_order(
                {
                    "client_order_id": "phase6-deadbeef",
                    "side": "BUY",
                    "order_type": "LIMIT",
                }
            )
        )
        self.assertFalse(
            is_coinbase_trading_bot_order(
                {"client_order_id": "manual-ui", "side": "BUY", "order_type": "LIMIT"}
            )
        )

    def test_limit_first_buy_builds_ledger_row(self) -> None:
        from phase6.core.exchange_fill_reconciler import build_ledger_row_from_market_buy

        order = {
            "order_id": "lim-1",
            "product_id": "LINK-USD",
            "side": "BUY",
            "status": "FILLED",
            "order_type": "LIMIT",
            "client_order_id": "phase6-abc123",
            "average_filled_price": "12.5",
            "filled_size": "8.0",
            "order_configuration": {"limit_limit_gtc": {"base_size": "8", "limit_price": "12.5"}},
        }
        row = build_ledger_row_from_market_buy(order, exchange=None, backfill=True)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["side"], "BUY")
        self.assertEqual(row["pair"], "LINK-USD")
        self.assertEqual(row["reason"], "limit_first_buy")
        self.assertEqual(row["qty"], 8.0)
        self.assertEqual(row["entry_price"], 12.5)

        # Market still works via trading proxy source
        mkt = {
            "order_id": "mkt-1",
            "product_id": "ETH-USD",
            "side": "BUY",
            "status": "FILLED",
            "order_type": "MARKET",
            "order_data_source": "ORDER_DATA_SOURCE_TRADING_PROXY",
            "average_filled_price": "2000",
            "filled_size": "0.01",
        }
        row2 = build_ledger_row_from_market_buy(mkt, exchange=None)
        self.assertIsNotNone(row2)
        assert row2 is not None
        self.assertEqual(row2["reason"], "rebalance_buy")

    def test_register_protective_order_bag_id(self) -> None:
        import phase6.core.protective_orders_registry as reg

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.jsonl"
            with patch.object(reg, "REGISTRY_PATH", path):
                reg.register_protective_order(
                    pair="LINK-USD",
                    sl_order_id="sl-9",
                    entry_price=12.0,
                    qty=1.0,
                    stop_price=11.6,
                    buy_order_id="buy-9",
                )
                rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["bag_id"], "LINK-USD:buy-9")
                self.assertEqual(rows[0]["buy_order_id"], "buy-9")

    def test_close_open_stops_for_flat_pair(self) -> None:
        import phase6.core.protective_orders_registry as reg

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.jsonl"
            with patch.object(reg, "REGISTRY_PATH", path):
                reg.register_protective_order(
                    pair="LINK-USD",
                    sl_order_id="ghost-1",
                    entry_price=10.0,
                    qty=1.0,
                    stop_price=9.7,
                    buy_order_id="old-buy",
                )
                n = reg.close_open_stops_for_flat_pair("LINK-USD", reason="test_flat")
                self.assertEqual(n, 1)
                rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
                closed = [r for r in rows if r.get("status") == "closed"]
                self.assertTrue(closed)
                self.assertEqual(closed[-1]["close_reason"], "test_flat")

    def test_maybe_close_flat_registry_when_qty_zero(self) -> None:
        from phase6.core import exchange_fill_reconciler as fr
        import phase6.core.protective_orders_registry as reg

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.jsonl"
            with patch.object(reg, "REGISTRY_PATH", path):
                reg.register_protective_order(
                    pair="AAA-USD",
                    sl_order_id="sl-a",
                    entry_price=1.0,
                    qty=2.0,
                    stop_price=0.97,
                )
                ex = Mock()
                ex.get_crypto_available.return_value = 0.0
                n = fr._maybe_close_flat_registry(ex, "AAA-USD", reason="unit")
                self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
