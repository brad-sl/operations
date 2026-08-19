#!/usr/bin/env python3
"""ENG-S3 P0: shadow buy must not call stop_loss_manager; live buy delegates settlement to SL manager."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.order_executor import OrderExecutor
from phase6.core.trade_ledger import TradeLedger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_shadow_buy_no_sl_manager_calls():
    sl = MagicMock()
    sl.attach_stop_loss = MagicMock(return_value=True)
    sl.attach_take_profit = MagicMock(return_value=True)
    ex = MagicMock()
    ex.get_price = MagicMock(return_value=100.0)
    ex.quantize_size = MagicMock(side_effect=lambda p, s: s)

    oe = OrderExecutor(ex, sl, mode="shadow")
    r = oe.execute_buy("BTC-USD", 50.0)
    assert r.get("success") is True
    sl.attach_stop_loss.assert_not_called()
    sl.attach_take_profit.assert_not_called()
    assert r.get("sl_attached") is False
    logger.info("[ENG-S3-01] shadow buy did not call SL manager — OK")


def test_live_buy_no_duplicate_settlement_poll():
    poll_calls = []
    fill_reads = []

    class Ex:
        def place_market_buy(self, pair, usd):
            return {"success": True, "order_id": "live-oid-1"}

        def get_order_fill_details(self, oid):
            fill_reads.append(oid)
            return {"average_filled_price": 100.0, "filled_size": 0.5, "status": "FILLED"}

        def quantize_size(self, pair, size):
            return size

    class SL:
        def attach_stop_loss(self, *a, **k):
            return True

        def attach_take_profit(self, *a, **k):
            return False

        default_tp_pct = None

    ex = Ex()
    ex.poll_for_settlement = lambda *a, **k: poll_calls.append(1) or True

    oe = OrderExecutor(ex, SL(), mode="live")
    r = oe.execute_buy("BTC-USD", 50.0)
    assert r.get("success") is True
    assert poll_calls == [], "order_executor must not call poll_for_settlement (ENG-S3-02)"
    assert len(fill_reads) <= 3, "no extended fill poll loop in order_executor"
    assert r.get("fill_verified") is True
    logger.info("[ENG-S3-02] live buy no duplicate settlement poll — OK")


def test_live_buy_no_market_price_sl_anchor():
    class Ex:
        def place_market_buy(self, pair, usd):
            return {"success": True, "order_id": "oid-delayed"}

        def get_price(self, pair):
            return 999.0

        def get_order_fill_details(self, oid):
            return {"average_filled_price": 0.0, "filled_size": 0.0}

        def quantize_size(self, pair, size):
            return size

    class SL:
        def attach_stop_loss(self, pair, entry, size, **k):
            assert entry != 999.0, "must not pass market price as entry anchor"
            return False

        default_tp_pct = None

    oe = OrderExecutor(Ex(), SL(), mode="live")
    r = oe.execute_buy("BTC-USD", 50.0)
    assert r.get("entry_price") in (0, 0.0)
    logger.info("[ENG-S3-02b] no market-price SL anchor in executor — OK")


def test_ledger_fill_verify():
    class Ex:
        def get_order_fill_details(self, oid):
            return {"average_filled_price": 99.5, "filled_size": 0.25}

    ledger = TradeLedger(base_dir=PROJECT_ROOT / "data/state/_isolation_ledger_tmp")
    ledger.trades_dir.mkdir(parents=True, exist_ok=True)
    ledger.jsonl_path = ledger.trades_dir / "test_eng_s3.jsonl"
    if ledger.jsonl_path.exists():
        ledger.jsonl_path.unlink()

    ledger.log_execution_result(
        {
            "pair": "BTC-USD",
            "side": "BUY",
            "order_id": "oid-x",
            "mode": "live",
            "qty": 0.1,
            "entry_price": 0,
            "success": True,
        },
        mode="live",
        exchange=Ex(),
        signal_source="test",
    )
    rows = ledger.get_recent_trades(1)
    assert rows[0].get("fill_verified") is True
    assert float(rows[0]["entry_price"]) == 99.5
    assert float(rows[0]["qty"]) == 0.25
    logger.info("[ENG-S3-03] ledger fill verify — OK")


def main():
    test_shadow_buy_no_sl_manager_calls()
    test_live_buy_no_duplicate_settlement_poll()
    test_live_buy_no_market_price_sl_anchor()
    test_ledger_fill_verify()
    print("[ENG-S3-P0] ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())