#!/usr/bin/env python3
"""Run offline Stoch→SL predictor analysis; write reports + optional trial touch."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.stoch_sl_predictor import (  # noqa: E402
    DEFAULT_TRIAL_START,
    parse_ts,
    render_markdown,
    run_analysis,
)

TRIAL_ID = "ANALYST-STOCH-SL-PREDICTOR-20260803"
REPORTS = ROOT / "reports"
STATE = ROOT / "data" / "state" / "trials" / f"{TRIAL_ID}.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=DEFAULT_TRIAL_START)
    ap.add_argument("--end", default=None)
    ap.add_argument("--phase", default="offline", help="offline|dig|final label in filename")
    ap.add_argument("--no-state", action="store_true", help="do not write trial JSON")
    args = ap.parse_args()

    start = parse_ts(args.start)
    end = parse_ts(args.end) if args.end else datetime.now(timezone.utc)
    analysis = run_analysis(start=start, end=end)

    REPORTS.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stem = f"STOCH_SL_PREDICTOR_{args.phase.upper()}_{day}"
    md_path = REPORTS / f"{stem}.md"
    json_path = REPORTS / f"{stem}.json"

    # JSON without huge duplication risk — keep episodes
    payload = {
        "trial_id": TRIAL_ID,
        "phase": args.phase,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis": analysis,
        "rules": {
            "allocator_change": False,
            "live_sl_change": False,
            "real_data_only": True,
            "requires_brad_go_for_live": True,
        },
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    md_path.write_text(render_markdown(analysis, TRIAL_ID))

    if not args.no_state:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        prev = {}
        if STATE.exists():
            try:
                prev = json.loads(STATE.read_text())
            except Exception:
                prev = {}
        now = datetime.now(timezone.utc).isoformat()
        trial = {
            **prev,
            "trial_id": TRIAL_ID,
            "title": "Stoch %K entry-time predictor of stop-loss (offline)",
            "status": "REPORT_READY",
            "cycle": "docs/testing/ANALYST_TEST_CYCLE.md",
            "protocol": f"docs/testing/trials/{TRIAL_ID}_PROTOCOL.md",
            "role": "crypto-analyst",
            "master_id": "ANALYST-STOCH-SL-PREDICTOR-20260803",
            "trial_kind": "offline_analysis",
            "family": "stoch_sl_predictor",
            "parent_trial": "STOCH-RSI-PARALLEL-20260721",
            "intent": {
                "entry_time_only": True,
                "no_live_sl": True,
                "no_allocator_change": True,
                "real_data_only": True,
            },
            "start_at": prev.get("start_at") or now,
            "analysis_window_start": args.start,
            "analysis_window_end": end.isoformat() if end else None,
            "updated_at": now,
            "final_recommendation": analysis["recommendation"]["enum"],
            "final_report": str(md_path.relative_to(ROOT)),
            "final_report_at": now,
        }
        reports = list(trial.get("reports") or [])
        reports.append(
            {
                "phase": args.phase,
                "path": str(md_path.relative_to(ROOT)),
                "json": str(json_path.relative_to(ROOT)),
                "at": now,
                "recommendation": analysis["recommendation"]["enum"],
            }
        )
        trial["reports"] = reports
        STATE.write_text(json.dumps(trial, indent=2) + "\n")

    print(md_path.read_text()[:4000])
    print(f"\n---\nWrote {md_path}\nJSON {json_path}")
    print("REC", analysis["recommendation"]["enum"], "|", analysis["recommendation"]["plain_english"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
