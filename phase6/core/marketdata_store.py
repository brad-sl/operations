"""MarketData bar store — SQLite SSOT for OHLCV (D1/D2).

Separate file: data/marketdata.db (not phase6.db trade path).
Schema allows finer grans later; D2 productionizes BTC 1d only.

Rules:
- Bars are the SSOT for regime windows; spot is separate with as_of.
- Freshness fail-closed for money-path consumers.
- Backtest freezes may be imported with source=import_*; live readers prefer live sources.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from phase6.core.paths import DATA_DIR, PROJECT_ROOT

MARKETDATA_DB = DATA_DIR / "marketdata.db"
GRAN_1D = 86400
GRAN_1H = 3600
GRAN_15M = 900
ALLOWED_GRAN = frozenset({60, 300, 900, 3600, 21600, 86400})

# Live climate gate (config knobs can override later)
MAX_GAP_DAYS_TAIL_1D = 2.0
MAX_LAG_SEC_1D = 2 * 86400 + 3600  # ~2d + slack


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ts_to_date(ts_open: int) -> date:
    return datetime.fromtimestamp(int(ts_open), tz=timezone.utc).date()


@contextmanager
def connect(db_path: Optional[Path] = None):
    path = Path(db_path) if db_path else MARKETDATA_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


DDL = """
CREATE TABLE IF NOT EXISTS md_venue (
  venue_id   INTEGER PRIMARY KEY,
  code       TEXT NOT NULL UNIQUE,
  name       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS md_pair (
  pair_id       INTEGER PRIMARY KEY,
  venue_id      INTEGER NOT NULL REFERENCES md_venue(venue_id),
  symbol        TEXT NOT NULL,
  base          TEXT NOT NULL,
  quote         TEXT NOT NULL,
  product_id    TEXT NOT NULL,
  active_core   INTEGER NOT NULL DEFAULT 0,
  active_held   INTEGER NOT NULL DEFAULT 0,
  active_tryout INTEGER NOT NULL DEFAULT 0,
  ingest_1d     INTEGER NOT NULL DEFAULT 0,
  ingest_1h     INTEGER NOT NULL DEFAULT 0,
  ingest_15m    INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  UNIQUE (venue_id, symbol)
);
CREATE INDEX IF NOT EXISTS md_pair_ingest_1d ON md_pair(ingest_1d);
CREATE INDEX IF NOT EXISTS md_pair_symbol ON md_pair(symbol);

CREATE TABLE IF NOT EXISTS md_ohlcv_bar (
  venue_id         INTEGER NOT NULL REFERENCES md_venue(venue_id),
  pair_id          INTEGER NOT NULL REFERENCES md_pair(pair_id),
  granularity_sec  INTEGER NOT NULL,
  ts_open          INTEGER NOT NULL,
  ts_close         INTEGER NOT NULL,
  open             REAL NOT NULL,
  high             REAL NOT NULL,
  low              REAL NOT NULL,
  close            REAL NOT NULL,
  volume           REAL,
  trades_count     INTEGER,
  source           TEXT NOT NULL,
  quality          TEXT NOT NULL DEFAULT 'ok',
  fetched_at       TEXT NOT NULL,
  symbol           TEXT NOT NULL,
  PRIMARY KEY (venue_id, pair_id, granularity_sec, ts_open),
  CHECK (granularity_sec IN (60,300,900,3600,21600,86400)),
  CHECK (high >= low AND high >= open AND high >= close AND low <= open AND low <= close),
  CHECK (ts_close > ts_open),
  CHECK (open > 0 AND high > 0 AND low > 0 AND close > 0)
);
CREATE INDEX IF NOT EXISTS md_ohlcv_pair_gran_ts
  ON md_ohlcv_bar (pair_id, granularity_sec, ts_open);
CREATE INDEX IF NOT EXISTS md_ohlcv_pair_gran_ts_desc
  ON md_ohlcv_bar (pair_id, granularity_sec, ts_open DESC);
CREATE INDEX IF NOT EXISTS md_ohlcv_source
  ON md_ohlcv_bar (source, granularity_sec);

CREATE TABLE IF NOT EXISTS md_series_freshness (
  pair_id           INTEGER NOT NULL REFERENCES md_pair(pair_id),
  granularity_sec   INTEGER NOT NULL,
  last_ts_open      INTEGER,
  last_close        REAL,
  last_fetched_at   TEXT,
  bar_count         INTEGER NOT NULL DEFAULT 0,
  gap_days_tail     REAL,
  lag_sec           INTEGER,
  status            TEXT NOT NULL,
  detail            TEXT,
  updated_at        TEXT NOT NULL,
  PRIMARY KEY (pair_id, granularity_sec)
);
CREATE INDEX IF NOT EXISTS md_fresh_status
  ON md_series_freshness (status, granularity_sec);

CREATE TABLE IF NOT EXISTS md_spot_latest (
  pair_id      INTEGER PRIMARY KEY REFERENCES md_pair(pair_id),
  price        REAL NOT NULL CHECK (price > 0),
  as_of        TEXT NOT NULL,
  source       TEXT NOT NULL,
  fetched_at   TEXT NOT NULL,
  symbol       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS md_spot_tick (
  pair_id      INTEGER NOT NULL REFERENCES md_pair(pair_id),
  as_of_ts     INTEGER NOT NULL,
  price        REAL NOT NULL,
  source       TEXT NOT NULL,
  PRIMARY KEY (pair_id, as_of_ts, source)
);
CREATE INDEX IF NOT EXISTS md_spot_tick_pair_ts
  ON md_spot_tick (pair_id, as_of_ts DESC);

CREATE TABLE IF NOT EXISTS md_ingest_job (
  job_id          INTEGER PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,
  granularity_sec INTEGER NOT NULL,
  enabled         INTEGER NOT NULL DEFAULT 1,
  interval_sec    INTEGER NOT NULL,
  last_run_at     TEXT,
  last_status     TEXT,
  last_error      TEXT
);

CREATE TABLE IF NOT EXISTS md_ingest_job_pair (
  job_id  INTEGER NOT NULL REFERENCES md_ingest_job(job_id),
  pair_id INTEGER NOT NULL REFERENCES md_pair(pair_id),
  PRIMARY KEY (job_id, pair_id)
);

CREATE TABLE IF NOT EXISTS md_import_batch (
  batch_id    INTEGER PRIMARY KEY,
  label       TEXT NOT NULL,
  source_path TEXT,
  source_kind TEXT NOT NULL,
  imported_at TEXT NOT NULL,
  row_count   INTEGER,
  notes       TEXT
);
"""


def init_schema(db_path: Optional[Path] = None) -> Path:
    path = Path(db_path) if db_path else MARKETDATA_DB
    with connect(path) as conn:
        conn.executescript(DDL)
        # seed venue
        conn.execute(
            "INSERT OR IGNORE INTO md_venue (venue_id, code, name) VALUES (1, 'coinbase', 'Coinbase Exchange')"
        )
        # default BTC 1d job
        conn.execute(
            """
            INSERT OR IGNORE INTO md_ingest_job
              (job_id, name, granularity_sec, enabled, interval_sec)
            VALUES (1, 'btc_1d_daily', 86400, 1, 86400)
            """
        )
    return path


def ensure_pair(
    symbol: str,
    *,
    venue_code: str = "coinbase",
    ingest_1d: int = 0,
    ingest_1h: int = 0,
    ingest_15m: int = 0,
    active_core: int = 0,
    db_path: Optional[Path] = None,
) -> int:
    symbol = str(symbol).upper().replace("/", "-")
    if "-" not in symbol:
        symbol = f"{symbol}-USD"
    base, quote = symbol.split("-", 1)
    now = _now_iso()
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT venue_id FROM md_venue WHERE code = ?", (venue_code,)
        ).fetchone()
        if not row:
            raise RuntimeError(f"unknown venue {venue_code}")
        venue_id = int(row["venue_id"])
        existing = conn.execute(
            "SELECT pair_id FROM md_pair WHERE venue_id = ? AND symbol = ?",
            (venue_id, symbol),
        ).fetchone()
        if existing:
            pid = int(existing["pair_id"])
            conn.execute(
                """
                UPDATE md_pair SET
                  ingest_1d = MAX(ingest_1d, ?),
                  ingest_1h = MAX(ingest_1h, ?),
                  ingest_15m = MAX(ingest_15m, ?),
                  active_core = MAX(active_core, ?),
                  updated_at = ?
                WHERE pair_id = ?
                """,
                (ingest_1d, ingest_1h, ingest_15m, active_core, now, pid),
            )
            return pid
        cur = conn.execute(
            """
            INSERT INTO md_pair (
              venue_id, symbol, base, quote, product_id,
              active_core, ingest_1d, ingest_1h, ingest_15m,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                venue_id,
                symbol,
                base,
                quote,
                symbol,
                active_core,
                ingest_1d,
                ingest_1h,
                ingest_15m,
                now,
                now,
            ),
        )
        if cur.lastrowid is None:
            raise RuntimeError(f"failed to insert pair {symbol}")
        pid = int(cur.lastrowid)
        # attach to btc job if BTC 1d
        if symbol == "BTC-USD" and ingest_1d:
            conn.execute(
                "INSERT OR IGNORE INTO md_ingest_job_pair (job_id, pair_id) VALUES (1, ?)",
                (pid,),
            )
        return pid


def seed_core_pairs(db_path: Optional[Path] = None) -> List[str]:
    """Seed basket pairs; mark BTC for 1d ingest (D2)."""
    init_schema(db_path)
    try:
        from phase6.core.paths import load_trading_basket

        basket = list(load_trading_basket())
    except Exception:
        basket = [
            "BTC-USD",
            "ETH-USD",
            "SOL-USD",
            "XRP-USD",
            "DOGE-USD",
            "ADA-USD",
            "AVAX-USD",
            "LINK-USD",
            "UNI-USD",
            "ARB-USD",
            "OP-USD",
        ]
    if "BTC-USD" not in basket:
        basket = ["BTC-USD"] + basket
    out = []
    for sym in basket:
        is_btc = sym.upper().replace("/", "-") in ("BTC-USD", "BTC")
        ensure_pair(
            sym,
            ingest_1d=1 if is_btc else 0,
            active_core=1,
            db_path=db_path,
        )
        out.append(sym)
    return out


def upsert_bars(
    bars: Sequence[Dict[str, Any]],
    *,
    symbol: str,
    granularity_sec: int,
    source: str,
    quality: str = "ok",
    db_path: Optional[Path] = None,
) -> int:
    """Upsert OHLCV bars. Each bar needs ts_open (int) or time/timestamp + ohlcv fields."""
    if granularity_sec not in ALLOWED_GRAN:
        raise ValueError(f"granularity_sec {granularity_sec} not allowed")
    init_schema(db_path)
    pair_id = ensure_pair(symbol, ingest_1d=1 if granularity_sec == GRAN_1D else 0, db_path=db_path)
    with connect(db_path) as conn:
        venue = conn.execute(
            "SELECT venue_id FROM md_pair WHERE pair_id = ?", (pair_id,)
        ).fetchone()
        venue_id = int(venue["venue_id"])
        symbol_n = conn.execute(
            "SELECT symbol FROM md_pair WHERE pair_id = ?", (pair_id,)
        ).fetchone()["symbol"]
        now = _now_iso()
        n = 0
        for b in bars:
            ts_open = b.get("ts_open")
            if ts_open is None:
                raw = b.get("time") or b.get("timestamp") or b.get("ts")
                if raw is None:
                    continue
                if isinstance(raw, (int, float)):
                    ts_open = int(raw)
                    # ms?
                    if ts_open > 10_000_000_000:
                        ts_open //= 1000
                else:
                    s = str(raw).replace("Z", "+00:00")
                    try:
                        dt = datetime.fromisoformat(s)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        ts_open = int(dt.timestamp())
                    except Exception:
                        continue
            # align daily bars to UTC midnight when near midnight
            if granularity_sec == GRAN_1D:
                d = datetime.fromtimestamp(ts_open, tz=timezone.utc).date()
                ts_open = int(
                    datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()
                )
            try:
                o = float(b["open"])
                h = float(b["high"])
                l = float(b["low"])
                c = float(b["close"])
            except (KeyError, TypeError, ValueError):
                continue
            if min(o, h, l, c) <= 0:
                continue
            # fix crossed candles lightly
            h = max(h, o, c, l)
            l = min(l, o, c, h)
            vol = b.get("volume")
            try:
                vol_f = float(vol) if vol is not None else None
            except (TypeError, ValueError):
                vol_f = None
            ts_close = int(ts_open) + int(granularity_sec)
            conn.execute(
                """
                INSERT INTO md_ohlcv_bar (
                  venue_id, pair_id, granularity_sec, ts_open, ts_close,
                  open, high, low, close, volume, source, quality, fetched_at, symbol
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(venue_id, pair_id, granularity_sec, ts_open) DO UPDATE SET
                  open=excluded.open,
                  high=excluded.high,
                  low=excluded.low,
                  close=excluded.close,
                  volume=COALESCE(excluded.volume, md_ohlcv_bar.volume),
                  source=excluded.source,
                  quality=excluded.quality,
                  fetched_at=excluded.fetched_at
                """,
                (
                    venue_id,
                    pair_id,
                    int(granularity_sec),
                    int(ts_open),
                    ts_close,
                    o,
                    h,
                    l,
                    c,
                    vol_f,
                    source,
                    quality,
                    now,
                    symbol_n,
                ),
            )
            n += 1
    recompute_freshness(symbol, granularity_sec, db_path=db_path)
    return n


def recompute_freshness(
    symbol: str,
    granularity_sec: int,
    *,
    db_path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    symbol = str(symbol).upper().replace("/", "-")
    now = now or datetime.now(timezone.utc)
    with connect(db_path) as conn:
        pair = conn.execute(
            "SELECT pair_id FROM md_pair WHERE symbol = ?", (symbol,)
        ).fetchone()
        if not pair:
            return {"status": "missing", "detail": "pair not registered"}
        pair_id = int(pair["pair_id"])
        rows = conn.execute(
            """
            SELECT ts_open, close, fetched_at FROM md_ohlcv_bar
            WHERE pair_id = ? AND granularity_sec = ?
            ORDER BY ts_open ASC
            """,
            (pair_id, int(granularity_sec)),
        ).fetchall()
        if not rows:
            payload = {
                "pair_id": pair_id,
                "granularity_sec": granularity_sec,
                "last_ts_open": None,
                "last_close": None,
                "last_fetched_at": None,
                "bar_count": 0,
                "gap_days_tail": None,
                "lag_sec": None,
                "status": "missing",
                "detail": "no bars",
                "updated_at": _now_iso(),
            }
        else:
            last_ts = int(rows[-1]["ts_open"])
            last_close = float(rows[-1]["close"])
            last_fetched = rows[-1]["fetched_at"]
            # gap near tip: for 1d, calendar days between consecutive last bars
            gap_tail = 0.0
            if granularity_sec == GRAN_1D and len(rows) >= 2:
                # scan last 40 bars for max consecutive calendar gap
                gaps = []
                for a, b in zip(rows[-40:], rows[-39:]):
                    da = _ts_to_date(int(a["ts_open"]))
                    db_ = _ts_to_date(int(b["ts_open"]))
                    gaps.append(max(0, (db_ - da).days - 1))
                gap_tail = float(max(gaps) if gaps else 0)
                # also lag from last bar to today
                lag_cal = (now.date() - _ts_to_date(last_ts)).days
                if lag_cal > 1:
                    gap_tail = max(gap_tail, float(lag_cal - 1))
            elif len(rows) >= 2:
                expected = granularity_sec
                holes = []
                for a, b in zip(rows[-200:], rows[-199:]):
                    delta = int(b["ts_open"]) - int(a["ts_open"])
                    if delta > expected * 1.5:
                        holes.append(delta / expected - 1.0)
                gap_tail = float(max(holes) if holes else 0.0)
            bar_close_ts = last_ts + granularity_sec
            lag_sec = int(now.timestamp()) - bar_close_ts
            # status
            status = "ok"
            detail = "ok"
            if granularity_sec == GRAN_1D:
                if gap_tail > MAX_GAP_DAYS_TAIL_1D:
                    status = "gapped"
                    detail = f"gap_days_tail={gap_tail}"
                elif lag_sec > MAX_LAG_SEC_1D:
                    status = "stale"
                    detail = f"lag_sec={lag_sec}"
            else:
                if gap_tail > 3:
                    status = "gapped"
                    detail = f"bar_holes~{gap_tail}"
                elif lag_sec > granularity_sec * 3:
                    status = "stale"
                    detail = f"lag_sec={lag_sec}"
            payload = {
                "pair_id": pair_id,
                "granularity_sec": granularity_sec,
                "last_ts_open": last_ts,
                "last_close": last_close,
                "last_fetched_at": last_fetched,
                "bar_count": len(rows),
                "gap_days_tail": gap_tail,
                "lag_sec": lag_sec,
                "status": status,
                "detail": detail,
                "updated_at": _now_iso(),
            }
        conn.execute(
            """
            INSERT INTO md_series_freshness (
              pair_id, granularity_sec, last_ts_open, last_close, last_fetched_at,
              bar_count, gap_days_tail, lag_sec, status, detail, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pair_id, granularity_sec) DO UPDATE SET
              last_ts_open=excluded.last_ts_open,
              last_close=excluded.last_close,
              last_fetched_at=excluded.last_fetched_at,
              bar_count=excluded.bar_count,
              gap_days_tail=excluded.gap_days_tail,
              lag_sec=excluded.lag_sec,
              status=excluded.status,
              detail=excluded.detail,
              updated_at=excluded.updated_at
            """,
            (
                payload["pair_id"],
                payload["granularity_sec"],
                payload["last_ts_open"],
                payload["last_close"],
                payload["last_fetched_at"],
                payload["bar_count"],
                payload["gap_days_tail"],
                payload["lag_sec"],
                payload["status"],
                payload["detail"],
                payload["updated_at"],
            ),
        )
        return payload


def get_freshness(
    symbol: str,
    granularity_sec: int,
    *,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    symbol = str(symbol).upper().replace("/", "-")
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT f.* FROM md_series_freshness f
            JOIN md_pair p ON p.pair_id = f.pair_id
            WHERE p.symbol = ? AND f.granularity_sec = ?
            """,
            (symbol, int(granularity_sec)),
        ).fetchone()
        if not row:
            return {"status": "missing", "symbol": symbol, "granularity_sec": granularity_sec}
        return dict(row) | {"symbol": symbol}


def freshness_ok_for_regime(fresh: Dict[str, Any]) -> bool:
    if not fresh:
        return False
    if str(fresh.get("status") or "") != "ok":
        return False
    gap = fresh.get("gap_days_tail")
    if gap is not None and float(gap) > MAX_GAP_DAYS_TAIL_1D:
        return False
    return True


def get_ohlcv(
    symbol: str,
    granularity_sec: int,
    *,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
    limit: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    symbol = str(symbol).upper().replace("/", "-")
    with connect(db_path) as conn:
        pair = conn.execute(
            "SELECT pair_id FROM md_pair WHERE symbol = ?", (symbol,)
        ).fetchone()
        if not pair:
            return []
        pair_id = int(pair["pair_id"])
        sql = [
            "SELECT ts_open, ts_close, open, high, low, close, volume, source, quality, symbol",
            "FROM md_ohlcv_bar WHERE pair_id = ? AND granularity_sec = ?",
        ]
        args: List[Any] = [pair_id, int(granularity_sec)]
        if start_ts is not None:
            sql.append("AND ts_open >= ?")
            args.append(int(start_ts))
        if end_ts is not None:
            sql.append("AND ts_open <= ?")
            args.append(int(end_ts))
        sql.append("ORDER BY ts_open ASC")
        if limit is not None and start_ts is None:
            # last N: use subquery
            q = f"""
            SELECT * FROM (
              SELECT ts_open, ts_close, open, high, low, close, volume, source, quality, symbol
              FROM md_ohlcv_bar WHERE pair_id = ? AND granularity_sec = ?
              ORDER BY ts_open DESC LIMIT ?
            ) ORDER BY ts_open ASC
            """
            rows = conn.execute(q, (pair_id, int(granularity_sec), int(limit))).fetchall()
        else:
            rows = conn.execute(" ".join(sql), args).fetchall()
        return [dict(r) for r in rows]


def get_btc_daily_closes(
    *,
    db_path: Optional[Path] = None,
    min_bars: int = 5,
) -> Tuple[List[Tuple[date, float]], Dict[str, Any]]:
    """Port used by regime_detector — closes + freshness meta."""
    fresh = get_freshness("BTC-USD", GRAN_1D, db_path=db_path)
    bars = get_ohlcv("BTC-USD", GRAN_1D, db_path=db_path)
    closes: List[Tuple[date, float]] = [
        (_ts_to_date(int(b["ts_open"])), float(b["close"])) for b in bars
    ]
    meta = {
        "source": "marketdata_db",
        "db_path": str(db_path or MARKETDATA_DB),
        "freshness": fresh,
        "bar_count": len(closes),
        "fresh_ok": freshness_ok_for_regime(fresh) and len(closes) >= min_bars,
        "last_bar": closes[-1][0].isoformat() if closes else None,
        "last_close": closes[-1][1] if closes else None,
    }
    return closes, meta


def upsert_spot(
    symbol: str,
    price: float,
    *,
    as_of: Optional[str] = None,
    source: str = "manual",
    db_path: Optional[Path] = None,
) -> None:
    if price <= 0:
        return
    init_schema(db_path)
    pair_id = ensure_pair(symbol, db_path=db_path)
    as_of = as_of or _now_iso()
    now = _now_iso()
    try:
        as_of_ts = int(datetime.fromisoformat(as_of.replace("Z", "+00:00")).timestamp())
    except Exception:
        as_of_ts = int(datetime.now(timezone.utc).timestamp())
    with connect(db_path) as conn:
        sym = conn.execute(
            "SELECT symbol FROM md_pair WHERE pair_id = ?", (pair_id,)
        ).fetchone()["symbol"]
        conn.execute(
            """
            INSERT INTO md_spot_latest (pair_id, price, as_of, source, fetched_at, symbol)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(pair_id) DO UPDATE SET
              price=excluded.price, as_of=excluded.as_of, source=excluded.source,
              fetched_at=excluded.fetched_at, symbol=excluded.symbol
            """,
            (pair_id, float(price), as_of, source, now, sym),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO md_spot_tick (pair_id, as_of_ts, price, source)
            VALUES (?, ?, ?, ?)
            """,
            (pair_id, as_of_ts, float(price), source),
        )


def get_spot(
    symbol: str,
    *,
    max_age_sec: int = 900,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    symbol = str(symbol).upper().replace("/", "-")
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT s.price, s.as_of, s.source, s.fetched_at, p.symbol
            FROM md_spot_latest s
            JOIN md_pair p ON p.pair_id = s.pair_id
            WHERE p.symbol = ?
            """,
            (symbol,),
        ).fetchone()
        if not row:
            return None
        try:
            as_of = datetime.fromisoformat(str(row["as_of"]).replace("Z", "+00:00"))
            if as_of.tzinfo is None:
                as_of = as_of.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - as_of).total_seconds()
        except Exception:
            return None  # undated → refuse
        if age > max_age_sec:
            return None
        return {
            "price": float(row["price"]),
            "as_of": row["as_of"],
            "source": row["source"],
            "age_sec": age,
            "symbol": row["symbol"],
        }


def mark_job_run(
    name: str,
    status: str,
    error: Optional[str] = None,
    *,
    db_path: Optional[Path] = None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE md_ingest_job
            SET last_run_at = ?, last_status = ?, last_error = ?
            WHERE name = ?
            """,
            (_now_iso(), status, error, name),
        )


def db_stats(db_path: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(db_path) if db_path else MARKETDATA_DB
    if not path.exists():
        return {"exists": False, "path": str(path)}
    with connect(path) as conn:
        bars = conn.execute("SELECT COUNT(*) c FROM md_ohlcv_bar").fetchone()["c"]
        pairs = conn.execute("SELECT COUNT(*) c FROM md_pair").fetchone()["c"]
        fresh = [
            dict(r)
            for r in conn.execute(
                """
                SELECT p.symbol, f.granularity_sec, f.status, f.bar_count,
                       f.gap_days_tail, f.lag_sec, f.last_ts_open, f.last_close
                FROM md_series_freshness f
                JOIN md_pair p ON p.pair_id = f.pair_id
                """
            ).fetchall()
        ]
    return {
        "exists": True,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "pairs": pairs,
        "bars": bars,
        "freshness": fresh,
    }
