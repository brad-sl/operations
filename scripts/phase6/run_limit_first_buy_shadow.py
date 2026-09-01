#!/usr/bin/env python3
"""CLI: limit-first buy shadow board (Phase C). No orders / no config writes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.limit_first_buy_shadow import (  # noqa: E402
    ShadowCfg,
    run_limit_first_buy_shadow,
    telegram_summary,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Limit-first buy shadow CF board (fee delta upper bound; no orders)"
    )
    ap.add_argument("--lookback-h", type=int, default=72)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument(
        "--quiet-ok",
        action="store_true",
        help="Empty stdout when no recent market buys (cron-friendly)",
    )
    ap.add_argument(
        "--with-book",
        action="store_true",
        help="Also snapshot live bid would-limit (read-only book; no orders)",
    )
    args = ap.parse_args()
    cfg = ShadowCfg(lookback_hours=args.lookback_h)
    exchange = None
    pairs = None
    if args.with_book:
        try:
            from phase6.core.exchange_client import CoinbaseExchangeClient
            from phase6.core.paths import load_trading_basket

            exchange = CoinbaseExchangeClient(mode="live")
            pairs = list(load_trading_basket() or [])[:12]
        except Exception:
            exchange = None
            pairs = None
    summary = run_limit_first_buy_shadow(cfg, exchange=exchange, pairs=pairs)
    body = telegram_summary(summary)
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
        return 0
    if args.telegram or args.quiet_ok:
        if body:
            print(body)
        return 0
    s = summary.get("summary") or {}
    print(
        body
        or f"limit-first C shadow ok n={s.get('n_buys')} delta_ub=${s.get('sum_fee_delta_upper_bound')} live_gate=OFF"
    )
    print("report: reports/LIMIT_FIRST_BUY_SHADOW_LATEST.md")
    print("state: data/state/limit_first_buy_shadow_latest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
