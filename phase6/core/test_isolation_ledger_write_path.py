#!/usr/bin/env python3
"""Isolation: every successful live BUY/SELL must hit TradeLedger (A)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.order_executor import OrderExecutor
from phase6.core.trade_ledger import TradeLedger


def _buy_result(pair: str = "LINK-USD", oid: str = "buy-oid-1") -> dict:
    return {
        "success": True,
        "pair": pair,
        "side": "BUY",
        "action": "BUY",
        "order_id": oid,
        "entry_price": 12.658,
        "size": 5.92,
        "qty": 5.92,
        "sl_attached": True,
        "fill_verified": True,
    }


def test_order_executor_writes_buy_when_ledger_wired(tmp_path: Path) -> None:
    ledger = TradeLedger(base_dir=tmp_path)

    class _Ex:
        def place_market_buy(self, pair, usd_amount):
            return {
                "success": True,
                "order_id": "oe-buy-1",
                "entry_price": 12.65,
                "size": 5.92,
            }

    oe = OrderExecutor(
        exchange=_Ex(),
        stop_loss_manager=None,
        mode="live",
        trade_ledger=ledger,
    )

    def fake_finalize(pair, usd_amount, result, tp_pct=None, execution_style="market_ioc"):
        out = dict(result)
        out.update(
            {
                "pair": pair,
                "side": "BUY",
                "action": "BUY",
                "entry_price": 12.65,
                "size": 5.92,
                "qty": 5.92,
                "sl_attached": False,
                "tp_attached": False,
                "execution_style": execution_style,
                "fill_status": "full",
                "fill_verified": True,
            }
        )
        return out

    oe._finalize_buy_fill = fake_finalize  # type: ignore
    # force_market bypasses limit-first pilot / live config
    r = oe.execute_buy("LINK-USD", 75.0, force_market=True)
    assert r.get("success") is True
    lines = ledger.jsonl_path.read_text().strip().splitlines()
    assert lines, "BUY must be journaled when trade_ledger is wired"
    rec = json.loads(lines[-1])
    assert rec["pair"] == "LINK-USD"
    assert str(rec["side"]).upper() == "BUY"
    assert abs(float(rec["qty"]) - 5.92) < 1e-9
    assert rec.get("order_id") == "oe-buy-1"


def test_order_executor_without_ledger_writes_nothing(tmp_path: Path) -> None:
    """Documents the pre-fix hole: unwired OrderExecutor is a silent no-op."""
    ledger_dir = tmp_path / "unused"
    # No TradeLedger attached
    ex = MagicMock()
    oe = OrderExecutor(exchange=ex, stop_loss_manager=None, mode="live", trade_ledger=None)
    oe._finalize_buy_fill = lambda *a, **k: _buy_result()  # type: ignore
    ex.place_market_buy.return_value = {"success": True, "order_id": "x"}
    r = oe.execute_buy("LINK-USD", 75.0, force_market=True)
    assert r.get("success") is True
    assert oe.trade_ledger is None


def test_trade_executor_buy_writes_ledger(tmp_path: Path) -> None:
    from trading.executor import TradeExecutor

    ledger = TradeLedger(base_dir=tmp_path)
    client = MagicMock()
    client.shadow_mode = False
    client.mode = "live"
    client.place_market_buy.return_value = {
        "success": True,
        "order_id": "te-buy-1",
        "entry_price": 12.658,
        "size": 5.92,
    }
    client.get_price.return_value = 12.658
    te = TradeExecutor(client=client, trade_ledger=ledger, logger=MagicMock())
    r = te.execute_buy("LINK-USD", 75.0)
    assert r.get("success") is True
    lines = ledger.jsonl_path.read_text().strip().splitlines()
    assert lines, "TradeExecutor BUY must journal"
    rec = json.loads(lines[-1])
    assert rec["pair"] == "LINK-USD"
    assert str(rec["side"]).upper() == "BUY"
    assert rec.get("order_id") == "te-buy-1"
    assert float(rec.get("qty") or 0) > 0


def test_trade_executor_sell_writes_exit_price(tmp_path: Path) -> None:
    from trading.executor import TradeExecutor

    ledger = TradeLedger(base_dir=tmp_path)
    client = MagicMock()
    client.shadow_mode = False
    client.mode = "live"
    client.place_market_sell.return_value = {
        "success": True,
        "order_id": "te-sell-1",
        "exit_price": 12.65,
        "average_filled_price": 12.65,
        "filled_size": 5.92,
    }
    client.get_price.return_value = 12.65
    te = TradeExecutor(client=client, trade_ledger=ledger, logger=MagicMock())
    r = te.execute_sell("LINK-USD", 5.92)
    assert r.get("success") is True
    rec = json.loads(ledger.jsonl_path.read_text().strip().splitlines()[-1])
    assert str(rec["side"]).upper() == "SELL"
    assert float(rec.get("exit_price") or rec.get("entry_price") or 0) > 0
    assert rec.get("order_id") == "te-sell-1"


def test_log_trade_idempotent_by_order_id(tmp_path: Path) -> None:
    ledger = TradeLedger(base_dir=tmp_path)
    row = {
        "pair": "LINK-USD",
        "side": "BUY",
        "qty": 5.92,
        "entry_price": 12.65,
        "order_id": "same-oid",
        "mode": "live",
        "signal_source": "test",
    }
    ledger.log_trade(dict(row))
    ledger.log_trade(dict(row))
    lines = [ln for ln in ledger.jsonl_path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1, f"duplicate order_id must not double-count: {len(lines)}"


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        test_order_executor_writes_buy_when_ledger_wired(p / "oe")
        test_order_executor_without_ledger_writes_nothing(p / "none")
        test_trade_executor_buy_writes_ledger(p / "te_buy")
        test_trade_executor_sell_writes_exit_price(p / "te_sell")
        test_log_trade_idempotent_by_order_id(p / "dedupe")
    print("ledger write path isolation PASS")
