#!/usr/bin/env bash
# Scale-up approval cron: plan + quiet TG when n_planned>0.
# Money OFF unless Brad ladder is autonomous-armed (then one auto step).
# Quiet: empty stdout when nothing to approve / nothing to apply.
set -euo pipefail
ROOT="${PHASE6_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
export PYTHONPATH=.
PY="${ROOT}/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3

"$PY" - <<'PY'
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(".").resolve()


def run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(
        args,
        cwd=str(ROOT),
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": "."},
        capture_output=True,
        text=True,
    )
    out = (p.stdout or "").strip()
    return p.returncode, out


# 1) Plan (always, no money)
rc, plan_out = run(
    [sys.executable, "scripts/phase6/run_tryout_scale_up_live.py", "--plan", "--json"]
)
n_plan = 0
try:
    plan = json.loads(plan_out) if plan_out else {}
    n_plan = int(plan.get("n_planned") or 0)
except Exception:
    plan = {}

# 2) Ladder
from phase6.core.tryout_scale_up_ladder import autonomous_apply_allowed, status_plain

auto = bool(autonomous_apply_allowed())

# 3) Autonomous: one planned step
if auto and n_plan > 0:
    rc, apply_out = run(
        [
            sys.executable,
            "scripts/phase6/run_tryout_scale_up_live.py",
            "--apply",
            "--go",
            "--no-dry-run",
            "--json",
        ]
    )
    try:
        d = json.loads(apply_out) if apply_out else {}
        n = int(d.get("n_applied") or 0)
        if n:
            print(
                f"SCALE-UP AUTO applied n={n} mode={d.get('mode')} "
                f"ladder={d.get('ladder') or status_plain()}"
            )
    except Exception:
        pass
    raise SystemExit(0)

# 4) Approval: quiet TG only when planned
if n_plan <= 0:
    raise SystemExit(0)

rc, body = run(
    [sys.executable, "scripts/phase6/run_tryout_scale_up_live.py", "--approval-telegram"]
)
if body:
    print(body)
PY
