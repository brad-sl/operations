#!/usr/bin/env python3
"""NEEDLE-04 isolation: same-session limit_first SL cannot void at +6m."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.same_session_sl_guard import (  # noqa: E402
    MIN_HOLD_MINUTES,
    due_deferred_attaches,
    is_limit_first_style,
    record_limit_first_fill,
    should_defer_sl_attach,
    sl_pct_too_tight_vs_fees,
    would_same_session_void,
)
from phase6.core.order_executor import OrderExecutor  # noqa: E402


SEP9_BUY = datetime(2026, 9, 9, 16, 1, tzinfo=timezone.utc)
SEP9_SL = datetime(2026, 9, 9, 16, 7, tzinfo=timezone.utc)


def test_sep9_timestamps_are_same_session_void():
    assert would_same_session_void(SEP9_BUY, SEP9_SL) is True
    assert would_same_session_void(SEP9_BUY, SEP9_BUY + timedelta(minutes=6)) is True
    assert would_same_session_void(
        SEP9_BUY, SEP9_BUY + timedelta(minutes=MIN_HOLD_MINUTES)
    ) is False


def test_limit_first_defers_attach_at_plus_6m(tmp_path: Path):
    state = tmp_path / "guard.json"
    record_limit_first_fill(
        "LINK-USD",
        fill_ts=SEP9_BUY,
        entry_price=14.0,
        size=1.73,
        order_id="sep9-buy",
        execution_style="limit_post_only",
        path=state,
    )
    defer, reason, rem = should_defer_sl_attach(
        "LINK-USD", now=SEP9_SL, execution_style="limit_post_only", path=state
    )
    assert defer is True, (reason, rem)
    assert rem > 50
    due = due_deferred_attaches(now=SEP9_SL, path=state)
    assert due == []
    due_later = due_deferred_attaches(
        now=SEP9_BUY + timedelta(minutes=MIN_HOLD_MINUTES + 1), path=state
    )
    assert len(due_later) == 1
    assert due_later[0]["pair"] == "LINK-USD"


def test_market_style_not_deferred(tmp_path: Path):
    state = tmp_path / "guard.json"
    record_limit_first_fill(
        "LINK-USD",
        fill_ts=SEP9_BUY,
        path=state,
        execution_style="limit_post_only",
    )
    defer, reason, _ = should_defer_sl_attach(
        "LINK-USD", now=SEP9_SL, execution_style="market_ioc", path=state
    )
    assert defer is False
    assert reason == "market_style"


def test_geometry_3pct_too_tight():
    assert sl_pct_too_tight_vs_fees(0.03) is True
    assert sl_pct_too_tight_vs_fees(0.08) is False


def test_finalize_limit_first_does_not_attach_inside_hold(tmp_path: Path):
    """limit_first fill → attach_stop_loss must not run inside 60m."""
    import phase6.core.same_session_sl_guard as g

    orig = g.STATE_PATH
    g.STATE_PATH = tmp_path / "guard.json"
    try:
        sl = MagicMock()
        sl.attach_stop_loss = MagicMock(return_value=True)
        sl.attach_take_profit = MagicMock(return_value=False)
        sl.config = {}

        class Ex:
            def quantize_size(self, pair, size):
                return size

        from phase6.core import sl_preflight

        sl_preflight.fetch_verified_order_fill = lambda *a, **k: {  # type: ignore
            "average_filled_price": 14.0,
            "filled_size": 1.73,
            "fill_verified": True,
        }

        oe = OrderExecutor(Ex(), sl, mode="live")
        stub = {"success": True, "order_id": "oid-sep9"}
        r = oe._finalize_buy_fill(
            "LINK-USD",
            25.0,
            stub,
            execution_style="limit_post_only",
            prefilled_entry=14.0,
            prefilled_size=1.73,
        )
        sl.attach_stop_loss.assert_not_called()
        assert r.get("sl_attached") is False
        assert r.get("sl_deferred") is True
    finally:
        g.STATE_PATH = orig


def test_is_limit_first_style():
    assert is_limit_first_style("limit_post_only")
    assert is_limit_first_style("limit_first_v1")
    assert not is_limit_first_style("market_ioc")
    assert not is_limit_first_style("limit_then_market_fallback")


if __name__ == "__main__":
    tmp = Path(tempfile.mkdtemp())
    test_sep9_timestamps_are_same_session_void()
    test_limit_first_defers_attach_at_plus_6m(tmp)
    test_market_style_not_deferred(tmp / "m")
    test_geometry_3pct_too_tight()
    test_is_limit_first_style()
    test_finalize_limit_first_does_not_attach_inside_hold(tmp / "f")
    print("test_isolation_needle_stage4_sl_guard: OK")
