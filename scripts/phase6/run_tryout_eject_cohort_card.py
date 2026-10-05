#!/usr/bin/env python3
"""CLI: E-EJECT-COHORT-CARD (measure-only).

  PYTHONPATH=. python scripts/phase6/run_tryout_eject_cohort_card.py
  PYTHONPATH=. python scripts/phase6/run_tryout_eject_cohort_card.py --days 7 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="E-EJECT-COHORT-CARD measure scorecard")
    ap.add_argument("--days", type=float, default=14.0, help="Lookback days (default 14)")
    ap.add_argument("--no-write", action="store_true", help="Do not write state/report")
    ap.add_argument("--json", action="store_true", help="Print full JSON")
    ap.add_argument("--plain", action="store_true", help="Print plain headline only")
    args = ap.parse_args()

    from phase6.core.tryout_eject_cohort_card import render_markdown, run_card

    payload = run_card(lookback_days=args.days, write=not args.no_write)
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0
    if args.plain:
        hd = payload.get("headline") or {}
        sb = payload.get("scoreboard") or {}
        print(hd.get("plain") or "—")
        print(
            f"n={sb.get('n_ejects')} cleared={sb.get('n_cleared_live_kindling')} "
            f"pct={sb.get('pct_cleared_live_kindling')} "
            f"net=${sb.get('pnl_net_usd')} fees=${sb.get('rt_fee_usd')}"
        )
        if payload.get("written"):
            print("WROTE", payload["written"])
        return 0
    print(render_markdown(payload))
    if payload.get("written"):
        print("WROTE", payload["written"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
