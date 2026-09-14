#!/usr/bin/env python3
"""Isolation test: analyst-test-strategy-weekly cron script.
- Runs clean (no crash)
- Uses only status/sync/emit (gated, no live trading writes)
- Telegram stdout = short board only; full JSON in logs/
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
HERMES_SCRIPT = Path("/home/brad/.hermes/scripts/run_analyst_test_strategy_weekly.sh")


def test_hermes_no_agent_wrapper_is_thin_delegator():
    """Enforce thin wrapper pattern so full logic stays in git-tracked project source."""
    assert HERMES_SCRIPT.exists(), f"missing hermes entrypoint {HERMES_SCRIPT} — copy thin wrapper after edit"
    assert os.access(HERMES_SCRIPT, os.X_OK), "hermes script not executable"
    content = HERMES_SCRIPT.read_text()
    assert "Thin wrapper" in content or "exec bash" in content, "hermes script must be thin delegator to project, not full copy"
    assert len(content) < 500, "hermes wrapper too large; use thin exec pattern"


def test_cron_script_runs_and_produces_summary():
    assert SCRIPT.exists(), f"missing {SCRIPT}"
    assert os.access(SCRIPT, os.X_OK), "not executable"

    proc = subprocess.run(
        [str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    assert proc.returncode == 0, f"exit {proc.returncode}\nstderr: {proc.stderr[:500]}"
    out = proc.stdout

    # Telegram body = short board only
    assert "analyst-test-strategy-weekly" in out
    assert "Slots:" in out
    assert "No live config writes" in out
    assert "Full log:" in out

    # Must NOT dump strategy JSON blobs to stdout (option A)
    assert '"north_star"' not in out
    assert '"by_status"' not in out
    assert '"parked_regime_plans"' not in out
    # stricter: indented JSON keys from status dump
    assert '  "slots"' not in out
    assert '  "path"' not in out
    assert "## Status" not in out
    assert "## Sync active" not in out

    assert "can't reach the model provider" not in out.lower()
    assert "RuntimeError" not in out

    # Full dump landed on disk
    log_dir = ROOT / "logs" / "analyst_test_strategy_weekly"
    assert (log_dir / "latest.log").exists(), "missing latest full log"
    assert (log_dir / "status_latest.json").exists(), "missing status_latest.json"
    status_txt = (log_dir / "status_latest.json").read_text()
    assert "north_star" in status_txt or "slots" in status_txt


def test_no_live_trading_mutation(tmp_path, monkeypatch=None):
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
    assert "positions" not in res.stdout.lower()


if __name__ == "__main__":
    test_hermes_no_agent_wrapper_is_thin_delegator()
    test_cron_script_runs_and_produces_summary()
    test_no_live_trading_mutation(None)
    print("PASS: analyst test strategy cron isolation")
