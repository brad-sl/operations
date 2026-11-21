#!/usr/bin/env python3
"""CLI: Alt A regime-gated ballast measure CF."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/home/brad/projects/crypto-trading-bot")
sys.path.insert(0, str(ROOT))

from phase6.research.measure_regime_ballast_cf import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
