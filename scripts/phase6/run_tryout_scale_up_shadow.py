#!/usr/bin/env python3
"""Run tryout scale-up shadow cycle (ride the wave) — no orders.

  PYTHONPATH=. python scripts/phase6/run_tryout_scale_up_shadow.py
  PYTHONPATH=. python scripts/phase6/run_tryout_scale_up_shadow.py --score-only
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.tryout_scale_up_shadow import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
