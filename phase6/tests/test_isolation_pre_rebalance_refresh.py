#!/usr/bin/env python3
"""Isolation: ANALYST-006/008 pre-rebalance data coverage assessment."""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phase6.core.pre_rebalance_data_refresh import assess_basket_coverage


def test_assess_coverage_legacy_scores():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "data/state").mkdir(parents=True)
        rsi = {"rsi": {"BTC-USD": {"rsi": 55.0, "fresh": True}}}
        (root / "data/state/rsi_cache.json").write_text(json.dumps(rsi))
        sent = {"scores": {"BTC-USD": 0.1, "ETH-USD": -0.05}}
        (root / "data/state/sentiment_cache.json").write_text(json.dumps(sent))
        report = assess_basket_coverage(["BTC-USD", "ETH-USD", "SOL-USD"], root)
        assert "BTC-USD" in report["per_pair"]
        assert report["per_pair"]["BTC-USD"]["sentiment"] == 0.1
        assert "SOL-USD" in report["missing_rsi"] or report["per_pair"]["SOL-USD"]["status"] != "ok"
        print(f"legacy report complete={report['complete']} missing={report['missing_rsi']}")


def test_assess_coverage_schema_v3():
    """Regression: refresh_sentiment.py writes schema_version 3 — pre-rebal must not flag all missing."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "data/state").mkdir(parents=True)
        now = 1_700_000_000.0
        rsi_path = root / "data/state/rsi_cache.json"
        rsi_path.write_text(json.dumps({"rsi": {"BTC-USD": {"rsi": 50.0}}}))
        os.utime(rsi_path, (now, now))
        sent_path = root / "data/state/sentiment_cache.json"
        sent = {
            "timestamp": "2026-07-08T04:01:02Z",
            "schema_version": 3,
            "sentiment": {
                "BTC-USD": {"sentiment_score": 0.12, "source": "x"},
                "ETH-USD": {"sentiment_score": 0.0, "source": "x"},
            },
        }
        sent_path.write_text(json.dumps(sent))
        os.utime(sent_path, (now, now))
        report = assess_basket_coverage(["BTC-USD", "ETH-USD"], root)
        assert report["per_pair"]["BTC-USD"]["sentiment"] == 0.12
        assert report["per_pair"]["ETH-USD"]["sentiment"] == 0.0
        assert "BTC-USD" not in report["missing_sentiment"]
        assert "ETH-USD" not in report["missing_sentiment"]
        print("schema_v3 sentiment parse OK")


if __name__ == "__main__":
    test_assess_coverage_legacy_scores()
    test_assess_coverage_schema_v3()
    print("[ANALYST-006/008 ISOLATION] PASSED")