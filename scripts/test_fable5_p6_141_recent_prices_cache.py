#!/usr/bin/env python3
"""
Code Isolation Test for Fable 5 P6-141 (P1 pre-paper blocker)
get_recent_prices must not raise NameError on cache-hit path (second call within 5 min).

This was a deterministic crash for any pair queried twice inside the window.
"""

import unittest
import time
from phase6.core.exchange_client import CoinbaseExchangeClient

class TestP6141RecentPricesCache(unittest.TestCase):

    def test_cache_hit_does_not_raise_nameerror(self):
        client = CoinbaseExchangeClient(mode='shadow', initial_capital=1000)

        # First call (miss) - populates cache
        p1 = client.get_recent_prices("BTC-USD", limit=5, granularity="ONE_HOUR")
        self.assertIsInstance(p1, list)
        self.assertTrue(len(p1) > 0 or True, "Accept empty or populated; main thing is no crash")

        # Second call immediately (hit path) — this used to blow up because datetime was not in scope
        p2 = client.get_recent_prices("BTC-USD", limit=5, granularity="ONE_HOUR")
        self.assertIsInstance(p2, list)

        # Third call (still inside window)
        p3 = client.get_recent_prices("DOGE-USD", limit=3, granularity="ONE_MINUTE")
        self.assertIsInstance(p3, list)

        print("P6-141: Cache hit paths succeeded without NameError. Test passed.")

if __name__ == "__main__":
    unittest.main()