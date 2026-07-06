#!/usr/bin/env python3
"""
P4-05: CycleCoordinator isolation — runner delegates run_cycle without behavior regression.

Verifies:
- Phase6Runner has _cycle_coordinator
- _run_cycle delegates (coordinator module importable)
- P4-02 mid_cycle flag loads from config
- _use_primary_allocator_path matches use_new_allocator + NEW_ALLOCATOR_AVAILABLE
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phase6.core.cycle_coordinator import CycleCoordinator
from phase6.core.phase6_runner import Phase6Runner, NEW_ALLOCATOR_AVAILABLE


def _temp_config(**gs):
    cfg = {
        "global_settings": {
            "use_new_allocator": True,
            "mid_cycle_allocator_enabled": True,
            "rebalance_cap_usd": 200,
            **gs,
        },
        "scheduler": {"daily_rebalance_times": ["09:00", "21:00"]},
        "phase_6_specific": {"opportunity_pool": []},
    }
    fd, path = tempfile.mkstemp(suffix=".json", prefix="p4_05_cfg_")
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f)
    return path


def test_cycle_coordinator_wiring():
    print("=== P4-05 CycleCoordinator isolation ===")
    path = _temp_config()
    try:
        runner = Phase6Runner(config_path=path, mode="shadow")
        assert hasattr(runner, "_cycle_coordinator"), "runner must own CycleCoordinator"
        assert isinstance(runner._cycle_coordinator, CycleCoordinator)
        assert runner.mid_cycle_allocator_enabled is True
        assert runner.use_new_allocator is True
        primary = runner._use_primary_allocator_path()
        print(f"use_new_allocator={runner.use_new_allocator} primary_path={primary} NEW_ALLOC={NEW_ALLOCATOR_AVAILABLE}")
        if NEW_ALLOCATOR_AVAILABLE:
            assert primary is True

        # Delegate smoke: should not raise (may skip eval if no signal mtime bump)
        runner._run_cycle(1)
        print("[P4-05] _run_cycle(1) delegated OK")
        print("[P4-05 ISOLATION] PASSED")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    test_cycle_coordinator_wiring()