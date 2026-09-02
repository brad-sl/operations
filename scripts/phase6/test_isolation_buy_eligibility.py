#!/usr/bin/env python3
"""Isolation: off-basket / missing-signal BUYs must be blocked (P0 OP-USD hole)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from phase6.core.buy_eligibility import (
        evaluate_buy_eligibility,
        filter_trade_plan_buy_eligibility,
        load_trading_basket_set,
        pair_in_live_buy_universe,
    )
    from phase6.core.paths import load_trading_basket

    basket = load_trading_basket()
    bask_set = load_trading_basket_set()
    print("basket", basket)
    assert "OP-USD" not in bask_set, "OP must not be in trading basket"
    assert "LINK-USD" in bask_set, "LINK should be in basket"
    assert not pair_in_live_buy_universe("OP-USD")
    assert pair_in_live_buy_universe("LINK-USD")
    assert pair_in_live_buy_universe("PAXG-USD")  # ballast

    # evaluate_buy_eligibility
    d_op = evaluate_buy_eligibility("OP-USD", rsi=45.0, sentiment=0.5)
    assert not d_op["allowed"] and "not_in_trading_basket" in d_op["reasons"]
    print("OP blocked:", d_op["reasons"])

    d_miss = evaluate_buy_eligibility("LINK-USD", rsi=None, sentiment=0.5)
    assert not d_miss["allowed"] and "missing_rsi" in d_miss["reasons"]
    print("LINK missing RSI blocked:", d_miss["reasons"])

    d_ok = evaluate_buy_eligibility("LINK-USD", rsi=44.0, sentiment=0.59)
    assert d_ok["allowed"], d_ok
    print("LINK ok:", d_ok)

    d_paxg = evaluate_buy_eligibility("PAXG-USD", rsi=None, sentiment=None)
    assert d_paxg["allowed"], "ballast may buy without RSI/sent"
    print("PAXG ballast ok:", d_paxg)

    # filter plan: OP ignition + LINK good + SELL kept
    plan = SimpleNamespace(
        actions=[
            {
                "pair": "OP-USD",
                "action": "BUY",
                "usd": 400,
                "ignition_scout": True,
                "entry_rsi": 51.0,
                "entry_sentiment": 0.16,
            },
            {
                "pair": "LINK-USD",
                "action": "BUY",
                "usd": 75,
                "entry_rsi": 44.0,
                "entry_sentiment": 0.59,
            },
            {"pair": "BTC-USD", "action": "SELL", "usd": 100},
            {
                "pair": "RAVE-USD",
                "action": "BUY",
                "usd": 200,
                # no rsi/sent stamps
            },
        ]
    )
    out = filter_trade_plan_buy_eligibility(
        plan,
        rsi_values={"LINK-USD": 44.0, "BTC-USD": 55.0},
        sentiment_scores={"LINK-USD": 0.59, "BTC-USD": 0.2},
        enforce=True,
    )
    pairs = [(a.get("pair"), a.get("action")) for a in out.actions]
    print("kept actions:", pairs)
    assert ("OP-USD", "BUY") not in pairs, "OP BUY must be stripped"
    assert ("RAVE-USD", "BUY") not in pairs, "RAVE off-basket must be stripped"
    assert ("LINK-USD", "BUY") in pairs
    assert ("BTC-USD", "SELL") in pairs
    blocked = getattr(out, "buy_eligibility_blocked", [])
    print("blocked:", blocked)
    assert any(b.get("pair") == "OP-USD" for b in blocked)

    # reproduce pre-fix hole: ignition-only re-filter would have kept OP if
    # only rsi_primary ran — eligibility alone is enough to kill it
    print("PASS test_isolation_buy_eligibility")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
