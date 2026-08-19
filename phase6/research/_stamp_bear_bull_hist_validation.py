#!/usr/bin/env python3
"""Stamp historical validation onto parked BEAR/BULL plans from dig JSON."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STRATEGY = ROOT / "data" / "state" / "trials" / "TEST_STRATEGY.json"
DIG = ROOT / "reports" / "REGIME_BEAR_BULL_HISTORICAL_2026-08-17.json"
NOW = datetime.now(timezone.utc).isoformat()
DAY = "2026-08-17"


def main() -> None:
    dig = json.loads(DIG.read_text())
    s = json.loads(STRATEGY.read_text())
    map_ = {
        "PLAN-BEAR-PARK-001": dig["bear"],
        "PLAN-BULL-KNOBS-002": dig["bull"],
    }
    for plan in s.get("roadmap") or []:
        pid = plan.get("plan_id")
        if pid not in map_:
            continue
        j = map_[pid]["judgment"] if "judgment" in map_[pid] else map_[pid]
        # dig structure: bear/bull have judgment nested in file under bear.judgment
        pass
    # reload nested correctly
    bear_j = dig["bear"]["judgment"]
    bull_j = dig["bull"]["judgment"]
    for plan in s.get("roadmap") or []:
        pid = plan.get("plan_id")
        if pid == "PLAN-BEAR-PARK-001":
            j = bear_j
            side = dig["bear"]
        elif pid == "PLAN-BULL-KNOBS-002":
            j = bull_j
            side = dig["bull"]
        else:
            continue
        plan["historical_validation"] = {
            "at": NOW,
            "report": "reports/REGIME_BEAR_BULL_HISTORICAL_2026-08-17.md",
            "json": "reports/REGIME_BEAR_BULL_HISTORICAL_2026-08-17.json",
            "primary_pass": bool(j.get("primary_pass")),
            "outcome_class": j.get("class"),
            "enum": j.get("enum"),
            "plain_english": j.get("plain"),
            "n_labeled_days": side.get("n_labeled_days"),
            "n_episodes": side.get("n_episodes"),
            "adequacy_90d": dig.get("adequacy_90d"),
            "live_promote": False,
            "status": (
                "premise_pass_park_for_live_confirm"
                if j.get("primary_pass")
                else "premise_weak_park_for_live_regime"
            ),
        }
        # stay parked planned
        plan["parked"] = True
        plan["status"] = "planned"
        if j.get("primary_pass"):
            plan["park_reason"] = (
                f"{DAY}: Historical premise PASS on long tape "
                f"({side.get('n_labeled_days')} labeled days, {side.get('n_episodes')} eps). "
                f"Still parked until live regime match for shadow confirm — no live writes. "
                f"Report: reports/REGIME_BEAR_BULL_HISTORICAL_2026-08-17.md"
            )
        else:
            plan["park_reason"] = (
                f"{DAY}: Historical premise WEAK/sparse. Stay parked; re-run at live "
                f"regime flip or longer tape. Report: reports/REGIME_BEAR_BULL_HISTORICAL_2026-08-17.md"
            )
        print(pid, "pass=", j.get("primary_pass"), j.get("class"))

    s.setdefault("notes", []).append(
        f"{DAY}: Historical bear/bull dig on long BTC (2020-11→2026-08). "
        f"90d: bear_days={dig['adequacy_90d']['bear_days']} bull_days={dig['adequacy_90d']['bull_days']} "
        f"(bull 90d inadequate). Full tape bear pass={bear_j.get('primary_pass')} "
        f"bull pass={bull_j.get('primary_pass')}. Plans stay parked for live confirm; no promote."
    )
    s["updated_at"] = NOW
    STRATEGY.write_text(json.dumps(s, indent=2) + "\n")
    print("OK")


if __name__ == "__main__":
    main()
