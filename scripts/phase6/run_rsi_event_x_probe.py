#!/usr/bin/env python3
"""CLI: RSI-event paid X probe (dry default). Never places orders.

  python3 scripts/phase6/run_rsi_event_x_probe.py           # dry
  python3 scripts/phase6/run_rsi_event_x_probe.py --go       # spend if wash+budget
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.rsi_event_x_probe import run_probe, telegram_summary  # noqa: E402
from phase6.core.x_query_budget import BudgetConfig  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="RSI-event X probe (dry default, no orders)")
    ap.add_argument("--go", action="store_true", help="Allow paid X under budget (still no orders)")
    ap.add_argument("--top-k", type=int, default=2)
    ap.add_argument("--floor", type=float, default=0.30)
    ap.add_argument("--rsi-max", type=float, default=40.0)
    ap.add_argument("--max-rsi-day", type=int, default=2, help="RSI lane pair-query cap/day")
    ap.add_argument("--max-day", type=int, default=6, help="Total pair-query cap/day")
    ap.add_argument("--cooldown-h", type=float, default=6.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--quiet-ok", action="store_true")
    args = ap.parse_args()

    bcfg = BudgetConfig(
        max_pair_queries_per_day=int(args.max_day),
        max_rsi_pair_queries_per_day=int(args.max_rsi_day),
        per_pair_cooldown_hours=float(args.cooldown_h),
    )
    result = run_probe(
        dry_run=not bool(args.go),
        spend_x=bool(args.go),
        top_k=int(args.top_k),
        floor=float(args.floor),
        rsi_max=float(args.rsi_max),
        budget_cfg=bcfg,
    )
    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0
    body = telegram_summary(result, floor=float(args.floor))
    if args.telegram or args.quiet_ok:
        if body:
            print(body)
        return 0
    print(result.get("plain_english") or "probe ok")
    print(
        f"dry={result.get('dry_run')} spend_exec={result.get('spend_x_executed')} "
        f"fetched={result.get('fetched')} live_gate=OFF"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
