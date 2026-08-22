#!/usr/bin/env python3
"""CLI: volume velocity shadow arm (RVOL nominator). No orders / no config writes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.volume_velocity_shadow import (  # noqa: E402
    VelocityConfig,
    run_volume_velocity_shadow,
    telegram_summary,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Volume velocity shadow (RVOL → evaluate queue research)")
    ap.add_argument("--rvol-1h", type=float, default=2.0)
    ap.add_argument("--scan-top", type=int, default=60)
    ap.add_argument("--min-vol-usd", type=float, default=250_000.0)
    ap.add_argument("--json", action="store_true", help="Print full JSON summary")
    ap.add_argument(
        "--telegram",
        action="store_true",
        help="Print short Telegram body (empty if nothing to say)",
    )
    args = ap.parse_args()
    cfg = VelocityConfig(
        rvol_1h_min=args.rvol_1h,
        candle_scan_top_n=args.scan_top,
        min_quote_volume_24h_usd=args.min_vol_usd,
    )
    summary = run_volume_velocity_shadow(cfg)
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    body = telegram_summary(summary)
    if args.telegram:
        if body:
            print(body)
        return 0
    if not args.json:
        print(body or f"velocity shadow ok noms={summary.get('nominations_this_run')} open={summary.get('open_tracks')}")
        print(f"report: reports/VOLUME_VELOCITY_SHADOW_LATEST.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
