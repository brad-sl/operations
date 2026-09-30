#!/usr/bin/env python3
"""CLI: pair lifecycle by crypto class. Measure-only. No thin-N edge claims."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.pair_lifecycle_by_class import (  # noqa: E402
    REPORT_PATH,
    STATE_PATH,
    build_pair_lifecycle_by_class,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lookback-days", type=float, default=None)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--json", action="store_true", help="print full payload JSON")
    args = ap.parse_args()
    payload = build_pair_lifecycle_by_class(
        lookback_days=args.lookback_days,
        write=not args.no_write,
    )
    print(f"Pair lifecycle by class written: {STATE_PATH}")
    print(f"report: {REPORT_PATH}")
    print(payload.get("plain_english"))
    by = payload.get("by_class") or []
    for c in by:
        print(
            f"  {c.get('key')}: n={c.get('n_rt')} win={c.get('win_rate')} "
            f"sl={c.get('sl_rate')} tp={c.get('tp_rate')} tax={c.get('process_tax_rate')} "
            f"pnl_sum={c.get('pnl_sum')} claim={c.get('claim_level')}"
        )
    for n in payload.get("hypothesis_notes") or []:
        print(f"note: {n}")
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
