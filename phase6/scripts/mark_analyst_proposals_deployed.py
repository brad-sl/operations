#!/usr/bin/env python3
"""Mark analyst proposals accepted + deployed (user: proceed with 1, 2, and 3)."""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "data/state/analyst_proposed_backlog.json"
IDS = [
    "ANALYST-20260708-004",
    "ANALYST-20260708-005",
    "ANALYST-20260708-006",
]
HANDOFFS = {
    "ANALYST-20260708-004": "phase6/research/scenarios/r2_defensive_sharpe_gate.json + weekly OPT pack switch",
    "ANALYST-20260708-005": "stop_loss_manager LOW-risk skip poll; sl_preflight tick/settlement (existing + hardened)",
    "ANALYST-20260708-006": "pre_rebalance parallel refresh + on-demand second pass + venv python",
}


def main() -> int:
    data = json.loads(BACKLOG.read_text())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for p in data.get("proposals", []):
        if p.get("id") in IDS:
            p["status"] = "accepted"
            p["accepted"] = "2026-07-08 (user: proceed with 1, 2, and 3)"
            p["deployed"] = now
            p["handoff"] = HANDOFFS.get(p["id"], "")
    BACKLOG.write_text(json.dumps(data, indent=2) + "\n")
    print(f"marked deployed: {IDS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())