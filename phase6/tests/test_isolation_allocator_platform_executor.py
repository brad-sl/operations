#!/usr/bin/env python3
"""
P4-04: Platform executor default (ARCH-4) isolation test.

Verifies:
- use_platform_executor defaults True when use_new_allocator is True
- Phase6Runner initializes trading.factory TradeExecutor on primary path
- _execute_trade_plan prefers platform TradeExecutor (not legacy OrderExecutor)
- Explicit fallback (use_platform_executor=False) uses OrderExecutor

Shadow mode only — no live orders.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.phase6_runner import (
    Phase6Runner,
    NEW_ALLOCATOR_AVAILABLE,
    PLATFORM_EXECUTOR_AVAILABLE,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
EVIDENCE_PATH = PROJECT_ROOT / "data/state/p4_04_platform_executor_evidence.json"


def _temp_config(
    use_new: bool = True,
    use_platform: bool | None = None,
) -> str:
    gs = {
        "use_new_allocator": use_new,
        "max_deployable_usd": 600.0,
        "rebalance_cap_usd": 200.0,
    }
    if use_platform is not None:
        gs["use_platform_executor"] = use_platform
    cfg = {
        "global_settings": gs,
        "scheduler": {"daily_rebalance_time": "21:00"},
        "phase_6_specific": {},
        "risk_management": {"stop_loss_pct": 0.03},
    }
    fd, path = tempfile.mkstemp(suffix=".json", prefix="test_p4_04_config_")
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f)
    return path


def _minimal_plan():
    return SimpleNamespace(
        actions=[
            {"pair": "BTC-USD", "action": "BUY", "usd": 25.0, "usd_amount": 25.0},
        ]
    )


def test_platform_executor_default_wiring():
    print("=== P4-04: Platform Executor Default Isolation Test ===\n")

    if not NEW_ALLOCATOR_AVAILABLE:
        print("SKIP: NEW_ALLOCATOR_AVAILABLE=False")
        return False
    if not PLATFORM_EXECUTOR_AVAILABLE:
        print("SKIP: PLATFORM_EXECUTOR_AVAILABLE=False")
        return False

    config_path = _temp_config(use_new=True, use_platform=None)
    evidence = {"checks": [], "platform_path": None, "fallback_path": None}
    try:
        runner = Phase6Runner(config_path=config_path, mode="shadow")
        assert runner.use_new_allocator is True, "ARCH-4 flag must be on"
        assert runner.use_platform_executor is True, (
            "use_platform_executor should default True when use_new_allocator True"
        )
        assert runner.trade_executor is not None, "TradeExecutor must be initialized"
        evidence["checks"].append("runner_flags_and_trade_executor_init")
        print(
            f"Runner: use_new_allocator={runner.use_new_allocator}, "
            f"use_platform_executor={runner.use_platform_executor}, "
            f"trade_executor={type(runner.trade_executor).__name__}"
        )

        # Spy: platform path must be used; legacy must not
        platform_spy = MagicMock(
            side_effect=runner.trade_executor.execute_rebalance_plan
        )
        runner.trade_executor.execute_rebalance_plan = platform_spy

        legacy_called = {"value": False}

        def _legacy_spy(plan):
            legacy_called["value"] = True
            return [{"success": True, "pair": "BTC-USD"}]

        runner.order_executor.execute_rebalance_plan = _legacy_spy

        # Shadow: _execute_trade_plan logs only (no delegate) — verify routing via live path mock
        runner.shadow_mode = False
        executed, skipped = runner._execute_trade_plan(_minimal_plan())
        assert platform_spy.called, "Platform TradeExecutor.execute_rebalance_plan must be called"
        assert not legacy_called["value"], "Legacy OrderExecutor must not run on primary path"
        evidence["platform_path"] = {
            "called": platform_spy.called,
            "call_count": platform_spy.call_count,
            "executed": executed,
            "skipped_count": len(skipped),
        }
        evidence["checks"].append("primary_path_uses_platform_executor")
        print("[P4-04] Primary path routed to platform TradeExecutor — PASS")

    finally:
        if os.path.exists(config_path):
            os.unlink(config_path)

    # Fallback flag
    config_path2 = _temp_config(use_new=True, use_platform=False)
    try:
        runner2 = Phase6Runner(config_path=config_path2, mode="shadow")
        assert runner2.use_platform_executor is False
        legacy_called2 = {"value": False}

        def _legacy_only(plan):
            legacy_called2["value"] = True
            return [{"success": True, "pair": "BTC-USD"}]

        runner2.order_executor.execute_rebalance_plan = _legacy_only
        runner2.shadow_mode = False
        runner2._execute_trade_plan(_minimal_plan())
        assert legacy_called2["value"], "Fallback must use OrderExecutor"
        evidence["fallback_path"] = {"legacy_called": legacy_called2["value"]}
        evidence["checks"].append("fallback_uses_order_executor")
        print("[P4-04] Explicit fallback uses legacy OrderExecutor — PASS")
    finally:
        if os.path.exists(config_path2):
            os.unlink(config_path2)

    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVIDENCE_PATH, "w") as f:
        json.dump(evidence, f, indent=2)
    print(f"\nEvidence written: {EVIDENCE_PATH}")
    print("\n[P4-04 ISOLATION] PASSED")
    return True


if __name__ == "__main__":
    ok = test_platform_executor_default_wiring()
    sys.exit(0 if ok else 1)