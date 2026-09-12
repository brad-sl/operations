#!/usr/bin/env python3
"""CLI: fee tier drift watch. Empty stdout when quiet (Hermes telegram hygiene).

Exit 0 always on successful evaluate (including no-drift); exit 1 only on hard failure
when --strict. Default: refresh live snapshot, alert stdout only if ≥5 bps vs baseline
and not deduped.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Watch Coinbase fee rates vs baseline (no orders)")
    ap.add_argument("--no-refresh", action="store_true", help="Use on-disk snapshot only")
    ap.add_argument("--threshold-bps", type=float, default=5.0)
    ap.add_argument("--json", action="store_true", help="Always print full verdict JSON")
    ap.add_argument("--force-page", action="store_true", help="Ignore dedupe (smoke/test)")
    ap.add_argument("--strict", action="store_true", help="Exit 1 if snapshot not ok")
    args = ap.parse_args()

    from phase6.core.fee_tier_drift_watch import run_watch

    verdict = run_watch(
        refresh=not args.no_refresh,
        threshold_bps=float(args.threshold_bps),
        page=True,
    )
    if args.force_page and verdict.get("drifted") and not verdict.get("page"):
        from phase6.core.fee_tier_drift_watch import format_alert

        verdict["page"] = True
        verdict["deduped"] = False
        verdict["telegram_body"] = format_alert(verdict)

    if args.json:
        print(json.dumps(verdict, indent=2, default=str))
    elif verdict.get("page") and verdict.get("telegram_body"):
        # stdout = Telegram body for no_agent deliver
        print(verdict["telegram_body"])
    # else: empty stdout = silent

    if args.strict and not verdict.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
