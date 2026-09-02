"""
RSI + StochRSI + sentiment snapshots for decision/trade analysis.

Canonical RSI: data/state/rsi_cache.json (scripts/refresh_rsi_prices.py).
Canonical sent: sentiment_scorer / data/state/sentiment_cache.json.
History: append-only data/state/rsi_indicator_history.jsonl (refresher).
Trade research SSOT: data/state/trade_signal_events.jsonl (BUY+SELL legs with
entry/exit RSI+sent + lag) — required for attribution / lag digs.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from phase6.core.paths import PROJECT_ROOT, RSI_CACHE, STATE_DIR

logger = logging.getLogger(__name__)

RSI_INDICATOR_HISTORY = STATE_DIR / "rsi_indicator_history.jsonl"
TRADE_SIGNAL_EVENTS = STATE_DIR / "trade_signal_events.jsonl"
HISTORY_SCHEMA_VERSION = 1
TRADE_SIGNAL_SCHEMA_VERSION = 1


def load_rsi_cache_root() -> Dict[str, Any]:
    if not RSI_CACHE.exists():
        return {}
    try:
        return json.loads(RSI_CACHE.read_text())
    except Exception as exc:
        logger.debug("rsi_cache load failed: %s", exc)
        return {}


def load_rsi_cache_pairs() -> Dict[str, Dict[str, Any]]:
    root = load_rsi_cache_root()
    raw = root.get("rsi") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def normalize_pair_indicators(
    pair: str,
    cache_entry: Optional[Dict[str, Any]],
    runner_rsi: Optional[float] = None,
) -> Dict[str, Any]:
    """Compact per-pair record for logs (plain RSI + Stoch for side-by-side analysis)."""
    out: Dict[str, Any] = {"pair": pair}
    if isinstance(cache_entry, dict):
        if cache_entry.get("rsi") is not None:
            out["rsi"] = round(float(cache_entry["rsi"]), 2)
        if cache_entry.get("stoch_k") is not None:
            out["stoch_k"] = round(float(cache_entry["stoch_k"]), 2)
        if cache_entry.get("stoch_d") is not None:
            out["stoch_d"] = round(float(cache_entry["stoch_d"]), 2)
        if cache_entry.get("candle_count") is not None:
            out["candle_count"] = int(cache_entry["candle_count"])
        if cache_entry.get("source"):
            out["source"] = cache_entry["source"]
        if cache_entry.get("timestamp"):
            out["cache_timestamp"] = cache_entry["timestamp"]
    if "rsi" not in out and runner_rsi is not None:
        out["rsi"] = round(float(runner_rsi), 2)
        out["source"] = out.get("source", "runner.rsi_values")
    return out


def build_basket_indicator_snapshot(
    *,
    universe: Optional[List[str]] = None,
    runner_rsi_values: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Full basket snapshot for rebalance decision_context.

    Returns:
      indicator_snapshot: {PAIR: {rsi, stoch_k, stoch_d, ...}}
      indicator_meta: cache file timestamp, pair count, schema
    """
    from phase6.core.paths import load_trading_basket

    basket = universe or load_trading_basket()
    cache_pairs = load_rsi_cache_pairs()
    root = load_rsi_cache_root()
    runner_rsi = runner_rsi_values or {}

    per_pair: Dict[str, Dict[str, Any]] = {}
    for pair in basket:
        per_pair[pair] = normalize_pair_indicators(
            pair,
            cache_pairs.get(pair),
            runner_rsi.get(pair),
        )

    with_stoch = sum(1 for v in per_pair.values() if v.get("stoch_k") is not None)
    return {
        "indicator_snapshot": per_pair,
        "indicator_meta": {
            "schema_version": HISTORY_SCHEMA_VERSION,
            "cache_file_timestamp": root.get("timestamp"),
            "pairs": len(basket),
            "pairs_with_stoch_k": with_stoch,
            "source_file": str(RSI_CACHE.relative_to(PROJECT_ROOT))
            if RSI_CACHE.is_relative_to(PROJECT_ROOT)
            else str(RSI_CACHE),
        },
    }


def indicators_for_trade_pair(
    pair: str,
    runner_rsi_values: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """RSI/Stoch + live sentiment for one pair at stamp time."""
    cache_pairs = load_rsi_cache_pairs()
    out = normalize_pair_indicators(
        pair,
        cache_pairs.get(pair),
        (runner_rsi_values or {}).get(pair),
    )
    sent, sent_meta = _load_pair_sentiment(pair)
    if sent is not None:
        out["sentiment"] = sent
    if sent_meta:
        out.update(sent_meta)
    out["stamped_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return out


def _f(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _load_pair_sentiment(pair: str) -> tuple[Optional[float], Dict[str, Any]]:
    """Best-effort live sentiment for pair. Never invents scores."""
    meta: Dict[str, Any] = {}
    try:
        from phase6.core.sentiment_scorer import load_sentiment_scores_detailed

        detailed = load_sentiment_scores_detailed(universe=[pair]) or {}
        # shapes: {pair: score} or {pair: {score, source, ...}} or {scores: {...}}
        if isinstance(detailed, dict) and "scores" in detailed and isinstance(detailed["scores"], dict):
            block = detailed["scores"].get(pair)
            meta["sentiment_mode"] = detailed.get("mode") or detailed.get("source")
        else:
            block = detailed.get(pair) if isinstance(detailed, dict) else None
        if isinstance(block, dict):
            s = _f(block.get("score", block.get("sentiment", block.get("value"))))
            if block.get("source"):
                meta["sentiment_source"] = block.get("source")
            if block.get("post_count") is not None:
                meta["sentiment_post_count"] = block.get("post_count")
            return s, meta
        if block is not None:
            return _f(block), meta
    except Exception as exc:
        logger.debug("detailed sentiment load failed: %s", exc)
    try:
        from phase6.core.sentiment_scorer import load_sentiment_scores

        scores = load_sentiment_scores(universe=[pair]) or {}
        if pair in scores:
            return _f(scores.get(pair)), meta
        # common alt keys
        base = pair.split("-")[0] if pair else ""
        for k, v in (scores or {}).items():
            if str(k).upper().startswith(base.upper()):
                return _f(v), meta
    except Exception as exc:
        logger.debug("sentiment_scores load failed: %s", exc)
    # raw cache fallback
    try:
        p = STATE_DIR / "sentiment_cache.json"
        if p.exists():
            raw = json.loads(p.read_text())
            scores = raw.get("scores") if isinstance(raw, dict) else None
            if not isinstance(scores, dict):
                scores = raw if isinstance(raw, dict) else {}
            block = scores.get(pair) or scores.get(pair.replace("-USD", ""))
            if isinstance(block, dict):
                s = _f(block.get("score", block.get("sentiment")))
                if block.get("source"):
                    meta["sentiment_source"] = block.get("source")
                meta["sentiment_cache_ts"] = raw.get("timestamp") or raw.get("updated_at")
                return s, meta
            if block is not None:
                meta["sentiment_cache_ts"] = raw.get("timestamp") if isinstance(raw, dict) else None
                return _f(block), meta
    except Exception as exc:
        logger.debug("sentiment_cache fallback failed: %s", exc)
    return None, meta


def _entry_lot_for_pair(pair: str, order_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        from phase6.core.rsi_primary_deploy import load_entry_lots

        lots = load_entry_lots()
    except Exception:
        lots = []
        try:
            p = STATE_DIR / "entry_driver_lots.json"
            if p.exists():
                data = json.loads(p.read_text())
                lots = data.get("lots") if isinstance(data, dict) else data
                lots = lots if isinstance(lots, list) else []
        except Exception:
            lots = []
    if order_id:
        for lot in lots:
            if str(lot.get("order_id") or "") == str(order_id) and str(lot.get("pair")) == pair:
                return lot
    # open lot for pair
    for lot in lots:
        if str(lot.get("pair")) == pair and lot.get("open", True):
            return lot
    # any lot for pair (most recent open-ish)
    cands = [x for x in lots if str(x.get("pair")) == pair]
    return cands[-1] if cands else None


def _lag_hours(entry_ts: Any, exit_ts: Any) -> Optional[float]:
    def _parse(x: Any) -> Optional[datetime]:
        if not x:
            return None
        try:
            return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        except Exception:
            return None

    a, b = _parse(entry_ts), _parse(exit_ts)
    if not a or not b:
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return round((b - a).total_seconds() / 3600.0, 4)


def stamp_trade_signal_fields(trade: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mutate+return trade with durable RSI+sentiment on BOTH legs.

    BUY:  entry_rsi, entry_sentiment, indicators_at_trade
    SELL: exit_rsi, exit_sentiment, + entry_* from entry_driver lot when known,
          lag_hours_entry_to_exit

    Safe no-op on missing caches. Never invents scores.
    """
    t = dict(trade)
    pair = str(t.get("pair") or t.get("product_id") or "")
    if not pair:
        return t
    side = str(t.get("side") or t.get("action") or "").upper()
    ind = t.get("indicators_at_trade")
    if not isinstance(ind, dict):
        ind = {}
    # Always refresh live snapshot fields (merge, don't wipe prior keys)
    live = indicators_for_trade_pair(pair)
    merged = dict(ind)
    merged.update({k: v for k, v in live.items() if v is not None})
    t["indicators_at_trade"] = merged

    rsi_now = _f(merged.get("rsi"), _f(t.get("entry_rsi") if side == "BUY" else t.get("exit_rsi")))
    sent_now = _f(merged.get("sentiment"), _f(t.get("entry_sentiment") if side == "BUY" else t.get("exit_sentiment")))

    if side == "BUY":
        if t.get("entry_rsi") is None and rsi_now is not None:
            t["entry_rsi"] = rsi_now
        if t.get("entry_sentiment") is None and sent_now is not None:
            t["entry_sentiment"] = sent_now
        # mirror into indicators for consumers that only read nested
        if t.get("entry_rsi") is not None:
            merged["entry_rsi"] = t["entry_rsi"]
        if t.get("entry_sentiment") is not None:
            merged["entry_sentiment"] = t["entry_sentiment"]
        merged["leg"] = "entry"
    elif side == "SELL":
        if t.get("exit_rsi") is None and rsi_now is not None:
            t["exit_rsi"] = rsi_now
        if t.get("exit_sentiment") is None and sent_now is not None:
            t["exit_sentiment"] = sent_now
        if t.get("exit_rsi") is not None:
            merged["exit_rsi"] = t["exit_rsi"]
        if t.get("exit_sentiment") is not None:
            merged["exit_sentiment"] = t["exit_sentiment"]
        merged["leg"] = "exit"
        # Join entry lot for attribution / lag
        lot = _entry_lot_for_pair(pair, order_id=str(t.get("entry_order_id") or t.get("parent_sl_order_id") or "") or None)
        if lot is None:
            lot = _entry_lot_for_pair(pair, order_id=None)
        if lot:
            if t.get("entry_rsi") is None and lot.get("entry_rsi") is not None:
                t["entry_rsi"] = _f(lot.get("entry_rsi"))
            if t.get("entry_sentiment") is None and lot.get("entry_sentiment") is not None:
                t["entry_sentiment"] = _f(lot.get("entry_sentiment"))
            if t.get("entry_drivers") is None and lot.get("drivers") is not None:
                t["entry_drivers"] = lot.get("drivers")
            if t.get("sentiment_only") is None and lot.get("sentiment_only") is not None:
                t["sentiment_only"] = lot.get("sentiment_only")
            if t.get("sentiment_led") is None and lot.get("sentiment_led") is not None:
                t["sentiment_led"] = lot.get("sentiment_led")
            if t.get("entry_order_id") is None and lot.get("order_id"):
                t["entry_order_id"] = lot.get("order_id")
            if t.get("entry_ts") is None and lot.get("ts"):
                t["entry_ts"] = lot.get("ts")
            lag = _lag_hours(lot.get("ts") or t.get("entry_ts"), t.get("timestamp"))
            if lag is not None:
                t["lag_hours_entry_to_exit"] = lag
                merged["lag_hours_entry_to_exit"] = lag
            if t.get("entry_rsi") is not None:
                merged["entry_rsi"] = t["entry_rsi"]
            if t.get("entry_sentiment") is not None:
                merged["entry_sentiment"] = t["entry_sentiment"]
        # deltas for digs (exit - entry) when both present
        er, xr = _f(t.get("entry_rsi")), _f(t.get("exit_rsi"))
        if er is not None and xr is not None:
            t["rsi_delta_entry_exit"] = round(xr - er, 4)
        es, xs = _f(t.get("entry_sentiment")), _f(t.get("exit_sentiment"))
        if es is not None and xs is not None:
            t["sent_delta_entry_exit"] = round(xs - es, 4)
    else:
        merged["leg"] = "unknown"

    t["indicators_at_trade"] = merged
    t["signal_stamp_schema"] = TRADE_SIGNAL_SCHEMA_VERSION
    return t


def append_trade_signal_event(trade: Dict[str, Any], *, path: Optional[Path] = None) -> None:
    """Append one research row (BUY or SELL) for attribution/lag digs."""
    out_path = path or TRADE_SIGNAL_EVENTS
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "schema_version": TRADE_SIGNAL_SCHEMA_VERSION,
            "timestamp": trade.get("timestamp"),
            "pair": trade.get("pair"),
            "side": str(trade.get("side") or "").upper(),
            "order_id": trade.get("order_id"),
            "entry_order_id": trade.get("entry_order_id"),
            "entry_rsi": trade.get("entry_rsi"),
            "entry_sentiment": trade.get("entry_sentiment"),
            "exit_rsi": trade.get("exit_rsi"),
            "exit_sentiment": trade.get("exit_sentiment"),
            "entry_drivers": trade.get("entry_drivers"),
            "sentiment_only": trade.get("sentiment_only"),
            "sentiment_led": trade.get("sentiment_led"),
            "lag_hours_entry_to_exit": trade.get("lag_hours_entry_to_exit"),
            "rsi_delta_entry_exit": trade.get("rsi_delta_entry_exit"),
            "sent_delta_entry_exit": trade.get("sent_delta_entry_exit"),
            "pnl": trade.get("pnl"),
            "pnl_pct": trade.get("pnl_pct"),
            "entry_price": trade.get("entry_price"),
            "exit_price": trade.get("exit_price"),
            "reason": trade.get("reason") or trade.get("exit_reason"),
            "signal_source": trade.get("signal_source"),
            "indicators_at_trade": trade.get("indicators_at_trade"),
            "mode": trade.get("mode"),
        }
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
    except Exception as exc:
        logger.debug("trade_signal_event append failed: %s", exc)


def append_indicator_history(
    rsi_entries: Dict[str, Any],
    *,
    run_timestamp: Optional[str] = None,
    history_path: Optional[Path] = None,
) -> None:
    """Append one refresher cycle to rsi_indicator_history.jsonl."""
    path = history_path or RSI_INDICATOR_HISTORY
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = run_timestamp or datetime.now(timezone.utc).isoformat()
    row = {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "timestamp": ts,
        "event": "rsi_refresher",
        "pair_count": len(rsi_entries),
        "pairs": {
            str(pair): {
                "rsi": entry.get("rsi"),
                "stoch_k": entry.get("stoch_k"),
                "stoch_d": entry.get("stoch_d"),
                "candle_count": entry.get("candle_count"),
                "source": entry.get("source"),
            }
            for pair, entry in rsi_entries.items()
            if isinstance(entry, dict)
        },
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")