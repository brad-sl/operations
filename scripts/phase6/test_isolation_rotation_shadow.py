#!/usr/bin/env python3
"""Isolation: rotation_shadow log-only builder + decision_context attach."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import indicator_snapshot as ind
from phase6.core.decision_context import build_rebalance_context
from phase6.core.rotation_shadow import build_rotation_shadow


def test_shadow_missed_buy():
    snap = {
        "AAA-USD": {"rsi": 55.0, "stoch_k": 10.0, "stoch_d": 12.0},
        "BBB-USD": {"rsi": 32.0, "stoch_k": 85.0, "stoch_d": 80.0},
        "CCC-USD": {"rsi": 48.0, "stoch_k": 50.0, "stoch_d": 50.0},
    }
    shadow = build_rotation_shadow(
        indicator_snapshot=snap,
        actions_taken=[{"pair": "BBB-USD", "action": "BUY", "usd": 75, "reason": "rotation"}],
        holdings_before={"AAA-USD": 100.0, "BBB-USD": 50.0, "CCC-USD": 50.0},
        cash_usd=200.0,
    )
    assert shadow["live_allocator_unchanged"] is True
    assert shadow["summary"]["n_missed_stoch_buys"] >= 1
    missed_pairs = {m["pair"] for m in shadow["missed_stoch_buys"]}
    assert "AAA-USD" in missed_pairs
    flags = {f["flag"] for f in shadow["action_flags"]}
    assert "buy_stoch_overbought" in flags
    print("PASS test_shadow_missed_buy")


def test_decision_context_includes_shadow():
    with tempfile.TemporaryDirectory() as td:
        cache = Path(td) / "rsi_cache.json"
        hist = Path(td) / "price_history.json"
        cache.write_text(
            json.dumps(
                {
                    "timestamp": "t",
                    "rsi": {
                        "LINK-USD": {"rsi": 48.0, "stoch_k": 12.0, "stoch_d": 15.0},
                        "SOL-USD": {"rsi": 60.0, "stoch_k": 88.0, "stoch_d": 80.0},
                    },
                }
            )
        )
        hist.write_text(
            json.dumps({"history": {"LINK-USD": [10.0, 11.0], "SOL-USD": [100.0, 101.0]}, "last_updated": "t"})
        )
        old_c, old_h = ind.RSI_CACHE, None
        import phase6.core.rotation_shadow as rs

        # patch paths
        ind.RSI_CACHE = cache
        real_load = rs.load_price_snapshot

        def _load(uni=None):
            return {"LINK-USD": 11.0, "SOL-USD": 101.0}

        rs.load_price_snapshot = _load  # type: ignore
        try:
            runner = MagicMock()
            runner.FIXED_UNIVERSE = ["LINK-USD", "SOL-USD"]
            runner.rsi_values = {"LINK-USD": 48.0, "SOL-USD": 60.0}
            runner.account_id = "acct"
            runner.trader_id = None
            runner._last_rebalance_slot_id = None
            runner._last_strategic_brief = None
            runner._capital_events_for_decision = []
            runner.portfolio = None
            runner.exchange = None
            ctx = build_rebalance_context(
                runner=runner,
                path="arch4_rotation",
                actions_taken=[{"pair": "SOL-USD", "action": "BUY", "usd": 50, "reason": "light_tilt_cash"}],
            )
            assert "rotation_shadow" in ctx
            assert ctx["rotation_shadow"]["summary"]["n_buys"] == 1
            assert "price_snapshot" in ctx
            assert ctx["price_snapshot"]["SOL-USD"] == 101.0
            # buying overbought stoch while missing oversold
            assert ctx["rotation_shadow"]["summary"]["n_missed_stoch_buys"] >= 1
            print("PASS test_decision_context_includes_shadow")
        finally:
            ind.RSI_CACHE = old_c
            rs.load_price_snapshot = real_load  # type: ignore


if __name__ == "__main__":
    test_shadow_missed_buy()
    test_decision_context_includes_shadow()
    print("ALL PASS")
