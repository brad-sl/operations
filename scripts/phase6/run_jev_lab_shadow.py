#!/usr/bin/env python3
"""Run Jev lab shadow (OpenRouter Decisions API). Measure-only — no orders.

  python3 scripts/phase6/run_jev_lab_shadow.py
  python3 scripts/phase6/run_jev_lab_shadow.py --dry-run
  python3 scripts/phase6/run_jev_lab_shadow.py --pairs BTC-USD,ETH-USD
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.jev_lab_shadow import LabConfig, run_lab  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Jev lab shadow (no orders)")
    p.add_argument("--pairs", default="BTC-USD,ETH-USD")
    p.add_argument("--dry-run", action="store_true", help="Mock answers, no HTTP")
    p.add_argument("--model", default="~typesafe/jev-latest")
    p.add_argument("--max-calls-per-day", type=int, default=24)
    p.add_argument("--json", action="store_true", help="Print full JSON")
    args = p.parse_args()
    pairs = [x.strip() for x in args.pairs.split(",") if x.strip()]
    cfg = LabConfig(
        pairs=pairs,
        dry_run=bool(args.dry_run),
        model=args.model,
        max_calls_per_day=int(args.max_calls_per_day),
    )
    summary = run_lab(cfg=cfg, pairs=pairs)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(summary.get("plain") or json.dumps(summary, indent=2))
        print(
            f"[meta] ok={summary.get('n_ok')}/{summary.get('n_pairs')} "
            f"paper_buy_tags={summary.get('paper_buy_tags')} "
            f"budget={summary.get('budget')} dry_run={summary.get('dry_run')}"
        )
    return 0 if int(summary.get("n_ok") or 0) > 0 or cfg.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
