"""
BTC-anchored market regime detection from real OHLCV (no synthetic prices).

Used for regime-adaptive knob maps (bull / bear / flat) when shadow overlay enables regime_policy.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.paths import PROJECT_ROOT

OHLCV_GLOB = "backtests/data/backtest_historical_ohlcv_*.json"

BULL_RETURN_PCT = 15.0
BEAR_RETURN_PCT = -10.0
FLAT_ABS_PCT = 8.0
LOOKBACK_DAYS = 30


def _load_btc_closes() -> List[Tuple[date, float]]:
    data_dir = PROJECT_ROOT / "backtests/data"
    if not data_dir.exists():
        return []
    candidates = [
        data_dir / "backtest_historical_ohlcv_BTC-USD_2025-04-20_to_2026-04-20.json",
        data_dir / "backtest_historical_ohlcv_BTC_2025-04-20_to_2026-04-20.json",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        for p in sorted(data_dir.glob("backtest_historical_ohlcv_BTC*.json"), reverse=True):
            path = p
            break
    if path is None:
        return []

    with open(path) as f:
        blob = json.load(f)
    if isinstance(blob, list):
        series = blob
    elif isinstance(blob, dict):
        series = blob.get("BTC-USD") or blob.get("BTC/USD") or []
    else:
        series = []
    out: List[Tuple[date, float]] = []
    for bar in series:
        ts = bar.get("timestamp") or bar.get("time") or ""
        close = bar.get("close")
        if close is None:
            continue
        try:
            if "T" in ts:
                d = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
            else:
                d = date.fromisoformat(ts[:10])
            out.append((d, float(close)))
        except Exception:
            continue
    out.sort(key=lambda x: x[0])
    return out


def detect_regime(
    as_of: Optional[date] = None,
    lookback_days: int = LOOKBACK_DAYS,
) -> Dict[str, Any]:
    """
    Classify regime over the last `lookback_days` ending at `as_of` (default: latest bar).
    """
    closes = _load_btc_closes()
    if len(closes) < 5:
        return {
            "regime": "unknown",
            "confidence": 0.0,
            "reason": "insufficient BTC OHLCV",
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    end_day = as_of or closes[-1][0]
    start_day = end_day - timedelta(days=lookback_days)
    window = [(d, c) for d, c in closes if start_day <= d <= end_day]
    if len(window) < 2:
        window = closes[-min(len(closes), lookback_days) :]

    p0 = window[0][1]
    p1 = window[-1][1]
    ret_pct = (p1 / p0 - 1.0) * 100.0 if p0 > 0 else 0.0

    if ret_pct >= BULL_RETURN_PCT:
        regime = "bull"
    elif ret_pct <= BEAR_RETURN_PCT:
        regime = "bear"
    elif abs(ret_pct) <= FLAT_ABS_PCT:
        regime = "flat"
    else:
        regime = "transition"

    confidence = min(1.0, len(window) / max(lookback_days, 1))
    return {
        "regime": regime,
        "confidence": round(confidence, 3),
        "btc_return_pct": round(ret_pct, 3),
        "window_start": window[0][0].isoformat(),
        "window_end": window[-1][0].isoformat(),
        "lookback_days": lookback_days,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }