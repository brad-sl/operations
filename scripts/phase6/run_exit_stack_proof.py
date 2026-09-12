#!/usr/bin/env python3
"""CLI: exit stack proof packet (PC-02). Measure-only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Build exit stack proof packet")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--json-stdout", action="store_true")
    args = ap.parse_args()
    from phase6.core.exit_stack_proof import build_live_exit_stack_proof

    payload = build_live_exit_stack_proof(write=not args.no_write)
    g = payload.get("go_nogo") or {}
    if args.json_stdout:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(g.get("headline"))
        print((payload.get("plain_english") or "")[:400])
        w30 = (payload.get("windows") or {}).get("30d") or {}
        print(
            f"30d sells={w30.get('n_sell')} tp:sl={w30.get('tp_vs_sl_count')} "
            f"tp_bank={w30.get('tp_bank_usd')} sl_bank={w30.get('sl_bank_usd')}"
        )
        if not args.no_write:
            print("wrote data/state/exit_stack_proof_latest.json + reports/EXIT_STACK_PROOF_LATEST.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
