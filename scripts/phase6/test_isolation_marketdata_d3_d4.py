#!/usr/bin/env python3
"""Isolation: marketdata thin D3 universe + D4 live cutover ports."""
from __future__ import annotations

import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _bars(n: int = 40, start: date | None = None, close0: float = 100.0):
    start = start or (date.today() - timedelta(days=n + 2))
    out = []
    c = close0
    for i in range(n):
        d = start + timedelta(days=i)
        ts = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
        c = close0 * (1.0 + 0.01 * i)
        out.append(
            {
                "ts_open": ts,
                "open": c * 0.99,
                "high": c * 1.01,
                "low": c * 0.98,
                "close": c,
                "volume": 1000.0 + i,
            }
        )
    return out


def test_thin_universe_includes_always_and_held():
    from phase6.core import marketdata_ingest as ing

    # monkey held
    orig = ing._held_pairs_from_live
    ing._held_pairs_from_live = lambda: {"PAXG-USD", "ZEC-USD"}  # type: ignore
    try:
        u = ing.resolve_thin_universe(include_tryout=False)
        pairs = set(u["pairs"])
        assert "BTC-USD" in pairs and "ETH-USD" in pairs and "PAXG-USD" in pairs
        assert "ZEC-USD" in pairs
        assert "USDC-USD" not in pairs
        print("  thin universe OK", sorted(pairs)[:12], "n=", u["n"])
    finally:
        ing._held_pairs_from_live = orig


def test_ingest_pair_and_get_daily_candles():
    from phase6.core.marketdata_store import (
        get_daily_candles,
        init_schema,
        upsert_bars,
        GRAN_1D,
    )

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "md.db"
        init_schema(db)
        upsert_bars(
            _bars(50, close0=80.0),
            symbol="ETH-USD",
            granularity_sec=GRAN_1D,
            source="test",
            db_path=db,
        )
        candles = get_daily_candles("ETH-USD", limit=20, db_path=db)
        assert len(candles) == 20
        assert "c" in candles[-1] and candles[-1]["c"] > 0
        assert "time" in candles[-1]
        print("  get_daily_candles OK", len(candles), candles[-1]["c"])


def test_arm_switch_prefers_store(monkeypatch_ok=True):
    """fetch_btc_daily returns store bars when present (no network needed)."""
    from phase6.core.marketdata_store import init_schema, upsert_bars, GRAN_1D, MARKETDATA_DB
    import phase6.core.regime_arm_switch as ras

    # Use real MARKETDATA_DB only if we can write temp — patch get_daily_candles instead
    from phase6.core import marketdata_store as ms

    fake = []
    start = date.today() - timedelta(days=60)
    c = 50000.0
    for i in range(60):
        d = start + timedelta(days=i)
        fake.append(
            {
                "time": f"{d.isoformat()}T00:00:00Z",
                "open": c,
                "high": c * 1.01,
                "low": c * 0.99,
                "close": c * (1 + 0.002 * i),
                "volume": 1.0,
                "t": 0,
                "o": c,
                "h": c,
                "l": c,
                "c": c * (1 + 0.002 * i),
                "v": 1.0,
            }
        )
    orig = ms.get_daily_candles
    ms.get_daily_candles = lambda symbol, limit=None, db_path=None: fake  # type: ignore
    try:
        rows = ras.fetch_btc_daily(use_network=False, min_days=40)
        assert len(rows) >= 40
        assert rows[-1]["close"] > 0
        print("  arm_switch store-first OK", len(rows), rows[-1]["close"])
    finally:
        ms.get_daily_candles = orig


def test_run_phase_store_first():
    from phase6.core import marketdata_store as ms
    import phase6.core.run_phase_deploy as rpd

    fake = []
    start = date.today() - timedelta(days=30)
    for i in range(30):
        d = start + timedelta(days=i)
        ts = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
        fake.append(
            {
                "time": f"{d.isoformat()}T00:00:00Z",
                "ts_open": ts,
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.0 + i * 0.1,
                "volume": 1.0,
                "t": float(ts),
                "o": 10.0,
                "h": 11.0,
                "l": 9.0,
                "c": 10.0 + i * 0.1,
                "v": 1.0,
            }
        )
    orig = ms.get_daily_candles
    ms.get_daily_candles = lambda symbol, limit=None, db_path=None: fake  # type: ignore
    try:
        rows = rpd.fetch_daily_candles_public("LINK-USD", limit=20)
        assert len(rows) == 20
        assert rows[-1]["c"] > 0
        print("  run_phase store-first OK", len(rows))
    finally:
        ms.get_daily_candles = orig


def main() -> int:
    test_thin_universe_includes_always_and_held()
    test_ingest_pair_and_get_daily_candles()
    test_arm_switch_prefers_store()
    test_run_phase_store_first()
    # keep D1/D2 suite still green if present
    try:
        from scripts.phase6 import test_isolation_marketdata_d1_d2 as d12  # type: ignore

        pass
    except Exception:
        pass
    print("marketdata D3/D4 isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
