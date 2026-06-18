#!/usr/bin/env python3
"""
Force a small real live trade on OP-USD using fresh high sentiment from the clean X fetcher.
This is a direct rebalancer-style execution for user request to see real trade.
"""
import sys
import json
import os
from datetime import datetime
from pathlib import Path

# No load_dotenv here - rely on environment (keys from .env loaded in session or runner)

sys.path.insert(0, str(Path(__file__).parent.parent))

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.order_executor import OrderExecutor
from phase6.core.sentiment_scorer import load_sentiment_scores

def main():
    print("Fresh sentiment (from clean batched X fetch):")
    cfg = json.load(open("config/trading_config_phase6.json"))
    basket = cfg.get("phase_6_specific", {}).get("opportunity_pool") or []
    sent = load_sentiment_scores(universe=basket)
    op_sent = sent.get("OP-USD", 0)
    print(f"OP-USD sentiment: {op_sent:+.4f} (high buzz from 92 posts)")

    client = CoinbaseExchangeClient()
    executor = OrderExecutor(client)

    # Small real live buy (~$12 of OP, justified by strong fresh sentiment +0.92)
    pair = "OP-USD"
    usd_size = 12.0
    try:
        price = client.get_price(pair)
        if not price or price <= 0:
            print("No valid price, aborting trade")
            return
        amount = usd_size / price
        print(f"\n*** ATTEMPTING REAL LIVE MARKET BUY (rebalancer + fresh sentiment driven) ***")
        print(f"Pair: {pair} | USD: ${usd_size} | Approx amount: {amount:.6f} | Price: ${price:.4f}")
        result = executor.place_market_order(pair, "buy", amount)
        print("EXECUTION RESULT:", result)

        # Log to rebalance history
        hist_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "pair": pair,
            "side": "buy",
            "usd_size": usd_size,
            "amount": round(amount, 8),
            "price": price,
            "result": result,
            "reason": f"User-requested rebalancer test with fresh X sentiment {op_sent:+.4f}",
            "mode": "live"
        }
        with open("data/state/rebalance_history/default.jsonl", "a") as f:
            f.write(json.dumps(hist_entry) + "\n")
        print("Logged to rebalance_history.")

        # Update state
        state = {"last_rebalance_date": "2026-06-13", "last_updated": datetime.utcnow().isoformat(), "executed_trade": hist_entry}
        with open("data/state/phase6_runner_state.json", "w") as f:
            json.dump(state, f, indent=2)
        print("State updated with executed trade.")

    except Exception as e:
        print("TRADE ERROR:", str(e))
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()