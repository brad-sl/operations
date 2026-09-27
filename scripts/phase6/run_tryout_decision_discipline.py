#!/usr/bin/env python3
"""CLI: tryout decision discipline (Jev-process map, measure/shadow default).

  python3 scripts/phase6/run_tryout_decision_discipline.py
  python3 scripts/phase6/run_tryout_decision_discipline.py --pair LINK-USD --rsi 35 --eng 0.40 --src paid_x
  python3 scripts/phase6/run_tryout_decision_discipline.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.tryout_decision_discipline import (  # noqa: E402
    CONFIG_PATH,
    LATEST_PATH,
    evaluate_candidate,
    load_config,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tryout decision discipline (shadow default)")
    ap.add_argument("--pair", default="LINK-USD")
    ap.add_argument("--rsi", type=float, default=40.0)
    ap.add_argument("--eng", type=float, default=0.35)
    ap.add_argument("--src", default="paid_x_probe")
    ap.add_argument("--floor", type=float, default=0.30)
    ap.add_argument("--rsi-max", type=float, default=55.0)
    ap.add_argument("--shell", type=float, default=25.0)
    ap.add_argument("--no-persist", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show-config", action="store_true")
    args = ap.parse_args()

    if args.show_config:
        cfg = load_config()
        print(json.dumps(cfg, indent=2))
        print(f"config_path={CONFIG_PATH}")
        return 0

    res = evaluate_candidate(
        pair=args.pair,
        rsi=args.rsi,
        eng=args.eng,
        eng_source=args.src,
        floor=args.floor,
        rsi_max=args.rsi_max,
        shell_usd=args.shell,
        regime={"strategy_mode": "deploy", "allow_new_buys": True, "regime": "flat"},
        seats_used_today=0,
        seats_max_day=6,
        open_tryout_seats=0,
        max_open_tryout=6,
        latch_age_min=15.0,
        persist=not args.no_persist,
    )
    if args.json:
        print(json.dumps(res, indent=2, default=str))
    else:
        print(res.get("plain_english"))
        pol = res.get("policy") or {}
        print(
            f"action={pol.get('action')} rung={pol.get('rung')} "
            f"setup={pol.get('setup_quality')} conf={pol.get('setup_confidence')} "
            f"live_apply={res.get('live_apply')} would_block={pol.get('would_block_if_live')}"
        )
        print(f"reasons: {pol.get('reasons')}")
        print(f"latest={LATEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
