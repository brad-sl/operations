#!/usr/bin/env python3
"""
Code Isolation Test for P6-151 (G3 critical leak) + G4 reserve projection.
get_positions / get_enriched_positions must NEVER return bare {} on error/unverified.
Must always return the sentinel shape: {"positions": ..., "verified": bool, "error": ...}
This prevents sticky holdings from seeing phantom zero and breaking reserve/funding checks.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.live_portfolio_manager import LivePortfolioManager

c = CoinbaseExchangeClient(mode="shadow")
lpm = LivePortfolioManager(exchange=c)

def test_sentinel_shape():
    # Good path
    good = lpm.get_positions()
    assert isinstance(good, dict), "get_positions must return dict"
    assert "verified" in good, "Missing verified flag (P6-151 leak)"
    assert "positions" in good, "Missing positions key"
    assert "error" in good, "Missing error key"

    good_enr = lpm.get_enriched_positions()
    assert isinstance(good_enr, dict)
    assert "verified" in good_enr, "get_enriched_positions must carry verified (G3 leak)"
    assert good_enr.get("verified") in (True, False)

    # Simulate error path by forcing unverified
    lpm.verified = False
    lpm.positions = {}
    err = lpm.get_enriched_positions()
    assert isinstance(err, dict)
    assert err.get("verified") is False, "Error path must have verified=False"
    assert "error" in err
    assert "positions" in err
    # Explicitly forbid bare {}
    assert err != {}, "Must not return bare {} on unverified/error (P6-151)"

    print("P6-151 / G3 sentinel shape: PASS (no bare {} leak)")

if __name__ == "__main__":
    test_sentinel_shape()
    print("P6-151 isolation test: ALL PASS")