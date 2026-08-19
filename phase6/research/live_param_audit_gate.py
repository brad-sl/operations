"""
P6 live param-audit confidence gate for ANALYST-OPT.

Optimization and promotion require exchange-verified fills to match configured
params before trusting scenario winners for shadow/live proposals.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]

MIN_CONFIDENCE_SCORE = 0.85
MIN_VERIFIED_FILLS = 1
MAX_SUMMARY_AGE_HOURS = 168  # refresh weekly OPT if stale


@dataclass
class LiveConfidenceGateEvaluation:
    passed: bool
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


def _summary_path(account_id: Optional[str] = None) -> Path:
    from phase6.core.paths import param_audit_summary_path
    from phase6.core.trading_log_store import default_account_id

    return param_audit_summary_path(account_id or default_account_id())


def load_latest_param_audit_summary(account_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    from phase6.core.paths import PARAM_AUDIT_DIR, param_audit_summary_path

    if account_id:
        path = param_audit_summary_path(account_id)
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return None
        return None

    candidates: list[Path] = []
    if PARAM_AUDIT_DIR.exists():
        for d in PARAM_AUDIT_DIR.iterdir():
            p = d / "latest_summary.json"
            if p.is_file():
                candidates.append(p)
    if not candidates:
        return None
    best = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        with open(best, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _summary_age_hours(summary: Dict[str, Any]) -> Optional[float]:
    ts = summary.get("generated_at") or (summary.get("param_snapshot") or {}).get("captured_at")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except Exception:
        return None


def evaluate_live_param_confidence(
    embedded: Optional[Dict[str, Any]] = None,
    *,
    account_id: Optional[str] = None,
) -> LiveConfidenceGateEvaluation:
    """Gate: fail_count==0 and confidence_score >= MIN_CONFIDENCE_SCORE."""
    out = LiveConfidenceGateEvaluation(passed=False)
    summary = embedded if embedded else load_latest_param_audit_summary(account_id)

    if not summary:
        out.failures.append(
            "live_param_audit: no latest_summary (run scripts/phase6/run_param_audit.py)"
        )
        return out

    out.summary = {
        "account_id": summary.get("account_id"),
        "run_id": summary.get("run_id"),
        "verified_fills": summary.get("verified_fills"),
        "fail_count": summary.get("fail_count"),
        "confidence_score": summary.get("confidence_score"),
        "findings": summary.get("findings"),
        "gate_min_confidence": MIN_CONFIDENCE_SCORE,
        "gate_max_fail_count": 0,
    }

    if not summary.get("ok", True):
        out.failures.append("live_param_audit: latest summary ok=false")

    fail_count = int(summary.get("fail_count") if summary.get("fail_count") is not None else 999)
    if fail_count > 0:
        out.failures.append(f"live_param_audit: fail_count={fail_count} (must be 0)")

    conf = summary.get("confidence_score")
    try:
        conf_f = float(conf) if conf is not None else 0.0
    except (TypeError, ValueError):
        conf_f = 0.0
    if conf_f < MIN_CONFIDENCE_SCORE:
        out.failures.append(
            f"live_param_audit: confidence_score={conf_f:.3f} < {MIN_CONFIDENCE_SCORE}"
        )

    vf = int(summary.get("verified_fills") or 0)
    if vf < MIN_VERIFIED_FILLS:
        out.failures.append(
            f"live_param_audit: verified_fills={vf} (need >= {MIN_VERIFIED_FILLS}; run reconcile --full)"
        )

    age = _summary_age_hours(summary)
    if age is not None and age > MAX_SUMMARY_AGE_HOURS:
        out.warnings.append(
            f"live_param_audit: summary age {age:.0f}h > {MAX_SUMMARY_AGE_HOURS}h — refresh before promotion"
        )

    out.passed = len(out.failures) == 0
    return out


def run_param_audit_cli() -> int:
    script = ROOT / "scripts/phase6/run_param_audit.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
    return proc.returncode


def require_live_param_confidence_for_opt(
    *,
    refresh: bool = False,
    account_id: Optional[str] = None,
) -> tuple[bool, LiveConfidenceGateEvaluation]:
    """Refresh optional param audit, then evaluate. Never aborts mid-refresh without evaluate."""
    extra_failures: List[str] = []
    if refresh:
        rc = run_param_audit_cli()
        if rc != 0:
            extra_failures.append(f"live_param_audit: run_param_audit.py exited {rc}")

    ev = evaluate_live_param_confidence(account_id=account_id)
    if extra_failures:
        # CLI fail is a warning if summary still evaluates clean; else hard failure noise
        if ev.passed:
            ev.warnings.extend(extra_failures)
        else:
            ev.failures = extra_failures + list(ev.failures)
    return ev.passed, ev


def attach_live_param_audit_to_leaderboard(
    leaderboard: Dict[str, Any],
    evaluation: LiveConfidenceGateEvaluation,
) -> Dict[str, Any]:
    leaderboard = dict(leaderboard)
    leaderboard["live_param_audit"] = {
        **evaluation.summary,
        "gate_passed": evaluation.passed,
        "gate_failures": evaluation.failures,
        "gate_warnings": evaluation.warnings,
    }
    return leaderboard