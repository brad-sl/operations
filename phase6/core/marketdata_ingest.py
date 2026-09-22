"""OHLCV ingest into marketdata.db.

D2: BTC 1d. D3 thin: held ∪ basket ∪ tryout doors ∪ BTC/ETH/PAXG @ 1d.
Sources: Coinbase public candles; local JSON mirror for BTC only.
Never uses undated price_cache or frozen backtest tip as live SSOT.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import requests

from phase6.core.marketdata_store import (
    GRAN_1D,
    MARKETDATA_DB,
    ensure_pair,
    get_freshness,
    get_ohlcv,
    init_schema,
    mark_job_run,
    seed_core_pairs,
    upsert_bars,
    upsert_spot,
)
from phase6.core.paths import PROJECT_ROOT, STATE_DIR

PUBLIC_CANDLES = "https://api.exchange.coinbase.com/products/{product_id}/candles"
LOCAL_BTC_1D = PROJECT_ROOT / "data" / "ohlcv" / "BTC-USD_1d_coinbase.json"
LOCAL_OHLCV_DIR = PROJECT_ROOT / "data" / "ohlcv"

# Always-on climate / ballast anchors (even if not held)
ALWAYS_1D: tuple[str, ...] = ("BTC-USD", "ETH-USD", "PAXG-USD")
# Stables never need bar ingest for climate
_SKIP_SYMBOLS = frozenset(
    {
        "USD",
        "USDC",
        "USDT",
        "DAI",
        "USD-USD",
        "USDC-USD",
        "USDT-USD",
        "DAI-USD",
    }
)


def _norm_pair(p: str) -> str:
    s = str(p or "").upper().replace("/", "-").strip()
    if not s:
        return ""
    if "-" not in s:
        s = f"{s}-USD"
    return s


def _held_pairs_from_live() -> Set[str]:
    out: Set[str] = set()
    path = STATE_DIR / "phase6_live_state.json"
    if not path.exists():
        return out
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    for key in ("positions", "trading_positions"):
        rows = blob.get(key)
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            pair = _norm_pair(r.get("pair") or r.get("product_id") or r.get("symbol") or "")
            if not pair or pair in _SKIP_SYMBOLS:
                continue
            # skip dust cash-like
            try:
                qty = float(r.get("amount") or r.get("qty") or r.get("quantity") or 0)
            except (TypeError, ValueError):
                qty = 0.0
            if qty <= 0:
                continue
            out.add(pair)
    return out


def resolve_thin_universe(*, include_tryout: bool = True) -> Dict[str, Any]:
    """held ∪ basket ∪ tryout doors ∪ ALWAYS_1D. No full Coinbase firehose."""
    sources: Dict[str, Any] = {
        "always": list(ALWAYS_1D),
        "held": [],
        "basket": [],
        "tryout": [],
    }
    pairs: Set[str] = set(ALWAYS_1D)

    held = _held_pairs_from_live()
    sources["held"] = sorted(held)
    pairs |= held

    try:
        from phase6.core.paths import load_trading_basket

        basket = [_norm_pair(p) for p in load_trading_basket()]
        basket = [p for p in basket if p and p not in _SKIP_SYMBOLS]
        sources["basket"] = basket
        pairs |= set(basket)
    except Exception as e:
        sources["basket_error"] = str(e)

    if include_tryout:
        try:
            from phase6.core.regime_cash_policy import (
                load_policy,
                recovery_tryout_pairs_effective,
            )

            pol = load_policy() if callable(load_policy) else {}
            oo = (pol or {}).get("operator_override") if isinstance(pol, dict) else {}
            rec = {}
            if isinstance(oo, dict):
                rec = oo.get("recovery_soft_down_20260828") or {}
            if not isinstance(rec, dict):
                rec = {}
            try_set = recovery_tryout_pairs_effective(rec)
            try_n = sorted(
                _norm_pair(p) for p in try_set if _norm_pair(p) not in _SKIP_SYMBOLS
            )
            sources["tryout"] = try_n
            pairs |= set(try_n)
        except Exception as e:
            sources["tryout_error"] = str(e)

    pairs = {p for p in pairs if p and p not in _SKIP_SYMBOLS}
    return {
        "pairs": sorted(pairs),
        "n": len(pairs),
        "sources": sources,
        "note": "thin D3 — held∪basket∪tryout∪BTC/ETH/PAXG; no discovery firehose",
    }


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


def _load_local_pair_1d_json(symbol: str) -> List[Dict[str, Any]]:
    """Optional local mirror data/ohlcv/{SYMBOL}_1d_coinbase.json."""
    sym = _norm_pair(symbol)
    if sym == "BTC-USD":
        return load_local_btc_1d_json()
    p = LOCAL_OHLCV_DIR / f"{sym}_1d_coinbase.json"
    if not p.exists():
        # short form BTC-USD style already tried
        short = sym.split("-")[0].lower()
        alt = LOCAL_OHLCV_DIR / f"{short}_1d_coinbase.json"
        if alt.exists():
            p = alt
        else:
            return []
    try:
        blob = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(blob, dict):
        rows = blob.get("candles") or blob.get(sym) or blob.get("data") or []
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


def ingest_pair_1d(
    symbol: str,
    *,
    db_path: Optional[Path] = None,
    lookback_days: int = 400,
    prefer_api: bool = True,
    also_local_file: bool = True,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """Ingest one product 1d into marketdata.db."""
    symbol = _norm_pair(symbol)
    init_schema(db_path)
    ensure_pair(symbol, ingest_1d=1, db_path=db_path)
    report: Dict[str, Any] = {
        "symbol": symbol,
        "granularity_sec": GRAN_1D,
        "api_rows": 0,
        "local_rows": 0,
        "upserted": 0,
        "errors": [],
        "ok": False,
    }
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(lookback_days))
    sess = session or requests.Session()
    try:
        if prefer_api:
            try:
                api_bars = _coinbase_candles(
                    symbol, GRAN_1D, start=start, end=end, session=sess
                )
                n = upsert_bars(
                    api_bars,
                    symbol=symbol,
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
                        symbol,
                        float(last["close"]),
                        as_of=datetime.fromtimestamp(
                            int(last["ts_open"]) + GRAN_1D, tz=timezone.utc
                        ).isoformat(),
                        source="coinbase_public_1d_close",
                        db_path=db_path,
                    )
            except Exception as e:
                report["errors"].append(f"api:{e}")
        if also_local_file:
            local = _load_local_pair_1d_json(symbol)
            if local:
                src = "coinbase_public" if report["api_rows"] else "local_ohlcv_json"
                n = upsert_bars(
                    local,
                    symbol=symbol,
                    granularity_sec=GRAN_1D,
                    source=src,
                    quality="ok",
                    db_path=db_path,
                )
                report["local_rows"] = len(local)
                report["upserted"] += n
        fresh = get_freshness(symbol, GRAN_1D, db_path=db_path)
        report["freshness"] = fresh
        bars = get_ohlcv(symbol, GRAN_1D, db_path=db_path)
        report["bar_count"] = len(bars)
        if bars:
            report["last"] = {
                "ts_open": bars[-1]["ts_open"],
                "close": bars[-1]["close"],
            }
        report["ok"] = str(fresh.get("status")) == "ok" and len(bars) >= 30
    except Exception as e:
        report["errors"].append(str(e))
        report["ok"] = False
    return report


def ingest_thin_1d(
    *,
    db_path: Optional[Path] = None,
    lookback_days: int = 400,
    prefer_api: bool = True,
    pairs: Optional[Sequence[str]] = None,
    sleep_s: float = 0.2,
) -> Dict[str, Any]:
    """D3 thin multi-pair 1d ingest. Marks universe ingest_1d=1, fills bars."""
    init_schema(db_path)
    seed_core_pairs(db_path, mark_1d=False)
    uni = resolve_thin_universe(include_tryout=True)
    target = [_norm_pair(p) for p in (pairs or uni["pairs"])]
    target = [p for p in target if p and p not in _SKIP_SYMBOLS]
    # register flags
    for p in target:
        ensure_pair(p, ingest_1d=1, active_core=1 if p in set(ALWAYS_1D) else 0, db_path=db_path)

    sess = requests.Session()
    per: List[Dict[str, Any]] = []
    n_ok = 0
    for i, sym in enumerate(target):
        rep = ingest_pair_1d(
            sym,
            db_path=db_path,
            lookback_days=lookback_days,
            prefer_api=prefer_api,
            also_local_file=(sym == "BTC-USD"),
            session=sess,
        )
        per.append(
            {
                "symbol": sym,
                "ok": rep.get("ok"),
                "bar_count": rep.get("bar_count"),
                "api_rows": rep.get("api_rows"),
                "status": (rep.get("freshness") or {}).get("status"),
                "errors": rep.get("errors") or [],
            }
        )
        if rep.get("ok"):
            n_ok += 1
        if i + 1 < len(target):
            time.sleep(sleep_s)

    ok = n_ok >= max(1, len(target) // 2)  # majority ok; BTC must preferably be ok
    btc_ok = any(r.get("symbol") == "BTC-USD" and r.get("ok") for r in per)
    report = {
        "job": "thin_1d_daily",
        "universe": uni,
        "n_pairs": len(target),
        "n_ok": n_ok,
        "btc_ok": btc_ok,
        "ok": bool(ok and btc_ok),
        "pairs": per,
        "db_path": str(db_path or MARKETDATA_DB),
    }
    mark_job_run(
        "thin_1d_daily",
        "ok" if report["ok"] else "degraded",
        error=None if report["ok"] else f"n_ok={n_ok}/{len(target)} btc_ok={btc_ok}",
        db_path=db_path,
    )
    return report


# Back-compat alias
def ingest_btc_1d(
    *,
    db_path: Optional[Path] = None,
    lookback_days: int = 400,
    prefer_api: bool = True,
    also_local_file: bool = True,
) -> Dict[str, Any]:
    """D2 path retained: BTC only + seed."""
    init_schema(db_path)
    seed_core_pairs(db_path)
    rep = ingest_pair_1d(
        "BTC-USD",
        db_path=db_path,
        lookback_days=lookback_days,
        prefer_api=prefer_api,
        also_local_file=also_local_file,
    )
    report = {
        "job": "btc_1d_daily",
        "symbol": "BTC-USD",
        "granularity_sec": GRAN_1D,
        "db_path": str(db_path or MARKETDATA_DB),
        "api_rows": rep.get("api_rows", 0),
        "local_rows": rep.get("local_rows", 0),
        "upserted": rep.get("upserted", 0),
        "errors": list(rep.get("errors") or []),
        "freshness": rep.get("freshness"),
        "bar_count": rep.get("bar_count"),
        "first": None,
        "last": rep.get("last"),
        "ok": bool(rep.get("ok")),
    }
    bars = get_ohlcv("BTC-USD", GRAN_1D, db_path=db_path)
    if bars:
        report["first"] = {"ts_open": bars[0]["ts_open"], "close": bars[0]["close"]}
        report["last"] = {"ts_open": bars[-1]["ts_open"], "close": bars[-1]["close"]}
    mark_job_run(
        "btc_1d_daily",
        "ok" if report["ok"] else "degraded",
        error="; ".join(report["errors"]) if report["errors"] else None,
        db_path=db_path,
    )
    return report
