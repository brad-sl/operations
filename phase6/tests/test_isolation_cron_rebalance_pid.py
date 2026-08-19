#!/usr/bin/env python3
"""Isolation: cron rebalance detects live runner via pgrep + pidfiles."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def test_cron_detects_pgrep_runner():
    from phase6.scripts import cron_rebalance as cr

    with patch("phase6.core.runner_pid.pgrep_runner_pids", return_value=[424242]):
        with patch("phase6.core.runner_pid._pid_alive", return_value=True):
            assert cr._is_runner_running() is True


def test_runner_main_accepts_rebalance_only_flag():
    import subprocess

    r = subprocess.run(
        [sys.executable, "-m", "phase6.core.phase6_runner", "--help"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert r.returncode == 0
    assert "--rebalance-only" in r.stdout


if __name__ == "__main__":
    test_cron_detects_pgrep_runner()
    test_runner_main_accepts_rebalance_only_flag()
    print("OK")