#!/usr/bin/env python3
"""
RSI + StochRSI Price Refresher (canonical, RSI-SENT-002 + Stoch parallel trial)

Single source of truth for the 15m cron (sync to ~/.hermes/scripts/ after edits).

- Full basket from config (load_trading_basket), not hard-coded 6.
- Fetches recent 15m candles (public Coinbase) and updates price_history.json.
- Computes Wilder RSI(14) + StochRSI(%K/%D) from up to 100 history points.
- Writes data/state/rsi_cache.json with stoch_k/stoch_d + freshness metadata.
- Appends data/state/rsi_indicator_history.jsonl for trial analysis.
- Persists RSI to phase6.db rsi_values when available.

Real data only. No fabrication.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.paths import PROJECT_ROOT as _PR, RSI_CACHE as _RSI_CACHE, PHASE6_DB, load_trading_basket

# Prefer paths.py PROJECT_ROOT when available
PROJECT_ROOT = Path(_PR)
RSI_CACHE_PATH = Path(_RSI_CACHE)
PRICE_HISTORY_PATH = PROJECT_ROOT / "data" / "state" / "price_history.json"
DB_PATH = Path(PHASE6_DB)
LIVE_STATE_PATH = PROJECT_ROOT / "data" / "state" / "phase6_live_state.json"

FALLBACK_BASKET = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD",
    "AVAX-USD", "LINK-USD", "UNI-USD", "ARB-USD", "OP-USD",
]


def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """Wilder's RSI — pure Python."""
    if len(prices) < period + 1:
        return []
    deltas = [prices[i + 1] - prices[i] for i in range(len(prices) - 1)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi_values: List[float] = []
    for i in range(period, len(deltas)):
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi_values.append(round(rsi, 2))
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    return rsi_values


def calculate_stochastic_rsi(
    prices: List[float], rsi_period: int = 14, k_period: int = 14, d_period: int = 3
) -> Tuple[List[float], List[float]]:
    """StochRSI %K / %D. Returns ([], []) if insufficient data."""
    rsi_values = calculate_rsi(prices, rsi_period)
    if len(rsi_values) < k_period:
        return [], []

    k_values: List[float] = []
    for i in range(k_period - 1, len(rsi_values)):
        window = rsi_values[i - k_period + 1 : i + 1]
        min_r = min(window)
        max_r = max(window)
        if max_r == min_r:
            k = 50.0
        else:
            k = 100.0 * (rsi_values[i] - min_r) / (max_r - min_r)
        k_values.append(round(k, 2))

    d_values: List[float] = []
    for i in range(d_period - 1, len(k_values)):
        d = sum(k_values[i - d_period + 1 : i + 1]) / d_period
        d_values.append(round(d, 2))
    return k_values, d_values


def load_basket() -> List[str]:
    try:
        pairs = load_trading_basket()
        if pairs:
            return list(pairs)
    except Exception as e:
        print(f"[WARN] load_trading_basket failed: {e}")
    return list(FALLBACK_BASKET)


def _load_history_dict() -> Dict[str, List[float]]:
    if not PRICE_HISTORY_PATH.exists():
        return {}
    try:
        data = json.loads(PRICE_HISTORY_PATH.read_text())
        h = data.get("history", data)
        if isinstance(h, dict):
            out: Dict[str, List[float]] = {}
            for k, v in h.items():
                if isinstance(v, list):
                    out[k] = [float(x) for x in v if isinstance(x, (int, float))]
            return out
    except Exception as e:
        print(f"[WARN] price_history load: {e}")
    return {}


def _save_history_dict(history: Dict[str, List[float]], max_len: int = 200) -> None:
    trimmed = {k: v[-max_len:] for k, v in history.items()}
    PRICE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "history": trimmed,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "refresh_rsi_prices",
    }
    PRICE_HISTORY_PATH.write_text(json.dumps(payload, indent=2))


def _fetch_closes(pair: str, limit: int = 100) -> List[float]:
    """Public Coinbase 15m closes; empty on failure.

    Default limit 100 so thin pairs (e.g. OP-USD) still accumulate RSI history.
    """
    try:
        from phase6.core.exchange_client import CoinbaseExchangeClient

        client = CoinbaseExchangeClient(mode="shadow")
        candles = client.get_recent_prices(pair, limit=limit, granularity="FIFTEEN_MINUTE")
        return [float(p) for p in candles if p and float(p) > 0]
    except Exception as e:
        print(f"  {pair}: candle fetch error: {e}")
        return []


def _merge_history(existing: List[float], new_closes: List[float], max_len: int = 200) -> List[float]:
    """Append a fresh candle window without collapsing flat closes (valid RSI bars).

    Only drop an exact overlapping prefix/suffix when the new window starts where
    the existing series already ends (same last price + same length tail match).
    """
    if not new_closes:
        return list(existing or [])[-max_len:]
    if not existing:
        return list(new_closes)[-max_len:]
    # Prefer full replace with longer fresh window when existing is short
    if len(existing) < 30 and len(new_closes) >= len(existing):
        return list(new_closes)[-max_len:]
    # If new window is a superset tail of existing, take new
    if len(new_closes) >= len(existing) and existing[-min(5, len(existing)) :] == new_closes[
        -min(5, len(existing)) :
    ]:
        return list(new_closes)[-max_len:]
    # Overlap: find largest k where existing[-k:] == new_closes[:k]
    max_k = min(len(existing), len(new_closes))
    best = 0
    for k in range(max_k, 0, -1):
        if existing[-k:] == new_closes[:k]:
            best = k
            break
    merged = list(existing) + list(new_closes[best:])
    return merged[-max_len:]


def _update_live_state_rsi(rsi_entries: Dict[str, Any], ts: str, merge: bool = False) -> None:
    try:
        live: Dict[str, Any] = {}
        if LIVE_STATE_PATH.exists():
            live = json.loads(LIVE_STATE_PATH.read_text())
            if not isinstance(live, dict):
                live = {}
        new_map: Dict[str, Any] = {
            p: v.get("rsi") for p, v in rsi_entries.items() if v.get("rsi") is not None
        }
        if merge:
            prev = live.get("rsi")
            existing: Dict[str, Any] = dict(prev) if isinstance(prev, dict) else {}
            existing.update(new_map)
            live["rsi"] = existing
        else:
            live["rsi"] = new_map
        live["last_rsi_update"] = ts
        live["rsi_source"] = (
            "contender_warm_merge" if merge else "decoupled_15m_refresher_stoch"
        )
        LIVE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        LIVE_STATE_PATH.write_text(json.dumps(live, indent=2))
        print(f"Live state RSI synced for {len(rsi_entries)} pairs (merge={merge})")
    except Exception as e:
        print(f"[WARN] live_state sync: {e}")


def _parse_pairs_arg(argv: List[str]) -> Optional[List[str]]:
    """Parse --pairs A,B or --pairs A --pairs B. None = full basket."""
    pairs: List[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--pairs" and i + 1 < len(argv):
            chunk = argv[i + 1]
            for part in chunk.split(","):
                p = part.strip().upper()
                if p and p not in pairs:
                    # normalize BASE-USD if bare ticker
                    if "-" not in p:
                        p = f"{p}-USD"
                    pairs.append(p)
            i += 2
            continue
        if a.startswith("--pairs="):
            chunk = a.split("=", 1)[1]
            for part in chunk.split(","):
                p = part.strip().upper()
                if p and p not in pairs:
                    if "-" not in p:
                        p = f"{p}-USD"
                    pairs.append(p)
            i += 1
            continue
        i += 1
    return pairs or None


def _load_existing_rsi_cache() -> Dict[str, Any]:
    if not RSI_CACHE_PATH.exists():
        return {}
    try:
        raw = json.loads(RSI_CACHE_PATH.read_text())
        rsi = raw.get("rsi") or {}
        return rsi if isinstance(rsi, dict) else {}
    except Exception as e:
        print(f"[WARN] existing rsi_cache load: {e}")
        return {}


def main(
    dry_run: bool = False,
    pairs: Optional[List[str]] = None,
    merge: bool = False,
) -> int:
    """
    Refresh RSI(+Stoch) for basket or an explicit pair list.

    merge=True (default when --pairs is set): write only updated keys into
    existing rsi_cache.json so a contender warm-up never wipes the live basket.
    """
    ts = datetime.now(timezone.utc).isoformat()
    subset = pairs is not None
    if merge is False and subset:
        merge = True  # safety: never clobber full cache with a shortlist write

    print(f"=== RSI + StochRSI Refresher @ {ts} ===")
    basket = list(pairs) if pairs else load_basket()
    mode = "merge-subset" if (subset or merge) else "full-basket"
    print(f"Mode: {mode}. Targets: {len(basket)} pairs -> {basket}")

    history = _load_history_dict()
    rsi_entries: Dict[str, Any] = {}
    db_rows: List[Tuple[str, str, float, str]] = []
    calls_made = 0
    errors: List[str] = []
    src_tag = "refresh_15m_contender_warm" if subset else "refresh_15m_long_stoch"

    for pair in basket:
        closes = _fetch_closes(pair, limit=100)
        if closes:
            calls_made += 1
            hist = history.get(pair, [])
            history[pair] = _merge_history(hist, closes, max_len=200)
            print(
                f"  {pair}: fetched {len(closes)} candles → hist={len(history[pair])} "
                f"(calls so far: {calls_made})"
            )
        else:
            print(f"  {pair}: no fresh candles; using persisted history only")

        prices = history.get(pair, [])[-100:]
        if len(prices) < 30:
            print(f"    -> insufficient history (n={len(prices)}); skip")
            errors.append(pair)
            continue

        rsi_list = calculate_rsi(prices, period=14)
        if not rsi_list:
            print(f"    -> RSI failed; skip")
            errors.append(pair)
            continue

        rsi_val = rsi_list[-1]
        k_list, d_list = calculate_stochastic_rsi(prices, rsi_period=14, k_period=14, d_period=3)
        stoch_k: Optional[float] = k_list[-1] if k_list else None
        stoch_d: Optional[float] = d_list[-1] if d_list else None
        if k_list and not d_list and len(k_list) >= 3:
            stoch_d = round(sum(k_list[-3:]) / 3.0, 2)

        src = (
            "15m_candles_contender_warm"
            if subset
            else (
                "15m_candles_from_history_longer_term"
                if closes
                else "price_history_fallback_longer_term"
            )
        )
        rsi_entries[pair] = {
            "rsi": rsi_val,
            "stoch_k": stoch_k,
            "stoch_d": stoch_d,
            "timestamp": ts,
            "source": src,
            "candle_count": len(prices),
            "age_minutes": 0,
            "fresh": bool(closes),
        }
        db_rows.append((ts, pair, float(rsi_val), src_tag))
        print(f"    -> RSI={rsi_val} (n={len(prices)}) StochK={stoch_k} StochD={stoch_d}")

    if dry_run:
        print("DRY-RUN: skip writes")
        print(
            f"Would write {len(rsi_entries)} pairs; stoch_ok="
            f"{sum(1 for v in rsi_entries.values() if v.get('stoch_k') is not None)}; merge={merge or subset}"
        )
        return 0

    _save_history_dict(history)

    if merge or subset:
        existing = _load_existing_rsi_cache()
        existing.update(rsi_entries)
        final_rsi = existing
        universe = sorted(set(list(existing.keys()) + basket))
        note = (
            "Merge write: contender/subset RSI warm into existing cache. "
            "Does not drop other pairs. Real 15m candles. No fabrication. No sentiment."
        )
    else:
        final_rsi = rsi_entries
        universe = basket
        note = (
            "Canonical 15m refresher: full basket + RSI + StochRSI. "
            "Real 15m candles + price_history. No fabrication. "
            "STOCH-RSI-PARALLEL trial instrumentation."
        )

    payload = {
        "timestamp": ts,
        "rsi": final_rsi,
        "calls_made": calls_made,
        "universe": universe,
        "errors": errors,
        "schema_version": 2,
        "merge_mode": bool(merge or subset),
        "updated_pairs": list(rsi_entries.keys()),
        "note": note,
    }
    RSI_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RSI_CACHE_PATH.write_text(json.dumps(payload, indent=2))
    print(f"Canonical RSI cache written to {RSI_CACHE_PATH} (entries={len(final_rsi)})")

    if rsi_entries:
        try:
            from phase6.core.indicator_snapshot import append_indicator_history

            append_indicator_history(rsi_entries, run_timestamp=ts)
            print(f"Appended indicator history ({len(rsi_entries)} pairs)")
        except Exception as e:
            print(f"[WARN] indicator history append failed: {e}")

    if db_rows and DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()
            cur.executemany(
                "INSERT OR REPLACE INTO rsi_values (ts, pair, value, source) VALUES (?, ?, ?, ?)",
                db_rows,
            )
            conn.commit()
            conn.close()
            print(f"DB rsi_values updated for {len(db_rows)} pairs")
        except Exception as e:
            print(f"[WARN] DB persist failed: {e}")

    # Live-state RSI: only patch keys we refreshed (never wipe basket RSI on subset)
    _update_live_state_rsi(rsi_entries, ts, merge=bool(merge or subset))

    stoch_n = sum(1 for v in rsi_entries.values() if v.get("stoch_k") is not None)
    print(
        f"Refresher complete. Calls: {calls_made}. Updated: {len(rsi_entries)}/{len(basket)}. "
        f"Stoch: {stoch_n}. Errors: {len(errors)}. Cache size: {len(final_rsi)}"
    )
    if subset:
        # Contender warm: success if we got any real RSI; empty is soft-fail 0 for pipeline
        if len(rsi_entries) == 0 and basket:
            print("WARN: contender warm produced no RSI")
            return 1
        print("SUCCESS: subset/contender RSI warm (merge).")
        return 0
    if len(rsi_entries) == len(basket) and stoch_n == len(basket):
        print("SUCCESS: Full basket RSI + StochRSI coverage.")
        return 0
    if len(rsi_entries) >= 6 and stoch_n >= 6:
        print("PARTIAL: core coverage OK; some pairs missing.")
        return 0
    print("WARN: coverage below minimum")
    return 1


if __name__ == "__main__":
    argv = sys.argv[1:]
    dry = "--dry-run" in argv
    pairs = _parse_pairs_arg(argv)
    merge = "--merge" in argv or pairs is not None
    raise SystemExit(main(dry_run=dry, pairs=pairs, merge=merge))
