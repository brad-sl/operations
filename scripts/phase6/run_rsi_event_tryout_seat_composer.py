#!/usr/bin/env python3
"""CLI: RSI-event → probe → TryoutSeatBuyAction composer (default all dry).

  # Regime-eligible doors, auto floor/max_rsi from quality_tryout
  python3 scripts/phase6/run_rsi_event_tryout_seat_composer.py

  # Post-15m-RSI cron path (money hard-off; paid X only with --go-x / COMPOSER_GO_X=1)
  python3 scripts/phase6/run_rsi_event_tryout_seat_composer.py --post-rsi --go-x --quiet-ok

  python3 scripts/phase6/run_rsi_event_tryout_seat_composer.py --go-x
  python3 scripts/phase6/run_rsi_event_tryout_seat_composer.py --go-x --go-buy --live

Never runs full book_rebalance.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.rsi_event_tryout_seat_composer import (  # noqa: E402
    ComposerConfig,
    run_composer,
    telegram_summary,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="RSI-event tryout seat composer (dry default)")
    ap.add_argument("--go-x", action="store_true", help="Allow paid X probe under budget")
    ap.add_argument("--go-buy", action="store_true", help="GO intent for seat (still dry without --live)")
    ap.add_argument(
        "--live",
        action="store_true",
        help="Allow money when combined with --go-buy (dry_run_buy=False)",
    )
    ap.add_argument(
        "--post-rsi",
        action="store_true",
        help="Post-15m RSI hook: scan all regime doors; money always OFF",
    )
    ap.add_argument(
        "--top-k",
        type=int,
        default=0,
        help="Max doors to rank for X (0 = all regime-eligible)",
    )
    ap.add_argument(
        "--floor",
        type=float,
        default=0.0,
        help="Sent floor (0 = quality_tryout min_sentiment)",
    )
    ap.add_argument(
        "--rsi-max",
        type=float,
        default=0.0,
        help="RSI door max (0 = quality_tryout max_rsi)",
    )
    ap.add_argument("--max-shell-usd", type=float, default=75.0)
    ap.add_argument("--pair", default="", help="Force pair override (still gated)")
    ap.add_argument("--max-rsi-day", type=int, default=4)
    ap.add_argument("--max-day", type=int, default=8)
    ap.add_argument("--cooldown-h", type=float, default=6.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument(
        "--quiet-ok",
        action="store_true",
        help="Exit 0 even when idle (cron-friendly)",
    )
    args = ap.parse_args()

    cfg = ComposerConfig(
        top_k=int(args.top_k),
        floor=float(args.floor),
        rsi_max=float(args.rsi_max),
        max_shell_usd=float(args.max_shell_usd),
        spend_x=bool(args.go_x),
        dry_run_x=not bool(args.go_x),
        go_buy=bool(args.go_buy) and (not bool(args.post_rsi)),
        dry_run_buy=not (bool(args.go_buy) and bool(args.live) and (not bool(args.post_rsi))),
        pair_override=str(args.pair or ""),
        max_rsi_day=int(args.max_rsi_day),
        max_day=int(args.max_day),
        cooldown_h=float(args.cooldown_h),
        post_rsi=bool(args.post_rsi),
        actor="post_rsi_cron" if args.post_rsi else "cli",
    )
    result = run_composer(cfg)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0
    if args.telegram:
        print(telegram_summary(result))
        return 0
    print(result.get("plain_english") or "composer ok")
    c = result.get("config") or {}
    print(
        f"money={c.get('money')} spend_x={c.get('spend_x')} post_rsi={c.get('post_rsi')} "
        f"universe={result.get('n_universe')} in_door={result.get('n_in_rsi_door')} "
        f"candidate={result.get('candidate')} seat_skip={result.get('seat_skipped_reason')}"
    )
    seat = result.get("seat_receipt") or {}
    if seat:
        print(f"seat status={seat.get('status')} reasons={list(seat.get('reasons') or [])[:4]}")
    if args.quiet_ok:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
