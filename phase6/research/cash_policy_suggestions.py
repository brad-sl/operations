"""
RC-06: Cash policy suggestions from regime cash param sweep → gated proposals / suggestions.

Adapts to current sweep output (detector threshold grid + score).
Best candidate_detector + score improvements → suggestion if gates pass.
Promote only with gates; suggestions for review before applying to regime_cash_policy.json (never auto-apply).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]

CASH_SWEEP_LATEST = ROOT / "data/state/regime_cash_param_sweep_latest.json"
CASH_SUGGESTIONS_BACKLOG = ROOT / "data/state/cash_policy_suggestions.json"
MASTER_PATH = ROOT / "docs/MASTER_TASK_TRACKING.md"


@dataclass
class CashGateResult:
    passed: bool
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    best_id: Optional[str] = None
    excess_vs_usdc: Optional[float] = None
    max_dd: Optional[float] = None
    score: Optional[float] = None


def evaluate_cash_gates(sweep_data: Dict[str, Any]) -> CashGateResult:
    """Gates for cash policy param suggestion from sweep best (current v1 format)."""
    result = CashGateResult(passed=False)
    best = sweep_data.get("best") or {}
    suggestions = sweep_data.get("suggestions") or {}
    current = sweep_data.get("current_policy_score") or {}
    
    best_score = best.get("score") or suggestions.get("best_score")
    current_score = current.get("score") or suggestions.get("current_score")
    improves = suggestions.get("improves_score", False)
    
    result.best_id = "detector_grid_best"
    result.score = best_score
    
    if not best or not best_score:
        result.failures.append("no best or score in sweep")
        return result
    
    # Gate: must improve score over current
    if not improves or (best_score is not None and current_score is not None and best_score <= current_score):
        result.failures.append(f"no score improvement: best={best_score} current={current_score}")
    
    # Gate: reasonable park bias or low risk in bear (from best)
    park_frac = best.get("park_fraction")
    if park_frac is not None and float(park_frac) > 0.95:
        result.warnings.append(f"very high park_fraction {park_frac} — conservative but review")
    
    risk_deploy = best.get("risk_deploy_in_bear", 0)
    if risk_deploy and int(risk_deploy) > 0:
        result.failures.append(f"deploys in bear: risk_deploy_in_bear={risk_deploy}")
    
    if not result.failures:
        result.passed = True
        if best_score and current_score:
            result.warnings.append(f"score delta +{round(best_score - current_score, 2)}")
    else:
        result.warnings.append("review simulation (BTC proxy exposure model for regime cash)")
    
    return result


def build_cash_suggestion(sweep_data: Dict[str, Any], gates: CashGateResult) -> Dict[str, Any]:
    best = sweep_data.get("best") or {}
    suggestions = sweep_data.get("suggestions") or {}
    run_id = sweep_data.get("generated_at", "unknown")
    candidate = suggestions.get("candidate_detector") or {
        "bull_return_pct": best.get("bull_return_pct"),
        "bear_return_pct": best.get("bear_return_pct"),
        "flat_abs_pct": best.get("flat_abs_pct"),
    }
    
    return {
        "id": "",  # filled on ingest
        "title": f"Cash policy suggestion: detector grid (score {gates.score})",
        "description": (
            f"From RC-06 sweep {run_id}. Candidate thresholds: {candidate}. "
            f"Score: {gates.score}. Improves: {suggestions.get('improves_score')}. "
            f"Park fraction: {best.get('park_fraction')}. Apply via review to regime_cash_policy.json detector section."
        ),
        "candidate_detector": candidate,
        "metrics": {
            "best_score": gates.score,
            "park_fraction": best.get("park_fraction"),
            "deploy_days": best.get("deploy_days"),
            "park_days": best.get("park_days"),
        },
        "gate_result": {
            "passed": gates.passed,
            "failures": gates.failures,
            "warnings": gates.warnings,
        },
        "source": "regime_cash_param_sweep_v1",
        "generated": datetime.now(timezone.utc).isoformat(),
        "category": "RC-06 / regime cash policy",
        "status": "proposed",
    }


def _today_seq(existing: List[dict]) -> int:
    prefix = date.today().strftime("%Y%m%d")
    mx = 0
    for p in existing:
        pid = p.get("id") or ""
        if pid.startswith(f"CASH-{prefix}-"):
            try:
                mx = max(mx, int(pid.split("-")[-1]))
            except (ValueError, IndexError):
                pass
    return mx + 1


def ingest_cash_suggestion(
    sweep_data: Dict[str, Any],
    *,
    write_master: bool = True,
) -> Tuple[Optional[Dict[str, Any]], CashGateResult]:
    """
    Evaluate gates on sweep best; if pass, append to cash_policy_suggestions.json and MASTER.
    """
    gates = evaluate_cash_gates(sweep_data)
    if not gates.passed:
        return None, gates
    
    if not CASH_SWEEP_LATEST.exists():
        return None, gates
    
    suggestions = {"suggestions": []}
    if CASH_SUGGESTIONS_BACKLOG.exists():
        try:
            suggestions = json.loads(CASH_SUGGESTIONS_BACKLOG.read_text())
        except Exception:
            pass
    
    existing = suggestions.get("suggestions") or []
    
    gen = sweep_data.get("generated_at")
    if any(s.get("generated") == gen for s in existing):
        return None, gates
    
    suggestion = build_cash_suggestion(sweep_data, gates)
    seq = _today_seq(existing)
    suggestion["id"] = f"CASH-{date.today().strftime('%Y%m%d')}-{seq:03d}"
    
    existing.append(suggestion)
    suggestions["suggestions"] = existing[-100:]
    
    CASH_SUGGESTIONS_BACKLOG.parent.mkdir(parents=True, exist_ok=True)
    CASH_SUGGESTIONS_BACKLOG.write_text(json.dumps(suggestions, indent=2), encoding="utf-8")
    
    if write_master and MASTER_PATH.exists():
        block = (
            f"\n**{suggestion['id']}** — {suggestion['title']}\n"
            f"Status: Proposed (RC-06 cash policy) — Review & apply candidate_detector to config/regime_cash_policy.json if approved\n"
            f"Source sweep: {gen} | score={gates.score}\n"
            f"Candidate: {suggestion.get('candidate_detector')}\n\n"
        )
        content = MASTER_PATH.read_text()
        if suggestion["id"] not in content:
            with open(MASTER_PATH, "a") as f:
                f.write(block)
    
    return suggestion, gates


def ingest_from_latest_sweep() -> Tuple[Optional[Dict[str, Any]], CashGateResult]:
    if not CASH_SWEEP_LATEST.exists():
        gr = CashGateResult(False, failures=["no regime_cash_param_sweep_latest.json"])
        return None, gr
    sweep = json.loads(CASH_SWEEP_LATEST.read_text())
    return ingest_cash_suggestion(sweep)


if __name__ == "__main__":
    sug, gates = ingest_from_latest_sweep()
    if sug:
        print(f"RC-06 cash suggestion ingested: {sug['id']}")
    else:
        print(f"RC-06 cash suggestion skipped: passed={gates.passed} failures={gates.failures}")
