#!/usr/bin/env python3
"""
Code Isolation Test for Fable 5 P6-132/133 (P0-Critical)
- get_positions must be importable from the class (not buried under if __name__)
- Must return verified sentinel shape, never treat unverified/error as zero for Fresh Start
- Fresh Start gate only triggers on explicit verified zero (not None or {})

Based on phase6/core/live_portfolio_manager.py and phase6/core/phase6_runner.py tri-state logic.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)).replace('/scripts',''))

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.live_portfolio_manager import LivePortfolioManager
from phase6.core.phase6_runner import Phase6Runner  # to inspect gate logic

import unittest
from unittest.mock import patch, MagicMock

class TestP6132_133LPMVerified(unittest.TestCase):

    def test_get_positions_is_class_method_not_name_main(self):
        """P6-132: Method must exist when module is imported."""
        self.assertTrue(hasattr(LivePortfolioManager, 'get_positions'))
        # Instantiate in shadow to confirm no AttributeError on normal use
        client = CoinbaseExchangeClient(mode='shadow', initial_capital=1000)
        lpm = LivePortfolioManager(client)
        pos = lpm.get_positions()
        self.assertIsInstance(pos, (dict, type(None)))  # can be internal state

    def test_lpm_returns_verified_shape_on_good_path(self):
        """Good path should give positions and be usable."""
        client = CoinbaseExchangeClient(mode='shadow', initial_capital=1000)
        lpm = LivePortfolioManager(client)
        # Force realistic holdings in shadow (the client should support this)
        holdings = lpm.exchange.get_holdings_verified()
        self.assertIn('verified', holdings)
        # After refresh, get_positions should not be the error case
        pos = lpm.get_positions(force_refresh=True)
        # In current implementation it may return internal; the key is it didn't crash and didn't claim verified zero incorrectly
        self.assertNotEqual(pos, {})  # after successful shadow init it has data or handled

    def test_lpm_unverified_error_path_does_not_coerce_to_zero(self):
        """P6-133: Error/unverified must surface verified=False equivalent, not {} or None as zero."""
        # Simulate bad client
        bad_client = MagicMock()
        bad_client.get_holdings_verified.return_value = {"positions": {}, "verified": False, "error": "api failure"}
        lpm = LivePortfolioManager(bad_client)
        lpm.refresh()
        # positions kept or None, but has_open_positions should return None (not False)
        has = lpm.has_open_positions()
        self.assertIsNone(has, "Unverified should return None for safety (tri-state), not False/zero")

    def test_fresh_start_gate_requires_explicit_verified_zero(self):
        """Simulate runner Fresh Start decision (from phase6_runner.run() logic).
        Only explicit verified empty (has_positions is False, not None) should trigger.
        """
        # Good verified zero case
        good_zero_client = MagicMock()
        good_zero_client.get_holdings_verified.return_value = {"positions": {}, "verified": True, "error": None}
        lpm_zero = LivePortfolioManager(good_zero_client)
        has_zero = lpm_zero.has_open_positions()
        self.assertIs(has_zero, False, "Explicit verified zero -> False (trigger Fresh Start)")

        # Error/non-verified case must NOT trigger
        err_client = MagicMock()
        err_client.get_holdings_verified.return_value = {"positions": {}, "verified": False, "error": "transient"}
        lpm_err = LivePortfolioManager(err_client)
        has_err = lpm_err.has_open_positions()
        self.assertIsNone(has_err, "Error path must return None, not trigger Fresh Start")

if __name__ == '__main__':
    unittest.main(verbosity=2)
