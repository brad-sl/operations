#!/usr/bin/env python3
"""CLI: basket swap shadow CF + parallel selection arms (no live promote)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.basket_swap_shadow_cf import (  # noqa: E402
    plain_english_summary,
    run_full,
    serious_consider_message,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Shadow CF + parallel basket select arms")
    p.add_argument(
        "--no-propose",
        action="store_true",
        help="Only refresh CF marks; do not generate new arm proposals",
    )
    p.add_argument("--json", action="store_true", help="Print full JSON bundle")
    p.add_argument(
        "--quiet-ok",
        action="store_true",
        help=(
            "Cron mode: print nothing unless a *seriously consider* gate fires "
            "(dual_agree and/or preferred arm + membership OK). "
            "Baseline scout heat and routine arm dumps stay silent. "
            "Full board always on disk."
        ),
    )
    p.add_argument(
        "--full-summary",
        action="store_true",
        help="Force full plain-English summary to stdout (manual/debug).",
    )
    args = p.parse_args()

    bundle = run_full(propose=not args.no_propose)
    if args.json:
        # compact serializable
        cf = bundle.get("cf") or {}
        out = {
            "as_of": cf.get("as_of"),
            "decide": cf.get("decide"),
            "by_arm_counts": cf.get("by_arm_counts"),
            "aggregate_by_arm": cf.get("aggregate_by_arm"),
            "new_proposals": (bundle.get("arms_prop") or {}).get("written") or [],
            "serious_consider": serious_consider_message(bundle) is not None,
        }
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.full_summary or not args.quiet_ok:
        print(plain_english_summary(bundle))
        return 0

    # quiet-ok: only Telegram-worthy serious-consider body
    msg = serious_consider_message(bundle)
    if msg:
        print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
