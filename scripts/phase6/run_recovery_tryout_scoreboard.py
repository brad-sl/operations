#!/usr/bin/env python3
"""Write recovery quality_tryout v2 scoreboard (shadow board + optional live mode report).

Usage:
  PYTHONPATH=. python scripts/phase6/run_recovery_tryout_scoreboard.py
  PYTHONPATH=. python scripts/phase6/run_recovery_tryout_scoreboard.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Recovery tryout v2 scoreboard")
    ap.add_argument("--json", action="store_true", help="print full JSON to stdout")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    from phase6.core.regime_cash_policy import _recovery_rec, load_policy
    from phase6.core.recovery_tryout_qualify import write_scoreboard, STATE_PATH, REPORT_PATH

    pol = load_policy()
    rec = _recovery_rec(pol) or {}
    board = write_scoreboard(rec=rec)
    if args.json:
        print(json.dumps(board, indent=2, default=str))
    elif not args.quiet:
        print(board.get("plain_english") or "")
        print(f"state: {STATE_PATH}")
        print(f"report: {REPORT_PATH}")
        print(f"eligible: {board.get('eligible_tryout_pairs')}")
        print(f"delta: {board.get('delta_vs_legacy')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
