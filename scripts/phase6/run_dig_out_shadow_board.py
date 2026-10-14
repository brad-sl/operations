#!/usr/bin/env python3
"""CLI: dig-out practical sequence shadow board. No orders / no live_apply."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.dig_out_shadow_board import run_and_persist, telegram_quiet  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Dig-out C1/D1/B/W2 shadow board (measure-only)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet-ok", action="store_true", help="Always print short non-empty header")
    args = ap.parse_args()
    board = run_and_persist()
    if args.json:
        print(json.dumps(board, indent=2, default=str))
        return 0
    print(telegram_quiet(board))
    if not args.quiet_ok:
        print("report: reports/DIG_OUT_SHADOW_BOARD_LATEST.md")
        print("state: data/state/dig_out_shadow_board_latest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
