#!/usr/bin/env python3
"""Isolation gate for GAP-06 perf API soak + period honesty helpers.

1) Unit: timeout payload must not look like silent 0 tiles (helper contract).
2) Live: run soak against :8502 if up; assert honesty always; SLA recorded in JSON.

  PYTHONPATH=. .venv/bin/python scripts/phase6/test_isolation_perf_api_soak.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase6.run_perf_api_soak import (  # noqa: E402
    COLD_SLA_S,
    WARM_P95_SLA_S,
    _period_honesty,
    run_soak,
)


def test_timeout_payload_rejects_zero_tiles():
    bad = {
        "status": "ok",
        "source": "timeout",
        "today": 0.0,
        "h24": 0.0,
        "d7": 0.0,
        "d14": 0.0,
        "d30": 0.0,
    }
    v = _period_honesty(bad)
    assert v, f"expected violations for timeout+zeros, got {v}"
    print("PASS: timeout+zeros flagged", v)


def test_real_snapshot_zeros_allowed():
    ok = {
        "status": "ok",
        "source": "portfolio_snapshots_db + positions (period_snapshots_db_adjusted)",
        "today": 0.0,
        "h24": 0.0,
        "d7": 0.1,
        "d14": -1.0,
        "d30": -1.5,
    }
    v = _period_honesty(ok)
    assert not v, v
    print("PASS: real source with mixed periods ok")


def test_none_periods_ok():
    ok = {
        "status": "ok",
        "source": "timeout",
        "today": None,
        "h24": None,
        "d7": None,
        "d14": None,
        "d30": None,
    }
    v = _period_honesty(ok)
    assert not v, v
    print("PASS: explicit None timeout tiles ok")


def test_live_soak_if_dash_up():
    result = run_soak("http://127.0.0.1:8502", warm_n=5, conc_n=5)
    out = ROOT / "data/state/perf_api_soak_isolation_evidence.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print("soak enum", result.get("enum"), "cold_s", (result.get("cold") or {}).get("s"))
    print("warm_p95", (result.get("warm") or {}).get("p95_s"))
    print("gates", result.get("gates"))
    if result.get("error"):
        print("SKIP/soft: dash error", result.get("error"))
        return
    g = result.get("gates") or {}
    assert g.get("honesty_ok") is True, f"honesty failed: {result}"
    assert g.get("all_http_200") is True, f"http failed: {result}"
    # SLA: record; ship path requires both — test fails hard only if honesty/http break
    cold_ok = g.get("cold_sla_ok")
    warm_ok = g.get("warm_sla_ok")
    print(f"SLA cold<{COLD_SLA_S}: {cold_ok} warm_p95<{WARM_P95_SLA_S}: {warm_ok}")
    print("PASS: live soak honesty+http (SLA informational in unit gate; report owns ship enum)")
    print("evidence", out)


if __name__ == "__main__":
    test_timeout_payload_rejects_zero_tiles()
    test_real_snapshot_zeros_allowed()
    test_none_periods_ok()
    test_live_soak_if_dash_up()
    print("ALL PERF API SOAK ISOLATION CHECKS PASSED")
