#!/usr/bin/env python3
"""Regression: RSI cache must not block price_history updates."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from phase6.core.price_freshness import is_quote_stale, apply_stale_price_pnl_guard
from phase6.core.price_history_manager import PriceHistoryManager


def test_stale_quote_detection():
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    assert is_quote_stale(old) is True
    fresh = datetime.now(timezone.utc).isoformat()
    assert is_quote_stale(fresh) is False


def test_stale_hides_pnl():
    pos = {"pair": "ARB-USD", "price_stale": True, "unrealized_pnl_pct": -0.15}
    out = apply_stale_price_pnl_guard(pos)
    assert out.get("pnl_unreliable") is True
    assert out.get("unrealized_pnl_pct") is None


def test_add_price_updates_timestamp():
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "ph.json")
        mgr = PriceHistoryManager(persist_path=path)
        mgr.add_price("ARB-USD", 0.095)
        assert mgr.get_latest_price("ARB-USD") == 0.095
        assert not mgr.is_quote_stale("ARB-USD", max_age_seconds=900)


def test_fresh_state_overrides_stale_history_ts():
    from phase6.core.price_staleness import resolve_position_price_stale
    from datetime import datetime, timezone

    fresh_state = datetime.now(timezone.utc).isoformat()
    old_pair_ts = "2026-07-08T22:47:05.039232"
    pos = {"current_price": 0.095, "pair": "ARB-USD"}
    assert resolve_position_price_stale(pos, pair_quote_ts=old_pair_ts, state_as_of=fresh_state) is False


if __name__ == "__main__":
    test_stale_quote_detection()
    test_stale_hides_pnl()
    test_add_price_updates_timestamp()
    test_fresh_state_overrides_stale_history_ts()
    print("OK")