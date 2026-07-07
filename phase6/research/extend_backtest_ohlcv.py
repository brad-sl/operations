#!/usr/bin/env python3
"""
Extend backtests/data/backtest_historical_ohlcv_* through today using Coinbase public candles.

Appends daily bars after the last candle in each file (no filename change — harness path stable).
Writes data/state/ohlcv_extension_manifest.json with actual coverage.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "backtests/data"
MANIFEST = ROOT / "data/state/ohlcv_extension_manifest.json"

# Short tickers with existing pack files
PAIR_FILES = {
    "btc": "BTC-USD",
    "eth": "ETH-USD",
    "sol": "SOL-USD",
    "xrp": "XRP-USD",
    "doge": "DOGE-USD",
    "avax": "AVAX-USD",
    "link": "LINK-USD",
    "arb": "ARB-USD",
    "near": "NEAR-USD",
}

FILENAME_SUFFIX = "_2025-04-20_to_2026-04-20.json"
GRANULARITY = 86400  # daily
MAX_CANDLES = 300


def _file_for(short: str) -> Path:
    return DATA_DIR / f"backtest_historical_ohlcv_{short}{FILENAME_SUFFIX}"


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _candle_row(ts: datetime, o: float, h: float, l: float, c: float, v: float) -> dict:
    return {
        "timestamp": ts.strftime("%Y-%m-%dT00:00:00Z"),
        "open": round(float(o), 8),
        "high": round(float(h), 8),
        "low": round(float(l), 8),
        "close": round(float(c), 8),
        "volume": int(v),
    }


def fetch_daily_candles(product_id: str, start: datetime, end: datetime) -> List[dict]:
    """Coinbase Exchange public API; returns ascending by time."""
    url = f"https://api.exchange.coinbase.com/products/{product_id}/candles"
    out: List[dict] = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=MAX_CANDLES), end)
        params = {
            "start": chunk_start.isoformat(),
            "end": chunk_end.isoformat(),
            "granularity": GRANULARITY,
        }
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(2.0)
            continue
        resp.raise_for_status()
        raw = resp.json()
        # [time, low, high, open, close, volume] newest first
        for row in reversed(raw):
            t = datetime.fromtimestamp(int(row[0]), tz=timezone.utc)
            if t < start or t >= end:
                continue
            out.append(_candle_row(t, row[3], row[2], row[1], row[4], row[5]))
        chunk_start = chunk_end
        time.sleep(0.25)
    # dedupe by day
    seen = set()
    deduped = []
    for c in sorted(out, key=lambda x: x["timestamp"]):
        if c["timestamp"] in seen:
            continue
        seen.add(c["timestamp"])
        deduped.append(c)
    return deduped


def extend_file(short: str, product_id: str, through: date) -> Dict[str, Any]:
    path = _file_for(short)
    if not path.exists():
        return {"short": short, "status": "missing_file"}

    candles = json.loads(path.read_text())
    if not candles:
        return {"short": short, "status": "empty"}

    last_ts = _parse_ts(candles[-1]["timestamp"])
    start_fetch = last_ts + timedelta(days=1)
    end_fetch = datetime(through.year, through.month, through.day, tzinfo=timezone.utc) + timedelta(days=1)

    if start_fetch >= end_fetch:
        return {
            "short": short,
            "status": "up_to_date",
            "last": candles[-1]["timestamp"],
            "count": len(candles),
        }

    new_bars = fetch_daily_candles(product_id, start_fetch, end_fetch)
    existing_days = {c["timestamp"][:10] for c in candles}
    appended = [c for c in new_bars if c["timestamp"][:10] not in existing_days]

    merged = candles + appended
    merged.sort(key=lambda x: x["timestamp"])
    path.write_text(json.dumps(merged, indent=2))

    return {
        "short": short,
        "product_id": product_id,
        "status": "extended",
        "appended": len(appended),
        "count": len(merged),
        "first": merged[0]["timestamp"],
        "last": merged[-1]["timestamp"],
        "source": "coinbase_public_candles",
    }


def global_bounds() -> Tuple[Optional[str], Optional[str]]:
    firsts, lasts = [], []
    for short in PAIR_FILES:
        p = _file_for(short)
        if not p.exists():
            continue
        data = json.loads(p.read_text())
        if data:
            firsts.append(data[0]["timestamp"][:10])
            lasts.append(data[-1]["timestamp"][:10])
    if not firsts:
        return None, None
    return min(firsts), max(lasts)


def main() -> int:
    through = date.today()
    results = []
    for short, pid in PAIR_FILES.items():
        try:
            results.append(extend_file(short, pid, through))
        except Exception as e:
            results.append({"short": short, "status": "error", "error": str(e)})

    start, end = global_bounds()
    manifest = {
        "extended_at": datetime.now(timezone.utc).isoformat(),
        "through_date": through.isoformat(),
        "data_start": start,
        "data_end": end,
        "pairs": results,
        "note": "Filenames unchanged; candle arrays include extension through data_end.",
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2))

    ok = sum(1 for r in results if r.get("status") in ("extended", "up_to_date"))
    print(f"OHLCV extend OK pairs={ok}/{len(PAIR_FILES)} data_end={end} manifest={MANIFEST}")
    for r in results:
        print(f"  {r.get('short')}: {r.get('status')} appended={r.get('appended', 0)}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())