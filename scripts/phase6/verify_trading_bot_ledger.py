#!/usr/bin/env python3
"""Compare Coinbase Trading Bot FILLED orders vs phase6_trades.jsonl by order_id."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.exchange_fill_reconciler import is_coinbase_trading_bot_order


def _ledger_order_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        oid = r.get("order_id")
        if oid:
            ids.add(str(oid))
    return ids


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=120)
    args = p.parse_args()

    ex = CoinbaseExchangeClient(mode="live")
    ledger_path = PROJECT_ROOT / "trades/phase6_trades.jsonl"
    known = _ledger_order_ids(ledger_path)

    api_ids: set[str] = set()
    by_side = Counter()
    by_type = Counter()
    for side in ("BUY", "SELL"):
        for o in ex.list_filled_orders(side=side, max_pages=40):
            if not is_coinbase_trading_bot_order(o):
                continue
            oid = o.get("order_id") or o.get("id")
            if not oid:
                continue
            api_ids.add(str(oid))
            by_side[side] += 1
            by_type[str(o.get("order_type") or "?")] += 1

    missing = sorted(api_ids - known)
    extra = sorted(known - api_ids)

    print("# Trading Bot ledger confidence report")
    print(f"api_filled_orders: {len(api_ids)}  (buy={by_side['BUY']} sell={by_side['SELL']})")
    print(f"jsonl_unique_order_ids: {len(known)}")
    print(f"missing_in_jsonl: {len(missing)}")
    print(f"jsonl_only_not_in_api_window: {len(extra)}")
    print("order_types_api:", dict(by_type))
    if missing:
        print("\nMissing order_ids (first 15):")
        for m in missing[:15]:
            print(" ", m)
    # rows with verified reconcile tag
    verified = 0
    reasons = Counter()
    for line in ledger_path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("fill_verified") and r.get("coinbase_trading_bot"):
            verified += 1
        if r.get("reason"):
            reasons[r["reason"]] += 1
    print(f"\njsonl fill_verified+coinbase_trading_bot rows: {verified}")
    print("jsonl reason counts:", dict(reasons))
    ok = len(missing) == 0
    print("PASS" if ok else "GAP — run reconcile_exchange_fills.py --full")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())