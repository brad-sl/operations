#!/usr/bin/env python3
"""CLI: live fee-tier snapshot (read-only). No orders."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Snapshot Coinbase fee tier (no orders)")
    ap.add_argument("--quiet-ok", action="store_true", help="Empty stdout on success")
    args = ap.parse_args()
    from phase6.core.fee_tier_snapshot import run_fee_tier_snapshot

    payload = run_fee_tier_snapshot()
    if not args.quiet_ok:
        print(json.dumps(payload, indent=2, default=str))
    elif not payload.get("ok"):
        print(json.dumps({"ok": False, "error": payload.get("error")}, default=str))
        return 1
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
