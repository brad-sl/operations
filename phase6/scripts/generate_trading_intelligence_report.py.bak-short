#!/usr/bin/env python3
"""
Phase 6 Trading Intelligence Report (enhanced for full basket coverage)

Now uses the canonical sentiment_scorer.load_latest_sentiment_for_basket
to report RSI + Sentiment for the *full* current trading basket (11+ pairs).

Includes:
- Per-pair RSI (from cache/DB via scorer), Sentiment (X primary + real Reddit), effective score, status (FULL / RSI-ONLY / etc.)
- Coverage summary (how many have both real signals)
- Current runner state snapshot (last rebalance, etc.)
- Recommendation on rebalance (especially now that full data is flowing)
- Real data only.

This replaces the previous stub. Called by hermes twice-daily-trading-intelligence cron (0 9,21).

Run: python3 phase6/scripts/generate_trading_intelligence_report.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from phase6.core.sentiment_scorer import load_latest_sentiment_for_basket, DEFAULT_UNIVERSE
from phase6.core.signal_generator import SignalGenerator

STATE_PATH = Path("/home/brad/projects/crypto-trading-bot/data/state/phase6_runner_state.json")
CONFIG_PATH = Path("/home/brad/projects/crypto-trading-bot/config/trading_config_phase6.json")
RSI_CACHE_PATH = Path("/home/brad/projects/crypto-trading-bot/data/state/rsi_cache.json")

def load_basket():
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        pairs = cfg.get("global_settings", {}).get("pairs", [])
        if not pairs:
            pairs = cfg.get("phase_6_specific", {}).get("opportunity_pool", DEFAULT_UNIVERSE)
        return pairs[:11]  # focus on core 11 for reports
    except Exception:
        return DEFAULT_UNIVERSE[:11]

def load_runner_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"last_rebalance_date": "unknown", "last_updated": "unknown"}

def load_rsi_cache():
    try:
        with open(RSI_CACHE_PATH) as f:
            return json.load(f).get("rsi", {})
    except Exception:
        return {}

def main():
    print("=== Phase 6 Trading Intelligence Report ===")
    print(f"Generated: {datetime.utcnow().isoformat()} UTC")
    print()

    basket = load_basket()
    print(f"Full basket under review: {len(basket)} pairs -> {basket}")
    print(f"DEFAULT_UNIVERSE in scorer: {len(DEFAULT_UNIVERSE)}")
    print()

    # Load full real data
    latest = load_latest_sentiment_for_basket(basket=basket)
    rsi_cache = load_rsi_cache()
    state = load_runner_state()

    # Generate signals for context
    sg = SignalGenerator()

    print("=== Per-Pair Full Data (RSI + Sentiment) ===")
    full_count = 0
    rsi_count = 0
    sent_count = 0

    for pair in basket:
        rsi_val = latest.get("rsi", {}).get(pair)
        sent_val = latest.get("sentiment", {}).get(pair, 0.0)
        posts = latest.get("posts", {}).get(pair, 0)  # may not be present
        # Fallback from cache for freshness note
        cache_entry = rsi_cache.get(pair, {})
        rsi_src = "cache" if pair in rsi_cache else "db (scorer)"
        if cache_entry.get("fresh"):
            rsi_src = f"cache (fresh, {cache_entry.get('candle_count', '?')} candles)"

        has_rsi = rsi_val is not None and abs(rsi_val) > 0.1
        has_sent = abs(sent_val) > 0.001 or (posts and posts >= 5)

        if has_rsi:
            rsi_count += 1
        if has_sent:
            sent_count += 1
        if has_rsi and has_sent:
            full_count += 1
            status = "FULL"
        elif has_rsi:
            status = "RSI-ONLY"
        elif has_sent:
            status = "SENT-ONLY"
        else:
            status = "MISSING"

        # Quick signal for context (using available rsi + sent)
        signal = sg.generate_signal(pair, rsi_val or 50.0, sentiment=sent_val or 0.0)

        print(f"{pair}:")
        print(f"  RSI: {rsi_val if rsi_val is not None else 'N/A'} ({rsi_src})")
        print(f"  Sentiment: {sent_val:.4f} (effective from scorer)")
        print(f"  Signal: {signal.signal} (conf={signal.confidence:.2f}) reason: {signal.reason}")
        print(f"  Status: {status}")
        print()

    print("=== Coverage Summary ===")
    print(f"Basket size: {len(basket)}")
    print(f"Pairs with RSI data: {rsi_count}")
    print(f"Pairs with real non-trivial Sentiment: {sent_count}")
    print(f"Pairs with BOTH (FULL): {full_count}")
    print()

    print("=== Runner / Rebalance State ===")
    print(f"last_rebalance_date: {state.get('last_rebalance_date')}")
    print(f"last_updated: {state.get('last_updated')}")
    print()

    print("=== Recommendation (post full-RSI-refresher fix) ===")
    if full_count >= len(basket) - 1:
        print("Full (or near-full) basket data is now flowing via RSI refresher + sentiment.")
        print("The previous force rebalance (~12:15) occurred before the complete RSI cache update.")
        print("RECOMMEND: Force a rebalance now (touch flag) to re-optimize allocations using the complete 11-pair signals + current sentiment.")
        print("This will allow downstream runner/rebalancer to make decisions on the full dynamic basket.")
    else:
        print("Coverage still incomplete for some pairs. Monitor the 15m RSI + 30m sentiment crons.")
        print("Do not force rebalance until coverage >= 10/11.")

    print()
    print("Report complete. Real data only. See docs/RSI_SENTIMENT_DATA_FLOW_DEPENDENCIES.md for flow.")

if __name__ == "__main__":
    main()