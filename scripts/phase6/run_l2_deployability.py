#!/usr/bin/env python3
"""CLI: L2 deployability board (PC-04). Measure-only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.l2_deployability import (  # noqa: E402
    REPORT_PATH,
    STATE_PATH,
    build_live_l2_deployability,
)


def main() -> int:
    payload = build_live_l2_deployability(write=True)
    s = payload.get("summary") or {}
    print(f"L2 deployability written: {STATE_PATH}")
    print(f"report: {REPORT_PATH}")
    print(
        f"arm={payload.get('preferred_arm')} scored={s.get('n_scored')} "
        f"pass={s.get('n_l2_pass')} verdict={s.get('verdict')}"
    )
    print(json.dumps({"summary": s, "live_membership_swaps": payload.get("live_membership_swaps")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
