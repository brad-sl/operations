#!/usr/bin/env python3
"""Audit rebalance BUY rows with sl_attached=false vs exchange protective orders."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

LEDGER = ROOT / "trades" / "phase6_trades.jsonl"


def main() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
    gaps = []
    for line in LEDGER.read_text().splitlines():
        if not line.strip():
            continue
        t = json.loads(line)
        if str(t.get("side")).upper() != "BUY":
            continue
        if t.get("sl_attached") is not False:
            continue
        ts = t.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if dt < cutoff:
            continue
        gaps.append(t)

    print(f"BUY sl_attached=false (last 72h): {len(gaps)}")
    for t in gaps:
        print(
            f"  {t.get('timestamp')} {t.get('pair')} order={str(t.get('order_id',''))[:8]}… "
            f"qty={t.get('qty')}"
        )

    if not gaps:
        return 0

    try:
        from phase6.core.config_loader import ConfigLoader
        from phase6.core.exchange_client import CoinbaseExchangeClient
        from phase6.core.stop_loss_manager import StopLossManager

        loader = ConfigLoader()
        client = CoinbaseExchangeClient(mode="live")
        slm = StopLossManager(client, loader._config, mode="live")
        basket = sorted({g["pair"] for g in gaps if g.get("pair")})
        missing_exchange = []
        if basket:
            active = slm.detect_active_protective_orders(basket)
            print("Exchange protective orders (detect):")
            for pair in basket:
                orders = active.get(pair) or []
                print(f"  {pair}: {len(orders)} order(s)")
                if not orders:
                    missing_exchange.append(pair)
                for o in orders[:2]:
                    print(f"    id={o.get('order_id')} stop={o.get('stop_price')} size={o.get('size')}")

        if missing_exchange:
            print("MISSING on exchange:", ", ".join(missing_exchange))
            return 1
        print("Ledger sl_attached=false but exchange stops present — logging gap only.")
        return 0
    except Exception as e:
        print(f"Exchange SL check skipped: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())