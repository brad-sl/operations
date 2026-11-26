#!/usr/bin/env python3
"""
Code Isolation Test for Rebalance Monitor Logic (Phase 6)

Imports pure evaluate_rebalance_health from monitor_phase6_runner.
Slot SSOT + date fallback + grace windows. No Telegram / no live writes.

Run:
  cd /home/brad/projects/crypto-trading-bot
  .venv/bin/python3 scripts/phase6/test_rebalance_monitor_logic.py
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "scripts" / "phase6" / "monitor_phase6_runner.py"


def _load_monitor():
    spec = importlib.util.spec_from_file_location("monitor_phase6_runner", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Avoid side effects of load_dotenv requiring network — module import is fine.
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("=== Phase 6 Rebalance Monitor Logic Isolation Test ===")
    mon = _load_monitor()
    ev = mon.evaluate_rebalance_health
    times = ["09:00", "21:00"]
    cases = []

    # Slot-based healthy: morning done, afternoon before evening grace
    cases.append(
        (
            "slots: morning done, now 12:30 same day",
            datetime(2026, 11, 25, 12, 30),
            ["2026-11-24|09:00", "2026-11-24|21:00", "2026-11-25|09:00"],
            None,
            True,
        )
    )
    # Evening not yet due
    cases.append(
        (
            "slots: morning only, now 20:02 before 21:00+grace",
            datetime(2026, 11, 25, 20, 2),
            ["2026-11-24|09:00", "2026-11-24|21:00", "2026-11-25|09:00"],
            None,
            True,
        )
    )
    # Evening missed after grace
    cases.append(
        (
            "slots: morning only, now 22:30 evening missed",
            datetime(2026, 11, 25, 22, 30),
            ["2026-11-24|09:00", "2026-11-24|21:00", "2026-11-25|09:00"],
            None,
            False,
        )
    )
    # Both today done late night
    cases.append(
        (
            "slots: both today done, 23:00",
            datetime(2026, 11, 25, 23, 0),
            [
                "2026-11-24|09:00",
                "2026-11-24|21:00",
                "2026-11-25|09:00",
                "2026-11-25|21:00",
            ],
            None,
            True,
        )
    )
    # Yesterday evening missing at next-day 03:15 (past yest 22:00 grace)
    cases.append(
        (
            "slots: missing yest 21:00, now next day 03:15",
            datetime(2026, 11, 24, 3, 15),
            ["2026-11-23|09:00"],  # no 21:00
            None,
            False,
        )
    )
    # False-alarm class: full slots through yest, early next morning
    cases.append(
        (
            "slots: full yest, now 03:15 next day (pre today windows)",
            datetime(2026, 11, 24, 3, 15),
            ["2026-11-23|09:00", "2026-11-23|21:00"],
            None,
            True,
        )
    )
    # Date fallback legacy cases
    cases.append(
        (
            "date fallback: last=today",
            datetime(2026, 6, 16, 12, 3),
            [],
            "2026-06-16",
            True,
        )
    )
    cases.append(
        (
            "date fallback: last=yest, now pre-latest-grace",
            datetime(2026, 6, 16, 12, 3),
            [],
            "2026-06-15",
            True,
        )
    )
    cases.append(
        (
            "date fallback: last=yest, now post-grace",
            datetime(2026, 6, 16, 22, 30),
            [],
            "2026-06-15",
            False,
        )
    )
    cases.append(
        (
            "date fallback: last=2d ago",
            datetime(2026, 6, 16, 12, 3),
            [],
            "2026-06-14",
            False,
        )
    )
    cases.append(
        (
            "no slots no date -> overdue",
            datetime(2026, 6, 16, 12, 3),
            [],
            None,
            False,
        )
    )

    passed = failed = 0
    for desc, now, slots, last, expect_ok in cases:
        ok, detail = ev(
            now=now,
            rebalance_times=times,
            completed_slots=slots,
            last_rebalance_date=last,
            grace_hours=1.0,
        )
        status = "PASS" if ok == expect_ok else "FAIL"
        if status == "PASS":
            passed += 1
        else:
            failed += 1
        print(f"[{status}] {desc}")
        print(f"        expect_healthy={expect_ok} got={ok} detail={detail}")
        print()

    print(f"=== Summary: {passed} passed, {failed} failed ===")
    if failed:
        print("TESTS FAILED - review slot/date logic.")
        return 1
    print("ALL TESTS PASSED - slot SSOT + grace + date fallback OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
