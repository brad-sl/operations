#!/usr/bin/env python3
"""CLI: BTC-regime preferred-arm switch (shadow | production).

Never enables live_membership_swaps. preferred_arm only when --apply.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.regime_arm_switch import run  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Switch paper-primary basket arm by BTC 7d regime. "
            "shadow|production both keep live membership OFF."
        )
    )
    p.add_argument(
        "--mode",
        choices=("shadow", "production"),
        default="shadow",
        help="shadow=default collect path; production=same selector for live attention SSOT",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write preferred_arm into basket_swap_brad_decision.json (live swaps still forced false)",
    )
    p.add_argument(
        "--no-network",
        action="store_true",
        help="Use cached BTC daily only (no Coinbase fetch)",
    )
    p.add_argument(
        "--min-dwell-hours",
        type=float,
        default=24.0,
        help="Min hours between preferred_arm flips (default 24)",
    )
    p.add_argument("--json", action="store_true", help="Print full result JSON")
    args = p.parse_args()

    result = run(
        mode=args.mode,
        apply=args.apply,
        use_network=not args.no_network,
        min_dwell_hours=args.min_dwell_hours,
    )
    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    snap = result.get("snapshot") or {}
    print(
        f"regime_arm_switch mode={result.get('mode')} apply={result.get('apply')} "
        f"tape={snap.get('sticky_tape')} ret7={snap.get('btc_ret_7d_pct')} "
        f"arm={result.get('after_preferred_arm')} "
        f"changed={result.get('changed')} written={result.get('decision_written')} "
        f"live_swaps=false"
    )
    if result.get("note"):
        print(result["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
