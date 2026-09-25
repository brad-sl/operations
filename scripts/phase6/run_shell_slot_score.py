#!/usr/bin/env python3
"""Score the evening tryout shell slot. Measure-only. Stdout empty unless actionable."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.shell_slot_score import (  # noqa: E402
    load_json,
    load_jsonl,
    render_md,
    score_slot,
)

STATE = ROOT / "data/state/shell_slot_score.jsonl"
LATEST = ROOT / "data/state/shell_slot_score_latest.json"
REPORT = ROOT / "reports/SHELL_SLOT_SCORE_LATEST.md"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--write", action="store_true", help="Append state + report")
    args = p.parse_args()
    readiness = load_json(ROOT / "data/state/tryout_readiness_latest.json")
    ledger = load_jsonl(ROOT / "trades/phase6_trades.jsonl")
    prior = [row.get("slot_id") for row in load_jsonl(STATE) if row.get("slot_id")]
    card = score_slot(
        readiness=readiness,
        ledger_rows=ledger,
        now=datetime.now(timezone.utc),
        prior_slot_ids=[s for s in prior if s],
    )
    if args.write:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        # Replace same slot_id if re-run
        rows = [r for r in load_jsonl(STATE) if r.get("slot_id") != card["slot_id"]]
        rows.append(card)
        STATE.write_text("".join(json.dumps(r) + "\n" for r in rows))
        LATEST.write_text(json.dumps(card, indent=2) + "\n")
        REPORT.write_text(render_md(card))
    body = card.get("telegram") or ""
    if body:
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
