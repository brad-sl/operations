#!/usr/bin/env python3
"""Run goldilocks swap-rank shadow cycle (no orders).

  PYTHONPATH=. python scripts/phase6/run_goldilocks_swap_shadow.py
  PYTHONPATH=. python scripts/phase6/run_goldilocks_swap_shadow.py --no-crumb
  PYTHONPATH=. python scripts/phase6/run_goldilocks_swap_shadow.py --score-only
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-crumb", action="store_true")
    ap.add_argument("--score-only", action="store_true", help="only backfill forward CF on crumbs")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    from phase6.core.goldilocks_swap_shadow import (
        ensure_decision_stub,
        run_shadow_cycle,
        score_open_crumbs,
        STATE_PATH,
        REPORT_PATH,
        DECISION_PATH,
    )

    ensure_decision_stub()
    if args.score_only:
        cf = score_open_crumbs()
        print(json.dumps(cf, indent=2, default=str) if args.json else cf.get("advantage_claim"))
        return 0

    board = run_shadow_cycle(write_crumb=not args.no_crumb, score_fwd=True)
    if args.json:
        print(json.dumps(board, indent=2, default=str))
    else:
        print(board.get("plain_english") or "")
        print(f"primed: {board.get('primed_pairs')}")
        print(f"baseline_swap: {board.get('baseline_swap')}")
        print(f"goldilocks_swap: {board.get('goldilocks_swap')}")
        cf = board.get("cf_summary") or {}
        if cf:
            print(f"cf: {cf.get('advantage_claim')}")
        print(f"state: {STATE_PATH}")
        print(f"report: {REPORT_PATH}")
        print(f"decision: {DECISION_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
