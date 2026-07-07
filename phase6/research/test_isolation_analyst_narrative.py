"""ANALYST-OPT R5: analyst narrative isolation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.analyst_narrative import (
    build_evolution_note,
    format_honest_assessment,
    optimization_proposal_candidates,
    persist_weekly_assessment,
)


def main() -> int:
    lb_path = ROOT / "data/state/analyst_scenario_leaderboard_latest.json"
    lb = json.loads(lb_path.read_text()) if lb_path.exists() else {}
    lines = format_honest_assessment(
        full_coverage_count=8,
        total_pairs=11,
        sl_risks={"SOL-USD": {"level": "HIGH"}},
        leaderboard=lb,
    )
    assert len(lines) >= 2
    assert any("Production" in l or "production" in l.lower() or "Insufficient" in l for l in lines)

    evo = build_evolution_note(full_coverage_count=8, total_pairs=11, leaderboard=lb)
    assert "evolution_note" in evo

    cands = optimization_proposal_candidates(None, lb)
    assert isinstance(cands, list)

    persist_weekly_assessment(lines, evo, None)
    assert (ROOT / "data/state/analyst_weekly_assessment_latest.json").exists()

    print("ANALYST-OPT R5 narrative isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())