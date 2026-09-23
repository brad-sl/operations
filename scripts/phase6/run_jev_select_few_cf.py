#!/usr/bin/env python3
"""CLI: Jev select-few counterfactual paper book. Measure-only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.jev_select_few_cf import (  # noqa: E402
    REPORT_PATH,
    STATE_PATH,
    SelectFewConfig,
    run_select_few_cf,
    telegram_card,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Jev select-few CF (no orders)")
    ap.add_argument("--dry-run", action="store_true", help="Mock Jev, no HTTP")
    ap.add_argument("--pairs", default="", help="Override pairs comma-list")
    ap.add_argument("--max-pairs", type=int, default=3)
    ap.add_argument("--notional", type=float, default=25.0)
    ap.add_argument("--max-open", type=int, default=4)
    ap.add_argument("--max-calls-per-day", type=int, default=12)
    ap.add_argument("--model", default="~typesafe/jev-latest")
    ap.add_argument("--no-refresh-ohlcv", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--tg", action="store_true", help="Print short card only")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    override = [x.strip() for x in str(args.pairs).split(",") if x.strip()]
    cfg = SelectFewConfig(
        max_pairs=int(args.max_pairs),
        max_open_seats=int(args.max_open),
        notional_usd=float(args.notional),
        max_calls_per_day=int(args.max_calls_per_day),
        model=str(args.model),
        dry_run=bool(args.dry_run),
        refresh_ohlcv=not bool(args.no_refresh_ohlcv),
        pairs_override=override,
        write=not bool(args.no_write),
    )
    payload = run_select_few_cf(cfg=cfg)
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    elif args.tg:
        print(telegram_card(payload))
    else:
        print(payload.get("plain") or telegram_card(payload))
        if not args.no_write:
            print(f"[meta] state={STATE_PATH} report={REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
