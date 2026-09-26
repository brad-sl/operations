#!/usr/bin/env python3
"""CLI: tryout scale-up approval → autonomous ladder.

  python3 scripts/phase6/run_tryout_scale_up_ladder.py
  python3 scripts/phase6/run_tryout_scale_up_ladder.py --arm-auto
  python3 scripts/phase6/run_tryout_scale_up_ladder.py --disarm
  python3 scripts/phase6/run_tryout_scale_up_ladder.py --disarm --kill
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.tryout_scale_up_ladder import (  # noqa: E402
    arm_autonomous,
    disarm,
    load_ladder,
    status_plain,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Tryout scale-up Brad ladder")
    p.add_argument("--arm-auto", action="store_true", help="Arm autonomous after N GOs")
    p.add_argument(
        "--force-arm",
        action="store_true",
        help="Arm even if GO count short (operator override)",
    )
    p.add_argument("--disarm", action="store_true", help="Back to approval mode")
    p.add_argument("--kill", action="store_true", help="With --disarm, freeze auto")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if args.arm_auto:
        out = arm_autonomous(force=bool(args.force_arm))
    elif args.disarm:
        out = disarm(kill=bool(args.kill))
    else:
        out = load_ladder()

    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(status_plain())
        if out.get("arm_refused"):
            print(f"arm_refused: {out['arm_refused']}")
        if out.get("note"):
            print(out["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
