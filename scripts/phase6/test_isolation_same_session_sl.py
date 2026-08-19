#!/usr/bin/env python3
"""Isolation: same-session BUY → SL metric (P6-SAME-SESSION-SL-METRIC-20260813)."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.same_session_sl import (  # noqa: E402
    find_same_session_events,
    format_brief_line,
    ops_finding_if_any,
    summarize,
)


def _row(ts: datetime, pair: str, side: str, reason: str) -> dict:
    return {
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "pair": pair,
        "side": side,
        "reason": reason,
        "qty": 1.0,
        "order_id": f"{pair}-{side}-{int(ts.timestamp())}",
    }


def main() -> int:
    now = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
    t0 = now - timedelta(hours=3)
    # In window: BUY then SL 6 minutes later
    buy_in = t0 + timedelta(minutes=10)
    sl_in = buy_in + timedelta(minutes=6)
    # Out of window: BUY then SL 3h later
    buy_out = t0
    sl_out = buy_out + timedelta(hours=3)
    # Under 5m
    buy_fast = t0 + timedelta(hours=1)
    sl_fast = buy_fast + timedelta(minutes=2)
    # Non-SL sell should not count
    buy_rot = t0 + timedelta(hours=1, minutes=30)
    rot = buy_rot + timedelta(minutes=4)

    rows = [
        _row(buy_out, "BTC-USD", "BUY", "rebalance_buy"),
        _row(sl_out, "BTC-USD", "SELL", "stop_loss_exchange"),
        _row(buy_in, "RAVE-USD", "BUY", "rebalance_buy"),
        _row(sl_in, "RAVE-USD", "SELL", "stop_loss_exchange"),
        _row(buy_fast, "LINK-USD", "BUY", "rebalance_buy"),
        _row(sl_fast, "LINK-USD", "SELL", "stop_loss_exchange"),
        _row(buy_rot, "ETH-USD", "BUY", "rebalance_buy"),
        _row(rot, "ETH-USD", "SELL", "rotation_exchange"),
    ]

    events = find_same_session_events(
        rows, window=timedelta(hours=2), lookback=timedelta(days=7), now=now
    )
    pairs = {e["pair"] for e in events}
    assert "RAVE-USD" in pairs, events
    assert "LINK-USD" in pairs, events
    assert "BTC-USD" not in pairs, events  # 3h > 2h
    assert "ETH-USD" not in pairs, events
    assert any(e["under_5m"] for e in events if e["pair"] == "LINK-USD")

    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "ledger.jsonl"
        state = Path(td) / "state.json"
        with ledger.open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        s = summarize(
            ledger_path=ledger,
            window_hours=2.0,
            lookback_days=7.0,
            now=now,
            persist=True,
            state_path=state,
        )
        assert s["count_2h"] == 2, s
        assert s["count_5m"] == 1, s
        assert state.is_file()
        line = format_brief_line(s)
        assert "Same-session SL (<2h): 2" in line, line
        assert "RAVE-USD" in line and "LINK-USD" in line
        finding = ops_finding_if_any(s)
        assert finding and finding["priority"] == "medium"

        empty = summarize(
            ledger_path=Path(td) / "empty.jsonl",
            now=now,
            persist=False,
        )
        # missing file → 0
        assert empty["count_2h"] == 0
        assert format_brief_line(empty) == "Same-session SL (<2h): 0"
        assert ops_finding_if_any(empty) is None

    # Live ledger smoke (must not crash)
    live = summarize(persist=True)
    assert "count_2h" in live
    print("PASS test_isolation_same_session_sl")
    print("  fixture:", format_brief_line(s))
    print("  live:", format_brief_line(live))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
