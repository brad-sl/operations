#!/usr/bin/env python3
"""Isolation: indicator_snapshot for RSI vs StochRSI decision/trade analysis."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import indicator_snapshot as ind
from phase6.core.decision_context import build_rebalance_context


def test_build_snapshot_from_cache():
    with tempfile.TemporaryDirectory() as td:
        cache = Path(td) / "rsi_cache.json"
        cache.write_text(
            json.dumps(
                {
                    "timestamp": "2026-07-11T00:00:00+00:00",
                    "rsi": {
                        "BTC-USD": {"rsi": 55.0, "stoch_k": 80.0, "stoch_d": 70.0, "candle_count": 100},
                        "ETH-USD": {"rsi": 40.0, "stoch_k": 10.0, "stoch_d": 15.0},
                    },
                }
            )
        )
        old = ind.RSI_CACHE
        ind.RSI_CACHE = cache
        try:
            snap = ind.build_basket_indicator_snapshot(
                universe=["BTC-USD", "ETH-USD", "SOL-USD"],
                runner_rsi_values={"SOL-USD": 48.5},
            )
            assert snap["indicator_meta"]["pairs_with_stoch_k"] == 2
            btc = snap["indicator_snapshot"]["BTC-USD"]
            assert btc["rsi"] == 55.0 and btc["stoch_k"] == 80.0
            sol = snap["indicator_snapshot"]["SOL-USD"]
            assert sol["rsi"] == 48.5 and "stoch_k" not in sol
            print("PASS build_basket_indicator_snapshot")
        finally:
            ind.RSI_CACHE = old


def test_append_history():
    with tempfile.TemporaryDirectory() as td:
        hist = Path(td) / "hist.jsonl"
        entries = {"OP-USD": {"rsi": 50.0, "stoch_k": 72.0, "stoch_d": 62.0, "candle_count": 100, "source": "x"}}
        ind.append_indicator_history(entries, run_timestamp="2026-07-11T01:00:00+00:00", history_path=hist)
        line = json.loads(hist.read_text().strip())
        assert line["pair_count"] == 1
        assert line["pairs"]["OP-USD"]["stoch_k"] == 72.0
        print("PASS append_indicator_history")


def test_rebalance_context_includes_snapshot():
    with tempfile.TemporaryDirectory() as td:
        cache = Path(td) / "rsi_cache.json"
        cache.write_text(
            json.dumps({"timestamp": "t", "rsi": {"LINK-USD": {"rsi": 48.0, "stoch_k": 86.0, "stoch_d": 85.0}}})
        )
        old = ind.RSI_CACHE
        ind.RSI_CACHE = cache
        try:
            runner = MagicMock()
            runner.FIXED_UNIVERSE = ["LINK-USD"]
            runner.rsi_values = {"LINK-USD": 48.0}
            runner.account_id = "acct"
            runner.trader_id = "t1"
            runner._last_rebalance_slot_id = None
            runner._last_strategic_brief = None
            runner._capital_events_for_decision = []
            ctx = build_rebalance_context(
                runner=runner,
                path="arch4",
                actions_taken=[{"pair": "LINK-USD", "action": "BUY", "usd": 50}],
            )
            assert "indicator_snapshot" in ctx
            assert ctx["indicator_snapshot"]["LINK-USD"]["stoch_k"] == 86.0
            assert ctx["indicator_meta"]["pairs_with_stoch_k"] == 1
            print("PASS build_rebalance_context indicator_snapshot")
        finally:
            ind.RSI_CACHE = old


if __name__ == "__main__":
    test_build_snapshot_from_cache()
    test_append_history()
    test_rebalance_context_includes_snapshot()
    print("ALL PASS")