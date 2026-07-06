#!/usr/bin/env python3
"""Isolation: _should_rebalance fires once per daily slot, not every 60s cycle."""
import sys
from datetime import datetime, date, time as dt_time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class _RunnerStub:
    daily_rebalance_times = ["09:00", "21:00"]
    daily_rebalance_time = "09:00"
    last_rebalance_date = date.today()
    _rebalance_slots_completed = set()
    _force_next_rebalance = False

    def _due_rebalance_slot_id(self, now=None):
        from phase6.core.phase6_runner import Phase6Runner

        return Phase6Runner._due_rebalance_slot_id(self, now)

    def _should_rebalance(self, now):
        from phase6.core.phase6_runner import Phase6Runner

        return Phase6Runner._should_rebalance(self, now)


def test_same_slot_not_repeated():
    r = _RunnerStub()
    noon = datetime.combine(date.today(), dt_time(14, 3, 0))
    assert r._should_rebalance(noon) is True
    r._rebalance_slots_completed.add(r._due_rebalance_slot_id(noon))
    assert r._should_rebalance(noon) is False
    assert r._should_rebalance(noon) is False
    print("[REBALANCE-SLOT] once-per-slot OK")


if __name__ == "__main__":
    test_same_slot_not_repeated()
    print("[SHOULD_REBALANCE SLOTS] PASSED")