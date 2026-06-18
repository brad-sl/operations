#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone

# Add project root to path
sys.path.append("/home/brad/projects/crypto-trading-bot")
from run_full_sentiment_v3 import write_canonical_cache, CANONICAL_CACHE

def test_no_data_preservation():
    print("Running isolation test: 0 posts preservation...")
    
    # 1. Setup mock existing cache
    mock_old_cache = {
        "schema_version": 3,
        "timestamp": "2026-06-10T10:00:00+00:00",
        "sentiment": {"BTC-USD": 0.5, "ETH-USD": -0.2},
        "meta": {"posts_analyzed": {"BTC-USD": 10, "ETH-USD": 8}},
        "sentiment_timestamps": {"BTC-USD": "2026-06-10T10:00:00+00:00", "ETH-USD": "2026-06-10T10:00:00+00:00"}
    }
    with open(CANONICAL_CACHE, "w") as f:
        json.dump(mock_old_cache, f)

    # 2. Simulate deficient new run (e.g., failed to fetch data)
    deficient_results = {
        "BTC-USD": {"sentiment": None, "posts": 0, "timestamp": None},
        "ETH-USD": {"sentiment": -0.1, "posts": 6, "timestamp": "2026-06-10T11:00:00+00:00"}
    }

    # 3. Apply write update
    write_canonical_cache(deficient_results)

    # 4. Verify
    with open(CANONICAL_CACHE, "r") as f:
        new_cache = json.load(f)
        
    print(f"New cache: {json.dumps(new_cache, indent=2)}")
    
    # Assertions
    assert new_cache["sentiment"]["BTC-USD"] == 0.5, "Failed to preserve BTC sentiment"
    assert new_cache["sentiment"]["ETH-USD"] == -0.1, "Failed to update ETH sentiment"
    
    print("\n✅ Isolation test passed: 0-post data preserved correctly.")

if __name__ == "__main__":
    test_no_data_preservation()
