"""
Test Price Wrapper — Isolated test data layer.

Separates test fixtures from production code. Uses PRICE_SOURCE environment variable
to switch between real Coinbase API and snapshot-based test data.

PRODUCTION RULE: Production code never touches this file.
TEST RULE: Test harnesses set PRICE_SOURCE=snapshot and use this wrapper.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class TestPriceWrapper:
    """
    Wraps price data for testing. Loads from JSON snapshots instead of API.
    
    Usage:
        import os
        os.environ['PRICE_SOURCE'] = 'snapshot'
        wrapper = TestPriceWrapper(snapshot_dir='test_fixtures')
        price_data = wrapper.get_price('BTC-USD')  # Returns snapshot data
    """
    
    def __init__(self, snapshot_dir: str = 'test_fixtures'):
        """
        Initialize test wrapper with snapshot directory.
        
        Args:
            snapshot_dir: Directory containing live_snapshot_*.json files
        """
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(exist_ok=True, parents=True)
        
        # Load most recent snapshot
        self.price_data = self._load_latest_snapshot()
        self.sentiment_data = self._load_sentiment_snapshot()
        
        logger.info(f"TestPriceWrapper initialized: {len(self.price_data)} pairs, "
                   f"{len(self.sentiment_data)} sentiment records")
    
    def _load_latest_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """
        Load most recent price snapshot (live_snapshot_*.json).
        Falls back to deterministic prices if no snapshot exists.
        
        Returns:
            {"BTC-USD": {"price": 67500, ...}, "XRP-USD": {"price": 2.50, ...}}
        """
        try:
            snapshot_files = sorted(self.snapshot_dir.glob('live_snapshot_*.json'))
            if not snapshot_files:
                logger.warning(f"No snapshots in {self.snapshot_dir}, using deterministic fallback")
                return self._deterministic_prices()
            
            latest = snapshot_files[-1]
            with open(latest, 'r') as f:
                data = json.load(f)
                logger.info(f"Loaded price snapshot: {latest.name}")
                return data
        except Exception as e:
            logger.error(f"Failed to load price snapshot: {e}, using deterministic fallback")
            return self._deterministic_prices()
    
    def _load_sentiment_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """
        Load sentiment snapshot (live_snapshot_sentiment.json).
        Falls back to empty dict if not found.
        
        Returns:
            {"BTC-USD": {"sentiment_score": 0.3, ...}, "XRP-USD": {...}}
        """
        try:
            sentiment_file = self.snapshot_dir / 'live_snapshot_sentiment.json'
            if not sentiment_file.exists():
                logger.warning(f"No sentiment snapshot found, using empty dict")
                return {}
            
            with open(sentiment_file, 'r') as f:
                data = json.load(f)
                logger.info(f"Loaded sentiment snapshot: {sentiment_file.name}")
                return data
        except Exception as e:
            logger.error(f"Failed to load sentiment snapshot: {e}")
            return {}
    
    def _deterministic_prices(self) -> Dict[str, Dict[str, Any]]:
        """
        Deterministic fallback prices for testing (UTC-hour based).
        NOT synthetic — these represent real price anchors.
        
        Returns:
            {"BTC-USD": {"price": 67500, ...}, "XRP-USD": {"price": 2.50, ...}}
        """
        utc_hour = datetime.now(timezone.utc).hour
        
        # BTC volatility: ±5% based on time of day
        btc_base = 67500.0
        btc_variance = (utc_hour - 12) / 12.0 * 0.05  # ±5% swing
        btc_price = btc_base * (1 + btc_variance)
        
        # XRP volatility: ±3% based on time of day
        xrp_base = 2.50
        xrp_variance = (utc_hour - 12) / 12.0 * 0.03  # ±3% swing
        xrp_price = xrp_base * (1 + xrp_variance)
        
        return {
            "BTC-USD": {
                "product_id": "BTC-USD",
                "price": round(btc_price, 2),
                "change_24h": 0.0,
                "change_percent_24h": 0.0,
            },
            "XRP-USD": {
                "product_id": "XRP-USD",
                "price": round(xrp_price, 2),
                "change_24h": 0.0,
                "change_percent_24h": 0.0,
            }
        }
    
    def get_price(self, product_id: str) -> Dict[str, Any]:
        """
        Get price from snapshot or deterministic fallback.
        
        Args:
            product_id: e.g., "BTC-USD"
        
        Returns:
            {"success": bool, "product_id": str, "price": float, ...}
        """
        if product_id not in self.price_data:
            logger.warning(f"Product {product_id} not in snapshot, generating deterministic price")
            prices = self._deterministic_prices()
            if product_id not in prices:
                raise ValueError(f"Unknown product: {product_id}")
            return {**prices[product_id], "success": True}
        
        data = self.price_data[product_id]
        return {
            "success": True,
            "product_id": product_id,
            "price": data.get("price", 0.0),
            "change_24h": data.get("change_24h", 0.0),
            "change_percent_24h": data.get("change_percent_24h", 0.0),
        }
    
    def get_sentiment(self, product_id: str) -> Dict[str, Any]:
        """
        Get sentiment from snapshot or UTC-hour fallback.
        
        Args:
            product_id: e.g., "BTC-USD"
        
        Returns:
            {"sentiment_score": float, "positive_tweets": int, ...}
        """
        if product_id in self.sentiment_data:
            return self.sentiment_data[product_id]
        
        # UTC-hour deterministic sentiment fallback
        utc_hour = datetime.now(timezone.utc).hour
        if 14 <= utc_hour < 21:
            sentiment = 0.3
        elif 0 <= utc_hour < 7:
            sentiment = -0.1
        else:
            sentiment = -0.2
        
        return {
            "sentiment_score": sentiment,
            "positive_tweets": 0,
            "negative_tweets": 0,
            "total_tweets": 0,
            "source": "UTC_HOUR_FALLBACK",
        }


def get_price_wrapper() -> 'TestPriceWrapper':
    """
    Factory function: Returns appropriate price wrapper based on PRICE_SOURCE.
    
    Usage:
        os.environ['PRICE_SOURCE'] = 'snapshot'
        wrapper = get_price_wrapper()
        price = wrapper.get_price('BTC-USD')
    
    Returns:
        TestPriceWrapper (test fixtures) or real CoinbaseWrapper (production)
    """
    price_source = os.getenv('PRICE_SOURCE', 'coinbase').lower()
    
    if price_source == 'snapshot':
        logger.info("Using TestPriceWrapper (snapshot mode)")
        return TestPriceWrapper()
    elif price_source == 'coinbase':
        logger.info("Using CoinbaseWrapper (real API mode)")
        from coinbase_wrapper import CoinbaseWrapper
        # Get credentials from env
        api_key = os.getenv('COINBASE_API_KEY', '')
        private_key = os.getenv('COINBASE_PRIVATE_KEY', '')
        passphrase = os.getenv('COINBASE_PASSPHRASE', '')
        return CoinbaseWrapper(api_key, private_key, passphrase, sandbox=True)
    else:
        raise ValueError(f"Invalid PRICE_SOURCE: {price_source}. Use 'coinbase' or 'snapshot'.")
