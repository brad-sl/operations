#!/usr/bin/env python3
"""CLI: tryout scale-up LIVE approval ping (plan only — never money).

Quiet cron contract:
  - stdout empty when nothing to approve / not armed / deduped
  - stdout = short TG card when n_planned > 0

  python3 scripts/phase6/run_tryout_scale_up_live_approval.py
  python3 scripts/phase6/run_tryout_scale_up_live_approval.py --force
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import tryout_scale_up_live as live  # noqa: E402
from phase6.core import tryout_scale_up_shadow as shadow  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Scale-up live approval ping (plan only)")
    ap.add_argument("--force", action="store_true", help="Bypass 12h fingerprint dedupe")
    ap.add_argument("--json", action="store_true", help="Dump plan JSON (always)")
    args = ap.parse_args()

    board = shadow.run_cycle()
    plan = live.plan_live_steps(board=board)
    if args.json:
        import json

        print(json.dumps(plan, indent=2, default=str))
        return 0

    body = live.approval_telegram_summary(plan, force=bool(args.force), mark_sent=True)
    if body:
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
