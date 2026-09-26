#!/usr/bin/env python3
"""CLI: tryout seat approval → autonomous policy.

  python3 scripts/phase6/run_rsi_event_tryout_seat_policy.py
  python3 scripts/phase6/run_rsi_event_tryout_seat_policy.py --arm-auto
  python3 scripts/phase6/run_rsi_event_tryout_seat_policy.py --disarm
  python3 scripts/phase6/run_rsi_event_tryout_seat_policy.py --record-go --pair ETH-USD --shell 25
  python3 scripts/phase6/run_rsi_event_tryout_seat_policy.py --required 2
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.rsi_event_tryout_seat_policy import (  # noqa: E402
    POLICY_PATH,
    arm_autonomous,
    disarm,
    load_policy,
    policy_status_plain,
    record_manual_go,
    save_policy,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tryout seat approval/autonomous policy")
    ap.add_argument("--arm-auto", action="store_true", help="Arm autonomous after N GOs")
    ap.add_argument("--force-arm", action="store_true", help="Arm even if GOs < required")
    ap.add_argument("--disarm", action="store_true", help="Back to approval mode")
    ap.add_argument("--kill", action="store_true", help="With --disarm: set kill flag")
    ap.add_argument("--record-go", action="store_true", help="Manually count a GO")
    ap.add_argument("--pair", default="")
    ap.add_argument("--shell", type=float, default=25.0)
    ap.add_argument("--receipt-id", default="")
    ap.add_argument("--required", type=int, default=None, help="Set required_manual_gos")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.required is not None:
        p = load_policy()
        p["required_manual_gos"] = max(1, int(args.required))
        save_policy(p)

    if args.record_go:
        if not args.pair:
            print("need --pair with --record-go", file=sys.stderr)
            return 2
        p = record_manual_go(
            pair=args.pair,
            shell_usd=float(args.shell),
            receipt_id=str(args.receipt_id or ""),
            note="cli_record_go",
            source="cli_record",
        )
    elif args.arm_auto:
        p = arm_autonomous(force=bool(args.force_arm))
        if p.get("arm_refused"):
            print(p["arm_refused"], file=sys.stderr)
            if args.json:
                print(json.dumps(p, indent=2, default=str))
            return 3
    elif args.disarm:
        p = disarm(kill=bool(args.kill))
    else:
        p = load_policy()

    if args.json:
        print(json.dumps(p, indent=2, default=str))
    else:
        print(policy_status_plain())
        print(f"path={POLICY_PATH}")
        if p.get("note"):
            print(f"note={p.get('note')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
