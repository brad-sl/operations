#!/usr/bin/env python3
"""CLI: emerging pair discovery funnel (public market data; no sentiment by default)."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.pair_discovery import DiscoveryConfig, report_plain_english, run_discovery


def main() -> int:
    p = argparse.ArgumentParser(description="Emerging pair discovery (shadow funnel)")
    p.add_argument("--min-volume-usd", type=float, default=2_000_000.0)
    p.add_argument("--prequal-top", type=int, default=40)
    p.add_argument("--contenders", type=int, default=5)
    p.add_argument("--quality-min", type=float, default=0.35)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-write", action="store_true")
    p.add_argument(
        "--include-active",
        action="store_true",
        help="Allow names already in the basket into contender list",
    )
    p.add_argument(
        "--deep",
        action="store_true",
        help="Opt-in deep path flag (still does not spend X unless wired)",
    )
    args = p.parse_args()

    cfg = DiscoveryConfig(
        min_quote_volume_24h_usd=args.min_volume_usd,
        prequal_top_n=args.prequal_top,
        contender_top_n=args.contenders,
        min_quality_score=args.quality_min,
        exclude_active_from_contenders=not args.include_active,
        run_deep=args.deep,
    )
    report = run_discovery(cfg=cfg, write=not args.no_write)
    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(report_plain_english(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
