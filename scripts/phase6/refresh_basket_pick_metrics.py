#!/usr/bin/env python3
"""Refresh basket pick mark-to-market metrics (1d/3d/7d/14d/30d). Safe, no trading."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.basket_pick_metrics import refresh_open_picks, summarize  # noqa: E402


def main() -> int:
    out = refresh_open_picks()
    print(json.dumps(out.get("summary") or summarize(), indent=2))
    print(f"marks_updated={out.get('updated')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
