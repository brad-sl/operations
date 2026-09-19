#!/usr/bin/env python3
"""CLI: Daily Dose locked-pool A/B (shadow). Same 08:00 freeze, dual top-N.

Does not replace live Telegram dose.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.daily_dose_jev_ab import DoseAbConfig, run_locked_ab  # noqa: E402
from phase6.core.paths import (  # noqa: E402
    DAILY_DOSE_JEV_AB_CARD,
    DAILY_DOSE_JEV_AB_LATEST,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily Dose locked A/B (shadow)")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--max-judge", type=int, default=16)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--print-card", action="store_true")
    ap.add_argument("--print-tg", action="store_true", help="Short operator card (stdout)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cfg = DoseAbConfig(top_n=args.top, max_judge=args.max_judge, dry_run=args.dry_run)
    payload = run_locked_ab(cfg=cfg)
    if not payload.get("ok", True) and payload.get("error"):
        print(f"DoseAB FAIL {payload.get('error')}", file=sys.stderr)
        return 2
    cmp_ = payload.get("compare") or {}
    rel = payload.get("relevance") or {}
    print(
        f"DoseAB OK day={payload.get('dose_day')} freeze={payload.get('freeze_n')} "
        f"jaccard={cmp_.get('jaccard')} auto={rel.get('auto_mark')} "
        f"dry={cfg.dry_run} → {DAILY_DOSE_JEV_AB_LATEST}"
    )
    if args.print_card and DAILY_DOSE_JEV_AB_CARD.is_file():
        print("--- card ---")
        print(DAILY_DOSE_JEV_AB_CARD.read_text(encoding="utf-8"))
    if args.print_tg:
        # Empty stdout = quiet cron; TG body only when --print-tg
        print(payload.get("tg_card") or "")
    if args.json:
        print(
            json.dumps(
                {
                    "compare": cmp_,
                    "relevance": rel,
                    "arm_a_titles": [x.get("title") for x in (payload.get("arm_a") or [])],
                    "arm_b_titles": [x.get("title") for x in (payload.get("arm_b") or [])],
                    "judge_stats": payload.get("judge_stats"),
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
