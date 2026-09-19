#!/usr/bin/env python3
"""CLI: Daily Dose Jev ranker shadow (measure-only).

Does not replace production daily dose or Telegram publish.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.daily_dose_jev_ranker import DoseJevConfig, run_ranker  # noqa: E402
from phase6.core.paths import (  # noqa: E402
    DAILY_DOSE_JEV_COMPARE,
    DAILY_DOSE_JEV_LATEST,
    DAILY_DOSE_JEV_PREVIEW,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily Dose Jev ranker (shadow)")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--max-judge", type=int, default=16, help="Max headlines to send to Jev")
    ap.add_argument("--window-hours", type=float, default=36.0)
    ap.add_argument(
        "--from-latest",
        action="store_true",
        help="Judge cards already in daily_dose_latest.json (no RSS refetch)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Mock Jev (no HTTP) — isolation / offline",
    )
    ap.add_argument("--print-compare", action="store_true")
    ap.add_argument("--print-preview", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cfg = DoseJevConfig(
        top_n=args.top,
        max_judge=args.max_judge,
        window_h=args.window_hours,
        from_latest_only=args.from_latest,
        dry_run=args.dry_run,
    )
    payload = run_ranker(cfg=cfg)
    cmp_ = payload.get("compare") or {}
    print(
        f"DoseJev OK judged={payload.get('judge_stats', {}).get('judged')} "
        f"jaccard={cmp_.get('jaccard')} overlap={cmp_.get('n_overlap')}/"
        f"{cmp_.get('n_baseline')} dry={cfg.dry_run} → {DAILY_DOSE_JEV_LATEST}"
    )
    if args.print_compare:
        print("--- compare ---")
        print(DAILY_DOSE_JEV_COMPARE.read_text(encoding="utf-8"))
    if args.print_preview:
        print("--- preview ---")
        print(DAILY_DOSE_JEV_PREVIEW.read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps({
            "compare": cmp_,
            "judge_stats": payload.get("judge_stats"),
            "jev_top_titles": [x.get("title") for x in (payload.get("jev_top") or [])],
            "baseline_top_titles": [x.get("title") for x in (payload.get("baseline_top") or [])],
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
