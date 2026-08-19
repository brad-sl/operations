#!/usr/bin/env python3
"""
ANALYST-OPT weekly job: scenario leaderboard (Path B) + production comparison + learnings dedup.
+ RC-06 continuous: scorecard → knob_map → cash policy suggestions → gated leaderboard promote.

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

DEFAULT_PACK = ROOT / "phase6/research/scenarios/r2_defensive_sharpe_gate.json"
LEGACY_PACK = ROOT / "phase6/research/scenarios/r1_arch4_smoke_three.json"


def main() -> int:
    cmd = [
        sys.executable,
        str(ROOT / "phase6/research/run_scenario_leaderboard.py"),
        "--pack",
        str(DEFAULT_PACK),
        "--compare-production",
        "--record-learning",
        "--refresh-param-audit",
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

    for step in (
        [sys.executable, str(ROOT / "phase6/research/run_regime_scorecard.py")],
        [sys.executable, str(ROOT / "phase6/research/apply_regime_knob_map_from_scorecard.py")],
    ):
        r2 = subprocess.call(step, cwd=str(ROOT))
        if r2 != 0:
            print(f"weekly regime chain failed: {' '.join(step)}", file=sys.stderr)
            return r2

    # RC-06: Continuous analyze → optimize: cash policy suggestions after scorecard/knob_map
    # Chain: scorecard → knob_map → cash policy suggestions → (integrate to) leaderboard; promote only with gates.
    print("RC-06: running regime cash param sweep for policy suggestions")
    sweep_cmd = [
        sys.executable,
        str(ROOT / "phase6/research/run_regime_cash_param_sweep.py"),
        "--quick",
    ]
    print(" ".join(sweep_cmd))
    r3 = subprocess.call(sweep_cmd, cwd=str(ROOT))
    if r3 != 0:
        print(f"cash sweep failed rc={r3}", file=sys.stderr)
        # continue; non-fatal for now

    from phase6.research.cash_policy_suggestions import ingest_from_latest_sweep

    cash_sug, cash_gates = ingest_from_latest_sweep()
    if cash_sug:
        print(f"RC-06 cash policy suggestion ingested: {cash_sug.get('id') if isinstance(cash_sug, dict) else cash_sug}")
    else:
        print(f"RC-06 cash policy suggestion skipped gates passed={cash_gates.passed} failures={cash_gates.failures}")

    print("ANALYST-OPT weekly OK (incl. RC-06 cash suggestions chain)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
