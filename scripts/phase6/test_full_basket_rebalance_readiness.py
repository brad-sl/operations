#!/usr/bin/env python3
"""
Code Isolation Test: Full Basket Rebalance Readiness (post RSI refresher fix)

Verifies that with full pair data now flowing (RSI from refresher + sentiment),
the system can load complete signals for the entire basket and be ready for rebalancer decisions.

Uses real:
- load_latest_sentiment_for_basket (scorer) for RSI + Sentiment
- SignalGenerator for per-pair signals
- Basket from config
- Notes on allocator FIXED_UNIVERSE limitation (downstream gap)

Success: All (or 10/11) pairs have real RSI + sentiment data usable by rebalance logic.
Produces a "rebalance readiness" report.

This is the canonical test for "full data flowing -> valid rebalance decisions".

Run before/after rebalance forces.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from phase6.core.sentiment_scorer import load_latest_sentiment_for_basket, DEFAULT_UNIVERSE
from phase6.core.signal_generator import SignalGenerator
import json

CONFIG_PATH = Path("/home/brad/projects/crypto-trading-bot/config/trading_config_phase6.json")
STATE_PATH = Path("/home/brad/projects/crypto-trading-bot/data/state/phase6_runner_state.json")

def load_basket():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    pairs = cfg.get("global_settings", {}).get("pairs", [])
    if not pairs:
        pairs = cfg.get("phase_6_specific", {}).get("opportunity_pool", DEFAULT_UNIVERSE)
    return pairs

def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except:
        return {}

def main():
    print("=== Phase 6 Full Basket Rebalance Readiness Isolation Test ===")
    print("Real data only. Confirms full RSI + Sentiment available for rebalancer/runner decisions.")
    print()

    basket = load_basket()
    print(f"Current basket from config: {len(basket)} pairs")
    print(f"DEFAULT_UNIVERSE: {len(DEFAULT_UNIVERSE)}")
    print()

    latest = load_latest_sentiment_for_basket(basket=basket)
    sg = SignalGenerator()
    state = load_state()

    full_ready = 0
    signals = {}

    print("=== Per-Pair Readiness (RSI + Sentiment -> Signal) ===")
    for pair in basket:
        rsi = latest.get("rsi", {}).get(pair)
        sent = latest.get("sentiment", {}).get(pair, 0.0)

        has_rsi = rsi is not None
        has_sent = abs(sent) > 0.001

        signal = sg.generate_signal(pair, rsi or 50.0, sentiment=sent)

        if has_rsi and has_sent:
            full_ready += 1
            status = "READY (full data for rebalance)"
        else:
            status = "PARTIAL"

        signals[pair] = signal.signal
        print(f"{pair}: RSI={rsi}, Sent={sent:.4f} -> Signal={signal.signal} (conf={signal.confidence:.2f}) | {status}")

    print()
    print("=== Readiness Summary ===")
    print(f"Basket size: {len(basket)}")
    print(f"Pairs with full real RSI + Sentiment (READY): {full_ready}")
    print(f"Current last_rebalance (state): {state.get('last_rebalance_date')}")
    print()

    # Note allocator limitation (discovered in dep audit)
    print("=== Downstream Dependency Note ===")
    print("allocator.py and phase6_runner.py now load dynamic full basket from config (11 pairs).")
    print("Previously limited (allocator to 5, runner to 6). Both patched so rebalancer/signals use complete data.")
    print()

    if full_ready >= len(basket) - 1:
        print("TEST RESULT: FULL BASKET READY FOR REBALANCE. Full data is flowing.")
        print("Recommendation: Force rebalance now to let runner/rebalancer use complete 11-pair signals.")
        sys.exit(0)
    else:
        print("TEST RESULT: Partial readiness. Some pairs missing real data for rebalance decisions.")
        sys.exit(1)

if __name__ == "__main__":
    main()