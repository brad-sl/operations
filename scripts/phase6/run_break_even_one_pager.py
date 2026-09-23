#!/usr/bin/env python3
"""CLI: break-even one-pager vs $150/mo bar. Measure-only."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.break_even_one_pager import (  # noqa: E402
    REPORT_PATH,
    STATE_PATH,
    build_break_even_one_pager,
    telegram_card,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Break-even one-pager (measure-only)")
    ap.add_argument("--tg", action="store_true", help="Print short Telegram card only")
    ap.add_argument("--lookback-days", type=int, default=None, help="Override week window with N days")
    ap.add_argument("--week-start", default="2026-09-23", help="PT date YYYY-MM-DD for week experiment")
    ap.add_argument("--be", type=float, default=150.0, help="Monthly take-home break-even bar USD")
    ap.add_argument("--x-week", type=float, default=25.0, help="Assumed X USD per week")
    ap.add_argument("--no-write", action="store_true", help="Skip state/report write")
    args = ap.parse_args()

    payload = build_break_even_one_pager(
        write=not args.no_write,
        lookback_days=args.lookback_days,
        week_start_pt=str(args.week_start),
        be_usd_mo=float(args.be),
        x_usd_per_week=float(args.x_week),
    )
    if args.tg:
        print(telegram_card(payload))
        return 0
    print(f"written: {STATE_PATH}")
    print(f"report: {REPORT_PATH}")
    print(telegram_card(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
