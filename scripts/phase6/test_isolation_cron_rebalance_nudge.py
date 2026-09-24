#!/usr/bin/env python3
"""Isolation: skip force nudge when due slot completed successfully in ~10m."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.cron_rebalance_nudge import (  # noqa: E402
    decide_force_nudge,
    due_rebalance_slot_id,
    latest_daily_rebalance_event,
)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def test_due_slot_id():
    now = datetime(2026, 9, 23, 9, 5, 0)
    assert due_rebalance_slot_id(now) == "2026-09-23|09:00"
    now2 = datetime(2026, 9, 23, 8, 59, 0)
    assert due_rebalance_slot_id(now2) is None
    now3 = datetime(2026, 9, 23, 21, 5, 0)
    assert due_rebalance_slot_id(now3) == "2026-09-23|21:00"
    print("due_slot_id OK")


def test_skip_when_recent_success():
    now_local = datetime(2026, 9, 23, 9, 5, 0)
    # 09:01 finalize ~4m ago relative to fixed "now" via event ts
    event_ts = datetime(2026, 9, 23, 16, 1, 2, tzinfo=timezone.utc)  # 09:01 PT
    # Pin decide now by monkeying age via event relative to real clock is flaky —
    # pass history + compute with a patched path: use decide with synthetic age by
    # setting event to (utcnow - 4m).
    now_utc = datetime.now(timezone.utc)
    event_ts = now_utc - timedelta(minutes=4)
    rows = [
        {
            "reason": "daily_rebalance",
            "timestamp": _iso(event_ts),
            "executed": 0,
            "skipped": 1,
            "mode": "live",
        }
    ]
    state = {"rebalance_slots_completed": [due_rebalance_slot_id(now_local)]}
    d = decide_force_nudge(
        runner_running=True,
        now=now_local,
        window_minutes=10.0,
        runner_state=state,
        history_rows=rows,
    )
    assert d.should_touch is False, d
    assert d.reason == "slot_completed_recently", d
    assert d.executed == 0
    assert d.skipped == 1
    print("skip_when_recent_success OK", d.as_dict())


def test_nudge_when_slot_missing():
    now_local = datetime(2026, 9, 23, 9, 5, 0)
    now_utc = datetime.now(timezone.utc)
    rows = [
        {
            "reason": "daily_rebalance",
            "timestamp": _iso(now_utc - timedelta(minutes=3)),
            "executed": 0,
            "skipped": 0,
        }
    ]
    d = decide_force_nudge(
        runner_running=True,
        now=now_local,
        runner_state={"rebalance_slots_completed": []},
        history_rows=rows,
    )
    assert d.should_touch is True
    assert d.reason == "due_slot_not_completed"
    print("nudge_when_slot_missing OK")


def test_nudge_when_stale_finalize():
    now_local = datetime(2026, 9, 23, 9, 5, 0)
    now_utc = datetime.now(timezone.utc)
    rows = [
        {
            "reason": "daily_rebalance",
            "timestamp": _iso(now_utc - timedelta(minutes=25)),
            "executed": 0,
            "skipped": 0,
        }
    ]
    state = {"rebalance_slots_completed": [due_rebalance_slot_id(now_local)]}
    d = decide_force_nudge(
        runner_running=True,
        now=now_local,
        window_minutes=10.0,
        runner_state=state,
        history_rows=rows,
    )
    assert d.should_touch is True
    assert d.reason == "slot_complete_but_stale_finalize"
    print("nudge_when_stale_finalize OK")


def test_force_nudge_override():
    now_local = datetime(2026, 9, 23, 9, 5, 0)
    now_utc = datetime.now(timezone.utc)
    rows = [
        {
            "reason": "daily_rebalance",
            "timestamp": _iso(now_utc - timedelta(minutes=2)),
            "executed": 1,
            "skipped": 0,
        }
    ]
    state = {"rebalance_slots_completed": [due_rebalance_slot_id(now_local)]}
    d = decide_force_nudge(
        runner_running=True,
        now=now_local,
        runner_state=state,
        history_rows=rows,
        force_nudge=True,
    )
    assert d.should_touch is True
    assert d.reason == "force_nudge_override"
    print("force_nudge_override OK")


def test_nudge_on_hard_fail_blob():
    now_local = datetime(2026, 9, 23, 9, 5, 0)
    now_utc = datetime.now(timezone.utc)
    rows = [
        {
            "reason": "daily_rebalance",
            "timestamp": _iso(now_utc - timedelta(minutes=2)),
            "executed": 0,
            "skipped": [{"reason": "network unreachable"}],
            "error": "timeout",
        }
    ]
    state = {"rebalance_slots_completed": [due_rebalance_slot_id(now_local)]}
    d = decide_force_nudge(
        runner_running=True,
        now=now_local,
        runner_state=state,
        history_rows=rows,
    )
    assert d.should_touch is True
    assert d.reason == "recent_event_hard_fail"
    print("nudge_on_hard_fail_blob OK")


def test_latest_picks_daily_only():
    now_utc = datetime.now(timezone.utc)
    rows = [
        {
            "reason": "fresh_start",
            "timestamp": _iso(now_utc - timedelta(minutes=1)),
            "executed": 5,
        },
        {
            "reason": "daily_rebalance",
            "timestamp": _iso(now_utc - timedelta(minutes=5)),
            "executed": 0,
        },
    ]
    latest = latest_daily_rebalance_event(rows)
    assert latest is not None
    assert latest["reason"] == "daily_rebalance"
    assert latest["executed"] == 0
    print("latest_picks_daily_only OK")


def test_before_first_slot_no_touch():
    now_local = datetime(2026, 9, 23, 7, 0, 0)
    d = decide_force_nudge(
        runner_running=True,
        now=now_local,
        runner_state={"rebalance_slots_completed": []},
        history_rows=[],
    )
    assert d.should_touch is False
    assert d.reason == "no_due_slot_yet"
    print("before_first_slot_no_touch OK")


if __name__ == "__main__":
    test_due_slot_id()
    test_skip_when_recent_success()
    test_nudge_when_slot_missing()
    test_nudge_when_stale_finalize()
    test_force_nudge_override()
    test_nudge_on_hard_fail_blob()
    test_latest_picks_daily_only()
    test_before_first_slot_no_touch()
    print("[CRON-REBALANCE-NUDGE] PASSED")
