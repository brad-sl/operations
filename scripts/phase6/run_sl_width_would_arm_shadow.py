#!/usr/bin/env python3
"""CLI: 3% vs 8% SL would-arm shadow. MEASURE_ONLY. No orders."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.sl_width_would_arm_shadow import run_and_persist  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="SL width would-arm shadow (3% fuse measure-only)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    out = run_and_persist()
    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return 0
    print(
        f"SL would-arm shadow · n={out.get('n_eval')} "
        f"3pct={out.get('n_would_3pct')} 8pct={out.get('n_would_8pct')} "
        f"live_apply=OFF status={out.get('status')}"
    )
    print("state: data/state/sl_width_would_arm_latest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
