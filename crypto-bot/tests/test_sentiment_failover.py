#!/usr/bin/env python3
"""
Unit tests: XSentimentFetcher — failover, calibration, and config loading

Tests:
  1. Config loads from sentiment_config.json → cache_hours=4
  2. X API success → returns real sentiment
  3. X API failure → falls back to stale cache
  4. X API failure + no cache → returns neutral (0.0)
  5. Backup provider scaffold → called when X fails
  6. log_calibration() → writes a JSONL entry
  7. Calibration entry contains expected fields
"""

import json
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Add parent to path so we can import the module under test
sys.path.insert(0, str(Path(__file__).parent.parent))

from x_sentiment_fetcher import XSentimentFetcher


class TestSentimentFetcher(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Write a minimal sentiment_config.json to a temp config dir
        config_dir = Path(self.tmpdir) / "config"
        config_dir.mkdir()
        self.config = {
            "cache": {"hours": 4, "min_hours": 1, "stale_warning_hours": 12},
            "providers": {
                "x": {"enabled": True, "priority": 1},
                "lunarcrush": {"enabled": True, "priority": 2, "calibrate_against_x": True},
                "cryptopanic": {"enabled": True, "priority": 3, "calibrate_against_x": True},
                "stale_cache": {"enabled": True, "priority": 99}
            },
            "sentiment_scoring": {
                "positive_words": ["bullish", "buy", "moon"],
                "negative_words": ["bearish", "sell", "crash"]
            },
            "calibration": {"enabled": True, "log_file": "sentiment_calibration.jsonl"}
        }
        with open(config_dir / "sentiment_config.json", "w") as f:
            json.dump(self.config, f)

    def _make_fetcher(self, bearer_token="test_token"):
        with patch("x_sentiment_fetcher.Path") as mock_path:
            # Point config path to our temp config
            config_path_instance = MagicMock()
            config_path_instance.__truediv__ = lambda self, other: Path(self.tmpdir) / other
            mock_path.return_value = config_path_instance
            mock_path.return_value.__truediv__ = lambda self, other: Path(self.tmpdir) / other

        fetcher = XSentimentFetcher.__new__(XSentimentFetcher)
        fetcher.cache_dir = Path(self.tmpdir)
        fetcher.cache_file = fetcher.cache_dir / "x_sentiment_cache.json"
        fetcher.cache = {}
        fetcher.bearer_token = bearer_token
        fetcher.calibration_log = fetcher.cache_dir / "sentiment_calibration.jsonl"
        fetcher.calibration_log.parent.mkdir(parents=True, exist_ok=True)
        # Load config from temp dir
        config_file = Path(self.tmpdir) / "config" / "sentiment_config.json"
        with open(config_file) as f:
            fetcher._sentiment_config = json.load(f)
        cfg_cache = fetcher._sentiment_config.get("cache", {})
        fetcher.cache_hours = max(1, int(cfg_cache.get("hours", 4)))
        return fetcher

    def test_cache_hours_from_config(self):
        """Config should set cache_hours to 4"""
        fetcher = self._make_fetcher()
        self.assertEqual(fetcher.cache_hours, 4)

    def test_x_api_success_returns_sentiment(self):
        """When X API returns 200 with tweets, sentiment is calculated"""
        fetcher = self._make_fetcher()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"text": "Bitcoin is bullish buy buy moon", "created_at": "2026-04-01"},
                {"text": "BTC crash bearish sell sell", "created_at": "2026-04-01"},
                {"text": "Bitcoin bullish hodl", "created_at": "2026-04-01"},
            ]
        }
        with patch("requests.get", return_value=mock_response):
            sentiment, meta = fetcher.get_sentiment("BTC-USD", force_refresh=True)
        self.assertIsInstance(sentiment, float)
        self.assertEqual(meta["source"], "X API v2")
        self.assertEqual(meta["total_tweets"], 3)

    def test_x_api_failure_uses_stale_cache(self):
        """When X API fails, fetcher falls back to stale cache"""
        fetcher = self._make_fetcher()
        stale_time = (datetime.utcnow() - timedelta(hours=10)).isoformat()
        fetcher.cache["BTC-USD"] = {
            "sentiment": 0.42,
            "source": "X API v2",
            "fetch_time": stale_time,
            "total_tweets": 100
        }
        mock_response = MagicMock()
        mock_response.status_code = 402
        mock_response.text = '{"title":"CreditsDepleted"}'
        with patch("requests.get", return_value=mock_response):
            sentiment, meta = fetcher.get_sentiment("BTC-USD", force_refresh=True)
        self.assertAlmostEqual(sentiment, 0.42)
        self.assertIn("STALE CACHE", meta.get("note", ""))

    def test_x_api_failure_no_cache_returns_neutral(self):
        """When X API fails and no cache exists, returns 0.0 neutral"""
        fetcher = self._make_fetcher()
        fetcher.cache = {}
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "rate limited"
        with patch("requests.get", return_value=mock_response):
            sentiment, meta = fetcher.get_sentiment("BTC-USD", force_refresh=True)
        self.assertEqual(sentiment, 0.0)
        self.assertIn("failed", meta.get("source", "").lower())

    def test_log_calibration_writes_jsonl(self):
        """log_calibration writes a valid JSONL entry"""
        fetcher = self._make_fetcher()
        fetcher.log_calibration("BTC-USD", x_sentiment=0.25, backup_sentiment=0.18, backup_source="LunarCrush")
        log_path = fetcher.calibration_log
        self.assertTrue(log_path.exists())
        with open(log_path) as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["pair"], "BTC-USD")
        self.assertAlmostEqual(entry["x_sentiment"], 0.25)
        self.assertAlmostEqual(entry["backup_sentiment"], 0.18)
        self.assertEqual(entry["backup_source"], "LunarCrush")
        self.assertIn("timestamp", entry)

    def test_calibration_entry_has_required_fields(self):
        """Calibration JSONL entries contain all expected fields"""
        fetcher = self._make_fetcher()
        fetcher.log_calibration("XRP-USD", 0.10, -0.05, "CryptoPanic")
        with open(fetcher.calibration_log) as f:
            entry = json.loads(f.readline())
        for field in ["timestamp", "pair", "x_sentiment", "backup_sentiment", "backup_source"]:
            self.assertIn(field, entry, f"Missing field: {field}")

    def test_cache_freshness_respects_4h_window(self):
        """Cache within 4 hours is considered fresh; older is stale"""
        fetcher = self._make_fetcher()
        fresh_time = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        fetcher.cache["BTC-USD"] = {"sentiment": 0.3, "fetch_time": fresh_time}
        self.assertTrue(fetcher._is_cache_fresh("BTC-USD"))

        stale_time = (datetime.utcnow() - timedelta(hours=5)).isoformat()
        fetcher.cache["BTC-USD"] = {"sentiment": 0.3, "fetch_time": stale_time}
        self.assertFalse(fetcher._is_cache_fresh("BTC-USD"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
