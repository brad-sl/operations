#!/usr/bin/env python3
"""
Health: post-fix Polymarket influence stamps for RERUN trial.

no_agent pattern: **empty stdout when OK**; print alert lines on fail.
Exit 0 always for cron friendliness unless --strict.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.run_polymarket_influence_backtest import (  # noqa: E402
    DEFAULT_FIX_CUTOFF,
    _load_influence,
    _parse_ts,
)

STATE = ROOT / "data" / "state" / "polymarket_influence_rerun_health_latest.json"


def check(since: datetime, min_n: int = 3, min_unique: int = 3, min_stdev: float = 0.01) -> dict:
    rows = [r for r in _load_influence() if r["ts"] >= since]
    biases = [r["bias"] for r in rows]
    unique = len({round(b, 3) for b in biases}) if biases else 0
    stdev = statistics.pstdev(biases) if len(biases) > 1 else 0.0
    stuck = bool(biases) and unique <= 1 and abs(biases[0] - 0.5) < 1e-9
    ok = (
        len(biases) >= min_n
        and unique >= min_unique
        and stdev >= min_stdev
        and not stuck
    )
    return {
        "schema": "polymarket_influence_rerun_health_v1",
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "since": since.isoformat(),
        "ok": ok,
        "n_post_fix": len(biases),
        "n_unique_bias_3dp": unique,
        "bias_stdev": stdev,
        "bias_min": min(biases) if biases else None,
        "bias_max": max(biases) if biases else None,
        "stuck_at_0_5": stuck,
        "trial_id": "ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902",
        "note": (
            "OK — post-fix meter has range"
            if ok
            else "WAIT/ALERT — need more post-fix stamps with bias range (024 hist was stuck 0.5)"
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=DEFAULT_FIX_CUTOFF)
    ap.add_argument("--min-n", type=int, default=3)
    ap.add_argument("--min-unique", type=int, default=3)
    ap.add_argument("--min-stdev", type=float, default=0.01)
    ap.add_argument("--strict", action="store_true", help="exit 1 on fail")
    ap.add_argument("--verbose", action="store_true", help="always print JSON")
    args = ap.parse_args()
    since = _parse_ts(args.since)
    assert since is not None
    rep = check(since, min_n=args.min_n, min_unique=args.min_unique, min_stdev=args.min_stdev)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(rep, indent=2) + "\n")
    if args.verbose or not rep["ok"]:
        print(rep["note"])
        print(json.dumps({k: rep[k] for k in (
            "ok", "n_post_fix", "n_unique_bias_3dp", "bias_stdev",
            "bias_min", "bias_max", "stuck_at_0_5", "since"
        )}, indent=2))
    # empty stdout when OK and not verbose
    if args.strict and not rep["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
