# PHASE 6 FABLE 5 REVIEW — BATCH 2 ANALYSIS

**Auditor note on continuity:** Batch 0/1 finding texts are not reproduced in this feed; I am tracking P6-101…P6-114 by the descriptions restated in your manifest. Where a prior finding's full definition wasn't restated (P6-102, P6-103, P6-107), my status calls below are explicitly "unchanged / no Batch-2 evidence" rather than fabricated closure.

---

## 1. UPDATED TOP RISKS (Batch 0 + 1 + 2)

1. **Stop-loss orders will be rejected or mispriced for sub-dollar assets (XRP, DOGE)** — wrapper hardcodes `:.2f` price formatting (NEW P6-115). 2 of 5 universe pairs effectively have **no stop protection**. This is now the top live-safety risk, ahead of P6-101.
2. **Order reconciliation is impossible as written** — `get_orders()` hits a wrong/nonexistent endpoint and the JWT `uri` claim includes the query string (NEW P6-117); the wrapper has **no cancel or get-order-status method at all** (NEW P6-118). This hard-blocks P6-105, P6-113, and P6-114.
3. **Canonical sentiment writer produces fabricated "fresh" neutral data** — `getattr(run, "output", {})` is wrong for the Apify client, so every run yields 0.0 scores with a fresh timestamp; the error path does the same (NEW P6-121). The live cache on disk is in a *different legacy schema* with ADA-USD and tz-naive timestamps (NEW P6-122). P6-108 is therefore **worse than assessed in Batch 1**.
4. **P6-101 (holdings error → Fresh Start)** — runner gate is the correct tri-state pattern, but closure is still blocked by unseen `LivePortfolioManager.has_open_positions()` / `exchange_client.get_holdings()`. The same error-vs-zero conflation exists *un-gated* at live init via `get_account_balance("USD")` (NEW P6-125).
5. **Ambiguous order failure → duplicate orders** — fresh `client_order_id` per attempt, 10s timeout, no post-timeout lookup (NEW P6-119).
6. **P6-114 confirmed open** — suspended-order snapshots and `last_rebalance_time` are in-memory only; a restart mid-suspension permanently loses stop coverage, and the wrapper can't even cancel/list to recover.
7. **Withdrawal reserve not visible anywhere in the planning path** — `allocation_engine.rebalance_plan` has no reserve concept; `enforce_withdrawal_reserve` is imported but usage not shown. ~$250 reserve compliance remains unverified.
8. **Inverse-vol bounds are mathematically infeasible for the fixed 5-pair universe** (max 5×0.15 = 0.75 < 1.0; renormalization silently violates the cap) (NEW P6-123).

---

## 2. NEW DETAILED FINDINGS

---

**ID:** P6-115
**Title:** Hardcoded `:.2f` price formatting breaks stop-limit and limit orders for sub-dollar assets
**Category:** Order Execution / Risk Controls
**Priority:** P0
**Severity:** Critical
**Evidence:** `coinbase_wrapper_FIXED.py` — `place_stop_limit_sell`: `"limit_price": f"{limit_price:.2f}", "stop_price": f"{stop_price:.2f}"`; same in `place_limit_buy`. Universe includes XRP-USD and DOGE-USD whose `quote_increment` is finer than $0.01 and whose prices are sub-dollar. A DOGE stop at $0.0850 serializes as `"0.09"` or `"0.08"`; depending on increment validation Coinbase rejects with `INVALID_PRICE_PRECISION` or accepts a stop ~6% away from intent.
**Impact:** Native stop-loss protection silently fails or is grossly mispriced on 2 of 5 universe pairs. In live mode, positions run unprotected — this defeats the StopLossManager/Coordinator design entirely for those pairs.
**Recommended Fix:** Fetch `/api/v3/brokerage/products/{product_id}` metadata once (cache it); quantize `stop_price`/`limit_price` to `quote_increment` and `base_size` to `base_increment` using `Decimal` with `ROUND_DOWN` (sells) / appropriate direction. Reject (fail loud) if quantized size/price is zero.
**Effort:** 0.5–1 day incl. tests against product metadata fixtures.
**Dependencies:** None (wrapper-local). Unblocks P6-105 partially.
**Backlog:** No — pre-live blocker.

---

**ID:** P6-116
**Title:** `base_size` formatted to fixed 8dp without quantization to product `base_increment`
**Category:** Order Execution
**Priority:** P1
**Severity:** High
**Evidence:** `f"{qty:.8f}"` in `place_market_buy/sell`, `place_limit_buy`, `place_stop_limit_sell`. Products have differing `base_increment` (DOGE/XRP increments are far coarser than 1e-8).
**Impact:** Rejected orders (`INVALID_SIZE`) on rebalance and stop placement; partial/blocked rebalances; sticky-rebalance loop retries indefinitely against a deterministic rejection.
**Recommended Fix:** Same product-metadata quantization layer as P6-115; share one `quantize_order(product_id, qty, price)` helper.
**Effort:** Folded into P6-115 fix.
**Dependencies:** P6-115.
**Backlog:** No.

---

**ID:** P6-117
**Title:** `get_orders()` uses wrong endpoint and JWT `uri` claim includes query string → reconciliation always fails
**Category:** Exchange Integration
**Priority:** P1
**Severity:** Critical
**Evidence:** `get_orders` requests `/api/v3/brokerage/orders/batch?order_status=...`. The Advanced Trade list-orders endpoint is `/api/v3/brokerage/orders/historical/batch`. Additionally, the full path *including query string* is passed into `_generate_jwt`, and the CDP JWT `uri` claim must be `METHOD host/path` **without** query parameters → 401 even if the path were correct.
**Impact:** Any open-order audit, stop reconciliation, or orphan detection (the backbone of P6-105/113/114 remediation) returns errors. Combined with the silent error-dict return from `_request`, callers may interpret the error payload as "no open orders" — same error-vs-empty antipattern as P6-101, applied to orders.
**Recommended Fix:** (a) Strip query string before JWT generation (`path.split('?')[0]`); (b) correct endpoint to `/orders/historical/batch`; (c) make `_request` return a typed result or raise, never an ambiguous `{'error': ...}` dict that walks like a success payload.
**Effort:** 0.5 day + one authenticated integration smoke test (read-only, safe).
**Dependencies:** None. Blocks closure of P6-105, P6-113, P6-114.
**Backlog:** No.

---

**ID:** P6-118
**Title:** Wrapper lacks cancel/get-order/fill retrieval; inconsistent return-key schema across methods; fills/fees invisible
**Category:** Exchange Integration / Accounting
**Priority:** P1
**Severity:** High
**Evidence:** No `cancel_order`, `cancel_orders` (batch), or `get_order(order_id)` exists. All placements return `status: 'PENDING'` with no fill price/size/fees (market IOC orders fill or cancel immediately — actual fill is knowable but never fetched). Return-key drift: `place_market_buy/sell` and `place_limit_buy` return `{'id': ...}` while `place_stop_limit_sell` returns `{'order_id': ...}` — consumers (OrderExecutor, StopLossManager/Coordinator) must branch per method or silently read `None`. The `OrderResponse` dataclass is defined and never used.
**Impact:** (a) CR-03/P6-114 rollback cannot cancel suspended stops; (b) trade ledger and portfolio accounting cannot record real fill prices/fees → P&L drift, reserve drift; (c) key drift is exactly the schema-mismatch class flagged in P6-105/113, now confirmed at the source.
**Recommended Fix:** Add `get_order(order_id)` (`/orders/historical/{order_id}`), `cancel_orders(order_ids)` (`/orders/batch_cancel`), and a fill-fetch (`/orders/historical/fills?order_id=`). Standardize *all* placement returns on the unused `OrderResponse` dataclass (single schema: `success, order_id, status, error, raw`). Poll market IOC orders once post-placement for `average_filled_price`, `filled_size`, `total_fees` and feed the ledger.
**Effort:** 1.5–2 days.
**Dependencies:** P6-117 (correct endpoints/JWT). Blocks P6-105, P6-113, P6-114.
**Backlog:** No.

---

**ID:** P6-119
**Title:** Ambiguous failures (timeout/5xx after acceptance) reported as FAILED with no idempotent retry path → duplicate orders
**Category:** Order Execution / Idempotency
**Priority:** P1
**Severity:** High
**Evidence:** `client_order_id = secrets.token_hex(16)` regenerated per call; `timeout=10`; on `RequestException` the wrapper returns `FAILED`. If Coinbase accepted the order but the response was lost, the order is live while the bot believes it failed; any retry uses a new `client_order_id`, defeating exchange-side dedupe.
**Impact:** Duplicate buys/sells in live mode → reserve breach, double exposure, phantom positions vs. ledger.
**Recommended Fix:** Caller-supplied deterministic `client_order_id` (e.g., `f"{cycle_id}-{pair}-{side}"`); on ambiguous failure, query orders by `client_order_id` before any retry; persist the attempted COID durably *before* the POST (write-ahead intent record).
**Effort:** 1 day (with P6-118's `get_order`).
**Dependencies:** P6-118.
**Backlog:** No.

---

**ID:** P6-120
**Title:** Stop-limit `client_order_id` uses second-granularity timestamp → collision on same-second re-placement
**Category:** Order Execution
**Priority:** P3
**Severity:** Low
**Evidence:** `client_order_id = f"sl-{product_id}-{int(time.time())}"`. Suspend→restore flows (P6-114) can re-place within the same second; Coinbase rejects duplicate COIDs.
**Recommended Fix:** Subsume under P6-119's deterministic-COID scheme with a monotonic component.
**Effort:** Trivial within P6-119.
**Dependencies:** P6-119.
**Backlog:** Yes (folds into P6-119).

---

**ID:** P6-121
**Title:** Canonical sentiment writer fabricates fresh neutral data: Apify results never retrieved; error path stamps 0.0 with current timestamp
**Category:** Data Integrity (Real-Data-Only constraint violation)
**Priority:** P1
**Severity:** Critical
**Evidence:** `run_full_sentiment_v3.py` — `run = client.actor(ACTOR_ID).call(...)` returns a run-info **dict**; `getattr(run, "output", {})` is always `{}` (dicts have no `.output` attribute; even if it did, actor results live in the dataset: `client.dataset(run["defaultDatasetId"]).iterate_items()`). Result: `items = []` always → `aggregate_sentiment` returns `(0.0, 0)` for every pair, written with a *fresh* timestamp. The `except` path likewise writes `{"sentiment": 0.0, "posts": 0, timestamp=now}`. Also `valid_scores` is computed and never used (dead intent).
**Impact:** Every consumer's freshness check passes while the data is fabricated neutral. Sentiment-adjusted weights silently degenerate to no-op or wrong baseline; P6-108's "baseline fabrication" risk is realized at the source, not just the reader. Violates the standing "real data only" constraint.
**Recommended Fix:** Retrieve from the run's default dataset; treat `posts == 0` as **failure**, not data — on failure either preserve the prior cached entry (with its old timestamp) or write an explicit `"status": "error"` marker; readers must require `posts >= N` and fresh timestamp jointly. Fix or remove `valid_scores`.
**Effort:** 0.5–1 day + one real actor run as verification.
**Dependencies:** None. Blocks P6-108 closure.
**Backlog:** No.

---

**ID:** P6-122
**Title:** Live `sentiment_cache.json` is in a divergent legacy schema (per-pair objects, ADA-USD, tz-naive timestamps) — v3 writer/reader schema mismatch
**Category:** Data Integrity / Schema
**Priority:** P1
**Severity:** High
**Evidence:** v3 writer emits `{timestamp, source, sentiment:{pair:score}, meta}`. The on-disk snapshot is `{pair: {sentiment, timestamp}}`, includes `ADA-USD` (not in `PAIRS`), and timestamps are tz-naive (`"2026-06-11T02:00:01.891784"`) while v3 writes tz-aware UTC ISO. Conclusions: (a) the canonical writer is not what produced the live cache — a legacy writer is still active or v3 never ran; (b) `_load_sentiment` in HybridRebalancer must currently parse one schema and will mis-read the other; (c) comparing tz-aware `datetime.now(timezone.utc)` against naive cache timestamps raises `TypeError` or yields wrong staleness math.
**Impact:** Staleness check (P6-108) is unreliable regardless of reader logic until the writer pipeline is unified; silent fallback paths likely return neutral/stale values as live.
**Recommended Fix:** Single versioned schema (`"schema_version": 3`) with tz-aware timestamps; reader rejects unknown versions loudly; kill/cron-disable the legacy writer; one migration of the existing file; add a `make sentiment-verify` check comparing writer output schema to reader expectations.
**Effort:** 0.5 day + locating the legacy writer (Batch 3).
**Dependencies:** P6-121; HybridRebalancer `_load_sentiment` source (requested below).
**Backlog:** No.

---

**ID:** P6-123
**Title:** `compute_inverse_vol_allocations` bounds infeasible for 5-asset universe — max_weight cap silently violated after renormalization
**Category:** Allocation Logic
**Priority:** P2
**Severity:** Medium
**Evidence:** Defaults `min_weight=0.04, max_weight=0.15`. With the fixed 5-pair universe, Σmax = 0.75 < 1.0, so post-clip renormalization (`v/total`) inflates weights to up to 0.20, breaching the documented cap. No iterative water-filling; bounds are advisory at best.
**Impact:** Concentration limits implied by config are not actually enforced; risk parity intent quietly distorted toward the lowest-vol asset (typically BTC).
**Recommended Fix:** Validate feasibility (`n*max_weight >= 1.0 >= n*min_weight`) and fail loud on config error; implement iterative clipping (fix capped assets, renormalize the remainder) so bounds hold post-normalization.
**Effort:** 0.5 day + unit tests for 5-asset edge.
**Dependencies:** Config values from `trading_config_phase6.json` (Batch 3) to confirm real bounds in use.
**Backlog:** No (small, but touches live weights).

---

**ID:** P6-124
**Title:** `rebalance_plan` schema drift vs docstring, silent 25% caps, no reserve awareness, dict-input crash path
**Category:** Allocation Logic / Contract Integrity
**Priority:** P2
**Severity:** Medium
**Evidence:** Docstring promises `{from_coin, to_coin, amount_usd}`; code emits `{pair, action, usd_amount}`. Each move silently clamped to `total_capital * 0.25` with no residual carry or logging. No concept of the ~$250 withdrawal reserve — buys can be planned against reserved cash. `cur_val.get("usd_value", cur_val)` returns the dict itself if `usd_value` missing → `float(dict)` TypeError.
**Impact:** Consumers coded to the docstring break; large rebalances permanently under-execute; reserve enforcement depends entirely on unseen downstream code; malformed holdings dicts crash planning.
**Recommended Fix:** Align docstring + emit one schema; surface clamped residuals (return `unexecuted_usd`); accept `reserve_usd` parameter and subtract from deployable buys (defense-in-depth even if runner also enforces); harden dict input handling.
**Effort:** 0.5–1 day.
**Dependencies:** Need `hybrid_rebalancer.py` and `order_executor.py` to confirm consumer expectations (Batch 3).
**Backlog:** No.

---

**ID:** P6-125
**Title:** Live-init `get_account_balance("USD")` lacks the tri-state error guard applied to holdings — error-vs-zero conflation at capital sizing
**Category:** Data Integrity / Fresh Start blast radius
**Priority:** P1
**Severity:** High
**Evidence:** `phase6_runner.py.__init__` (live branch): `actual_usd = self.exchange.get_account_balance("USD"); effective_capital = min(max_deployable, actual_usd)`. If the client returns `0.0` on API error (pattern under audit in P6-101), `effective_capital=0` silently — portfolio manager initialized with zero capital while real holdings exist; if it returns `None`, `min()` raises TypeError at startup (fail-loud, acceptable but unhandled).
**Impact:** Same root cause family as P6-101 but outside the gated path: degraded API at startup can zero out capital assumptions, distorting reserve math and deployable cash for the whole session.
**Recommended Fix:** Extend the verified-sentinel contract (`None` = unverified, never 0) to `get_account_balance`; on `None`, abort startup in live mode with explicit error (do not proceed, do not default).
**Effort:** 0.25 day once the P6-101 sentinel contract lands in `exchange_client.py`.
**Dependencies:** P6-101 fix; `exchange_client.py` source (Batch 3).
**Backlog:** No.

---

**ID:** P6-126
**Title:** Runner state housekeeping: unlocked read-modify-write of state file; `_write_recovery_state` swallows AttributeError via bare except
**Category:** Robustness
**Priority:** P3
**Severity:** Low
**Evidence:** `_save_state` does read→merge→write with no lock/atomic rename; `_write_recovery_state` uses `getattr(self, "portfolio", {})` → `{}` lacks `.get_positions()` → AttributeError silently eaten by `except Exception: pass`; "emergency" mode inferred from `≤2 positions` heuristic. Also `_force_next_rebalance` is a hand-toggled commented flag.
**Recommended Fix:** Atomic write (`tmp` + `os.replace`); narrow excepts with a warning log; move force-rebalance to a CLI flag.
**Effort:** 0.25 day.
**Dependencies:** None.
**Backlog:** Yes.

---

## 3. CLOSURE ASSESSMENT — PRIOR P0/P1

| ID | Status | Assessment |
|---|---|---|
| **P6-101** | **Still blocked** | Runner gate is correct tri-state (`None` → skip Fresh Start; `False` → fresh start; truthy → takeover). But closure requires confirming `LivePortfolioManager.has_open_positions()` and `exchange_client.get_holdings()` actually return `None` on *any* API error and `False` only on verified-zero (incl. dust policy). New sibling gap P6-125 must close with it. **Blocked by:** `live_portfolio_manager.py`, `exchange_client.py`. |
| **P6-102** | **Unchanged** | No Batch-2 file touches it; status as per Batch 1. No new evidence either way. |
| **P6-103** | **Unchanged** | Same — no Batch-2 evidence; still open pending Batch-1 remediation/files. |
| **P6-105** | **Schema confirmed, NOT ready to close** | Wrapper's real return shapes are now documented (mixed `id`/`order_id` keys, no fills, always-PENDING). The mismatch risk is confirmed and *worse*: see P6-115/116/117/118. **Blocked by:** `order_executor.py`, `stop_loss_manager.py`, `stop_loss_coordinator.py` consumer-side parsing. |
| **P6-107** | **Unchanged** | No Batch-2 evidence; needs the risk-tier files (Batch 3). |
| **P6-108** | **Worsened, blocked** | Source-side fabrication confirmed (P6-121) plus live-cache schema divergence (P6-122). Reader-side freshness logic cannot be trusted until writer is fixed and unified. **Blocked by:** P6-121/122 fixes + `hybrid_rebalancer._load_sentiment` full source. |
| **P6-109** | **Still open** | Confirmed `last_rebalance_time` in-memory only; runner persists only `last_rebalance_date`. Allocation engine has no stickiness support and silently clamps moves (P6-124). Recommend persisting rebalance timestamp into `phase6_runner_state.json` (mechanism already exists). **Blocked by:** `hybrid_rebalancer.py` full source. |
| **P6-114** | **Confirmed open, escalating** | `_suspended_orders` in-memory only; *and* the wrapper cannot cancel or list orders (P6-117/118), so even a durable snapshot couldn't be acted on today. Fix order: P6-117 → P6-118 → durable snapshot file (`data/state/suspended_stops.json`, atomic write) → restore-on-startup. |
| **P6-113** | Same as P6-105 — schema now known; blocked on consumer files + P6-118 standardization. |

---

## 4. BATCH 3 REQUEST

Please provide Batch 3 with the planned tiers (sentiment tier, backtest harness, config/docs, ledger) **plus these specific files**, which are now hard blockers for closure:

1. `phase6/core/live_portfolio_manager.py` (full — `has_open_positions`, `get_positions`, dust handling) — closes P6-101
2. `phase6/core/exchange_client.py` (full — `get_holdings`, `get_account_balance`, `get_recent_prices`, error→return contracts) — closes P6-101/125
3. `phase6/core/rebalancing/hybrid_rebalancer.py` (full — `_load_sentiment`, `last_rebalance_time`, sticky/proportional logic) — closes P6-108/109/122
4. `phase6/core/order_executor.py` + `phase6/core/stop_loss_manager.py` + `phase6/core/stop_loss_coordinator.py` (full) — closes P6-105/113/114
5. `src/capital_allocation/withdrawal_reserve.py` + `phase6/scripts/deploy_capital.py` — verifies ~$250 reserve end-to-end
6. Remainder of `phase6_runner.py` (the feed truncated at RSI pre-seeding: `_handle_fresh_start`, `_run_cycle`, `_perform_daily_rebalance`, `_write_dashboard_cache`)
7. `trading_config_phase6.json` (actual min/max weights, scheduler, reserve values) — closes P6-123 feasibility check
8. `phase6/core/sentiment_scorer.py` (`load_sentiment_scores`, `get_sentiment_adjusted_weights`) and **any cron/systemd entry or legacy script still writing `sentiment_cache.json`** (the live cache proves one exists)
9. `phase6/core/trade_ledger.py` + backtest harness

---

## 5. GO/NO-GO SUMMARY — LIVE-SAFETY GATE (updated)

**Overall: NO-GO for live mode.** Shadow mode acceptable for continued soak.

| Item | Finding(s) | Status | Go condition |
|---|---|---|---|
| Stop prices/sizes valid for XRP/DOGE | **P6-115, P6-116** | 🔴 NO-GO | Product-metadata quantization layer + rejection tests on all 5 pairs |
| Order reconciliation & cancel capability | **P6-117, P6-118** | 🔴 NO-GO | Correct endpoints, JWT query-string fix, `cancel/get_order/fills`, unified `OrderResponse` |
| Duplicate-order protection | **P6-119 (+120)** | 🔴 NO-GO | Deterministic client_order_id + post-ambiguity lookup, write-ahead intent |
| Fresh Start on verified-zero only | **P6-101, P6-125** | 🟡 BLOCKED | Sentinel contract verified in portfolio manager + exchange client; balance call gated |
| Sentiment integrity & freshness | **P6-108, P6-121, P6-122** | 🔴 NO-GO | Dataset-based retrieval, posts≥N gate, unified versioned schema, legacy writer killed |
| Suspended-stop durability / rollback | **P6-114** | 🔴 NO-GO | Durable snapshot + restore-on-startup; depends on P6-117/118 |
| Sticky rebalance / durable rebalance timestamp | **P6-109, P6-124** | 🟡 BLOCKED | Persist `last_rebalance_time`; confirm hybrid rebalancer logic in Batch 3 |
| Allocation bounds actually enforced | **P6-123** | 🟡 OPEN | Feasibility validation + iterative clipping |
| ~$250 withdrawal reserve end-to-end | (open, Batch 1) | 🟡 BLOCKED | `withdrawal_reserve.py` + `_handle_fresh_start` remainder in Batch 3 |
| P6-102 / P6-103 / P6-107 | prior batch | 🟡 UNCHANGED | Per Batch-1 remediation; no Batch-2 evidence |

**Minimum critical path to live:** P6-115/116 → P6-117 → P6-118 → P6-119 → P6-101/125 verification → P6-121/122 → P6-114 durable snapshot → reserve verification (Batch 3).

Please provide **Batch 3** (sentiment tier, backtest harness, config/docs, ledger) including the nine specific files enumerated above.