"""
BTC-anchored market regime detection from real OHLCV (no synthetic prices).

Merges live BTC price when historical OHLCV lags (REGIME-CASH RC-05).
Thresholds can be passed in (from config/regime_cash_policy.json detector block).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.paths import PROJECT_ROOT, STATE_DIR

OHLCV_GLOB = "backtests/data/backtest_historical_ohlcv_*.json"

BULL_RETURN_PCT = 15.0
BEAR_RETURN_PCT = -10.0
FLAT_ABS_PCT = 8.0
LOOKBACK_DAYS = 30
# Boundary layers inside residual "transition" (observability + shadow only until promote)
SOFT_UP_WIDTH_PCT = 2.0   # flat .. flat+soft → soft_up
PRE_BULL_WIDTH_PCT = 1.0  # bull-pre .. bull → pre_bull; middle residual → climb

# Treat OHLCV as stale if last bar is older than this many calendar days
STALE_DAYS = 2


def classify_regime_layer(
    ret_pct: float,
    *,
    bull_return_pct: float = BULL_RETURN_PCT,
    bear_return_pct: float = BEAR_RETURN_PCT,
    flat_abs_pct: float = FLAT_ABS_PCT,
    soft_up_width_pct: float = SOFT_UP_WIDTH_PCT,
    pre_bull_width_pct: float = PRE_BULL_WIDTH_PCT,
) -> Dict[str, Any]:
    """Split BTC 30d into coarse policy regime + boundary layer.

    Coarse policy keys (live money):
      bull | bear | flat | transition (upside residual only) | soft_down | unknown

    Brad 2026-08-24: downside residual is first-class soft_down (de-risk), not
    the same ``transition`` bucket as flat→bull (deploy). Signed residual.
    """
    bull = float(bull_return_pct)
    bear = float(bear_return_pct)
    flat = abs(float(flat_abs_pct))
    soft_w = max(0.0, float(soft_up_width_pct))
    pre_w = max(0.0, float(pre_bull_width_pct))
    r = float(ret_pct)

    if r >= bull:
        layer, coarse = "bull", "bull"
    elif r <= bear:
        layer, coarse = "bear", "bear"
    elif abs(r) <= flat:
        layer, coarse = "flat", "flat"
    elif r < 0:
        # bear < r < -flat  → soft_down (live de-risk, not upside transition)
        layer, coarse = "soft_down", "soft_down"
    else:
        # r > flat — upside residual still coarse "transition"
        soft_hi = flat + soft_w
        pre_lo = bull - pre_w
        if r <= soft_hi + 1e-12:
            layer = "soft_up"
        elif r >= pre_lo - 1e-12:
            layer = "pre_bull"
        elif r < bull:
            layer = "climb"
        else:
            layer = "transition_core"
        coarse = "transition"

    labels = {
        "bull": "Bull — full deploy posture",
        "bear": "Bear — park",
        "flat": "Flat — range / gated micro",
        "soft_down": "Soft-down — thin residual near bear (de-risk)",
        "soft_up": "Soft-up — just above flat (layer of transition deploy)",
        "climb": "Climb — up but not bull (layer of transition deploy)",
        "pre_bull": "Pre-bull — last step into bull (layer of transition deploy)",
        "transition_core": "Transition-core — residual",
        "unknown": "Unknown",
    }
    # Live-aligned stance labels (dashboard/shadow); money still via coarse regime policy
    shadow_stance = {
        "bull": "deploy",
        "bear": "park",
        "flat": "flat_b",
        "soft_down": "derisk",
        "soft_up": "transition_deploy",
        "climb": "transition_deploy",
        "pre_bull": "transition_deploy",
        "transition_core": "transition_deploy",
        "unknown": "park",
    }.get(layer, "park")

    return {
        "regime_layer": layer,
        "regime": coarse,
        "layer_label": labels.get(layer, layer),
        "shadow_stance": shadow_stance,
        "btc_return_pct": round(r, 3),
        "layer_thresholds": {
            "bull_return_pct": bull,
            "bear_return_pct": bear,
            "flat_abs_pct": flat,
            "soft_up_width_pct": soft_w,
            "pre_bull_width_pct": pre_w,
            "soft_up_hi": round(flat + soft_w, 4),
            "climb_lo": round(flat + soft_w, 4),
            "climb_hi": round(bull - pre_w, 4),
            "pre_bull_lo": round(bull - pre_w, 4),
            "soft_down_lo": bear,
            "soft_down_hi": -flat,
        },
    }


def _load_btc_closes_from_legacy_json() -> List[Tuple[date, float]]:
    """Legacy research freezes — NOT live SSOT. Used only as last-resort offline fill."""
    data_dir = PROJECT_ROOT / "backtests/data"
    if not data_dir.exists():
        return []
    # Prefer longer tape if present; never sole live tip without freshness gate
    candidates = [
        data_dir / "long" / "ohlcv_daily_btc.json",
        data_dir / "backtest_historical_ohlcv_btc_2025-04-20_to_2026-04-20.json",
        data_dir / "backtest_historical_ohlcv_BTC-USD_2025-04-20_to_2026-04-20.json",
        data_dir / "backtest_historical_ohlcv_BTC_2025-04-20_to_2026-04-20.json",
    ]
    # fresher local mirror written by marketdata ingest
    local_fresh = PROJECT_ROOT / "data" / "ohlcv" / "BTC-USD_1d_coinbase.json"
    path = next((p for p in candidates if p.exists()), None)
    # If only local fresh exists, use it
    if local_fresh.exists():
        path = local_fresh
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
        series = (
            blob.get("BTC-USD")
            or blob.get("BTC/USD")
            or blob.get("candles")
            or blob.get("data")
            or []
        )
    else:
        series = []
    out: List[Tuple[date, float]] = []
    for bar in series:
        ts = bar.get("timestamp") or bar.get("time") or ""
        close = bar.get("close")
        if close is None:
            continue
        try:
            if isinstance(ts, (int, float)):
                d = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
            elif "T" in str(ts):
                d = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).date()
            else:
                d = date.fromisoformat(str(ts)[:10])
            out.append((d, float(close)))
        except Exception:
            continue
    out.sort(key=lambda x: x[0])
    return out


def _load_btc_closes_with_meta() -> Tuple[List[Tuple[date, float]], Dict[str, Any]]:
    """Primary: marketdata.db BTC 1d. Fallback: local/legacy JSON (flagged).

    Returns (closes, load_meta). load_meta includes freshness + source.
    """
    meta: Dict[str, Any] = {"source": None, "fresh_ok": False}
    try:
        from phase6.core.marketdata_store import get_btc_daily_closes

        closes, md = get_btc_daily_closes()
        meta.update(md)
        if closes and md.get("fresh_ok"):
            meta["source"] = "marketdata_db"
            return closes, meta
        if closes:
            # DB has bars but freshness failed — still return closes; detect_regime fail-closes
            meta["source"] = "marketdata_db_stale"
            return closes, meta
    except Exception as e:
        meta["marketdata_error"] = str(e)

    # Fallback JSON (may be fresh local file OR frozen research)
    closes = _load_btc_closes_from_legacy_json()
    meta["source"] = "legacy_json_fallback"
    meta["fresh_ok"] = False
    if closes:
        last = closes[-1][0]
        lag = (datetime.now(timezone.utc).date() - last).days
        meta["legacy_last"] = last.isoformat()
        meta["legacy_lag_days"] = lag
        # Only treat as fresh_ok if tip is within STALE_DAYS (local file case)
        meta["fresh_ok"] = lag <= STALE_DAYS and len(closes) >= 5
    return closes, meta


def _load_btc_closes() -> List[Tuple[date, float]]:
    """Backward-compatible: closes list only (research/climate helpers)."""
    closes, _meta = _load_btc_closes_with_meta()
    return closes


def _live_btc_price() -> Optional[float]:
    """Dated spot only — never undated price_cache_*.json (fossil SSOT bug class).

    Order: marketdata spot (max_age) → live_state BTC mark if held.
    """
    try:
        from phase6.core.marketdata_store import get_spot

        spot = get_spot("BTC-USD", max_age_sec=6 * 3600)
        if spot and spot.get("price"):
            return float(spot["price"])
    except Exception:
        pass

    live = STATE_DIR / "phase6_live_state.json"
    if live.exists():
        try:
            st = json.loads(live.read_text(encoding="utf-8"))
            for pos in st.get("trading_positions") or st.get("positions") or []:
                if not isinstance(pos, dict):
                    continue
                if pos.get("pair") in ("BTC-USD", "BTC"):
                    for k in ("current_price", "price", "mark_price", "last_price"):
                        if pos.get(k) is not None and float(pos[k]) > 0:
                            return float(pos[k])
            prices = st.get("prices") or {}
            if prices.get("BTC-USD"):
                return float(prices["BTC-USD"])
        except (json.JSONDecodeError, TypeError, ValueError, OSError, KeyError):
            pass

    # Explicitly DO NOT read price_cache_BTC_USD.json (undated bootstrap, caused false bear).
    return None


def _merge_live_close(
    closes: List[Tuple[date, float]],
    *,
    today: Optional[date] = None,
) -> Tuple[List[Tuple[date, float]], Dict[str, Any]]:
    """Tip hygiene only: same-day replace or +1 day append when lag is small.

    Will NOT invent a multi-day bridge (no 19-day skip-fill). Large gaps stay gapped;
    detect_regime fail-closes via freshness.
    """
    meta: Dict[str, Any] = {
        "live_appended": False,
        "ohlcv_last": None,
        "live_price": None,
        "refused_gap_fill": False,
    }
    if not closes:
        return closes, meta
    meta["ohlcv_last"] = closes[-1][0].isoformat()
    live_px = _live_btc_price()
    meta["live_price"] = live_px
    if live_px is None:
        return closes, meta

    end = today or datetime.now(timezone.utc).date()
    last_d, last_px = closes[-1]
    lag_days = (end - last_d).days
    meta["lag_days"] = lag_days
    if lag_days < STALE_DAYS and abs(live_px - last_px) / max(last_px, 1e-12) < 0.001:
        return closes, meta

    # Refuse multi-day hole fill with a single spot print
    if lag_days > STALE_DAYS:
        meta["refused_gap_fill"] = True
        meta["gap_days_not_filled"] = lag_days - 1
        return closes, meta

    out = list(closes)
    if last_d == end:
        out[-1] = (end, live_px)
        meta["live_appended"] = True
        meta["live_mode"] = "replace_same_day"
    elif last_d < end and lag_days <= STALE_DAYS:
        out.append((end, live_px))
        meta["live_appended"] = True
        meta["live_mode"] = "append_today"
        meta["gap_days_not_filled"] = max(0, lag_days - 1)
    return out, meta


def detect_regime(
    as_of: Optional[date] = None,
    lookback_days: int = LOOKBACK_DAYS,
    *,
    bull_return_pct: float = BULL_RETURN_PCT,
    bear_return_pct: float = BEAR_RETURN_PCT,
    flat_abs_pct: float = FLAT_ABS_PCT,
    soft_up_width_pct: float = SOFT_UP_WIDTH_PCT,
    pre_bull_width_pct: float = PRE_BULL_WIDTH_PCT,
    use_live_price: bool = True,
) -> Dict[str, Any]:
    """
    Classify regime over the last `lookback_days` ending at `as_of` (default: latest bar).

    Also emits regime_layer (soft_up/climb/pre_bull/…) for boundary observability.
    Coarse `regime` key stays the policy lookup key (bull|bear|flat|transition|unknown).

    D2: prefers marketdata.db BTC 1d; fail-closed to unknown when series is gapped/stale
    rather than inventing false bear/bull from fossil cache + frozen backtest tip.
    """
    closes, load_meta = _load_btc_closes_with_meta()
    live_meta: Dict[str, Any] = {"load": load_meta}
    if use_live_price and closes:
        closes, merge_meta = _merge_live_close(closes)
        live_meta.update(merge_meta)

    # Fail-closed: stale/gapped market data must not drive confident money-path regime
    fresh_ok = bool(load_meta.get("fresh_ok"))
    if load_meta.get("source") == "marketdata_db_stale":
        fresh_ok = False
    if live_meta.get("refused_gap_fill"):
        fresh_ok = False

    if len(closes) < 5 or not fresh_ok:
        reason = "insufficient BTC OHLCV"
        if closes and not fresh_ok:
            reason = (
                f"BTC OHLCV not fresh for regime "
                f"(source={load_meta.get('source')}, "
                f"fresh={load_meta.get('freshness') or load_meta.get('legacy_lag_days')})"
            )
        return {
            "regime": "unknown",
            "regime_layer": "unknown",
            "layer_label": "Unknown",
            "shadow_stance": "park",
            "confidence": 0.0,
            "reason": reason,
            "btc_return_pct": None,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "live_merge": live_meta,
            "data_source": load_meta.get("source"),
            "fresh_ok": False,
        }

    end_day = as_of or closes[-1][0]
    start_day = end_day - timedelta(days=lookback_days)
    window = [(d, c) for d, c in closes if start_day <= d <= end_day]
    if len(window) < 2:
        window = closes[-min(len(closes), lookback_days) :]

    p0 = window[0][1]
    p1 = window[-1][1]
    ret_pct = (p1 / p0 - 1.0) * 100.0 if p0 > 0 else 0.0

    layer_info = classify_regime_layer(
        ret_pct,
        bull_return_pct=bull_return_pct,
        bear_return_pct=bear_return_pct,
        flat_abs_pct=flat_abs_pct,
        soft_up_width_pct=soft_up_width_pct,
        pre_bull_width_pct=pre_bull_width_pct,
    )
    regime = str(layer_info["regime"])

    # Confidence: bar count + recency of last bar
    bar_conf = min(1.0, len(window) / max(lookback_days, 1))
    lag = (datetime.now(timezone.utc).date() - window[-1][0]).days
    recency = 1.0 if lag <= 1 else max(0.4, 1.0 - 0.1 * lag)
    confidence = round(min(1.0, bar_conf * recency), 3)

    return {
        "regime": regime,
        "regime_layer": layer_info["regime_layer"],
        "layer_label": layer_info["layer_label"],
        "shadow_stance": layer_info["shadow_stance"],
        "confidence": confidence,
        "btc_return_pct": round(ret_pct, 3),
        "window_start": window[0][0].isoformat(),
        "window_end": window[-1][0].isoformat(),
        "lookback_days": lookback_days,
        "thresholds": {
            "bull_return_pct": bull_return_pct,
            "bear_return_pct": bear_return_pct,
            "flat_abs_pct": flat_abs_pct,
            "soft_up_width_pct": soft_up_width_pct,
            "pre_bull_width_pct": pre_bull_width_pct,
        },
        "layer_thresholds": layer_info.get("layer_thresholds"),
        "live_merge": live_meta,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "data_source": load_meta.get("source"),
        "fresh_ok": True,
    }
