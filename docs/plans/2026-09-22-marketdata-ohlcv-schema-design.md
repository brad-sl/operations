# Market Data / OHLCV schema design (design-first)

> **Status:** D1+D2 SHIPPED 2026-09-22 — `data/marketdata.db` + BTC 1d ingest + regime_detector port. No unpark GO. Finer grans deferred.  
> **Date:** 2026-09-22  
> **Why:** Recurring stale OHLCV / false climate park. Platform has spot snapshots + JSON piles, not a bar SSOT.  
> **Parent:** CW-1 sensor hygiene · climate/weather spine · decision-data integrity.
>
> **Shipped evidence:** live ingest 400 BTC 1d bars; `detect_regime` → `transition/climb` ~+11% from `marketdata_db` (was false `bear` −14% on fossil cache). `regime_cash_status.json` refreshed via `resolve_regime_cash` (still transition park policy — knobs unchanged). Cron `phase6-marketdata-btc-1d` 07:40 PT.

## 0. Verdict up front

| Question | Answer |
|----------|--------|
| Do we have this DB today? | **No** |
| Is `phase6.db.prices` enough? | **No** — tick/spot only (`ts,pair,price`), ~25–30k rows/day, not OHL/V bars |
| Design first? | **Yes** — this doc |
| Implement without review? | **No** — Brad + schema pass, then migrate |

---

## 1. Needs assessment (consumers → queries)

### 1.1 Functional consumers (live / near-live)

| Consumer | Granularity | Window | Pairs | Query shape | Failure mode today |
|----------|-------------|--------|-------|-------------|--------------------|
| **REGIME-CASH / climate** | **1d** | 30–90 calendar/bars | **BTC only** (anchor) | last N closes; ret%; gap_days | Frozen backtest JSON + fossil `price_cache` |
| **Climate/weather board** | 1d | 7/14/30 + long dwell | BTC | multi-horizon closes | Same |
| **Paper B / breakout+RSI** | 1d | 14–30 | BTC | highs/lows + closes | Same sensor |
| **Runner RSI path** | 15m / 1h closes | ~100 pts | basket ∪ held | recent closes series | `get_recent_prices` + RAM history (OK-ish) |
| **SL / marks / dash** | spot | now | held ∪ basket | last price + as_of | live_state / exchange |
| **Arm switch (7d tape)** | 1d or spot chain | 7d | BTC | ret 7d | Separate path (sometimes fresher) |

### 1.2 Research / shadow (batch)

| Consumer | Granularity | Window | Pairs |
|----------|-------------|--------|-------|
| Basket CF / swap shadows | 1h often | weeks–months | basket |
| Discovery / volume velocity | 1h | short | universe scrape |
| Bear ladder / hard-exit CF | 1d | months | BTC + legs |
| Long WF / MACD etc. | 1d | years | few majors |
| Breadth bakeoff | 1d | long | multi |

### 1.3 Universe drivers (who gets ingested)

| Set | Source | Size order |
|-----|--------|------------|
| **Core basket** | `load_trading_basket()` / config pairs | ~11–20 |
| **Held** | live positions (ex stables as needed) | small |
| **Tryout / thaw active** | tryout seats + latch | 0–few |
| **Research extended** | explicit job list, not default live ingest | optional |
| **Anchor** | always **BTC-USD** 1d | mandatory P0 |

**Live ingest default:** `core ∪ held ∪ tryout_active ∪ {BTC-USD}`.  
Not full Coinbase catalog.

### 1.4 Access patterns (what to optimize)

1. **Hot path A — regime:**  
   `OHLCV 1d BTC WHERE ts_open >= ? ORDER BY ts_open`  
   (+ freshness: `max(ts_open)`, gap detect)

2. **Hot path B — spot:**  
   `latest spot WHERE pair = ? AND as_of >= now - max_age`

3. **Hot path C — RSI series:**  
   `closes for pair @ gran IN (900,3600) last N bars ORDER BY ts_open`

4. **Warm — multi-pair daily panel:**  
   `pair IN (…) AND gran=86400 AND ts_open BETWEEN ? AND ?`

5. **Cold — research export:**  
   bulk range scan by pair+gran (partition/prune by time)

6. **Ops — freshness board:**  
   one row per (pair, gran): last_bar, lag, gap_tail, ingest_ok

### 1.5 Non-goals (keep out of this DB)

- Full tick L2 / order book  
- Replacing trade ledger (`trades`)  
- Sentiment primary store  
- Storing every public candle for all Coinbase products forever  

Derived indicators (RSI) may **read** bars and write feature tables — bars remain source of truth.

### 1.6 Volume / size (order of magnitude)

| Series | Rows/year/pair | 20 pairs | Notes |
|--------|----------------|----------|-------|
| 1d OHLCV | ~365 | ~7k | Tiny |
| 1h OHLCV | ~8.8k | ~175k | Fine in SQLite |
| 15m OHLCV | ~35k | ~700k | OK; retain policy |
| Spot snapshots (current `prices`) | ~25k/**day** whole book | millions/yr | **Do not** use as bar store; retain/downsample separately |

**Conclusion:** Bar store is small if scoped. Spot log is the fat table — isolate + TTL.

---

## 2. Design principles

1. **One bar fact table** — not per-feature candle copies.  
2. **Integer time + gran** — `ts_open` = bar open UTC epoch seconds; `granularity_sec` in {60,300,900,3600,21600,86400}.  
3. **Composite PK** — `(venue, pair_id, granularity_sec, ts_open)` — idempotent upsert.  
4. **FK to pair dimension** — no string soup without registry (still store `pair` text denorm for debuggability optional).  
5. **Freshness is first-class** — status table; consumers **fail closed** on stale/gap.  
6. **Feature tables reference bars by key or by (pair_id, gran, ts)** — no duplicate OHLCV.  
7. **Backtest freezes are imports**, labeled `source_run_id`, never silent live SSOT.  
8. **Spot ≠ bar** — separate latest/history spot with `as_of` + `max_age` semantics.

---

## 3. Proposed schema (SQLite-first, Postgres-ready)

> Engine: start **SQLite** file `data/marketdata.db` (or schema inside `phase6.db` under `md_*` prefix).  
> Types below use SQLite; Postgres: `TIMESTAMPTZ`, `GENERATED`, etc.

### 3.1 Dimensions

```sql
-- Venue (extensible)
CREATE TABLE md_venue (
  venue_id        INTEGER PRIMARY KEY,
  code            TEXT NOT NULL UNIQUE,      -- 'coinbase'
  name            TEXT NOT NULL
);

-- Pair registry (FK target for everything)
CREATE TABLE md_pair (
  pair_id         INTEGER PRIMARY KEY,
  venue_id        INTEGER NOT NULL REFERENCES md_venue(venue_id),
  symbol          TEXT NOT NULL,             -- 'BTC-USD'
  base            TEXT NOT NULL,             -- 'BTC'
  quote           TEXT NOT NULL,             -- 'USD'
  product_id      TEXT NOT NULL,             -- venue product id
  active_core     INTEGER NOT NULL DEFAULT 0, -- in load_trading_basket
  active_held     INTEGER NOT NULL DEFAULT 0, -- refreshed by book job
  active_tryout   INTEGER NOT NULL DEFAULT 0,
  ingest_1d       INTEGER NOT NULL DEFAULT 0,
  ingest_1h       INTEGER NOT NULL DEFAULT 0,
  ingest_15m      INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  UNIQUE (venue_id, symbol)
);

CREATE INDEX md_pair_ingest_1d ON md_pair(ingest_1d) WHERE ingest_1d = 1;
CREATE INDEX md_pair_symbol ON md_pair(symbol);
```

### 3.2 Bar fact (core SSOT)

```sql
CREATE TABLE md_ohlcv_bar (
  venue_id         INTEGER NOT NULL REFERENCES md_venue(venue_id),
  pair_id          INTEGER NOT NULL REFERENCES md_pair(pair_id),
  granularity_sec  INTEGER NOT NULL CHECK (granularity_sec IN (60,300,900,3600,21600,86400)),
  ts_open          INTEGER NOT NULL,  -- unix sec UTC, bar open
  ts_close         INTEGER NOT NULL,  -- ts_open + granularity_sec (or venue close)
  open             REAL NOT NULL,
  high             REAL NOT NULL,
  low              REAL NOT NULL,
  close            REAL NOT NULL,
  volume           REAL,              -- base volume; NULL if unknown
  trades_count     INTEGER,           -- optional
  source           TEXT NOT NULL,     -- 'coinbase_public' | 'coinbase_auth' | 'import_backtest' | 'import_long'
  quality          TEXT NOT NULL DEFAULT 'ok'
                   CHECK (quality IN ('ok','partial','gap_fill_linear','suspect','import')),
  fetched_at       TEXT NOT NULL,     -- ISO when we wrote the row
  -- Optional denorm for greppability (keep small):
  symbol           TEXT NOT NULL,     -- copy of md_pair.symbol
  PRIMARY KEY (venue_id, pair_id, granularity_sec, ts_open),
  CHECK (high >= low AND high >= open AND high >= close AND low <= open AND low <= close),
  CHECK (ts_close > ts_open),
  CHECK (open > 0 AND high > 0 AND low > 0 AND close > 0)
);

-- Hot: range scan by pair+gran+time (regime, RSI, CF)
CREATE INDEX md_ohlcv_pair_gran_ts
  ON md_ohlcv_bar (pair_id, granularity_sec, ts_open);

-- Freshness / “latest bar per series”
CREATE INDEX md_ohlcv_pair_gran_ts_desc
  ON md_ohlcv_bar (pair_id, granularity_sec, ts_open DESC);

-- Ops: find imports vs live
CREATE INDEX md_ohlcv_source ON md_ohlcv_bar (source, granularity_sec);
```

**Why PK this way:** natural idempotent upsert from Coinbase candle fetches; no surrogate id churn; FK-ready.

**Why not only `symbol` in PK:** venue + pair_id allow multi-venue later without rewrite.

### 3.3 Freshness / coverage (feature-ops table — tiny)

```sql
CREATE TABLE md_series_freshness (
  pair_id           INTEGER NOT NULL REFERENCES md_pair(pair_id),
  granularity_sec   INTEGER NOT NULL,
  last_ts_open      INTEGER,
  last_close        REAL,
  last_fetched_at   TEXT,
  bar_count         INTEGER NOT NULL DEFAULT 0,
  gap_days_tail     REAL,              -- calendar gaps near tip (1d) or bar holes
  lag_sec           INTEGER,           -- now - last bar close
  status            TEXT NOT NULL CHECK (status IN
                      ('ok','stale','gapped','missing','disabled')),
  detail            TEXT,
  updated_at        TEXT NOT NULL,
  PRIMARY KEY (pair_id, granularity_sec)
);

-- Cron / detector gate: SELECT * WHERE status != 'ok' AND pair ingest flags
CREATE INDEX md_fresh_status ON md_series_freshness (status, granularity_sec);
```

**Contract:** `detect_regime` may run only if BTC 1d `status='ok'` and `gap_days_tail <= 2` (config). Else `regime=unknown`, **do not** write confident bear/bull.

### 3.4 Spot (separate from bars)

```sql
-- Latest spot only (one row per pair) — hot path B
CREATE TABLE md_spot_latest (
  pair_id      INTEGER PRIMARY KEY REFERENCES md_pair(pair_id),
  price        REAL NOT NULL CHECK (price > 0),
  as_of        TEXT NOT NULL,          -- quote time
  source       TEXT NOT NULL,          -- 'exchange_ticker' | 'runner_mark' | ...
  fetched_at   TEXT NOT NULL,
  symbol       TEXT NOT NULL
);

-- Optional short history (TTL job deletes > N days) — NOT for 30d regime
CREATE TABLE md_spot_tick (
  pair_id      INTEGER NOT NULL REFERENCES md_pair(pair_id),
  as_of_ts     INTEGER NOT NULL,       -- unix sec
  price        REAL NOT NULL,
  source       TEXT NOT NULL,
  PRIMARY KEY (pair_id, as_of_ts, source)
);

CREATE INDEX md_spot_tick_pair_ts ON md_spot_tick (pair_id, as_of_ts DESC);
```

**Migrate note:** existing `phase6.db.prices` can feed `md_spot_tick` with retention (e.g. 7–30d) or stay as audit; **regime must not read undated price_cache JSON.**

### 3.5 Ingest control (membership-driven fetch)

```sql
CREATE TABLE md_ingest_job (
  job_id         INTEGER PRIMARY KEY,
  name           TEXT NOT NULL UNIQUE,  -- 'btc_1d_daily' | 'basket_1h' | ...
  granularity_sec INTEGER NOT NULL,
  enabled        INTEGER NOT NULL DEFAULT 1,
  interval_sec   INTEGER NOT NULL,
  last_run_at    TEXT,
  last_status    TEXT,
  last_error     TEXT
);

CREATE TABLE md_ingest_job_pair (
  job_id    INTEGER NOT NULL REFERENCES md_ingest_job(job_id),
  pair_id   INTEGER NOT NULL REFERENCES md_pair(pair_id),
  PRIMARY KEY (job_id, pair_id)
);
```

Universe refresh job sets `md_pair.active_*` and `ingest_*` from basket ∪ held ∪ tryout.

### 3.6 Feature-specific tables (derived — thin)

**Do not copy OHLCV.** Store outputs keyed to bar identity or time.

```sql
-- Example: daily BTC regime sample (measure + live write audit)
CREATE TABLE feat_regime_btc_daily (
  ts_open           INTEGER NOT NULL,  -- aligns to BTC 1d bar
  pair_id           INTEGER NOT NULL REFERENCES md_pair(pair_id),
  lookback_days     INTEGER NOT NULL,
  btc_return_pct    REAL NOT NULL,
  regime            TEXT NOT NULL,
  regime_layer      TEXT NOT NULL,
  confidence        REAL,
  gap_days_tail     REAL,
  freshness_status  TEXT NOT NULL,
  source_bar_last   INTEGER NOT NULL,  -- last ts_open used
  computed_at       TEXT NOT NULL,
  PRIMARY KEY (ts_open, lookback_days),
  FOREIGN KEY (pair_id, ts_open)  -- logical; SQLite may use WITHOUT ROWID pattern
    -- Enforce in app: bar must exist at (pair_id, 86400, ts_open)
);

-- Example: RSI point (can replace/complement rsi_values long-term)
CREATE TABLE feat_rsi (
  pair_id          INTEGER NOT NULL REFERENCES md_pair(pair_id),
  granularity_sec  INTEGER NOT NULL,
  ts_open          INTEGER NOT NULL,
  length           INTEGER NOT NULL DEFAULT 14,
  value            REAL NOT NULL,
  method           TEXT NOT NULL DEFAULT 'wilder',
  computed_at      TEXT NOT NULL,
  PRIMARY KEY (pair_id, granularity_sec, ts_open, length, method)
);

CREATE INDEX feat_rsi_pair_ts ON feat_rsi (pair_id, granularity_sec, ts_open DESC);
```

Add other feature tables the same way: **PK includes time + pair + params; FK/logic to bars; no OHLC columns.**

### 3.7 Import lineage (backtest freezes)

```sql
CREATE TABLE md_import_batch (
  batch_id      INTEGER PRIMARY KEY,
  label         TEXT NOT NULL,          -- 'backtest_hist_2025-04_2026-04'
  source_path   TEXT,
  source_kind   TEXT NOT NULL,          -- 'backtest_freeze' | 'long_json' | 'manual'
  imported_at   TEXT NOT NULL,
  row_count     INTEGER,
  notes         TEXT
);

-- Optional bridge if we need to tag bars
-- ALTER: md_ohlcv_bar already has source; batch_id can be added later NULLABLE
```

Live readers: `WHERE source NOT IN ('import_backtest') OR allow_import=1` for research only.

---

## 4. Optimal query cookbook (drives indexes)

```sql
-- A. Regime 30d closes (BTC 1d)
SELECT ts_open, close
FROM md_ohlcv_bar
WHERE pair_id = :btc AND granularity_sec = 86400
  AND ts_open >= :start
ORDER BY ts_open;

-- A2. Freshness gate
SELECT status, gap_days_tail, last_ts_open, lag_sec
FROM md_series_freshness
WHERE pair_id = :btc AND granularity_sec = 86400;

-- B. Spot with max age (app checks as_of)
SELECT price, as_of, source FROM md_spot_latest WHERE pair_id = :pid;

-- C. Last 100 hourly closes for RSI
SELECT ts_open, close FROM md_ohlcv_bar
WHERE pair_id = :pid AND granularity_sec = 3600
ORDER BY ts_open DESC LIMIT 100;

-- D. Panel for basket CF
SELECT symbol, ts_open, open, high, low, close, volume
FROM md_ohlcv_bar
WHERE granularity_sec = 3600
  AND pair_id IN (SELECT pair_id FROM md_ingest_job_pair WHERE job_id = :job)
  AND ts_open BETWEEN :a AND :b
ORDER BY pair_id, ts_open;

-- E. Gaps (1d): app-side walk; or generate series table later
```

Indexes in §3 match A–D. No need for covering index explosion at this scale.

---

## 5. Freshness / integrity rules (money-path)

| Rule | Behavior |
|------|----------|
| BTC 1d `status != ok` | `detect_regime` → `unknown`; **no** new confident park/deploy write from garbage |
| `gap_days_tail > 2` (1d) | stale/gapped; alert Telegram ops |
| Spot without `as_of` or age > max (e.g. 120s trade, 900s regime merge) | ignore |
| `price_cache_*.json` undated | **deprecated** for regime |
| Backtest JSON path | import only; not live `_load_btc_closes` |
| Merge live close | only if freshness ok **or** explicit single-day tip replace when last bar is yesterday; **never** skip-fill 19-day holes with one print |

---

## 6. Ingest topology (Fetch → write → read)

```
load_trading_basket ∪ held ∪ tryout ∪ {BTC}
        │
        ▼
 md_pair flags (ingest_1d / 1h / 15m)
        │
        ▼
 ingest jobs (cron)
   coinbase candles → UPSERT md_ohlcv_bar
                   → recompute md_series_freshness
        │
        ├── spot ticker → md_spot_latest (+ optional tick)
        │
        ▼
 ports:
   get_ohlcv(pair, gran, start, end) → rows or error(stale)
   get_spot(pair, max_age) → price|None
        │
        ├── regime_detector / climate / paper B
        ├── runner RSI (phase-in)
        └── research (read-only)
```

---

## 7. Size controls

| Table | Retention |
|-------|-----------|
| `md_ohlcv_bar` 1d | years (small) |
| `md_ohlcv_bar` 1h | 180–400d configurable |
| `md_ohlcv_bar` 15m | 30–90d (RSI needs short) |
| `md_spot_tick` | 7–30d |
| `feat_*` | per feature policy |
| Legacy `prices` | downsample or cap; stop growth without TTL |

SQLite file expected **≪ 1 GB** for scoped live universe; Postgres only if multi-tenant later.

---

## 8. Migration sketch (after schema approval)

1. Create `md_*` tables (empty).  
2. Seed `md_venue`, `md_pair` from `load_trading_basket` + BTC.  
3. Import **fresh** `data/ohlcv/BTC-USD_1d_coinbase.json` → bars `source=coinbase_public`.  
4. Optional: import long JSON as `import_*` for research.  
5. **Do not** import Sep-cutoff backtest freeze as live tip.  
6. Wire `regime_detector` to port only; delete use of undated price_cache.  
7. Cron freshness alert.  
8. Isolation tests: gap refuse, upsert idempotent, regime unknown on stale.  
9. Later: RSI/features dual-write; retire duplicate fetchers gradually.

**Out of scope for first ship:** rewrite all research loaders; multi-venue; tick DB.

---

## 9. Review checklist (schema review)

- [ ] PK `(venue, pair, gran, ts_open)` accepted  
- [ ] Spot vs bar split accepted  
- [ ] Freshness fail-closed thresholds (2d gap, spot max_age)  
- [ ] Universe = basket∪held∪tryout∪BTC — not full catalog  
- [ ] Feature tables have **no** duplicate OHLC  
- [ ] Indexes match A–D queries only (no kitchen-sink)  
- [ ] Retention caps on 15m/1h/spot_tick  
- [ ] SQLite path + backup story  
- [ ] No live unpark coupled to migrate  

---

## 10. Implementation phases (when GO)

| Phase | Deliverable | Money knobs |
|-------|-------------|-------------|
| **D0** | This design approved | none |
| **D1** | DDL + empty DB + pair seed + isolation | none |
| **D2** | BTC 1d ingest + freshness + **regime_detector port** | none (fix false bear) |
| **D3** | Basket 1d/1h ingest jobs | none |
| **D4** | Deprecate JSON/cache paths for live climate | none |
| **D5** | Feature tables RSI/regime samples as needed | none |

---

## 11. References

- Smoke: stale climate 2026-09-22 (`live_price=66812` from Apr `price_cache`; hist OHLCV ends 2026-09-02; fresh file through 2026-09-22)  
- `phase6/research/regime_detector.py` — current landmine loaders  
- `phase6/core/paths.py` — `load_trading_basket()`  
- CW-1 pack: `docs/plans/2026-09-21-climate-weather-remaining-four.md`  
- Existing: `data/phase6.db` tables `prices`, `rsi_values` (spot/derived only)

---

## 12. Open decisions for Brad

1. **New file `data/marketdata.db` vs `md_*` inside `phase6.db`?**  
   - Recommend **separate `marketdata.db`** (clear ownership, backup, less lock fight with trade writes).  
2. **First gran to productionize:** BTC **1d only** (D2) before 1h/15m? (Recommend yes.)  
3. **Retention:** 15m 60d / 1h 365d defaults OK?  
4. **GO D1+D2** after schema review, still **no unpark**?
"""
