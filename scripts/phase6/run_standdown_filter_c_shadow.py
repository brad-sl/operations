#!/usr/bin/env python3
"""CLI: stand-down filter C shadow board. No orders / no config writes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.standdown_filter_c_shadow import (  # noqa: E402
    StanddownConfig,
    run_standdown_filter_c_shadow,
    telegram_summary,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Stand-down filter C shadow (elevated-tape would-block log; no orders)"
    )
    ap.add_argument("--r24", type=float, default=5.0, help="Primary elev threshold %% (frozen dig=5)")
    ap.add_argument("--pair", action="append", default=[], help="Limit to pair(s); default basket")
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--telegram",
        action="store_true",
        help="Print short body only when would-block non-empty (quiet-ok pattern)",
    )
    ap.add_argument(
        "--quiet-ok",
        action="store_true",
        help="Exit 0 with no stdout when nothing to block (cron-friendly)",
    )
    args = ap.parse_args()
    cfg = StanddownConfig(
        r24_primary_pct=args.r24,
        pairs=tuple(args.pair) if args.pair else (),
    )
    summary = run_standdown_filter_c_shadow(cfg)
    body = telegram_summary(summary)
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
        return 0
    if args.telegram or args.quiet_ok:
        if body:
            print(body)
        return 0
    n = summary.get("n_would_block") or len(summary.get("would_block") or [])
    print(
        body
        or f"C shadow ok would_block={n} pairs={summary.get('n_pairs')} live_gate=OFF"
    )
    print("report: reports/STANDDOWN_FILTER_C_SHADOW_LATEST.md")
    print("state: data/state/standdown_filter_c_shadow_latest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
