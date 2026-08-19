"""Isolation: P6 live param confidence gate for ANALYST-OPT."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.live_param_audit_gate import evaluate_live_param_confidence


def test_low_confidence_fails() -> None:
    ev = evaluate_live_param_confidence(
        {"fail_count": 0, "confidence_score": 0.5, "verified_fills": 10, "ok": True}
    )
    assert not ev.passed
    assert any("confidence_score" in f for f in ev.failures)


def test_fail_count_blocks() -> None:
    ev = evaluate_live_param_confidence(
        {"fail_count": 2, "confidence_score": 1.0, "verified_fills": 10, "ok": False}
    )
    assert not ev.passed
    assert any("fail_count" in f for f in ev.failures)


def test_pass_threshold() -> None:
    ev = evaluate_live_param_confidence(
        {"fail_count": 0, "confidence_score": 0.9, "verified_fills": 5, "ok": True}
    )
    assert ev.passed, ev.failures


def main() -> int:
    test_low_confidence_fails()
    test_fail_count_blocks()
    test_pass_threshold()
    print("live_param_audit_gate isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())