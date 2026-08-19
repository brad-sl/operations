#!/usr/bin/env python3
"""Reconcile Coinbase Trading Bot FILLED orders into trades/phase6_trades.jsonl."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.exchange_fill_reconciler import (
    reconcile_filled_stops,
    reconcile_all_filled_sells,
    reconcile_trading_bot_ledger,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Reconcile Coinbase filled orders into TradeLedger")
    p.add_argument("--backfill-days", type=int, default=120, help="How far back to query FILLED orders")
    p.add_argument("--dry-run", action="store_true", help="Scan only; do not write JSONL")
    p.add_argument("--all-sells", action="store_true", help="Ingest stop + MARKET rotation SELLs")
    p.add_argument(
        "--full",
        action="store_true",
        help="Trading Bot parity: all sells + missing verified BUYs (recommended)",
    )
    p.add_argument("--shadow", action="store_true", help="Use shadow exchange (no API)")
    args = p.parse_args()

    exchange = CoinbaseExchangeClient(mode="shadow" if args.shadow else "live")
    if args.full:
        result = reconcile_trading_bot_ledger(
            exchange,
            backfill_days=args.backfill_days,
            dry_run=args.dry_run,
        )
    elif args.all_sells:
        result = reconcile_all_filled_sells(
            exchange,
            backfill_days=args.backfill_days,
            dry_run=args.dry_run,
            include_non_stop=True,
        )
    else:
        result = reconcile_filled_stops(
            exchange,
            backfill_days=args.backfill_days,
            dry_run=args.dry_run,
        )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())