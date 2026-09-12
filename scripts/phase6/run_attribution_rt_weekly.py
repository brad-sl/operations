#!/usr/bin/env python3
"""CLI: attribution RT weekly (PC-06). Measure-only. No thin-N edge claims."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.attribution_rt_weekly import (  # noqa: E402
    REPORT_PATH,
    STATE_PATH,
    build_attribution_rt_weekly,
)


def main() -> int:
    payload = build_attribution_rt_weekly(write=True)
    s = payload.get("summary") or {}
    print(f"Attribution RT weekly written: {STATE_PATH}")
    print(f"report: {REPORT_PATH}")
    print(
        f"n_rt={s.get('n_rt_primary')} full_stamp={s.get('n_full_core_stamp')} "
        f"edge_claim_allowed={s.get('edge_claim_allowed')}"
    )
    print(json.dumps({"summary": s, "coverage_audit": payload.get("coverage_audit")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
