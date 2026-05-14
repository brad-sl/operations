#!/usr/bin/env python3
"""
Test suite for OptimizedPriceFetcher
Validates: batching, rate limiting, caching, fallback rotation, logging
"""

import sys
import time
import unittest
from unittest.mock import patch, MagicMock
from price_fetcher_optimized import (
    OptimizedPriceFetcher,
    TokenBucket,
    PriceCache,
    FallbackSourceRotation,
    PublicExchangePriceWrapper
)


class TestTokenBucket(unittest.TestCase):
    """Test rate limiter"""
    
    def test_token_bucket_acquire_immediate(self):
        """Should acquire token immediately if available"""
        bucket = TokenBucket(capacity=5, refill_rate_seconds=1.0)
        assert bucket.acquire(num_tokens=1, timeout=1.0) == True
    
    def test_token_bucket_capacity(self):
        """Should enforce capacity limit"""
        bucket = TokenBucket(capacity=2, refill_rate_seconds=0.5)
        assert bucket.acquire(num_tokens=2, timeout=1.0) == True
        # Should timeout trying to acquire 3rd token
        assert bucket.acquire(num_tokens=1, timeout=0.1) == False
    
    def test_token_bucket_refill(self):
        """Should refill tokens over time"""
        bucket = TokenBucket(capacity=1, refill_rate_seconds=0.1)
        assert bucket.acquire(num_tokens=1, timeout=1.0) == True
        # Should wait ~0.1s and acquire next token
        assert bucket.acquire(num_tokens=1, timeout=1.0) == True


class TestPriceCache(unittest.TestCase):
    """Test caching layer"""
    
    def test_cache_hit(self):
        """Should return cached value if fresh"""
        cache = PriceCache(ttl_seconds=30)
        cache.set('BTC-USD', 72000.0)
        
        price = cache.get('BTC-USD')
        assert price == 72000.0
        assert cache.hits == 1
    
    def test_cache_miss_expiry(self):
        """Should return None if cache expired"""
        cache = PriceCache(ttl_seconds=0.1)
        cache.set('BTC-USD', 72000.0)
        time.sleep(0.2)
        
        price = cache.get('BTC-USD')
        assert price is None
        assert cache.misses == 1
    
    def test_cache_stats(self):
        """Should track hit/miss statistics"""
        cache = PriceCache(ttl_seconds=30)
        cache.set('BTC-USD', 72000.0)
        
        cache.get('BTC-USD')  # hit
        cache.get('ETH-USD')  # miss
        
        stats = cache.get_stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1


class TestFallbackSourceRotation(unittest.TestCase):
    """Test fallback source rotation"""
    
    def test_initial_source_coingecko(self):
        """Should start with CoinGecko"""
        fallback = FallbackSourceRotation()
        assert fallback.get_available_source() == 'coingecko'
    
    def test_mark_failure_rotation(self):
        """Should rotate to next source on failure"""
        fallback = FallbackSourceRotation(cooldown_seconds=10)
        fallback.mark_failure('coingecko')
        # Should rotate to kraken (not in cooldown)
        assert fallback.get_available_source() == 'kraken'
    
    def test_cooldown_tracking(self):
        """Should track cooldown status"""
        fallback = FallbackSourceRotation(cooldown_seconds=1)
        fallback.mark_failure('coingecko')
        
        stats = fallback.get_stats()
        assert stats['coingecko']['available'] == False
        assert stats['kraken']['available'] == True


class TestOptimizedPriceFetcher(unittest.TestCase):
    """Test main fetcher"""
    
    def setUp(self):
        self.fetcher = OptimizedPriceFetcher()
    
    def test_get_price_single_pair(self):
        """Should fetch single pair"""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'bitcoin': {'usd': 72000}
            }
            mock_get.return_value = mock_response
            
            price = self.fetcher.get_price('BTC-USD')
            assert price == 72000.0
    
    def test_get_prices_batch_consolidation(self):
        """Should consolidate multiple pairs into single API call"""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'bitcoin': {'usd': 72000},
                'ethereum': {'usd': 3800},
                'solana': {'usd': 180}
            }
            mock_get.return_value = mock_response
            
            prices = self.fetcher.get_prices(['BTC-USD', 'ETH-USD', 'SOL-USD'])
            
            # Should call API once for all pairs
            assert mock_get.call_count == 1
            assert prices['BTC-USD'] == 72000.0
            assert prices['ETH-USD'] == 3800.0
            assert prices['SOL-USD'] == 180.0
    
    def test_cache_prevents_duplicate_calls(self):
        """Should use cache for subsequent calls"""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'bitcoin': {'usd': 72000}
            }
            mock_get.return_value = mock_response
            
            # First call
            prices1 = self.fetcher.get_prices(['BTC-USD'])
            api_calls_1 = mock_get.call_count
            
            # Second call (should hit cache)
            prices2 = self.fetcher.get_prices(['BTC-USD'])
            api_calls_2 = mock_get.call_count
            
            assert api_calls_1 == 1
            assert api_calls_2 == 1  # No additional call due to cache
            assert prices1['BTC-USD'] == prices2['BTC-USD']
    
    def test_429_triggers_fallback(self):
        """Should activate fallback on 429 rate limit"""
        with patch('requests.get') as mock_get:
            # First call: 429 from CoinGecko
            error_response = MagicMock()
            error_response.status_code = 429
            
            fallback_response = MagicMock()
            fallback_response.status_code = 200
            fallback_response.json.return_value = {
                'result': {
                    'XBTUSDT': {'c': [72000]}
                }
            }
            
            mock_get.side_effect = [error_response, fallback_response]
            
            prices = self.fetcher.get_prices(['BTC-USD'])
            assert prices['BTC-USD'] > 0  # Should have fallback price
    
    def test_backward_compatibility_wrapper(self):
        """Should work with old PublicExchangePriceWrapper interface"""
        wrapper = PublicExchangePriceWrapper()
        
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'bitcoin': {'usd': 72000}
            }
            mock_get.return_value = mock_response
            
            # Old interface
            price = wrapper.get_price('BTC-USD')
            assert price == 72000.0
            
            # Batch interface
            prices = wrapper.get_prices_batch(['BTC-USD', 'ETH-USD'])
            assert 'BTC-USD' in prices
    
    def test_metrics_tracking(self):
        """Should track performance metrics"""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'bitcoin': {'usd': 72000}
            }
            mock_get.return_value = mock_response
            
            self.fetcher.get_prices(['BTC-USD'])
            
            metrics = self.fetcher.get_metrics()
            assert metrics['total_requests'] == 1
            assert metrics['api_calls']['coingecko'] == 1
            assert metrics['cache_stats']['hits'] == 0  # First call


def run_tests():
    """Run all tests with detailed output"""
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    exit_code = run_tests()
    sys.exit(exit_code)
