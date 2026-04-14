#!/usr/bin/env python3

# Simple smoke test for Phase 4b sentiment pipeline
# Wires in an X sentiment fetcher and prints sentiments for BTC-USD / XRP-USD

import logging
import json
from pathlib import Path

# Basic config
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Lazy import to avoid heavy deps during smoke test
try:
    from x_sentiment_fetcher import XSentimentFetcher
except Exception as e:
    logging.error(f"Could not import sentiment fetcher: {e}")
    raise

# Initialize with config-based cache hours (4 hours per spec)
import os
cache_hours = 4
fetcher = XSentimentFetcher(cache_dir=LOG_DIR, cache_hours=cache_hours)

print("\n=== Testing Phase 4b Silly Smoke Test ===\n")
for pair in ['BTC-USD', 'XRP-USD']:
    sentiment, metadata = fetcher.get_sentiment(pair, force_refresh=True)
    print(f"{pair}: {sentiment:.2f}")
    print(f"  Source: {metadata.get('source')}")
    print(f"  Tweets: {metadata.get('total_tweets', 'N/A')}")
    print()

# Optional: print calibration segment if any
cal_path = fetcher.calibration_log
if cal_path.exists():
    print("Calibration log entries:")
    with open(cal_path) as f:
        for line in f:
            print(line.strip())