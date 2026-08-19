#!/usr/bin/env python3
"""CLI: basket swap shadow CF + parallel selection arms (no live promote)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.basket_swap_shadow_cf import plain_english_summary, run_full  # noqa: E402


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
        help="If decide=keep_shadow_collecting and no new proposals, print nothing (cron silent)",
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
        }
        print(json.dumps(out, indent=2, default=str))
        return 0

    text = plain_english_summary(bundle)
    decide = (bundle.get("cf") or {}).get("decide") or {}
    written = (bundle.get("arms_prop") or {}).get("written") or []
    status = decide.get("status") or ""
    if args.quiet_ok and status == "keep_shadow_collecting" and not written:
        # still always write reports on disk; silent stdout for Hermes no_agent
        return 0
    # Always surface modify_selector or new proposals or weekly-ish interest
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
