# PHASE 6 — FABLE 5 REVIEW — BATCH 4 / CLOSURE PASS

**Reviewer:** Fable 5 | **Scope:** Final gate re-evaluation with complete artifacts | **Verdict summary up front:** **CONDITIONAL GO for paper trading** (2 pre-start blockers, both small) / **NO-GO for live** (6 open live-mode defects).

---

## 1. NEW FINDINGS THIS PASS (complete-source review)

| ID | Sev | Component | Finding |
|---|---|---|---|
| **P6-141** | **P1 (crash, affects PAPER + LIVE)** | `exchange_client.get_recent_prices` | `datetime` is **not imported at module level**; it is imported inside the `try` block. The cache-hit branch (`if (datetime.now() - cached_time).seconds < 300`) executes **before** the local import and is **outside the try/except** → `NameError` propagates to caller on **any second call for the same cache key within 5 minutes**. Function-local `from datetime import datetime` does not persist across calls. If ATR (P6-004) and any other indicator both call this for the same pair in one cycle, the cycle crashes. Fix is one line (module-level import). This is the only known crash bug in the shadow path. |
| **P6-142** | **P1** | `allocation_engine.rebalance_plan` | Dict-shape handling uses `cur_val.get("usd_value", cur_val)` but the data boundary (`get_enriched_positions`, per the P6-001 fix comment) emits **`"value_usd"`**. On key miss, the default returns the **dict itself**, then `float(cur)` → `TypeError`, or silently wrong allocation if a numeric sneaks through. Key mismatch `usd_value` ≠ `value_usd`. Requires isolation test on the exact caller payload. |
| **P6-143** | **P1 (G4 gate)** | `allocation_engine.rebalance_plan` | `usd_needed` / `usd_available` are computed and **never used** (dead code). Buy moves are emitted **without funding constraint** — buys are not netted against sells or available cash. Combined with the runner calling `enforce_withdrawal_reserve(target_allocations_usd={})` (confirmed by Scotty note), the **projected post-allocation reserve check is a no-op on the buy side**. This is a direct violation of the verbatim constraint "withdrawal reserve respected in *projected* post-allocation state in every path." |
| **P6-144** | **P1 (live only)** | `exchange_client._ensure_live_client` | The on-demand init path (the only one actually reachable — `_init_live_client` is **never called**; `__init__` always sets `real_client=None`) does **not** perform the `private_key.replace("\\n", "\n")` normalization that `_init_live_client` does. Live init will fail with escaped-newline keys from env. Either route on-demand through `_init_live_client` or duplicate the normalization. |
| **P6-145** | **P1 (live only)** | `exchange_client.place_stop_limit_sell` | (a) `"reduce_only": True` inside `stop_limit_stop_limit_gtc` — not a valid field for Advanced Trade spot stop-limits; risks `INVALID_ARGUMENT` rejection of every native stop. (b) `base_size: str(qty)`, `limit_price`, `stop_price` are sent **unquantized** — `_round_size_for_product` / `_quantize_price` exist but are not called here. Float repr like `0.30000000000000004` will be rejected. |
| **P6-146** | **P1 (live only)** | `get_product_metadata` (both files) | `ADA-USD` is in the active config pairs but has no metadata case → falls to default `price_increment: 0.01` on a ~$0.45 asset. Stop/limit prices for ADA will be quantized to 2 decimals → rejected or grossly mispriced. ETH default happens to be acceptable; ADA is not. |
| **P6-147** | P2 | `exchange_client` | **Two `def get_open_orders` definitions** in the same class. The second (live `/historical/batch` impl) silently shadows the first (stub). Current effective behavior is correct, but this is exactly the failure mode that bit Phase 5. Delete the stub. |
| **P6-148** | **P1 (verify)** | `config/trading_config_phase6.json` | The active config contains **no withdrawal reserve key** (`min_reserve` is referenced in the runner notes as "200 in config" but is absent from the pasted active config). If the runner falls back to a default of 0 when the key is missing, the reserve is unprotected. Additionally `max_deployable_usd: 1000 == total_capital: 1000` leaves zero reserve headroom at the config level; if reserve=200 is intended, deployable should be ≤ 800. |
| **P6-149** | P2 (verify in repo) | `coinbase_wrapper_FIXED.place_market_buy` | Paste ends with `import tracebac` (sic) inside the exception handler. If literal in the file, the handler raises `ImportError` and masks the original order failure. Verify against the actual file; likely paste truncation, but must be confirmed since this is the live order path. |
| **P6-151** | P1 | `get_enriched_positions` / deprecated `get_holdings` | `get_holdings()` collapses unverified → `{}`, so `get_enriched_positions` **cannot distinguish "verified empty" from "API error"**. Any consumer of enriched positions (daily rebalance) that receives `{}` on a transient API failure could treat real holdings as nonexistent — a sticky-holdings (G3) leak around the tri-state fix. Enriched positions should carry/propagate the `verified` sentinel, or call `get_holdings_verified` and bail on unverified. |
| P6-152 | P2 | `exchange_client.place_market_buy` vs wrapper | Exchange client uses `quote_size` via raw `_request`; wrapper's own method uses `base_size` (its "FIX 1"). `quote_size` is valid API for market IOC buys, so not a defect — but two divergent order paths exist. Pick one and delete the other. |

**Carried open from prior batches:** P6-127 (`round(price, 2)` in live `get_price` — confirmed still present per Scotty note despite paste showing full precision; the **repo state governs**: DOGE at $0.12xx gets up to ~4% pricing error, sub-cent assets → 0.0), P6-125 (`get_account_balance` returns 0.0 on live error — fail direction is mostly safe for Fresh Start but silently corrupts reserve math; should return `None`/raise), P6-140 (handoff written, not closed), HybridRebalancer default sentiment path `~/.trading-bot/sentiment_cache.json` (stale-cache risk if instantiated without explicit path).

---

## 2. GATE RE-EVALUATION (G1–G9)

| Gate | Status | Evidence / Condition |
|---|---|---|
| **G1 — Real data only** | **CONDITIONAL PASS (paper) / FAIL (live)** | Shadow prices are explicitly simulated and labeled — acceptable for paper. `get_recent_prices` uses real public candles in both modes — good. Live `get_price` retains `round(2)` (P6-127) → live fails until fixed. Live `get_price` returns `0.0` on total failure rather than raising — callers must guard (verify divide-by-price sites). |
| **G2 — Fresh Start on verified-zero only (tri-state)** | **PASS (conditional on artifacts)** | `get_holdings_verified` returns proper `{positions, verified, error}` sentinel; LPM `has_open_positions` returns `None` on unverified; P6-132/133 isolation tests written + passing this session. Condition: tests committed and referenced in close-out. |
| **G3 — Sticky holdings / rebalance from actual positions** | **CONDITIONAL PASS** | Enrichment normalizes to `-USD` keys with `value_usd` (P6-001 fix verified in source). **Two leaks:** P6-151 (enriched positions can't see unverified → `{}` looks like empty book) and P6-142 (key mismatch in `rebalance_plan` dict handling). Both must be fixed or proven unreachable via caller payload test. |
| **G4 — Withdrawal reserve in projected post-allocation state, every path** | **FAIL** | `enforce_withdrawal_reserve` called with empty target dict (no-op on buy side) + `rebalance_plan` emits unfunded buys (P6-143) + active config has no reserve key (P6-148). This was the verbatim constraint; it is not currently met in the daily-rebalance path. Fresh Start path has a real deployable-cash guard (min_reserve), but the reserve must come from config, not lore. |
| **G5 — Sentiment quality/aging + 24h cooldown incl. recovery** | **CONDITIONAL PASS** | Canonical writer/reader confirmed (`run_full_sentiment_v3.py` → repo-root `sentiment_cache.json` → `sentiment_scorer.py`). Condition: prove (one log line or test) that the runner's rebalancer instance is constructed with the canonical path, not HybridRebalancer's `~/.trading-bot/` default. Cooldown logic accepted from prior batches; re-verify in paper logs day 1. |
| **G6 — Stop-loss integrity / order correctness** | **PASS (paper) / FAIL (live)** | Shadow stop logging fine. Live native stops blocked by P6-145 (reduce_only + unquantized fields) and P6-146 (ADA metadata). Real ATR usage (P6-004) is hostage to the P6-141 crash. |
| **G7 — Exchange client live-safety** | **FAIL (live) / PASS (paper)** | P6-144 (init path key normalization), P6-125 (0.0 on error), P6-127, P6-149 (verify), duplicate method (P6-147). None block shadow. |
| **G8 — Config/capital consistency** | **CONDITIONAL PASS** | Active config is coherent for a $1k paper book; reserve key absent (P6-148) and deployable==total are the open items. No phantom `capital_allocation_config.json` — confirmed using defaults; document this. |
| **G9 — Test/verification artifacts + sign-off process** | **CONDITIONAL PASS** | P6-101 closed with sign-off; P6-132/133 isolation tests passing. Kanban DB corruption acknowledged — MASTER_TASK_TRACKING.md + handoffs accepted as system of record for this phase, **provided** every P0/P1 in this report gets a handoff entry before conclude. |

---

## 3. TOP RISKS TABLE (updated)

| # | Risk | ID(s) | Mode affected | Likelihood | Impact |
|---|---|---|---|---|---|
| 1 | Reserve not enforced in projected state on buy side | P6-143, P6-148, runner empty-dict call | Paper + Live | High (structural) | Reserve depletion; constraint violation |
| 2 | `get_recent_prices` NameError on cache hit | P6-141 | Paper + Live | High if any pair queried 2× per 5 min | Cycle crash mid-loop |
| 3 | Unverified holdings → `{}` → rebalance treats book as empty | P6-151 | Paper + Live | Medium (transient API errors) | Phantom "fresh" rebalance; sells/buys against ghost state |
| 4 | `rebalance_plan` dict key mismatch | P6-142 | Paper + Live | Medium (depends on caller payload) | TypeError crash or wrong allocations |
| 5 | Live price rounding | P6-127 | Live | Certain | Mispriced DOGE/XRP/ADA decisions |
| 6 | Native stop rejection (reduce_only / quantization / ADA increments) | P6-145, P6-146 | Live | High | Positions running unprotected |
| 7 | Live client init fails on escaped key | P6-144 | Live | High with env-stored keys | Silent fallback to "no live client" |
| 8 | Balance 0.0 on error | P6-125 | Live | Medium | Corrupted reserve/sizing math |

---

## 4. GO/NO-GO — PAPER TRADING START

### **GO — CONDITIONAL**, with 2 pre-start blockers:

1. **P6-141** — add module-level `from datetime import datetime` (or restructure cache check). One-line fix + isolation test (call twice within window, assert no exception). **Do not start without this**; it is a known deterministic crash.
2. **P6-148 verification** — confirm what the runner actually resolves for `min_reserve` when the key is absent from active config. If it resolves to 0/None, add `"min_reserve": 200` (and set `max_deployable_usd: 800`) before start. 15-minute task.

Everything else live-mode-only or observable-in-paper. Paper trading is the correct instrument for shaking out G3/G4/G5 behavior — **provided the punch-list below is executed in parallel, not deferred.**

### NO-GO — LIVE (unchanged)
Blockers: P6-127, P6-143/G4, P6-144, P6-145, P6-146, P6-125, P6-149 verification. Re-gate after paper results.

---

## 5. PUNCH-LIST — FIRST 1–2 DAYS OF PAPER TRADING

**Day 1 (fixes, in priority order):**
1. ~~P6-141 fix~~ (pre-start blocker, above).
2. **P6-143 + runner empty-dict call**: make `_perform_daily_rebalance` build real `target_allocations_usd` from the plan's BUY legs and pass them to `enforce_withdrawal_reserve`; add funding constraint inside `rebalance_plan` (buys ≤ sells_proceeds + deployable_cash − reserve). Isolation test: plan that would breach reserve must be trimmed/rejected. **Scotty sign-off required** (constraint-level fix).
3. **P6-142**: isolation test feeding the *actual* runner payload into `rebalance_plan`; fix key to `value_usd` (accept both during transition).
4. **P6-151**: change `get_enriched_positions` to use `get_holdings_verified` and return a sentinel (or raise) on unverified; runner skips rebalance cycle on unverified — log loudly.
5. Delete duplicate `get_open_orders` stub (P6-147); pin HybridRebalancer sentiment path explicitly at construction and log the resolved path at startup (closes G5 condition).

**Day 1–2 (observation checklist, every cycle in logs):**
- Fresh Start does **not** trigger while shadow positions exist; logs show tri-state value, not bool coercion.
- Reserve math line per cycle: cash, projected post-allocation cash, reserve floor — all three logged.
- Sentiment cache age logged per read; verify aging rejection fires on a deliberately stale cache (one forced test).
- 24h cooldown: stop a position manually in shadow, confirm pair excluded from next deploy/recovery cycle with explicit log reason.
- `get_recent_prices` cache hit/miss counters — confirm no public-API hammering and no exceptions.
- Rebalance moves: confirm proportional/damped deltas from actual enriched positions, no move exceeds `rebalance_cap_usd` (500) or 25% clamp, and SELL legs precede BUY legs in execution order.

**Day 2 (live-prep, non-blocking for paper):**
- P6-127 (strip `round(2)`), P6-144 (unify init path), P6-145 (drop reduce_only, quantize all stop fields via existing helpers), P6-146 (add ADA/ETH metadata or implement the real `/products` fetch the placeholder promises), P6-125 (None-on-error), P6-149 (verify wrapper file tail).

---

## 6. REMAINING BEFORE "CONCLUDE"

1. Handoff entries in MASTER_TASK_TRACKING.md for P6-141…P6-152 (Kanban DB not trusted — agreed).
2. Committed isolation tests: P6-141, P6-142, P6-143/G4 reserve projection, P6-151. (P6-132/133 already passing — reference commit hashes.)
3. One forced-failure shadow run: simulated holdings-API error mid-session → assert no rebalance, no Fresh Start, loud log.
4. ≥48h continuous paper run artifact (logs + order log + reserve trace) attached to close-out.
5. Scotty sign-off on the G4 fix specifically — it is the only **constraint-level** gate still failing.
6. Live re-gate (G1/G6/G7) as a separate Batch 5 mini-pass before any live capital; do not fold it into this closure.

**Closure statement:** With blockers 1–2 of §4 done, Fable 5 approves **paper trading start**. G4 is the single remaining constraint failure and must be fixed within the paper window, not after it. Live remains gated.

— Fable 5, Batch 4 closure complete.