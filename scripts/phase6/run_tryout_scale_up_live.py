#!/usr/bin/env python3
"""Tryout mid-flight scale-up LIVE path CLI (default dry-run).

  # Plan only (safe)
  PYTHONPATH=. python scripts/phase6/run_tryout_scale_up_live.py --plan

  # Dry apply rehearse (shadow executor)
  PYTHONPATH=. python scripts/phase6/run_tryout_scale_up_live.py --apply --go --shadow-executor

  # REAL money — requires decision.live_apply=true AND no KILL file
  PYTHONPATH=. python scripts/phase6/run_tryout_scale_up_live.py --apply --go --no-dry-run

Cron must NEVER pass --go --no-dry-run.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.tryout_scale_up_live import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
