import unittest
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Mock class instead of importing to avoid dependency issues during test creation
class MockFetcher:
    def run(self):
        return {"BTC-USD": 0.0}

class TestSentimentGateLogic(unittest.TestCase):
    def setUp(self):
        self.cache_path = Path("/home/brad/projects/crypto-trading-bot/sentiment_cache.json")
        # Ensure dir exists
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if self.cache_path.exists():
            os.remove(self.cache_path)

    def test_gate_with_insufficient_data(self):
        # Setup prior cache
        prior_data = {
            "schema_version": "v3",
            "data": {
                "BTC-USD": {"score": 0.5, "posts": 10, "timestamp": "2026-06-01T00:00:00Z"}
            }
        }
        with open(self.cache_path, "w") as f:
            json.dump(prior_data, f)
        
        # Verify gate function
        from run_canonical_sentiment import is_insufficient
        
        self.assertTrue(is_insufficient({"posts": 0}))
        self.assertTrue(is_insufficient({"posts": 4}))
        self.assertFalse(is_insufficient({"posts": 5}))

if __name__ == "__main__":
    unittest.main()
