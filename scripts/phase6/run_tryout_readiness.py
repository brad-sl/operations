#!/usr/bin/env python3
"""CLI: refresh tryout readiness board (PC-03)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Build tryout readiness board")
    ap.add_argument("--no-write", action="store_true", help="Print only; do not write artifacts")
    ap.add_argument("--json-stdout", action="store_true")
    args = ap.parse_args()
    from phase6.core.tryout_readiness import build_live_tryout_readiness

    payload = build_live_tryout_readiness(write=not args.no_write)
    if args.json_stdout:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(
            f"can_buy={payload.get('can_buy_before_next_rebalance')} "
            f"mode={payload.get('sent_mode')} "
            f"floor={((payload.get('entry_floors') or {}).get('live_floor_used'))} "
            f"eligible={payload.get('eligible_tryout_pairs')}"
        )
        print((payload.get("plain_english") or "")[:300])
        if not args.no_write:
            print("wrote data/state/tryout_readiness_latest.json + reports/TRYOUT_READINESS_LATEST.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
