#!/usr/bin/env python3
"""CLI for POOL-CYCLING-001 shadow (default) / proposed / apply."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.pool_cycling import (  # noqa: E402
    PoolCyclingConfig,
    report_to_plain_english,
    run_pool_cycling,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Pool cycling: active basket ↔ opportunity pool")
    p.add_argument("--shadow", action="store_true", default=True, help="Shadow only (default)")
    p.add_argument(
        "--write-proposed",
        action="store_true",
        help="Write data/state/pool_cycling_proposed_pairs.json if swaps exist",
    )
    p.add_argument(
        "--apply-config",
        action="store_true",
        help="DANGEROUS: rewrite global_settings.pairs (creates .bak). Not for cron.",
    )
    p.add_argument("--max-swaps", type=int, default=1)
    p.add_argument("--min-delta", type=float, default=0.08)
    p.add_argument("--weak-max", type=float, default=0.35)
    p.add_argument("--strong-min", type=float, default=0.40)
    p.add_argument("--json", action="store_true", help="Print full report JSON")
    p.add_argument("--no-log", action="store_true", help="Do not append jsonl / latest")
    args = p.parse_args()

    if args.apply_config:
        print(
            "WARNING: --apply-config will mutate trading_config_phase6.json "
            "(backup created). Prefer --write-proposed + manual promote.",
            file=sys.stderr,
        )

    cfg = PoolCyclingConfig(
        min_score_delta=args.min_delta,
        weak_max_score=args.weak_max,
        strong_min_score=args.strong_min,
        max_swaps=args.max_swaps,
    )
    report = run_pool_cycling(
        cfg=cfg,
        write_log=not args.no_log,
        write_proposed=args.write_proposed or args.apply_config,
        apply_config=args.apply_config,
    )
    if args.json:
        from dataclasses import asdict

        print(json.dumps(asdict(report), indent=2))
    else:
        print(report_to_plain_english(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
