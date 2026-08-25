#!/usr/bin/env python3
"""
Sentiment-fade shadow tick (P1). No live sells.

Run:
  cd /home/brad/projects/crypto-trading-bot && PYTHONPATH=. python3 scripts/phase6/run_sentiment_fade_shadow.py
  PYTHONPATH=. python3 scripts/phase6/run_sentiment_fade_shadow.py --backfill-link
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.rsi_primary_deploy import (
    backfill_lot_from_buy_trade,
    load_entry_lots,
    run_sentiment_fade_shadow,
)


def backfill_link() -> None:
    """Tag open LINK lot from latest LINK BUY in ledger + live rsi/sent caches."""
    trades_p = ROOT / "trades" / "phase6_trades.jsonl"
    link_buy = None
    if trades_p.exists():
        for ln in trades_p.read_text().splitlines():
            try:
                t = json.loads(ln)
            except Exception:
                continue
            if str(t.get("pair")) == "LINK-USD" and str(t.get("side") or "").upper() == "BUY":
                link_buy = t
    if not link_buy:
        # synthetic from known 09:00 fill
        link_buy = {
            "pair": "LINK-USD",
            "side": "BUY",
            "qty": 164.59,
            "entry_price": 11.603782489823198,
            "reason": "rebalance_buy",
        }
        print("No ledger LINK BUY found; using known 2026-08-24 fill shape")

    rsi, sent = 46.6, 0.89
    try:
        rsi_c = json.loads((ROOT / "data/state/rsi_cache.json").read_text())
        r = (rsi_c.get("rsi") or {}).get("LINK-USD")
        if r is not None:
            # keep entry thesis RSI if we have it; else live
            pass
    except Exception:
        pass
    try:
        from phase6.core.sentiment_scorer import load_sentiment_scores

        s = load_sentiment_scores(universe=["LINK-USD"]) or {}
        # Entry thesis used hot sent; for backfill of *entry* tag use 0.89 if live lower
        # Prefer explicit entry snapshot when tagging historical
    except Exception:
        s = {}

    # Entry tag should reflect *entry* conditions (poster child), not live fade already
    row = backfill_lot_from_buy_trade(link_buy, rsi=46.6, sentiment=0.89)
    print("Backfilled lot:", json.dumps(row, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill-link", action="store_true")
    ap.add_argument("--notify", action="store_true")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config/trading_config_phase6.json").read_text())
    if args.backfill_link:
        backfill_link()

    lots = load_entry_lots()
    print(f"Open entry lots: {sum(1 for x in lots if x.get('open', True))}")
    events = run_sentiment_fade_shadow(config_dict=cfg, notify=args.notify)
    print(f"Fade events this tick: {len(events)}")
    for e in events:
        print(json.dumps(e, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
