#!/usr/bin/env python3
"""Isolation: fee tier drift watch thresholds + dedupe + alert body."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core import fee_tier_drift_watch as w


def test_no_drift_at_baseline():
    v = w.evaluate_drift(
        {"maker_fee_rate": 0.004, "taker_fee_rate": 0.008, "pricing_tier": "Intro 2"}
    )
    assert v["ok"] and not v["drifted"], v
    assert v["delta_bps"]["maker"] == 0.0
    assert v["delta_bps"]["taker"] == 0.0
    print("PASS no_drift_at_baseline")


def test_5bps_threshold():
    # 4 bps under — no alert
    v = w.evaluate_drift(
        {"maker_fee_rate": 0.0044, "taker_fee_rate": 0.008, "pricing_tier": "Intro 2"},
        threshold_bps=5.0,
    )
    assert not v["drifted"], v
    # exactly 5 bps maker
    v2 = w.evaluate_drift(
        {"maker_fee_rate": 0.0045, "taker_fee_rate": 0.008, "pricing_tier": "Intro 2"},
        threshold_bps=5.0,
    )
    assert v2["drifted"] and v2["hits"]["maker"] and not v2["hits"]["taker"], v2
    # email-shaped 0.50 / 0.90
    v3 = w.evaluate_drift(
        {"maker_fee_rate": 0.005, "taker_fee_rate": 0.009, "pricing_tier": "Restructure"},
        threshold_bps=5.0,
    )
    assert v3["drifted"] and v3["hits"]["maker"] and v3["hits"]["taker"], v3
    body = w.format_alert(v3)
    assert "FEE TIER DRIFT" in body and "maker" in body and "taker" in body
    print("PASS 5bps_threshold")


def test_dedupe_fingerprint():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        w.ALERT_SEEN = td_path / "seen.json"
        fp = "Intro 2|m=0.005|t=0.009|thr=5"
        ok1, seen = w.should_page(fp, dedupe_hours=72.0)
        assert ok1
        w._save_seen(seen)
        seen2 = w._load_seen()
        ok2, _ = w.should_page(fp, seen=seen2, dedupe_hours=72.0)
        assert not ok2
        # different fingerprint pages again
        ok3, _ = w.should_page(fp + "|x", seen=w._load_seen(), dedupe_hours=72.0)
        assert ok3
    print("PASS dedupe_fingerprint")


def main():
    test_no_drift_at_baseline()
    test_5bps_threshold()
    test_dedupe_fingerprint()
    print("ALL PASS isolation_fee_tier_drift_watch")


if __name__ == "__main__":
    main()
