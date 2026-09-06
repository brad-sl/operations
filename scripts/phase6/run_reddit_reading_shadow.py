#!/usr/bin/env python3
"""CLI: Hermes reddit-reading skill → shadow sentiment cache (no live gates).

  PYTHONPATH=. python scripts/phase6/run_reddit_reading_shadow.py
  PYTHONPATH=. python scripts/phase6/run_reddit_reading_shadow.py --doctor
  PYTHONPATH=. python scripts/phase6/run_reddit_reading_shadow.py --deep
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.reddit_reading_shadow import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
