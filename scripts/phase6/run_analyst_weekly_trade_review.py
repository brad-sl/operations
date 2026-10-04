#!/usr/bin/env python3
"""CLI: Analyst weekly 7d trade review fact pack (measure-only)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.analyst_weekly_trade_review import (  # noqa: E402
    REPORT_PATH,
    STATE_PATH,
    build_fact_pack,
    format_tg_card,
    load_latest,
    render_markdown,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=7, help="Lookback days (default 7)")
    ap.add_argument("--no-write", action="store_true", help="Do not persist state/report")
    ap.add_argument(
        "--no-refresh-attribution",
        action="store_true",
        help="Skip attribution_rt_weekly rebuild",
    )
    ap.add_argument(
        "--tg-card",
        action="store_true",
        help="Print short Telegram card to stdout (for agent/cron delivery)",
    )
    ap.add_argument("--json", action="store_true", help="Print full JSON payload")
    ap.add_argument("--md", action="store_true", help="Print markdown report body")
    ap.add_argument(
        "--load-latest",
        action="store_true",
        help="Load existing latest pack instead of rebuilding",
    )
    args = ap.parse_args(argv)

    if args.load_latest:
        payload = load_latest()
        if not payload:
            print("No latest pack at", STATE_PATH, file=sys.stderr)
            return 1
    else:
        payload = build_fact_pack(
            lookback_days=int(args.days),
            write=not args.no_write,
            refresh_attribution=not args.no_refresh_attribution,
        )

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0
    if args.md:
        print(render_markdown(payload))
        return 0
    if args.tg_card:
        print(format_tg_card(payload), end="")
        return 0

    s = payload.get("summary") or {}
    print(f"Analyst weekly 7d fact pack → {STATE_PATH}")
    print(f"report: {REPORT_PATH}")
    print(
        f"primary B/S={s.get('n_primary_buys')}/{s.get('n_primary_sells')} "
        f"pnl=${s.get('realized_pnl_usd')} wr={s.get('exit_wr')} "
        f"tax=${s.get('process_tax_usd')} seeds={len(payload.get('seed_hypotheses') or [])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
