#!/usr/bin/env python3
"""CLI: return-entropy shadow board (evaluate-only). No orders / no config writes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.return_entropy_shadow import (  # noqa: E402
    EntropyConfig,
    run_return_entropy_shadow,
    telegram_summary,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Return entropy shadow board (no orders)")
    ap.add_argument("--window", type=int, default=48)
    ap.add_argument("--bins", type=int, default=10)
    ap.add_argument("--structure-max", type=float, default=0.35)
    ap.add_argument("--noise-min", type=float, default=0.70)
    ap.add_argument("--pair", action="append", default=[], help="Limit to pair(s); default basket+BTC/ETH")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--telegram", action="store_true")
    args = ap.parse_args()
    cfg = EntropyConfig(
        window=args.window,
        n_bins=args.bins,
        structure_max=args.structure_max,
        noise_min=args.noise_min,
        pairs=tuple(args.pair) if args.pair else (),
    )
    summary = run_return_entropy_shadow(cfg)
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    body = telegram_summary(summary)
    if args.telegram:
        if body:
            print(body)
        return 0
    if not args.json:
        print(
            body
            or f"entropy shadow ok n={summary.get('n_pairs')} labels={summary.get('by_label')}"
        )
        print("report: reports/RETURN_ENTROPY_SHADOW_LATEST.md")
        print("metrics: reports/RETURN_ENTROPY_SUCCESS_METRICS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
