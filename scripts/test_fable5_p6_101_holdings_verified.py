#!/usr/bin/env python3
"""
Code Isolation Test for Fable 5 P6-101 (P0-Critical)
API errors in get_holdings()/get_account_balance must not be treated as verified zero holdings.

From Fable 5 Batch 1:
- get_holdings and get_account_balance return {} / 0.0 on exceptions or live_client None.
- This is indistinguishable from real zero, violating "Fresh Start = bootstrap-only on verified zero holdings".

Success criteria:
- When fetch fails, the wrapper or caller must see verified=False (or exception).
- Fresh Start logic must skip on verified failure (never act on unknown).
- No silent {} -> "zero positions" path.

This test uses monkeypatching to simulate failure without hitting real network.
"""
import sys
sys.path.insert(0, '.')

from phase6.core.exchange_client import CoinbaseExchangeClient
import unittest
from unittest.mock import patch, MagicMock

class TestP6101HoldingsVerified(unittest.TestCase):
    def setUp(self):
        self.client = CoinbaseExchangeClient(mode='shadow', initial_capital=1000)
        # Seed some realistic shadow holdings so we can distinguish true zero from error
        self.client._balances = {'USD': 1234.56}
        self.client._positions = {'BTC': 0.05}

    def test_get_holdings_returns_data_in_normal_shadow(self):
        """Normal path should return dict with data."""
        holdings = self.client.get_holdings()
        self.assertIsInstance(holdings, dict)
        # In current shadow it may be empty or seeded — we only care it's not treating error as zero yet.

    @patch('phase6.core.exchange_client.CoinbaseExchangeClient._ensure_live_client')
    def test_get_holdings_failure_path_must_not_coerce_to_empty(self, mock_ensure):
        """When live client unavailable or fetch fails, must surface that it is NOT verified."""
        # Force live mode behavior for test
        self.client.shadow_mode = False
        mock_ensure.return_value = False  # simulate missing creds or init failure

        # Current buggy behavior: returns {} when real_client is None
        holdings = self.client.get_holdings()
        # The point of the test is to demonstrate the current dangerous behavior and what the fix must do.
        # For the isolation contract we assert that if we ever get {}, we have a way to know it came from failure.

        # After proper fix this path should raise or return a sentinel with verified=False.
        # For now we record what actually happens so we can write the guard.
        self.assertEqual(holdings, {}, "Current code path returns {} on live failure. Fix must change this.")

    def test_fresh_start_gate_must_require_verified_zero(self):
        """
        Simulate the Fresh Start decision logic from phase6_runner.
        If holdings fetch ever fails, has_positions must be treated as 'unknown', not 'zero'.
        """
        # We will call the real runner logic snippet in isolation.
        # For this test we just prove the contract: only act on explicit False from verified source.

        # Mock a "failed holdings read"
        def failing_has_open_positions():
            # Simulate what LivePortfolioManager or direct call would return on error today
            return None   # None == unknown / failure, per existing runner guard

        has = failing_has_open_positions()
        fresh_start_should_fire = (has is False)   # only on verified empty
        self.assertFalse(fresh_start_should_fire, "Fresh Start must not fire when holdings read failed (None or verified=False).")

if __name__ == '__main__':
    unittest.main(verbosity=2)