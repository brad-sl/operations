#!/usr/bin/env python3
# See docs/DATA_FLOW_AND_LOCATIONS.md + phase6/core/paths.py for paths, state, config hygiene
"""
Hermes Cron wrapper for Phase 6 rebalance checks.

Usage (from cron or directly):
  python3 phase6/scripts/cron_rebalance.py --live

Behavior (P2-04 reliability):
- If a continuous Phase6Runner is already running, touch
  data/state/force_rebalance.flag so the live runner picks it up on its next cycle.
  This avoids duplicate process launches (which trigger singleton abort + cron failure).
- Otherwise, spawns a one-shot --rebalance-only runner (for cron-only deployments).

Intended for scheduled rebalances (morning/evening/midday per CRON_SCHEDULE.md).
The continuous runner (if used) handles its own loops but respects the flag.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Allow `python3 phase6/scripts/cron_rebalance.py` without -m
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _is_runner_running() -> bool:
    """Check for existing Phase 6 runner (P2-04 reliability)."""
    from phase6.core.runner_pid import is_runner_running

    return is_runner_running()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true",
                        help="Use --mode live --confirm-live (real trades). Default is shadow for safety.")
    parser.add_argument("--config", default="config/trading_config_phase6.json")
    args = parser.parse_args()

    project_root = _PROJECT_ROOT
    os.chdir(project_root)

    # P2-04 reliability: If a continuous runner is already active, trigger via flag
    # instead of spawning a duplicate (which hits singleton and causes cron failure).
    if _is_runner_running():
        from phase6.core.paths import FORCE_REBALANCE_FLAG

        FORCE_REBALANCE_FLAG.parent.mkdir(parents=True, exist_ok=True)
        FORCE_REBALANCE_FLAG.touch()
        print("[CRON] Runner already running — touched force_rebalance.flag to trigger next cycle.")
        print("[CRON] Cron check completed successfully (no new process spawned).")
        sys.exit(0)

    cmd = [
        sys.executable, "-m", "phase6.core.phase6_runner",
        "--config", args.config,
        "--rebalance-only",
    ]

    if args.live:
        cmd.extend(["--mode", "live", "--confirm-live"])
        print("[CRON] Running in LIVE mode (real orders may be placed)")
    else:
        cmd.extend(["--mode", "shadow"])
        print("[CRON] Running in SHADOW mode (no real orders)")

    print(f"[CRON] Executing: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print("[CRON] Rebalance run completed successfully.")
        sys.exit(result.returncode)
    except subprocess.CalledProcessError as e:
        print(f"[CRON] Rebalance run failed with exit code {e.returncode}")
        sys.exit(e.returncode)


if __name__ == "__main__":
    main()