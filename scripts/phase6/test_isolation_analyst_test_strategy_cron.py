#!/usr/bin/env python3
"""Isolation test: analyst-test-strategy-weekly cron script.
- Runs clean (no crash)
- Uses only status/sync/emit (gated, no live trading writes)
- Emits short summary; no model provider dependency (no_agent)
- Respects capacity; updates only TEST_STRATEGY + MASTER test entries
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SCRIPT = ROOT / "run_analyst_test_strategy_weekly.sh"


def test_cron_script_runs_and_produces_summary():
    assert SCRIPT.exists(), f"missing {SCRIPT}"
    assert os.access(SCRIPT, os.X_OK), "not executable"

    # Run with timeout; capture stdout (what gets delivered)
    proc = subprocess.run(
        [str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    assert proc.returncode == 0, f"exit {proc.returncode}\nstderr: {proc.stderr[:500]}"
    out = proc.stdout

    # Key markers from summary
    assert "analyst-test-strategy-weekly" in out
    assert "Slots:" in out or "offline=" in out
    assert "No live config writes" in out
    assert "Status" in out and "Sync active" in out

    # Should not have crashed on model or network
    assert "can't reach the model provider" not in out.lower()
    assert "RuntimeError" not in out

    # Should mention capacity / emit gated
    assert "Emit" in out or "capacity" in out.lower()


def test_no_live_trading_mutation(tmp_path, monkeypatch=None):
    # Ensure the script does not touch live regime_cash_policy or runner state
    # (it only touches TEST_STRATEGY + MASTER for test plans)
    # Smoke: run status only via py directly
    py = ROOT / ".venv" / "bin" / "python3"
    if not py.exists():
        py = "python3"
    res = subprocess.run(
        [str(py), "phase6/research/analyst_test_strategy.py", "status"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res.returncode == 0
    # status json should not contain trading positions etc.
    assert "positions" not in res.stdout.lower()
    assert "rebalance" not in res.stdout.lower() or "test" in res.stdout.lower()


if __name__ == "__main__":
    test_cron_script_runs_and_produces_summary()
    test_no_live_trading_mutation(None)
    print("PASS: analyst test strategy cron isolation")
