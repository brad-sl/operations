#!/usr/bin/env python3
"""CLI: bank/trail-while-green triple shadow CF (A / C / A→C). Measure-only."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/brad/projects/crypto-trading-bot")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.bank_trail_while_green_cf import run_cf  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Bank/trail while green triple CF (measure-only)")
    ap.add_argument(
        "--since",
        default="2026-08-06T00:00:00+00:00",
        help="ISO start for exchange SL legs",
    )
    ap.add_argument("--cfg", default=None, help="Policy JSON path")
    ap.add_argument("--json-stdout", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    cfg = Path(args.cfg) if args.cfg else None
    payload = run_cf(since=since, cfg_path=cfg, write=not args.no_write)
    s = payload.get("summary") or {}
    print("Bank/trail-while-green CF — MEASURE_ONLY (no live apply)")
    print(f"Since {payload.get('since')} · legs {s.get('n_legs')} · actual sum {s.get('actual_pnl_sum')}")
    for k in ("A", "C", "AC"):
        a = s.get(k) or {}
        print(
            f"  {k}: would_arm {a.get('n_would_arm')}/{a.get('n')}  "
            f"sum_Δ$ {a.get('sum_delta_vs_actual_usd')}  med {a.get('median_delta_vs_actual_usd')}"
        )
    wo = s.get("would_arm_only") or {}
    print(f"Would-arm legs only (n={s.get('n_would_arm_legs')}):")
    for k in ("A", "C", "AC"):
        a = wo.get(k) or {}
        print(
            f"  {k}: sum_Δ$ {a.get('sum_delta_vs_actual_usd')}  med {a.get('median_delta_vs_actual_usd')}"
        )
    print(f"Winner all-legs: {s.get('winner_by_sum_delta')} · would-arm-only: {s.get('winner_would_arm_only')}")
    if payload.get("wrote_md"):
        print(f"Report: {payload['wrote_md']}")
    if args.json_stdout:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
