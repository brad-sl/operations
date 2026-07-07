#!/usr/bin/env python3
"""Daily shadow drift check + auto-rollback on monitor breach."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.shadow_drift_monitor import run_monitor_and_rollback


def main() -> int:
    report = run_monitor_and_rollback()
    print(json.dumps(report, indent=2))
    if report.get("status") == "inactive":
        return 0
    return 0 if report.get("monitor_ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())