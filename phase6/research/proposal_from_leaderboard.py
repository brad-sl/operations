"""
ANALYST-OPT R3: Create shadow-trial proposal from gated leaderboard → backlog + MASTER.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.research.promotion_gates import GateResult, evaluate_promotion_gates

ROOT = Path(__file__).resolve().parents[2]
PROPOSED_BACKLOG = ROOT / "data/state/analyst_proposed_backlog.json"
MASTER_PATH = ROOT / "docs/MASTER_TASK_TRACKING.md"


def _today_seq(existing: List[dict]) -> int:
    prefix = date.today().strftime("%Y%m%d")
    pat = re.compile(rf"ANALYST-{prefix}-(\d+)")
    mx = 0
    for p in existing:
        pid = p.get("id") or ""
        m = pat.match(pid)
        if m:
            mx = max(mx, int(m.group(1)))
    return mx + 1


def build_proposal(leaderboard: Dict[str, Any], gates: GateResult) -> Dict[str, Any]:
    winner = next(
        (s for s in leaderboard.get("scenarios", []) if s.get("id") == gates.winner_id),
        {},
    )
    wm = winner.get("metrics") or {}
    run_id = leaderboard.get("run_id", "unknown")
    seq = 0  # filled by ingest
    return {
        "id": "",  # set on ingest
        "title": f"Shadow trial: scenario '{gates.winner_id}' from {leaderboard.get('pack_id')}",
        "description": (
            f"Optimization run {run_id} (engine {leaderboard.get('engine_mode')}). "
            f"Apply knob set via shadow overlay; compare monitor PnL vs backtest. "
            f"Winner metrics: sharpe={wm.get('sharpe_ratio')}, return_pct={wm.get('total_return_pct')}, "
            f"max_dd={wm.get('max_drawdown_pct')}."
        ),
        "benefits": (
            f"Data-driven knob trial cited to run_id. Beats baseline '{gates.baseline_id}' on "
            f"{leaderboard.get('primary_metric')} when gates passed."
        ),
        "risks": (
            "Backtest ≠ live (sentiment proxy, SL, execution). "
            "Regime shift can invalidate bull-only winners — require bear/flat scorecard per "
            "docs/research/REGIME_SCENARIO_PROCEDURE.md. Mitigation: 48h shadow + rollback."
        ),
        "priority": "Medium",
        "effort": "Low",
        "category": "ANALYST-OPT / Shadow trial",
        "status": "proposed",
        "source_run_id": run_id,
        "source_pack_id": leaderboard.get("pack_id"),
        "scenario_id": gates.winner_id,
        "gate_result": {
            "passed": gates.passed,
            "failures": gates.failures,
            "warnings": gates.warnings,
        },
        "generated": datetime.now(timezone.utc).isoformat(),
    }


def ingest_proposal(
    leaderboard: Dict[str, Any],
    *,
    write_master: bool = True,
) -> Tuple[Optional[Dict[str, Any]], GateResult]:
    """
    Evaluate gates; if pass, append to analyst_proposed_backlog and MASTER.
    Returns (proposal or None, gate_result).
    """
    gates = evaluate_promotion_gates(leaderboard)
    if not gates.passed:
        return None, gates

    run_id = leaderboard.get("run_id", "")
    backlog = {"proposals": []}
    if PROPOSED_BACKLOG.exists():
        with open(PROPOSED_BACKLOG) as f:
            backlog = json.load(f)
    existing = backlog.get("proposals") or []

    if any(p.get("source_run_id") == run_id for p in existing):
        return None, gates

    proposal = build_proposal(leaderboard, gates)
    seq = _today_seq(existing)
    proposal["id"] = f"ANALYST-{date.today().strftime('%Y%m%d')}-{seq:03d}"

    existing.append(proposal)
    backlog["proposals"] = existing[-200:]
    PROPOSED_BACKLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(PROPOSED_BACKLOG, "w") as f:
        json.dump(backlog, f, indent=2)

    if write_master and MASTER_PATH.exists():
        block = (
            f"\n**{proposal['id']}** — {proposal['title']}\n"
            f"Status: Proposed (ANALYST-OPT R3 shadow trial) — Awaiting Review\n"
            f"Source run: {run_id} | scenario: {gates.winner_id}\n"
            f"Description: {proposal['description'][:400]}\n"
            f"Gates: passed | warnings: {gates.warnings}\n\n"
        )
        content = MASTER_PATH.read_text()
        if proposal["id"] not in content:
            with open(MASTER_PATH, "a") as f:
                f.write(block)

    return proposal, gates


def ingest_from_latest_leaderboard() -> Tuple[Optional[Dict[str, Any]], GateResult]:
    latest = ROOT / "data/state/analyst_scenario_leaderboard_latest.json"
    if not latest.exists():
        gr = GateResult(False, failures=["no analyst_scenario_leaderboard_latest.json"])
        return None, gr
    with open(latest) as f:
        lb = json.load(f)
    return ingest_proposal(lb)