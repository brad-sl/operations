#!/usr/bin/env python3
"""Isolation: source-aware X 15m / Reddit 60m aging (grid 2026-04-21 optimal).

Brad 2026-09-04: raw unaged decision path was a bug. X is highly transitory;
Reddit was the ~hour bridge. Aging must bind load_sentiment_scores by default.
"""
from __future__ import annotations

import math
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def test_decay_math():
    from phase6.core.sentiment_scorer import _exponential_decay_factor

    # X 15m HL: at 15m → 0.5; at 30m → 0.25; at 45m → 0.125
    assert abs(_exponential_decay_factor(15.0, 15.0) - 0.5) < 1e-9
    assert abs(_exponential_decay_factor(30.0, 15.0) - 0.25) < 1e-9
    assert abs(_exponential_decay_factor(45.0, 15.0) - 0.125) < 1e-9
    # Reddit 60m HL: at 45m still ~0.595 (bridge still relevant)
    d45 = _exponential_decay_factor(45.0, 60.0)
    assert 0.55 < d45 < 0.65, d45
    # Staleness hard zero
    assert _exponential_decay_factor(121.0, 15.0, 120.0) == 0.0
    print("decay_math: PASS")


def test_loader_ages_x_and_keeps_raw():
    from phase6.core import sentiment_scorer as ss

    now = datetime.now(timezone.utc)
    age_min = 45.0  # 3 X half-lives → decay 0.125
    ts = (now - timedelta(minutes=age_min)).isoformat()

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        x_path = td_path / "x.json"
        can_path = td_path / "can.json"
        free_path = td_path / "free.json"
        x_path.write_text(
            __import__("json").dumps(
                {
                    "LINK-USD": {
                        "sentiment": 0.80,
                        "post_count": 12,
                        "timestamp": ts,
                    },
                    "BTC-USD": {
                        "sentiment": 0.40,
                        "post_count": 8,
                        "timestamp": ts,
                    },
                }
            )
        )
        can_path.write_text("{}")
        free_path.write_text("{}")

        old_x, old_c, old_f = ss.X_CACHE, ss.CANONICAL_CACHE, ss.FREE_CACHE
        old_rr = getattr(ss, "REDDIT_READING_CACHE", None)
        old_leg = getattr(ss, "REDDIT_LEGACY_CACHE", None)
        try:
            ss.X_CACHE = str(x_path)
            ss.CANONICAL_CACHE = str(can_path)
            ss.FREE_CACHE = str(free_path)
            # Isolation: no live Reddit bridge (this suite is pure aging math)
            ss.REDDIT_READING_CACHE = str(td_path / "no_reddit.json")
            ss.REDDIT_LEGACY_CACHE = str(td_path / "no_legacy.json")
            old_load_rr = ss.load_latest_reddit_scores
            ss.load_latest_reddit_scores = lambda *a, **k: (
                {p: 0.0 for p in (["LINK-USD", "BTC-USD"])},
                {"available": False, "source": None, "non_zero": 0},
            )

            detail = ss.load_sentiment_scores_detailed(
                universe=["LINK-USD", "BTC-USD"],
                cache_path=str(can_path),
                apply_aging=True,
            )
            assert detail["aging_applied"] is True
            link = detail["scores"]["LINK-USD"]
            assert link["source"] == "x"
            assert abs(float(link["sentiment_raw"]) - 0.80) < 1e-6
            expected = 0.80 * (0.5 ** (age_min / 15.0))
            assert abs(float(link["sentiment"]) - expected) < 1e-3, (link, expected)
            assert float(link["decay_factor"]) < 0.15  # ~0.125
            assert float(link["half_life_min"]) == 15.0

            raw = ss.load_sentiment_scores(
                universe=["LINK-USD"], cache_path=str(can_path), apply_aging=False
            )
            aged = ss.load_sentiment_scores(
                universe=["LINK-USD"], cache_path=str(can_path), apply_aging=True
            )
            assert abs(raw["LINK-USD"] - 0.80) < 1e-6
            assert abs(aged["LINK-USD"] - expected) < 1e-3
            # No double-age via get_aged
            aged2 = ss.get_aged_sentiment_scores(
                universe=["LINK-USD"], cache_path=str(can_path)
            )
            # allow tiny drift if wall-clock age ticks between calls
            assert abs(aged2["LINK-USD"] - aged["LINK-USD"]) < 1e-3
            print("loader_ages_x: PASS", "decay", link["decay_factor"], "aged", aged["LINK-USD"])
        finally:
            ss.X_CACHE = old_x
            ss.CANONICAL_CACHE = old_c
            ss.FREE_CACHE = old_f
            if old_rr is not None:
                ss.REDDIT_READING_CACHE = old_rr
            if old_leg is not None:
                ss.REDDIT_LEGACY_CACHE = old_leg
            try:
                ss.load_latest_reddit_scores = old_load_rr
            except NameError:
                pass


def test_reddit_bridge_longer_than_x():
    """At 45m, Reddit 60m HL retains ~0.6 vs X 15m ~0.125 — the hour bridge."""
    from phase6.core.sentiment_scorer import _exponential_decay_factor

    x = _exponential_decay_factor(45.0, 15.0)
    r = _exponential_decay_factor(45.0, 60.0)
    assert r > 4 * x, (x, r)
    print("reddit_bridge_ratio: PASS", f"x={x:.3f} reddit={r:.3f} ratio={r/x:.1f}x")


if __name__ == "__main__":
    test_decay_math()
    test_reddit_bridge_longer_than_x()
    test_loader_ages_x_and_keeps_raw()
    print("=== ALL PASS ===")
