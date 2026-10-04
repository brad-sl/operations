#!/usr/bin/env python3
"""CLI: fee audit on tryout scale-window eject cohort (P2).

Examples:
  PYTHONPATH=. python scripts/phase6/run_tryout_eject_fee_audit.py
  PYTHONPATH=. python scripts/phase6/run_tryout_eject_fee_audit.py --fetch-live
  PYTHONPATH=. python scripts/phase6/run_tryout_eject_fee_audit.py --fetch-live --backfill --go
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
    ap = argparse.ArgumentParser(description="Tryout eject fee audit (measure)")
    ap.add_argument("--fetch-live", action="store_true", help="Pull total_fees from Coinbase orders")
    ap.add_argument("--no-fetch-live", action="store_true", help="Estimates only (tier rate)")
    ap.add_argument("--lookback-days", type=float, default=None, help="Optional window filter")
    ap.add_argument("--backfill", action="store_true", help="Stamp net fees onto ledger eject rows")
    ap.add_argument("--go", action="store_true", help="With --backfill: write ledger (else dry-run)")
    ap.add_argument("--json", action="store_true", help="Print full JSON payload")
    args = ap.parse_args()

    from phase6.core.tryout_eject_fee_audit import run_audit, render_markdown

    fetch = True
    if args.no_fetch_live:
        fetch = False
    elif args.fetch_live:
        fetch = True

    payload = run_audit(
        fetch_live=fetch,
        backfill=bool(args.backfill),
        dry_run_backfill=not bool(args.go),
        lookback_days=args.lookback_days,
    )
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(render_markdown(payload))
        sb = payload.get("scoreboard") or {}
        sm = payload.get("sums") or {}
        print(
            f"\nSUMMARY n={payload.get('n_ejects')} "
            f"gross=${sm.get('pnl_gross_usd')} rt_fees=${sm.get('rt_fee_usd')} "
            f"net=${sm.get('pnl_net_usd')} wiped={sb.get('gross_green_net_red_n')} "
            f"blind_wr={sb.get('fee_blind_wr')} aware_wr={sb.get('fee_aware_wr')}"
        )
        if payload.get("backfill"):
            print("BACKFILL", payload["backfill"])
        if payload.get("written"):
            print("WROTE", payload["written"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
