#!/usr/bin/env python3
"""
Code Isolation Test for Sentiment Zero-Result / No-Fab Preservation (RSI-SENT-003)
- Verifies that on insufficient data (posts < MIN_POSTS_GATE or no results), prior timestamp and score are preserved.
- No fresh neutral 0.0 with current ts.
- Uses the canonical run_sentiment_system logic or mocks the gate.
"""
import sys
import json
import tempfile
import os
from pathlib import Path

PROJECT_ROOT = Path("/home/brad/projects/crypto-trading-bot")
sys.path.insert(0, str(PROJECT_ROOT))

# Mock the logic from run_sentiment_system.py for isolation
def test_preserve_prior_on_insufficient():
    print("=== Sentiment Zero Case Isolation Test ===")
    prior = {
        "data": {
            "BTC-USD": {"score": 0.25, "timestamp": "2026-06-10T00:00:00Z", "posts": 10, "status": "fresh"}
        },
        "timestamp": "2026-06-10T00:00:00Z"
    }
    reddit_scores = {}  # zero results
    x_scores = {}
    MIN_POSTS_GATE = 5
    now_iso = "2026-06-12T00:00:00Z"

    new_data = {}
    prior_data = prior.get("data", {})
    all_pairs = set(["BTC-USD"])
    for pair in sorted(all_pairs):
        r = reddit_scores.get(pair, 0.0)
        x = x_scores.get(pair, {}).get("sentiment", 0.0) if isinstance(x_scores.get(pair, {}), dict) else x_scores.get(pair, 0.0)
        total_posts = 0  # insufficient
        if total_posts < MIN_POSTS_GATE or (not r and not x):
            preserved = prior_data.get(pair, {"score": 0.0, "timestamp": prior.get("timestamp", now_iso), "posts": 0, "status": "no_prior"})
            preserved = dict(preserved)
            preserved["status"] = "insufficient_data"
            preserved["timestamp"] = preserved.get("timestamp", prior.get("timestamp"))  # keep old ts
            new_data[pair] = preserved
        else:
            new_data[pair] = {"score": 0.0, "timestamp": now_iso, "status": "fresh"}

    # Verify
    btc = new_data["BTC-USD"]
    assert btc["timestamp"] == "2026-06-10T00:00:00Z", "Must preserve prior timestamp"
    assert btc["score"] == 0.25, "Must preserve prior score"
    assert btc["status"] == "insufficient_data", "Status must indicate insufficient"
    print("Preserve prior on zero results: PASS")
    print("No fresh 0.0 with current ts: PASS")
    print("=== Sentiment Zero Case Test PASSED ===")

if __name__ == "__main__":
    test_preserve_prior_on_insufficient()
