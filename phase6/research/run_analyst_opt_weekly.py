#!/usr/bin/env python3
"""
ANALYST-OPT weekly job: scenario leaderboard (Path B) + production comparison + learnings dedup.

Writes data/state/analyst_scenario_leaderboard_latest.json for the daily intelligence brief.

Usage:
  python3 phase6/research/run_analyst_opt_weekly.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DEFAULT_PACK = ROOT / "phase6/research/scenarios/r1_arch4_smoke_three.json"


def main() -> int:
    cmd = [
        sys.executable,
        str(ROOT / "phase6/research/run_scenario_leaderboard.py"),
        "--pack",
        str(DEFAULT_PACK),
        "--compare-production",
        "--record-learning",
    ]
    print(" ".join(cmd))
    rc = subprocess.call(cmd, cwd=str(ROOT))
    if rc != 0:
        return rc

    from phase6.research.proposal_from_leaderboard import ingest_from_latest_leaderboard

    proposal, gates = ingest_from_latest_leaderboard()
    if proposal:
        print(f"R3 proposal ingested: {proposal['id']}")
    else:
        print(f"R3 proposal skipped gates passed={gates.passed} failures={gates.failures}")

    from phase6.research.learnings_dedup import dedup_learnings_file

    removed = dedup_learnings_file(ROOT / "data/state/analyst_learnings.json")
    if removed:
        print(f"deduped analyst_learnings.json removed={removed} duplicate entries")

    from phase6.research.optimization_brief import format_optimization_section, load_leaderboard
    from phase6.research.analyst_narrative import (
        build_evolution_note,
        format_honest_assessment,
        persist_weekly_assessment,
    )

    lb = load_leaderboard()
    opt_brief = None
    if lb:
        _, opt_brief = format_optimization_section(lb)
    lines = format_honest_assessment(
        full_coverage_count=0,
        total_pairs=11,
        sl_risks={},
        opt_brief=opt_brief,
        leaderboard=lb,
    )
    evolution = build_evolution_note(
        full_coverage_count=0,
        total_pairs=11,
        opt_brief=opt_brief,
        leaderboard=lb,
    )
    path = persist_weekly_assessment(lines, evolution, opt_brief)
    print(f"weekly assessment: {path}")

    from phase6.research.sync_analyst_skill_pitfall import sync_repo_skill

    if sync_repo_skill():
        print("repo skill pitfalls updated")

    print("ANALYST-OPT weekly OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())