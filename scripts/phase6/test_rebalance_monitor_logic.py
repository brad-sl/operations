#!/usr/bin/env python3
"""
Code Isolation Test for Rebalance Monitor Logic (Phase 6)

Verifies the schedule-aware check_last_rebalance function.
Uses the actual config daily_rebalance_time ("21:00").
Tests healthy vs overdue cases based on real runner scheduler rules.

Run standalone with real config. No side effects on live state.

Expected: 
- On rebalance day before target+grace: healthy (no false alarm)
- After grace on rebalance day if last still previous: overdue
- Last==today: healthy
- >1 day: overdue

This is the canonical isolation test per trading-bot-operations + code-isolation-testing.
"""

import json
from datetime import datetime, date, time as dt_time, timedelta
import os
import sys

# Paths relative to project root (crontab cds here)
CONFIG_PATH = "config/trading_config_phase6.json"
STATE_FILE = "data/state/phase6_runner_state.json"  # for reference only, not mutated

def load_daily_rebalance_time(config_path=CONFIG_PATH):
    try:
        with open(config_path) as f:
            cfg = json.load(f)
        sched = cfg.get("scheduler", {})
        return sched.get("daily_rebalance_time", "21:00")
    except Exception as e:
        print(f"[TEST] Failed to load config, defaulting to 21:00: {e}")
        return "21:00"

def check_last_rebalance(last_date_str, now_dt, rebalance_time_str):
    """Improved schedule-aware version (matches runner's 21:00 target + grace).
    Returns True if healthy (no alert), False if overdue (should alert).
    """
    if not last_date_str:
        return False
    try:
        last_date = datetime.fromisoformat(last_date_str).date()
    except Exception:
        return False

    now = now_dt
    today = now.date()
    target = dt_time.fromisoformat(rebalance_time_str)
    grace_delta = timedelta(hours=1)  # 1h after target window (e.g. 22:00 for 21:00)

    if last_date == today:
        return True

    days = (today - last_date).days
    if days <= 0:
        return True

    if days == 1:
        # Yesterday's rebalance; today's window not yet passed or just in grace
        target_dt = datetime.combine(today, target) + grace_delta
        if now < target_dt:
            return True
        else:
            return False

    # More than 1 day stale
    return False

def main():
    print("=== Phase 6 Rebalance Monitor Logic Isolation Test ===")
    print(f"Config daily_rebalance_time: {load_daily_rebalance_time()}")
    print(f"Test time base: simulated PDT (same as host)")
    print()

    rebal_time = load_daily_rebalance_time()
    test_cases = []

    # Case 1: Last rebalance today -> healthy (no alert)
    now = datetime(2026, 6, 16, 12, 3)  # today 12pm
    test_cases.append(("last=today (16th 12pm)", "2026-06-16", now, True))

    # Case 2: Last=yesterday (15th), now=16th 12pm (before 21:00+1h) -> healthy (waiting for 21:00 window)
    now = datetime(2026, 6, 16, 12, 3)
    test_cases.append(("last=yest (15th), now=16th 12pm (pre-21:00)", "2026-06-15", now, True))

    # Case 3: Last=yesterday, now=16th 22:30 (after 21:00+1h grace) -> overdue (missed window)
    now = datetime(2026, 6, 16, 22, 30)
    test_cases.append(("last=yest, now=16th 22:30 (post-grace)", "2026-06-15", now, False))

    # Case 4: Last=yesterday, now=16th 21:05 (just after target, within grace) -> healthy
    now = datetime(2026, 6, 16, 21, 5)
    test_cases.append(("last=yest, now=16th 21:05 (in window)", "2026-06-15", now, True))

    # Case 5: Last=2 days ago -> overdue
    now = datetime(2026, 6, 16, 12, 3)
    test_cases.append(("last=14th (2d ago), now=16th 12pm", "2026-06-14", now, False))

    # Case 6: Last=today at late night -> healthy
    now = datetime(2026, 6, 16, 23, 0)
    test_cases.append(("last=today (16th 23pm)", "2026-06-16", now, True))

    # Case 7: Last=yest, now=17th early morning (before 21:00) -> healthy (new day but window pending)
    now = datetime(2026, 6, 17, 8, 0)
    test_cases.append(("last=16th, now=17th 08:00 (pre-window)", "2026-06-16", now, True))

    passed = 0
    failed = 0
    for desc, last_str, now_dt, expected_healthy in test_cases:
        result = check_last_rebalance(last_str, now_dt, rebal_time)
        status = "PASS" if result == expected_healthy else "FAIL"
        if status == "PASS":
            passed += 1
        else:
            failed += 1
        print(f"[{status}] {desc}")
        print(f"        last={last_str}, now={now_dt}, expected_healthy={expected_healthy}, got={result}")
        print()

    print(f"=== Summary: {passed} passed, {failed} failed ===")
    if failed == 0:
        print("ALL TESTS PASSED - logic correctly suppresses false alarms before 21:00+grace and only alerts on true misses.")
        print("This matches runner's _should_rebalance (target=21:00, no early morning false positives).")
        sys.exit(0)
    else:
        print("TESTS FAILED - review logic.")
        sys.exit(1)

if __name__ == "__main__":
    main()
