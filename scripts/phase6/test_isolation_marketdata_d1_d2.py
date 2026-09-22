#!/usr/bin/env python3
"""Isolation: marketdata.db schema + BTC 1d port + regime fail-closed (D1/D2)."""
from __future__ import annotations

import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_schema_and_upsert():
    from phase6.core import marketdata_store as md

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "marketdata.db"
        md.init_schema(db)
        md.seed_core_pairs(db)
        # 40 daily bars ending today
        today = datetime.now(timezone.utc).date()
        bars = []
        px = 50000.0
        for i in range(40, 0, -1):
            d = today - timedelta(days=i - 1)
            ts = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
            px = px * (1.0 + 0.002)
            bars.append(
                {
                    "ts_open": ts,
                    "open": px * 0.99,
                    "high": px * 1.01,
                    "low": px * 0.98,
                    "close": px,
                    "volume": 100.0,
                }
            )
        n = md.upsert_bars(
            bars,
            symbol="BTC-USD",
            granularity_sec=md.GRAN_1D,
            source="test",
            db_path=db,
        )
        assert n == 40, n
        fr = md.get_freshness("BTC-USD", md.GRAN_1D, db_path=db)
        assert fr["status"] == "ok", fr
        assert fr["bar_count"] == 40
        closes, meta = md.get_btc_daily_closes(db_path=db)
        assert len(closes) == 40
        assert meta["fresh_ok"] is True
        rows = md.get_ohlcv("BTC-USD", md.GRAN_1D, limit=5, db_path=db)
        assert len(rows) == 5
        # idempotent upsert
        n2 = md.upsert_bars(
            bars[-3:],
            symbol="BTC-USD",
            granularity_sec=md.GRAN_1D,
            source="test",
            db_path=db,
        )
        assert n2 == 3
        fr2 = md.get_freshness("BTC-USD", md.GRAN_1D, db_path=db)
        assert fr2["bar_count"] == 40
        print("  schema/upsert OK", fr2["status"], fr2["bar_count"])


def test_freshness_gapped_fail():
    from phase6.core import marketdata_store as md

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "marketdata.db"
        md.init_schema(db)
        today = datetime.now(timezone.utc).date()
        # last bar 10 days ago → gapped/stale
        bars = []
        for i in range(40, 10, -1):
            d = today - timedelta(days=i)
            ts = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
            bars.append(
                {
                    "ts_open": ts,
                    "open": 1.0,
                    "high": 1.1,
                    "low": 0.9,
                    "close": 1.0,
                    "volume": 1.0,
                }
            )
        md.upsert_bars(
            bars, symbol="BTC-USD", granularity_sec=md.GRAN_1D, source="test", db_path=db
        )
        fr = md.get_freshness("BTC-USD", md.GRAN_1D, db_path=db)
        assert fr["status"] in ("gapped", "stale"), fr
        assert md.freshness_ok_for_regime(fr) is False
        print("  gapped freshness OK", fr["status"], fr.get("gap_days_tail"))


def test_spot_requires_as_of_age():
    from phase6.core import marketdata_store as md

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "marketdata.db"
        md.init_schema(db)
        md.upsert_spot("BTC-USD", 90000.0, as_of=datetime.now(timezone.utc).isoformat(), source="t", db_path=db)
        s = md.get_spot("BTC-USD", max_age_sec=60, db_path=db)
        assert s and s["price"] == 90000.0
        # expired
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        md.upsert_spot("BTC-USD", 80000.0, as_of=old, source="t", db_path=db)
        s2 = md.get_spot("BTC-USD", max_age_sec=60, db_path=db)
        assert s2 is None
        print("  spot max_age OK")


def test_regime_uses_db_not_fossil():
    """Wire detect_regime through temp marketdata with climb tape (~+11%)."""
    import phase6.research.regime_detector as rd
    from phase6.core import marketdata_store as md

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "marketdata.db"
        md.init_schema(db)
        today = datetime.now(timezone.utc).date()
        bars = []
        # 30d climb from 77k-ish to 86k
        for i in range(35, 0, -1):
            d = today - timedelta(days=i - 1)
            ts = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
            # linear-ish climb
            close = 77000.0 + (35 - i) * (9500.0 / 34.0)
            bars.append(
                {
                    "ts_open": ts,
                    "open": close * 0.995,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": 1000.0,
                }
            )
        md.upsert_bars(
            bars, symbol="BTC-USD", granularity_sec=md.GRAN_1D, source="test", db_path=db
        )
        # Point MARKETDATA_DB at temp
        orig = md.MARKETDATA_DB
        try:
            md.MARKETDATA_DB = db  # type: ignore
            # also patch module path constant used at import of get_btc
            d = rd.detect_regime(use_live_price=False)
            assert d.get("fresh_ok") is True, d
            assert d.get("data_source") == "marketdata_db", d
            assert d.get("regime") != "bear", d  # climb must not be false bear
            assert d.get("btc_return_pct") is not None and d["btc_return_pct"] > 0, d
            print(
                "  regime via DB OK",
                d["regime"],
                d["regime_layer"],
                d["btc_return_pct"],
                d["window_end"],
            )
        finally:
            md.MARKETDATA_DB = orig  # type: ignore


def test_merge_refuses_multiday_gap():
    from phase6.research.regime_detector import _merge_live_close
    import phase6.research.regime_detector as rd

    old = date.today() - timedelta(days=10)
    closes = [(old - timedelta(days=i), 50000.0) for i in range(40, 0, -1)]
    closes = sorted(closes, key=lambda x: x[0])
    closes[-1] = (old, 50000.0)
    orig = rd._live_btc_price
    try:
        rd._live_btc_price = lambda: 86000.0  # type: ignore
        out, meta = _merge_live_close(closes)
        assert meta.get("refused_gap_fill") is True, meta
        assert out[-1][0] == old  # unchanged tip
        assert meta.get("live_appended") is False
        print("  refuse multiday gap-fill OK", meta)
    finally:
        rd._live_btc_price = orig  # type: ignore


def test_merge_allows_small_lag():
    from phase6.research.regime_detector import _merge_live_close
    import phase6.research.regime_detector as rd

    old = date.today() - timedelta(days=1)
    closes = [(old - timedelta(days=i), 50000.0 + i) for i in range(40, 0, -1)]
    closes = sorted(closes, key=lambda x: x[0])
    closes[-1] = (old, 50000.0)
    orig = rd._live_btc_price
    try:
        rd._live_btc_price = lambda: 51000.0  # type: ignore
        out, meta = _merge_live_close(closes)
        assert meta.get("live_appended") is True, meta
        assert out[-1][0] == date.today()
        print("  small lag append OK", meta.get("live_mode"))
    finally:
        rd._live_btc_price = orig  # type: ignore


if __name__ == "__main__":
    test_schema_and_upsert()
    test_freshness_gapped_fail()
    test_spot_requires_as_of_age()
    test_merge_refuses_multiday_gap()
    test_merge_allows_small_lag()
    test_regime_uses_db_not_fossil()
    print("marketdata D1/D2 isolation PASS")
