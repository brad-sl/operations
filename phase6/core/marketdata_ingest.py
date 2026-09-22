"""BTC (and later multi-pair) OHLCV ingest into marketdata.db.

D2: BTC 1d only. Schema already accepts finer grans for later backfill.
Sources (in order of preference for tip):
  1) Coinbase public candles API
  2) data/ohlcv/BTC-USD_1d_coinbase.json (local fresh file)
Never uses undated price_cache or frozen backtest tip as live SSOT.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import requests

from phase6.core.marketdata_store import (
    GRAN_1D,
    MARKETDATA_DB,
    get_freshness,
    get_ohlcv,
    init_schema,
    mark_job_run,
    seed_core_pairs,
    upsert_bars,
    upsert_spot,
)
from phase6.core.paths import PROJECT_ROOT

PUBLIC_CANDLES = "https://api.exchange.coinbase.com/products/{product_id}/candles"
LOCAL_BTC_1D = PROJECT_ROOT / "data" / "ohlcv" / "BTC-USD_1d_coinbase.json"


def _coinbase_candles(
    product_id: str,
    granularity_sec: int,
    *,
    start: datetime,
    end: datetime,
    session: Optional[requests.Session] = None,
) -> List[Dict[str, Any]]:
    """Fetch candles; Coinbase returns [time, low, high, open, close, volume], newest first.

    Public API caps ~300 bars/request — page forward in chunks of ≤300.
    """
    sess = session or requests.Session()
    url = PUBLIC_CANDLES.format(product_id=product_id)
    out: List[Dict[str, Any]] = []
    max_bars = 300
    chunk = timedelta(seconds=int(granularity_sec) * (max_bars - 5))
    cursor_start = start
    max_pages = 40
    for _ in range(max_pages):
        if cursor_start >= end:
            break
        cursor_end = min(cursor_start + chunk, end)
        params = {
            "start": cursor_start.isoformat().replace("+00:00", "Z"),
            "end": cursor_end.isoformat().replace("+00:00", "Z"),
            "granularity": int(granularity_sec),
        }
        resp = sess.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"candles HTTP {resp.status_code}: {resp.text[:200]}")
        batch = resp.json() or []
        for c in batch:
            if not isinstance(c, (list, tuple)) or len(c) < 6:
                continue
            ts, low, high, open_, close, vol = c[0], c[1], c[2], c[3], c[4], c[5]
            out.append(
                {
                    "ts_open": int(ts),
                    "open": float(open_),
                    "high": float(high),
                    "low": float(low),
                    "close": float(close),
                    "volume": float(vol),
                }
            )
        # advance
        if cursor_end >= end:
            break
        cursor_start = cursor_end - timedelta(seconds=int(granularity_sec))  # slight overlap
        time.sleep(0.15)
    by_ts = {b["ts_open"]: b for b in out}
    return [by_ts[k] for k in sorted(by_ts)]


def load_local_btc_1d_json(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    p = path or LOCAL_BTC_1D
    if not p.exists():
        return []
    blob = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(blob, dict):
        rows = blob.get("candles") or blob.get("BTC-USD") or blob.get("data") or []
    else:
        rows = blob
    out: List[Dict[str, Any]] = []
    for b in rows or []:
        if not isinstance(b, dict):
            continue
        out.append(
            {
                "time": b.get("time") or b.get("timestamp"),
                "open": b.get("open"),
                "high": b.get("high"),
                "low": b.get("low"),
                "close": b.get("close"),
                "volume": b.get("volume"),
            }
        )
    return out


def ingest_btc_1d(
    *,
    db_path: Optional[Path] = None,
    lookback_days: int = 400,
    prefer_api: bool = True,
    also_local_file: bool = True,
) -> Dict[str, Any]:
    """D2 main path: fill BTC-USD daily bars + freshness."""
    init_schema(db_path)
    seed_core_pairs(db_path)
    report: Dict[str, Any] = {
        "job": "btc_1d_daily",
        "symbol": "BTC-USD",
        "granularity_sec": GRAN_1D,
        "db_path": str(db_path or MARKETDATA_DB),
        "api_rows": 0,
        "local_rows": 0,
        "upserted": 0,
        "errors": [],
    }
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(lookback_days))
    try:
        if prefer_api:
            try:
                api_bars = _coinbase_candles(
                    "BTC-USD", GRAN_1D, start=start, end=end
                )
                n = upsert_bars(
                    api_bars,
                    symbol="BTC-USD",
                    granularity_sec=GRAN_1D,
                    source="coinbase_public",
                    quality="ok",
                    db_path=db_path,
                )
                report["api_rows"] = len(api_bars)
                report["upserted"] += n
                if api_bars:
                    last = api_bars[-1]
                    upsert_spot(
                        "BTC-USD",
                        float(last["close"]),
                        as_of=datetime.fromtimestamp(
                            int(last["ts_open"]) + GRAN_1D, tz=timezone.utc
                        ).isoformat(),
                        source="coinbase_public_1d_close",
                        db_path=db_path,
                    )
            except Exception as e:
                report["errors"].append(f"api:{e}")
        if also_local_file and (report["api_rows"] == 0 or True):
            # Always merge local file as secondary fill (won't clobber newer API if same ts
            # — last writer wins; prefer API already wrote tip). Use quality import only if API empty.
            local = load_local_btc_1d_json()
            if local:
                src = "coinbase_public" if report["api_rows"] else "local_ohlcv_json"
                qual = "ok" if report["api_rows"] else "ok"
                n = upsert_bars(
                    local,
                    symbol="BTC-USD",
                    granularity_sec=GRAN_1D,
                    source=src,
                    quality=qual,
                    db_path=db_path,
                )
                report["local_rows"] = len(local)
                report["upserted"] += n
        fresh = get_freshness("BTC-USD", GRAN_1D, db_path=db_path)
        report["freshness"] = fresh
        bars = get_ohlcv("BTC-USD", GRAN_1D, db_path=db_path)
        report["bar_count"] = len(bars)
        if bars:
            report["first"] = {
                "ts_open": bars[0]["ts_open"],
                "close": bars[0]["close"],
            }
            report["last"] = {
                "ts_open": bars[-1]["ts_open"],
                "close": bars[-1]["close"],
            }
        ok = str(fresh.get("status")) == "ok" and len(bars) >= 30
        report["ok"] = ok
        mark_job_run(
            "btc_1d_daily",
            "ok" if ok else "degraded",
            error="; ".join(report["errors"]) if report["errors"] else None,
            db_path=db_path,
        )
    except Exception as e:
        report["ok"] = False
        report["errors"].append(str(e))
        mark_job_run("btc_1d_daily", "error", error=str(e), db_path=db_path)
    return report


def write_local_btc_mirror(
    *,
    db_path: Optional[Path] = None,
    path: Optional[Path] = None,
) -> Path:
    """Optional: rewrite data/ohlcv JSON from DB so other tools see same tip."""
    path = path or LOCAL_BTC_1D
    bars = get_ohlcv("BTC-USD", GRAN_1D, db_path=db_path)
    payload = []
    for b in bars:
        d = datetime.fromtimestamp(int(b["ts_open"]), tz=timezone.utc)
        payload.append(
            {
                "time": d.strftime("%Y-%m-%dT00:00:00Z"),
                "open": b["open"],
                "high": b["high"],
                "low": b["low"],
                "close": b["close"],
                "volume": b.get("volume"),
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
