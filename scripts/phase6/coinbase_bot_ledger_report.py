#!/usr/bin/env python3
"""Print FILLED orders that match Coinbase UI filter: Trading Bot transactions only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.exchange_fill_reconciler import is_coinbase_trading_bot_order


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--side", choices=("BUY", "SELL", "ALL"), default="ALL")
    p.add_argument("--types", default="", help="Comma filter e.g. STOP_LIMIT,MARKET")
    args = p.parse_args()

    ex = CoinbaseExchangeClient(mode="live")
    cut = datetime.now(timezone.utc) - timedelta(days=args.days)
    type_f = {t.strip().upper() for t in args.types.split(",") if t.strip()}

    sides = ("BUY", "SELL") if args.side == "ALL" else (args.side,)
    rows = []
    for side in sides:
        for o in ex.list_filled_orders(side=side, max_pages=40):
            if not is_coinbase_trading_bot_order(o):
                continue
            ct = o.get("created_time") or ""
            try:
                dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
            except Exception:
                continue
            if dt < cut:
                continue
            ot = str(o.get("order_type") or "")
            if type_f and ot.upper() not in type_f:
                continue
            rows.append(o)

    rows.sort(key=lambda x: x.get("created_time", ""), reverse=True)
    print(f"# Coinbase Trading Bot FILLED — last {args.days}d — {len(rows)} rows")
    print(f"{'created_utc':<20} {'pair':<10} {'side':<4} {'type':<12} {'qty':>16} {'avg_px':>14}")
    for o in rows:
        print(
            f"{(o.get('created_time') or '')[:19]:<20} "
            f"{o.get('product_id',''):<10} "
            f"{o.get('side',''):<4} "
            f"{(o.get('order_type') or ''):<12} "
            f"{str(o.get('filled_size','')):>16} "
            f"{str(o.get('average_filled_price','')):>14}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())