#!/usr/bin/env python3
"""CLI: RSI-event → X → tryout shadow board. No orders / no paid X by default."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.rsi_event_x_tryout_shadow import (  # noqa: E402
    ShadowConfig,
    run_shadow,
    telegram_summary,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="RSI-event X tryout shadow (tryout doors, top-K; no orders)"
    )
    ap.add_argument("--rsi-max", type=float, default=40.0, help="Wash band max RSI (default 40)")
    ap.add_argument("--rsi-min", type=float, default=0.0)
    ap.add_argument("--top-k", type=int, default=2, help="Max would-query pairs if many flip")
    ap.add_argument("--floor", type=float, default=0.30, help="Tryout sentiment floor")
    ap.add_argument("--pair", action="append", default=[], help="Override universe to these pairs")
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--telegram",
        action="store_true",
        help="Short body only when top-K non-empty (quiet-ok pattern)",
    )
    ap.add_argument(
        "--quiet-ok",
        action="store_true",
        help="Exit 0 with no stdout when nothing selected (cron-friendly)",
    )
    args = ap.parse_args()
    cfg = ShadowConfig(
        rsi_wash_max=float(args.rsi_max),
        rsi_wash_min=float(args.rsi_min),
        top_k=int(args.top_k),
        tryout_floor=float(args.floor),
        pairs_override=tuple(args.pair) if args.pair else (),
        place_orders=False,
        mutate_config=False,
        spend_x=False,
    )
    board = run_shadow(cfg)
    body = telegram_summary(board)
    if args.json:
        print(json.dumps(board, indent=2, default=str))
        return 0
    if args.telegram or args.quiet_ok:
        if body:
            print(body)
        return 0
    print(body or board.get("plain_english") or "shadow ok")
    print(f"trigger_pool={board.get('n_trigger_pool')} selected={board.get('n_selected_top_k')} "
          f"would_buy={board.get('n_would_buy_if_x_pass')} live_gate=OFF")
    arts = board.get("artifacts") or {}
    print(f"report: {arts.get('report', 'reports/RSI_EVENT_X_TRYOUT_SHADOW_LATEST.md')}")
    print(f"state: {arts.get('latest', 'data/state/rsi_event_x_tryout_shadow_latest.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
