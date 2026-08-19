#!/usr/bin/env python3
"""
Sweep dust / post-SL residual positions.

Uses phase6.core.sl_dust_sweep (real exchange balances when --execute).

Usage:
  .venv/bin/python scripts/phase6/sweep_dust_positions.py
  .venv/bin/python scripts/phase6/sweep_dust_positions.py --max-usd 50
  .venv/bin/python scripts/phase6/sweep_dust_positions.py --execute --max-usd 50
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Sweep dust alt positions / SL residuals")
    p.add_argument("--max-usd", type=float, default=50.0)
    p.add_argument("--min-usd", type=float, default=0.0)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--include-open-stop", action="store_true",
                   help="Sell even if an open stop exists (dangerous; default skip)")
    args = p.parse_args()

    from phase6.core.sl_dust_sweep import (
        list_orphan_dust_from_live_state,
        sweep_orphan_dust,
    )

    preview = list_orphan_dust_from_live_state(max_usd=args.max_usd, min_usd=args.min_usd)
    print(json.dumps({"dry_run": not args.execute, "candidates": preview}, indent=2))
    if not preview:
        print("No dust positions in range.")
        return 0
    if not args.execute:
        print("Dry-run only. Pass --execute to place market sells.")
        return 0

    logging.basicConfig(level=logging.INFO)
    from phase6.core.exchange_client import CoinbaseExchangeClient

    ex = CoinbaseExchangeClient(mode="live")
    summary = sweep_orphan_dust(
        ex,
        dry_run=False,
        max_usd=args.max_usd,
        min_usd=args.min_usd,
        skip_if_open_stop=not args.include_open_stop,
        config={
            "risk_management": {
                "dust_sweep_after_sl": True,
                "dust_sweep_max_usd": args.max_usd,
                "dust_sweep_min_usd": args.min_usd,
            }
        },
    )
    print(json.dumps(summary, indent=2, default=str))
    sold = [r for r in summary.get("results") or [] if r.get("success") and not r.get("skipped")]
    failed = [
        r
        for r in summary.get("results") or []
        if not r.get("success") and not r.get("skipped")
    ]
    print(f"sold={len(sold)} failed={len(failed)}")
    # Micro-dust exchange rejects are OK; only fail hard if a non-skip failure on meaningful size
    hard = [r for r in failed if float(r.get("usd_est") or r.get("value_usd_snapshot") or 0) >= 1.0]
    return 0 if not hard else 2


if __name__ == "__main__":
    raise SystemExit(main())
