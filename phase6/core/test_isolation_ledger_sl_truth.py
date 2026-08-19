#!/usr/bin/env python3
"""Isolation: rebalance ledger sl_attached reflects exchange protective orders."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.ledger_sl_truth import enrich_buy_sl_truth
from phase6.core.trade_ledger import TradeLedger


def test_enrich_buy_sl_from_exchange():
    slm = MagicMock()
    slm.detect_active_protective_orders.return_value = {
        "LINK-USD": [{"order_id": "abc", "stop_price": 7.5}],
    }
    row = {"success": True, "side": "BUY", "pair": "LINK-USD", "sl_attached": False}
    enrich_buy_sl_truth(row, slm)
    assert row["sl_attached"] is True
    assert row["sl_truth_source"] == "exchange_protective_order"


def test_log_execution_result_writes_truth(tmp_path):
    ledger = TradeLedger(base_dir=tmp_path)
    slm = MagicMock()
    slm.detect_active_protective_orders.return_value = {"OP-USD": [{"order_id": "x"}]}
    ex = MagicMock()
    ledger.log_execution_result(
        {
            "success": True,
            "pair": "OP-USD",
            "side": "BUY",
            "size": 1.0,
            "entry_price": 0.5,
            "order_id": "oid",
            "sl_attached": False,
        },
        mode="live",
        exchange=ex,
        signal_source="arch4_rebalance",
        stop_loss_manager=slm,
    )
    line = ledger.jsonl_path.read_text().strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["sl_attached"] is True
    assert rec["sl_truth_source"] == "exchange_protective_order"


def test_rebalance_plan_finalizes_ledger_with_sl_truth(tmp_path):
    """record_ledger=False buys must still land in ledger with exchange SL truth."""
    from phase6.core.order_executor import OrderExecutor

    ledger = TradeLedger(base_dir=tmp_path)
    slm = MagicMock()
    slm.detect_active_protective_orders.return_value = {
        "LINK-USD": [{"order_id": "stop1", "stop_price": 7.0}],
    }
    ex = MagicMock()
    oe = OrderExecutor(
        exchange=ex,
        stop_loss_manager=slm,
        mode="live",
        trade_ledger=ledger,
    )

    def fake_buy(pair, usd_amount, tp_pct=None, *, record_ledger=True):
        result = {
            "success": True,
            "pair": pair,
            "side": "BUY",
            "action": "BUY",
            "order_id": "buy1",
            "entry_price": 10.0,
            "size": 1.0,
            "sl_attached": False,
            "fill_verified": True,
        }
        if record_ledger:
            enrich_buy_sl_truth(result, oe.stop_loss_manager)
            oe._record_to_ledger(result, signal_source="order_executor_buy")
        return result

    oe.execute_buy = fake_buy  # type: ignore
    results = oe.execute_rebalance_plan(
        [{"pair": "LINK-USD", "action": "BUY", "usd_amount": 10.0}]
    )
    assert results and results[0].get("sl_attached") is True
    assert results[0].get("sl_truth_source") == "exchange_protective_order"
    line = ledger.jsonl_path.read_text().strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["sl_attached"] is True
    assert rec["signal_source"] == "order_executor_rebalance"
    assert rec.get("sl_truth_source") == "exchange_protective_order"


if __name__ == "__main__":
    test_enrich_buy_sl_from_exchange()
    test_log_execution_result_writes_truth(Path("/tmp/ledger_sl_truth_iso"))
    test_rebalance_plan_finalizes_ledger_with_sl_truth(Path("/tmp/ledger_sl_truth_rebal"))
    print("ledger sl truth isolation PASS")
