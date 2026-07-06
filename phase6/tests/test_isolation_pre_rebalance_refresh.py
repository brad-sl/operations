#!/usr/bin/env python3
"""Isolation: ANALYST-006/008 pre-rebalance data coverage assessment."""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phase6.core.pre_rebalance_data_refresh import assess_basket_coverage


def test_assess_coverage():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "data/state").mkdir(parents=True)
        rsi = {"rsi": {"BTC-USD": {"rsi": 55.0, "fresh": True}}}
        (root / "data/state/rsi_cache.json").write_text(json.dumps(rsi))
        sent = {"scores": {"BTC-USD": 0.1, "ETH-USD": -0.05}}
        (root / "data/state/sentiment_cache.json").write_text(json.dumps(sent))
        report = assess_basket_coverage(["BTC-USD", "ETH-USD", "SOL-USD"], root)
        assert "BTC-USD" in report["per_pair"]
        assert "SOL-USD" in report["missing_rsi"] or report["per_pair"]["SOL-USD"]["status"] != "ok"
        print(f"report complete={report['complete']} missing={report['missing_rsi']}")
    print("[ANALYST-006/008 ISOLATION] PASSED")


if __name__ == "__main__":
    test_assess_coverage()