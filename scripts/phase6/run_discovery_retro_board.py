#!/usr/bin/env python3
"""CLI: discovery retro board (shadow lookback — no config / no orders)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.discovery_retro_board import RetroConfig, run_retro_board


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Discovery retro board: today's gainers × frozen contender history + "
            "T-7 forward book. Research only."
        )
    )
    p.add_argument("--top", type=int, default=15, help="Top N gainers by 24h %")
    p.add_argument(
        "--min-volume-usd",
        type=float,
        default=100_000.0,
        help="Min 24h quote volume for gainer universe",
    )
    p.add_argument(
        "--min-ret-pct",
        type=float,
        default=8.0,
        help="Min 24h return %% to enter gainer list",
    )
    p.add_argument(
        "--forward-days",
        type=float,
        default=7.0,
        help="Forward-book lookback days for T-N contender cohort",
    )
    p.add_argument("--json", action="store_true", help="Print full JSON board")
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write reports/state (stdout only)",
    )
    p.add_argument(
        "--no-prices",
        action="store_true",
        help="Skip Coinbase fetches (structure-only; needs --gainers-json)",
    )
    p.add_argument(
        "--gainers-json",
        type=str,
        default="",
        help="Optional path to JSON list of {product_id, ret_24h_pct, ...}",
    )
    args = p.parse_args()

    cfg = RetroConfig(
        top_gainers_n=args.top,
        min_gainer_volume_usd=args.min_volume_usd,
        min_gainer_ret_pct=args.min_ret_pct,
        forward_book_lookback_days=args.forward_days,
        write=not args.no_write,
        fetch_prices=not args.no_prices,
    )

    gainers_override = None
    if args.gainers_json:
        gainers_override = json.loads(Path(args.gainers_json).read_text(encoding="utf-8"))
        cfg.fetch_prices = True  # still need post-flag / forward book unless no-prices

    if args.no_prices and not args.gainers_json:
        print(
            "ERROR: --no-prices requires --gainers-json (or omit --no-prices)",
            file=sys.stderr,
        )
        return 2

    from phase6.core.discovery_retro_board import build_board, persist_board

    if gainers_override is not None:
        board = build_board(cfg, gainers_override=gainers_override)
        if cfg.write:
            board["wrote"] = persist_board(board)
        else:
            board["wrote"] = {}
    else:
        board = run_retro_board(cfg)

    if args.json:
        print(json.dumps(board, indent=2, default=str))
    else:
        print(board.get("plain_english") or "")
        wrote = board.get("wrote") or {}
        if wrote:
            print()
            for k, v in wrote.items():
                print(f"wrote {k}: {v}")
        print()
        print("Lead class counts:", board.get("lead_class_counts"))
        print("Hypotheses:")
        for h in board.get("method_hypotheses") or []:
            print(" ", h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
