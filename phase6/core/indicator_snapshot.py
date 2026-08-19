"""
RSI + StochRSI snapshots for decision/trade analysis (RSI vs StochRSI comparison).

Canonical source: data/state/rsi_cache.json (written by scripts/refresh_rsi_prices.py).
History: append-only data/state/rsi_indicator_history.jsonl (one row per refresher run).
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
HISTORY_SCHEMA_VERSION = 1


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
    cache_pairs = load_rsi_cache_pairs()
    return normalize_pair_indicators(
        pair,
        cache_pairs.get(pair),
        (runner_rsi_values or {}).get(pair),
    )


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