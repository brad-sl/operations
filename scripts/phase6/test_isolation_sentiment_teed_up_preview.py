#!/usr/bin/env python3
"""Isolation: sentiment teed-up preview (display only)."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.sentiment_teed_up_preview import (  # noqa: E402
    load_sentiment_teed_up_preview,
    next_x_sentiment_refresh_meta,
)


def test_next_x_refresh_is_future():
    meta = next_x_sentiment_refresh_meta()
    assert "next_pt" in meta
    assert meta["hours_until"] is None or meta["hours_until"] >= 0
    assert meta["schedule_pt"] == ["08:50", "20:50"]
    # Fixed local noon PT → next should be 20:50 same day
    noon = datetime(2026, 9, 5, 12, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    m2 = next_x_sentiment_refresh_meta(now=noon.astimezone())
    assert "20:50" in (m2.get("next_pt") or "")


def test_preview_bundle_shape():
    b = load_sentiment_teed_up_preview(basket=["BTC-USD", "ETH-USD"])
    assert b.get("drives_gates") is False
    assert "by_pair" in b
    assert "next_x_refresh" in b
    assert "label" in b
    bp = b["by_pair"]
    assert "BTC-USD" in bp
    row = bp["BTC-USD"]
    assert "live" in row
    assert "teed" in row
    assert row.get("drives_gates") is False
    # teed should prefer free when free cache is fresh with nz (usual ops state)
    if row.get("teed") is not None:
        assert row.get("teed_source") in (
            "free",
            "adanos",
            "x_raw",
            "free_stale",
            "adanos_stale",
        )


def main() -> int:
    test_next_x_refresh_is_future()
    test_preview_bundle_shape()
    print("ALL PASS isolation_sentiment_teed_up_preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
