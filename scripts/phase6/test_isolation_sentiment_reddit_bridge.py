#!/usr/bin/env python3
"""Isolation: complete clock — X ages out → latest Reddit bridge (not free)."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_x_aged_out_hands_to_reddit():
    from phase6.core import sentiment_scorer as ss

    now = datetime.now(timezone.utc)
    x_age = 60.0  # past 45m handoff; X decay ~0.0625
    x_ts = (now - timedelta(minutes=x_age)).isoformat()
    rr_ts = (now - timedelta(minutes=20.0)).isoformat()  # fresh reddit

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        x_path = td_path / "x.json"
        can_path = td_path / "can.json"
        free_path = td_path / "free.json"
        rr_path = td_path / "rr.json"

        x_path.write_text(
            json.dumps(
                {
                    "BTC-USD": {
                        "sentiment": 0.80,
                        "post_count": 20,
                        "timestamp": x_ts,
                    },
                    "ETH-USD": {
                        "sentiment": -0.50,
                        "post_count": 10,
                        "timestamp": x_ts,
                    },
                }
            )
        )
        can_path.write_text("{}")
        # Free has different values — must NOT win over Reddit on aged X
        free_path.write_text(
            json.dumps(
                {
                    "timestamp": rr_ts,
                    "sentiment": {
                        "BTC-USD": {"sentiment_score": 0.99},
                        "ETH-USD": {"sentiment_score": 0.99},
                    },
                }
            )
        )
        rr_path.write_text(
            json.dumps(
                {
                    "timestamp": rr_ts,
                    "schema_version": 1,
                    "status": "ok",
                    "source": "reddit_reading",
                    "sentiment": {
                        "BTC-USD": {"sentiment_score": 0.40, "n_posts": 5},
                        "ETH-USD": {"sentiment_score": -0.20, "n_posts": 4},
                    },
                }
            )
        )

        old = (
            ss.X_CACHE,
            ss.CANONICAL_CACHE,
            ss.FREE_CACHE,
            ss.REDDIT_READING_CACHE,
            ss.REDDIT_LEGACY_CACHE,
        )
        try:
            ss.X_CACHE = str(x_path)
            ss.CANONICAL_CACHE = str(can_path)
            ss.FREE_CACHE = str(free_path)
            ss.REDDIT_READING_CACHE = str(rr_path)
            ss.REDDIT_LEGACY_CACHE = str(td_path / "missing_legacy.json")

            detail = ss.load_sentiment_scores_detailed(
                universe=["BTC-USD", "ETH-USD"],
                cache_path=str(can_path),
                apply_aging=True,
            )
            assert detail.get("reddit_bridge", {}).get("bridged_pairs", 0) >= 1, detail
            assert "reddit" in str(detail.get("mode") or ""), detail.get("mode")
            btc = detail["scores"]["BTC-USD"]
            assert "reddit" in str(btc.get("source") or ""), btc
            # Aged reddit ~ 0.40 * 0.5**(20/60) ≈ 0.317
            assert abs(float(btc["sentiment_raw"]) - 0.40) < 1e-6, btc
            assert float(btc["sentiment"]) > 0.25, btc
            assert float(btc["sentiment"]) < 0.40, btc
            # Must not be free 0.99
            assert float(btc["sentiment"]) < 0.5, btc
            eth = detail["scores"]["ETH-USD"]
            assert "reddit" in str(eth.get("source") or ""), eth
            assert float(eth["sentiment"]) < 0, eth
            print(
                "x_aged_out_hands_to_reddit: PASS",
                "mode",
                detail["mode"],
                "btc",
                btc["sentiment"],
                btc["source"],
            )
        finally:
            (
                ss.X_CACHE,
                ss.CANONICAL_CACHE,
                ss.FREE_CACHE,
                ss.REDDIT_READING_CACHE,
                ss.REDDIT_LEGACY_CACHE,
            ) = old


def test_fresh_x_not_bridged():
    from phase6.core import sentiment_scorer as ss

    now = datetime.now(timezone.utc)
    x_ts = (now - timedelta(minutes=5.0)).isoformat()
    rr_ts = now.isoformat()

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        x_path = td_path / "x.json"
        can_path = td_path / "can.json"
        free_path = td_path / "free.json"
        rr_path = td_path / "rr.json"
        x_path.write_text(
            json.dumps(
                {
                    "BTC-USD": {
                        "sentiment": 0.55,
                        "post_count": 15,
                        "timestamp": x_ts,
                    }
                }
            )
        )
        can_path.write_text("{}")
        free_path.write_text("{}")
        rr_path.write_text(
            json.dumps(
                {
                    "timestamp": rr_ts,
                    "sentiment": {"BTC-USD": {"sentiment_score": 0.11}},
                }
            )
        )
        old = (
            ss.X_CACHE,
            ss.CANONICAL_CACHE,
            ss.FREE_CACHE,
            ss.REDDIT_READING_CACHE,
            ss.REDDIT_LEGACY_CACHE,
        )
        try:
            ss.X_CACHE = str(x_path)
            ss.CANONICAL_CACHE = str(can_path)
            ss.FREE_CACHE = str(free_path)
            ss.REDDIT_READING_CACHE = str(rr_path)
            ss.REDDIT_LEGACY_CACHE = str(td_path / "nope.json")
            detail = ss.load_sentiment_scores_detailed(
                universe=["BTC-USD"], cache_path=str(can_path), apply_aging=True
            )
            btc = detail["scores"]["BTC-USD"]
            assert btc.get("source") == "x", btc
            assert abs(float(btc["sentiment_raw"]) - 0.55) < 1e-6
            # decay at 5m / 15m HL ≈ 0.79
            assert float(btc["sentiment"]) > 0.40, btc
            assert int(detail.get("reddit_bridge", {}).get("bridged_pairs") or 0) == 0
            print("fresh_x_not_bridged: PASS", btc["sentiment"], btc["source"])
        finally:
            (
                ss.X_CACHE,
                ss.CANONICAL_CACHE,
                ss.FREE_CACHE,
                ss.REDDIT_READING_CACHE,
                ss.REDDIT_LEGACY_CACHE,
            ) = old


if __name__ == "__main__":
    test_x_aged_out_hands_to_reddit()
    test_fresh_x_not_bridged()
    # keep prior aging suite green
    from phase6.core.test_isolation_sentiment_aging import (
        test_decay_math,
        test_loader_ages_x_and_keeps_raw,
        test_reddit_bridge_longer_than_x,
    )

    test_decay_math()
    test_reddit_bridge_longer_than_x()
    test_loader_ages_x_and_keeps_raw()
    print("=== ALL PASS isolation_sentiment_reddit_bridge ===")
