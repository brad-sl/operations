#!/usr/bin/env python3
"""Isolation: SL_MISSING_EXCHANGE false-page grace (CR-03 + hold-locked)."""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase6.monitor_reentry_sl_tp import (  # noqa: E402
    classify_sl_missing,
    _cr03_schedule_near,
    _cr03_suspend_in_flight,
    _log_wall_to_utc,
)


def test_classify() -> None:
    assert classify_sl_missing(has_open_stop=True, hold_frac=0.0, cr03_active=True) == "ok_orders"
    assert classify_sl_missing(has_open_stop=False, hold_frac=None, cr03_active=True) == "note_cr03"
    assert (
        classify_sl_missing(has_open_stop=False, hold_frac=0.98, cr03_active=False)
        == "note_hold_locked"
    )
    assert (
        classify_sl_missing(has_open_stop=False, hold_frac=0.5, cr03_active=False)
        == "alert_missing"
    )
    assert (
        classify_sl_missing(has_open_stop=False, hold_frac=None, cr03_active=False)
        == "alert_missing"
    )
    # CR-03 wins over hold (still a note, not page)
    assert classify_sl_missing(has_open_stop=False, hold_frac=0.99, cr03_active=True) == "note_cr03"


def test_schedule_near_pt_slots() -> None:
    # 09:00:30 PT → near
    local = datetime(2026, 9, 5, 9, 0, 30, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert _cr03_schedule_near(local.astimezone(timezone.utc)) is True
    # 09:00:52 PT — exact collision with today's false page
    local2 = datetime(2026, 9, 5, 9, 0, 52, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert _cr03_schedule_near(local2.astimezone(timezone.utc)) is True
    # midday quiet
    local3 = datetime(2026, 9, 5, 12, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert _cr03_schedule_near(local3.astimezone(timezone.utc)) is False
    # 21:06 PT second slot
    local4 = datetime(2026, 9, 5, 21, 6, 10, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert _cr03_schedule_near(local4.astimezone(timezone.utc)) is True


def test_suspend_in_flight_from_log() -> None:
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "runner.log"
        # wall clock PT strings as runner writes them
        log.write_text(
            "2026-09-05 09:00:52,054 - phase6.core.rebalance_coordinator - INFO - "
            "[CR-03] Entered suspend_reattach_context - performing rebalance body\n"
        )
        now = datetime(2026, 9, 5, 9, 0, 55, tzinfo=ZoneInfo("America/Los_Angeles")).astimezone(
            timezone.utc
        )
        active, why = _cr03_suspend_in_flight(now, log_path=log)
        assert active is True, why
        assert "suspend_open" in why

        # after reattach + settle, quiet
        log.write_text(
            log.read_text()
            + "2026-09-05 09:01:08,022 - phase6.core.stop_loss_coordinator - INFO - "
            "[CR-03] Re-attached stops for 2 pairs: ['PAXG-USD', 'LINK-USD']\n"
        )
        later = datetime(2026, 9, 5, 9, 5, 0, tzinfo=ZoneInfo("America/Los_Angeles")).astimezone(
            timezone.utc
        )
        active2, why2 = _cr03_suspend_in_flight(later, log_path=log)
        assert active2 is False, why2

        # immediately after reattach still settle grace
        settle = datetime(2026, 9, 5, 9, 1, 20, tzinfo=ZoneInfo("America/Los_Angeles")).astimezone(
            timezone.utc
        )
        active3, why3 = _cr03_suspend_in_flight(settle, log_path=log)
        assert active3 is True, why3
        assert "reattach_settle" in why3


def test_log_wall_pt() -> None:
    dt = _log_wall_to_utc("2026-09-05 09:00:52")
    assert dt is not None
    assert dt.tzinfo is not None
    # 09:00 PT = 16:00 UTC in September (PDT)
    assert dt.hour == 16 and dt.minute == 0


def main() -> int:
    test_classify()
    print("PASS classify")
    test_schedule_near_pt_slots()
    print("PASS schedule")
    test_suspend_in_flight_from_log()
    print("PASS suspend_in_flight")
    test_log_wall_pt()
    print("PASS log_wall")
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
