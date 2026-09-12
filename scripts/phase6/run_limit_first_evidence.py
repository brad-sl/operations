#!/usr/bin/env python3
"""CLI: limit-first fill evidence (PC-05). Measure-only. Honest zero OK."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.limit_first_evidence import (  # noqa: E402
    REPORT_PATH,
    STATE_PATH,
    build_limit_first_evidence,
)


def main() -> int:
    payload = build_limit_first_evidence(write=True)
    a = payload.get("aggregate") or {}
    d = payload.get("drought") or {}
    print(f"Limit-first evidence written: {STATE_PATH}")
    print(f"report: {REPORT_PATH}")
    print(
        f"attempts={a.get('limit_attempts')} filled={a.get('limit_filled')} "
        f"fill_rate={a.get('fill_rate')} drought={d.get('drought')} "
        f"mkt_fb={a.get('market_fallback_events')}"
    )
    print(json.dumps({"aggregate": a, "drought": d, "integrity": payload.get("integrity")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
