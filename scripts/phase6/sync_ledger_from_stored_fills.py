#!/usr/bin/env python3
"""Backfill phase6_trades.jsonl from trades/phase6_exchange_fills.jsonl — no Coinbase API."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.exchange_fill_reconciler import reconcile_stored_exchange_fills_into_ledger


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    out = reconcile_stored_exchange_fills_into_ledger(dry_run=args.dry_run)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())