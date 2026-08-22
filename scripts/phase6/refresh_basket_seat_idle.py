#!/usr/bin/env python3
"""Refresh basket seat idle snapshot (observe-only). No trading / no membership writes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.basket_seat_idle import (  # noqa: E402
    SeatIdleConfig,
    build_seat_idle_snapshot,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--min-seat-days", type=int, default=7)
    p.add_argument("--min-idle-days", type=int, default=7)
    p.add_argument("--flat-usd", type=float, default=40.0)
    p.add_argument(
        "--allow-held-flag",
        action="store_true",
        help="Flag idle even when held >= flat threshold (default requires flat)",
    )
    p.add_argument("--no-write", action="store_true", help="Print only; do not persist")
    p.add_argument("--quiet", action="store_true", help="One-line summary only")
    args = p.parse_args()

    cfg = SeatIdleConfig(
        min_seat_days=args.min_seat_days,
        min_idle_days=args.min_idle_days,
        flat_held_usd=args.flat_usd,
        require_flat_for_flag=not args.allow_held_flag,
    )
    snap = build_seat_idle_snapshot(cfg=cfg, write=not args.no_write)
    if args.quiet:
        print(
            f"seat_idle n={snap['n_active']} flagged={snap['n_idle_flagged']} "
            f"pairs={','.join(snap['idle_flagged_pairs']) or '-'} "
            f"as_of={snap['as_of_date']}"
        )
        return 0

    # Compact human table
    print(
        f"basket_seat_idle  as_of={snap['as_of_date']}  "
        f"flagged={snap['n_idle_flagged']}/{snap['n_active']}  "
        f"hard_eject={snap['hard_eject']}"
    )
    print(
        f"{'pair':12} {'seat_d':>6} {'cap_id':>6} {'flat_st':>7} "
        f"{'held':>8} {'buys':>4} {'flag':>5}  since_src"
    )
    for row in snap.get("rows") or []:
        print(
            f"{row['pair']:12} "
            f"{str(row.get('seat_days')):>6} "
            f"{str(row.get('capital_idle_days')):>6} "
            f"{str(row.get('flat_day_streak')):>7} "
            f"{float(row.get('held_usd') or 0):>8.1f} "
            f"{int(row.get('buys_while_seated') or 0):>4} "
            f"{'Y' if row.get('idle_cycle_flag') else '.':>5}  "
            f"{row.get('active_since_source')}"
        )
    if snap.get("idle_flagged_pairs"):
        print("idle_cycle_candidates:", ", ".join(snap["idle_flagged_pairs"]))
    else:
        print("idle_cycle_candidates: (none)")
    print(json.dumps({"summary": {
        "n_active": snap["n_active"],
        "n_idle_flagged": snap["n_idle_flagged"],
        "idle_flagged_pairs": snap["idle_flagged_pairs"],
        "as_of_date": snap["as_of_date"],
        "wrote": not args.no_write,
    }}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
