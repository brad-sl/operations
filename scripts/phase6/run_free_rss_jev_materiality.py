#!/usr/bin/env python3
"""CLI: Free/RSS Jev materiality shadow (measure-only).

Does not write live sentiment_cache.json or change floors.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.free_rss_jev_materiality import FreeJevConfig, run_free_rss_jev, telegram_summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Free/RSS Jev materiality shadow")
    ap.add_argument("--dry-run", action="store_true", help="Mock Jev, no HTTP, no disk writes")
    ap.add_argument("--max-judge", type=int, default=24)
    ap.add_argument("--max-calls-day", type=int, default=96)
    ap.add_argument("--print-compare", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-hybrid", action="store_true", help="RSS_jev pairs only (skip funding/F&G merge)")
    args = ap.parse_args()

    cfg = FreeJevConfig(
        max_judge=args.max_judge,
        max_calls_per_day=args.max_calls_day,
        dry_run=bool(args.dry_run),
        merge_free_hybrid=not bool(args.no_hybrid),
    )
    result = run_free_rss_jev(cfg=cfg)
    if args.json:
        print(
            json.dumps(
                {
                    "meta": result.get("meta"),
                    "telegram": telegram_summary(result),
                    "free_jev": result.get("free_jev"),
                },
                indent=2,
                default=str,
            )
        )
    else:
        print(telegram_summary(result))
        m = result.get("meta") or {}
        print(
            f"obs={m.get('n_obs')} judged={m.get('n_judged')} ok={m.get('n_ok')} err={m.get('n_err')} "
            f"budget={m.get('budget_calls')}/{m.get('max_calls_per_day')}"
        )
        if args.print_compare:
            print()
            print(result.get("compare_md") or "")
        elif not args.dry_run:
            print(f"compare → data/state/free_rss_jev_compare.md")
            print(f"cache  → data/state/sentiment_cache_free_jev.json")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
