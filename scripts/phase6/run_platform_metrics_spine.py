#!/usr/bin/env python3
"""CLI: build platform metrics spine (full pair lifecycle + runner ops). Measure-only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Platform metrics spine (lifecycle + ops)")
    ap.add_argument("--no-write", action="store_true", help="Print only; do not write artifacts")
    ap.add_argument("--json-stdout", action="store_true")
    ap.add_argument("--md-stdout", action="store_true", help="Print markdown report to stdout")
    args = ap.parse_args()

    from phase6.core.platform_metrics_spine import build_spine, render_markdown

    payload = build_spine(write=not args.no_write)
    if args.json_stdout:
        print(json.dumps(payload, indent=2, default=str))
        return 0
    if args.md_stdout:
        print(render_markdown(payload))
        return 0

    go = payload.get("go_nogo") or {}
    life = payload.get("lifecycle") or {}
    funnel = life.get("funnel") or {}
    runner = payload.get("runner_ops") or {}
    choke = life.get("choke_point") or {}
    print("platform-metrics-spine")
    print(
        f"ops={go.get('ops')} money_path={go.get('money_path')} "
        f"auto_membership={go.get('auto_membership')} edge={go.get('edge_claim_allowed')}"
    )
    print(
        f"lifecycle seat={funnel.get('n_seated')} sig={funnel.get('n_signaled')} "
        f"fill={funnel.get('n_filled')} win={funnel.get('n_filled_win')} "
        f"choke={choke.get('id')}"
    )
    print(
        f"runner ops_ok={runner.get('ops_ok')} can_buy={runner.get('can_buy_before_next_rebalance')} "
        f"sl_cov={runner.get('sl_coverage')} swaps={life.get('live_membership_swaps')}"
    )
    print(go.get("plain_english") or "")
    if not args.no_write:
        for a in payload.get("actions_taken") or []:
            print(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
