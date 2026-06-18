# PHASE 6 FABLE 5 REVIEW — BATCH 3 FINDINGS

**Reviewer verdict up front: NO-GO. Two requested artifacts arrived truncated/missing (exchange_client.py cut mid-method; phase6_runner.py fragment is ~15 lines of docstring), and this batch surfaced 5 new CRITICALs including a method that does not exist at runtime (`LivePortfolioManager.get_positions`), live SELLs that always fail (one-sided rebalances), and a reserve enforcement that only acts *after* the reserve is already breached.**

---

## 1. PER-FILE FINDINGS

### 1.1 phase6/core/exchange_client.py

| ID | Sev | Finding | Detail / Required Fix |
|---|---|---|---|
| **P6-126** | **CRITICAL** | **File truncated / likely syntax error.** Second `get_open_orders` definition ends mid-line (`o.get("pr`). Also two `get_open_orders` definitions exist (an earlier stub returning `[]`, a later real one). If the repo file matches what was sent, the module does not import. | Re-send the full file. Remove the duplicate stub; one definition only. Cannot certify P6-117 until the real tail is seen. |
| **P6-127** | **CRITICAL** | `get_price` live path does `round(price, 2)`. For DOGE (~$0.12) this is a ~±4% quantization error; XRP loses 2 significant digits. This price feeds **position sizing, stop placement, valuation, and enriched positions**. | Return full-precision float (or Decimal). Quantization belongs at order-construction time per product increments, never at the price feed. |
| **P6-128** | HIGH | `place_stop_limit_sell` live: (a) fallback `limit_p = round(stop_price * 0.995, 2)` re-introduces 2-dp rounding for DOGE/XRP; (b) `str(qty)`/`str(stop_price)` serialize raw floats — risk of `1e-08` notation and excess decimals → exchange rejection; (c) `reduce_only: True` is not valid for spot `stop_limit_stop_limit_gtc` and may cause INVALID_ARGUMENT. | Accept pre-quantized **strings** end-to-end; remove `reduce_only`; never re-round internally. This is the live continuation of P6-115/116 — quantization in SLM is undone/bypassed here. |
| **P6-129** | HIGH | `get_recent_prices`: cache-hit path uses `datetime.now()` **before** `datetime` is imported (import is inside the later `try`). First call works, any call within 5 min raises `NameError` → returns nothing → volatility/RSI inputs vanish intermittently. | Module-level `from datetime import datetime, timedelta, timezone`. |
| **P6-130** | HIGH | `_ensure_live_client` does **not** apply the `\\n → \n` private-key normalization that `_init_live_client` does, and `__init__` never eagerly initializes the live client → live mode fails **at first order time** with a PEM error instead of at startup. | Single init path; normalize key; fail fast at startup in live mode with a credential/permission probe. |
| **P6-125** | **CONFIRMED OPEN** | `get_account_balance` returns `0.0` on exception — error indistinguishable from verified-zero. Any Fresh Start / deployable-cash logic consuming this can treat a transient API failure as "no money." | Add `get_account_balance_verified()` returning `{value, verified, error}` mirroring `get_holdings_verified()`. This is the last sentinel gap on the exchange client itself. |
| **P6-131** | MED | `place_market_buy` returns only `success/order_id` — no fill price, no filled base size, no order status poll. Downstream (OrderExecutor) fabricates fills from spot price. | Poll `GET /orders/historical/{order_id}` (or fills endpoint) and return `filled_size`, `average_filled_price`, `status`. |
| P6-117 | PARTIAL | Live `get_open_orders` now hits `/orders/historical/batch?order_status=OPEN`, but query-string-in-path signing depends on the wrapper's `_request`; unverified. Shadow mode returns `[]` (no parity for CR-03 testing). | Verify wrapper signs path+query correctly; add shadow open-order tracking so CR-03 is testable in isolation. |

✅ Positive: `get_holdings_verified()` correctly implements the verified sentinel (includes `hold` balances — good), and the deprecated `get_holdings()` returns `{}` only when *unverified*, which is safe **only if no caller treats `{}` as verified-zero** — see P6-154 (runner unseen).

---

### 1.2 phase6/core/live_portfolio_manager.py

| ID | Sev | Finding | Detail / Required Fix |
|---|---|---|---|
| **P6-132** | **CRITICAL** | `get_positions()` is defined **inside the `if __name__ == "__main__":` block**, indented under it. When the module is *imported* (the only way it's used in production), the method **does not exist**. Any rebalance path calling `lpm.get_positions()` raises `AttributeError` — or worse, a `hasattr` guard silently falls back to stale internal state. Classic merge artifact. | Move the method into the class body. Add an import-time smoke test asserting the method exists (Code Isolation Testing). |
| **P6-133** | **CRITICAL** | Even as written, `get_positions` (a) returns `{}` on any exception — **violates the verified sentinel contract**: empty-from-error is indistinguishable from verified-flat, exactly the P6-101 failure mode, now on the positions path; (b) hardcodes the 5-pair list, so ADA-USD (in config!) is invisible; (c) silently falls back to internal paper state in live if the exchange read partially fails. | Return `{positions, verified, error}`; derive pair list from config; never fall back from live→internal silently. |
| **P6-134** | HIGH | `reconcile_positions` calls `risk_engine.update_pnl(sum(unrealized))` **every cycle**, cumulatively adding total unrealized PnL to `daily_pnl`. After N cycles daily_pnl ≈ N× unrealized → circuit breaker fires falsely on drawdown, or masks real losses on gains. | `update_pnl` is for realized increments only. Track unrealized separately; daily loss = realized + Δunrealized vs day-start equity. |
| **P6-135** | HIGH | Reconciliation theater: if the client lacks `get_position` (CoinbaseExchangeClient does), the fallback compares the position **to itself** → zero drift ever detected in live, while logging "reconciliation complete." | Reconcile against `get_holdings_verified()` + live prices; abort reconciliation (not fake-pass) when unverified. |
| **P6-136** | HIGH | `record_trade` is broken twice: (a) CSV — tmp file is only `os.replace`d when the CSV *doesn't* exist; once it exists, the append block is `pass` → **every trade after the first is lost**; (b) SQLite — `trades_live` table is never created, so every insert raises, is caught, rolled back, and swallowed → **DB ledger permanently empty, silently**. | Plain `open(..., "a")` append with fsync; `CREATE TABLE IF NOT EXISTS` in `_ensure_atomic_db`; surface insert failures. |
| **P6-137** | MED | `total_capital` defaults to 10,000 vs config 1,000; `RiskLimits.max_daily_loss_pct=0.05` vs config `0.02`; RiskEngine never reads `trading_config_phase6.json`. Daily-loss breaker is therefore 10× looser than intended ($500 vs $20 effective on real capital). | Wire RiskLimits from config at construction; assert capital matches live equity at startup. |

---

### 1.3 phase6/core/rebalancing/hybrid_rebalancer.py

| ID | Sev | Finding | Detail / Required Fix |
|---|---|---|---|
| **P6-138** | HIGH | Reads `~/.trading-bot/sentiment_cache.json` by default — **not** the canonical `/home/brad/projects/crypto-trading-bot/sentiment_cache.json`. Unless every constructor overrides `cache_path`, the rebalancer sees permanent neutral 0.0 (fabricated neutral on missing file, no freshness gating, no aging). It also duplicates parsing logic instead of using `sentiment_scorer`. Deltas vs runner-supplied `previous_sentiment` (from the *real* cache) will be spurious. | Delete `_load_sentiment`; call `sentiment_scorer.get_aged_sentiment_scores()`; refuse to evaluate (skip cycle, don't neutral-default) when freshness gate fails. |
| **P6-108** | **CONFIRMED OPEN** | `last_rebalance_time` in-memory only — restart resets the 24h interval guard. Additionally it is set on **decision**, not on confirmed execution: a failed rebalance suppresses retries for 24h. | Persist to state file; set only after execution success confirmation. |
| **P6-139** | MED | `generate_rebalance_plan` allocates `weights × total_capital` with no reserve subtraction, no sticky-holdings/min-move-beyond-$25 logic, no allocation bounds. Naive `datetime.utcnow()`. | Route through allocation_engine with reserve-net deployable capital (see P6-145/149); use tz-aware time. |

---

### 1.4 phase6/core/order_executor.py

| ID | Sev | Finding | Detail / Required Fix |
|---|---|---|---|
| **P6-140** | **CRITICAL** | `execute_sell` in live returns `success: False, not_implemented`. `execute_rebalance_plan` will therefore execute **all BUY legs and zero SELL legs in live** → portfolio drifts long, cash (and reserve) is consumed with nothing freed, plan invariants silently violated. Also unit bug: plan's `usd_amount` is passed as `size` (base units) to `execute_sell` — wrong even in shadow. | Either implement live market sell (with quantized base size from verified holdings) **or** hard-refuse to execute any plan containing SELL legs in live (atomicity: all-or-nothing plan gate). Honest failure is good; *partial plan execution is not.* |
| **P6-141** | HIGH | Buy "fill" data is fabricated: `price = get_price()` **after** the order, `size = usd/price` estimate. The SL is then attached at that estimated entry with the estimated size → stop size can exceed actual filled base size (placement rejected) or under-protect; entry/stop levels off by slippage + the P6-127 2-dp rounding. | Use real fill data from order status (P6-131) before SL attach; attach SL sized to *verified* post-fill holdings. |
| **P6-142** | MED | `_retry_with_backoff` retries only on **exceptions**; `place_market_buy` returns `{"success": False, ...}` without raising (rate limits, rejections) → zero retries on the most common failure mode. | Treat `success=False` results as retryable per error class. |

✅ Positive: live SELL fails loudly rather than fabricating `success=True` — the prior fabrication finding is resolved at the *honesty* level, but P6-140 makes it operationally unsafe.

---

### 1.5 phase6/core/stop_loss_manager.py

| ID | Sev | Finding | Detail / Required Fix |
|---|---|---|---|
| **P6-115/116** | PARTIAL | Quantization is now applied in `attach_stop_loss` ✅, but: (a) product metadata is a **hardcoded placeholder** (`get_product_metadata`), not fetched from `/products/{id}` — the DOGE/XRP increments shown (DOGE base 1.0, price 0.00001) must be verified against live product specs before any trust; (b) the `stop_price >= entry_price` adjustment branch does raw float subtraction and `str(float)` — bypasses quantization, can emit `0.11999999999999998`; (c) quantized strings are converted back to floats and re-stringified inside `place_stop_limit_sell` → precision round-trip (compounds P6-128). | Fetch metadata live (cache it); keep Decimal strings end-to-end; re-quantize after any adjustment. **Live verification with a real $10 DOGE stop is mandatory before promotion.** |
| **P6-118** | **CONFIRMED OPEN** | `detect_active_protective_orders` filters on `order.get("type")` and top-level `order.get("stop_price")`. Real Coinbase Advanced Trade orders carry `order_type` (e.g. `"STOP_LIMIT"`) and the stop price nested in `order_configuration.stop_limit_stop_limit_gtc.stop_price`. **In live, detection returns nothing** → CR-03 "no protective orders to suspend" → rebalance proceeds with live stops still armed → stops fire mid-rebalance on positions being sold. | Parse real order shape (`order_type`, nested `order_configuration`); add a fixture test with a captured real order JSON (Code Isolation Testing). Note the *coordinator* checks `order_type` (would work) — the two CR-03 paths disagree; unify. |
| **P6-143** | MED | Config has `"take_profit_pct": null`. `config.get(...).get("take_profit_pct", 0.06)` returns `None` (key exists) → `entry_price * (1 + None)` TypeError if TP is ever attached. | `pct = cfg.get("take_profit_pct") or 0.06`, or treat null as "TP disabled" explicitly. |

---

### 1.6 phase6/core/stop_loss_coordinator.py

| ID | Sev | Finding | Detail / Required Fix |
|---|---|---|---|
| **P6-114** | **CONFIRMED OPEN** | No durable journal. `suspend_protective_orders` cancels orders, collects IDs in a **local variable**, then sets `self._suspended_orders = {p: [] for p in pairs}` — the canceled orders' parameters (stop price, size) are **discarded immediately**, even in memory. A crash inside the protected window leaves positions naked with no record of what was canceled or what to restore. | Before each cancel: append `{order_id, pair, stop_price, limit_price, size, ts}` to an fsync'd journal file; reattach/rollback reads the journal; clear journal only after verified reattach (`verify_reconciliation` pass). |
| **P6-144** | HIGH | Reattach semantics: (a) uses `entry_price or current_price` — for restoration this **moves the stop** relative to current price, not the original level (after a dip, the restored stop can sit materially lower than the canceled one); (b) reattach failures return `status: failed` but **do not raise** — the context manager logs and exits cleanly, leaving naked positions with a green log line; (c) rollback re-attaches from `new_positions` captured *before* the rebalance — stale if the plan partially executed (compounds P6-140). | Reattach at journaled original stop levels for restoration; raise/alert on any `failed`; recompute positions from `get_holdings_verified()` at reattach time. |

---

### 1.7 src/capital_allocation/withdrawal_reserve.py + phase6/scripts/deploy_capital.py + config

| ID | Sev | Finding | Detail / Required Fix |
|---|---|---|---|
| **P6-145** | **CRITICAL** | **Reserve enforcement is reactive, not preventive, and is bypassed entirely in the deploy path.** (a) `enforce_withdrawal_reserve` returns targets unchanged unless the reserve is *already* flagged — a plan that spends a currently-healthy $600 reserve down to $200 passes untouched (it checks pre-trade reserve, never projected post-trade reserve). (b) `deploy_capital()` advertises `withdrawal_reserve_min: 250` in `get_deployment_thresholds()` but **never calls the reserve module or subtracts any reserve** — `new_capital` is deployed in full. The focus item "reserve respected in every allocation/rebalance/deploy path" **fails in 2 of 3 visible paths** (third path = runner, unseen). | Enforce on projected post-trade reserve: `deployable = max(0, cash − min_reserve)`; call it inside `deploy_capital` and in the rebalance plan builder; refuse plans whose net cash outflow breaches reserve. |
| **P6-146** | HIGH | RSI hard gate **deletes existing holdings** from `current_allocations` (`current_allocations = {p:v ... if rsi >= min_rsi}`) — the returned allocation map omits oversold pairs entirely, and their capital is redistributed to others. Downstream rebalance-to-target will **liquidate oversold positions**, the exact opposite of sticky holdings (and of "don't sell into capitulation"). Also: emergency-recovery candidates use `effective_candidate_pairs` captured *before* the RSI filter → recovery pairs bypass the RSI gate. | RSI gate must only exclude pairs from receiving *new* capital; existing allocations pass through unchanged. Apply the gate to `effective_candidate_pairs` too. |
| **P6-147** | HIGH | `cooldown_pairs` (24h post-stop cooldown) is filtered **only in the emergency-recovery branch**. Normal new-pair selection ignores it → a stopped-out pair with momentarily positive sentiment can be re-bought within minutes. Contract violation. | Filter cooldown pairs from all candidate selection and from receiving new capital, unconditionally. |
| **P6-148** | HIGH | `deploy_capital` renormalizes **all** pairs (existing + new) to `total_capital` with sentiment-tilted weights → existing holdings get resized (sells generated) just to deploy new cash — not sticky. Worse, for `source="reserve"`, pairs with sentiment < −0.30 are dropped from `eligible` and thus from the output → **silent full liquidation** of those pairs by the consuming rebalancer. | Deploy *only* `new_capital` across eligible targets; pass existing allocations through unchanged (proportional-adjustment contract); never drop an existing pair from the returned map. |
| **P6-149** | HIGH | Three conflicting reserve definitions: `withdrawal_reserve.py` default $500; `deploy_capital` thresholds $250; config `reserve_min_pct: 0.2` (=$200) while `max_deployable_usd: 1000 == total_capital` (zero headroom). Whichever path runs decides the reserve. | Single source: `capital_allocation_config.json` → consumed everywhere; config validator asserts `max_deployable + min_reserve ≤ total_capital`. |
| **P6-150** | HIGH | Config universe is **6 pairs incl. ADA-USD**, but: sentiment collector covers 5 (ADA gets fabricated-neutral forever), `sentiment_scorer.DEFAULT_UNIVERSE` is 5, and `LivePortfolioManager.get_positions` hardcodes 5 → ADA holdings invisible to position sourcing, eternally neutral sentiment, eligible for buys via config. | Either remove ADA-USD from config or add it to every universe definition; derive all universes from config; assert sentiment coverage == config pairs at startup. Also blocks P6-109 sign-off (bounds feasibility checked against which N — 5 or 6?). `allocation_engine.py` still unseen — P6-109 remains open. |

---

### 1.8 Sentiment (sentiment_scorer.py + run_full_sentiment_v3.py)

| ID | Sev | Finding | Detail / Required Fix |
|---|---|---|---|
| **P6-121/122** | PARTIAL → new gap | Fabrication is fixed ✅ (insufficient data → preservation, not fake-neutral-with-fresh-stamp). **But** `write_canonical_cache` always writes a fresh **top-level** `timestamp`, even when every pair was preserved from the old cache, and `get_aged_sentiment_scores`/`get_sentiment_freshness_minutes` use only the global timestamp → preserved stale scores receive **zero decay** and pass freshness gates. The per-pair `sentiment_timestamps` exist but are never consumed. | **P6-151 (HIGH):** age per-pair using `sentiment_timestamps`; set global timestamp = max(per-pair ts of *actually updated* pairs); if `get_sentiment_freshness_minutes()` returns `None`, treat as infinitely stale (current code does `or 0.0` → missing timestamp = "perfectly fresh"). |
| P6-152 | LOW | `aggregate_sentiment`'s `valid_scores` is dead code; v3 branch of `load_sentiment_scores` early-returns skipping the log line; missing-cache → neutral 0.0 is acceptable **only** because consumers should freshness-gate — which P6-151 currently breaks. | Clean up; document that 0.0 + stale-gate is the contract. |
| Writer survey | OPEN | Cannot confirm "no other active writers" from this bundle. Strong hint of a second cache lineage: hybrid_rebalancer's default path `~/.trading-bot/sentiment_cache.json` implies something once wrote there. | Provide `grep -rn "sentiment_cache" --include="*.py"` + crontab/systemd timer listing. |

---

### 1.9 phase6/core/trade_ledger.py + harness

| ID | Sev | Finding | Detail / Required Fix |
|---|---|---|---|
| **P6-153** | MED | Two divergent trade-recording systems (TradeLedger JSONL/CSV vs LPM's broken CSV+SQLite, P6-136) with different schemas — no single auditable ledger. TradeLedger itself: no fsync, naive `utcnow`, CSV not escape-safe, and it faithfully records whatever it's given — which, per P6-141, is fabricated fill data. | Designate TradeLedger as canonical; LPM delegates to it; record *verified* fill fields (order_id, filled_size, avg_fill_price, fees) once P6-131/141 land. |
| **P6-154** | **BLOCKER (process)** | Item 6 (runner remainder) arrived as a 15-line docstring fragment; item 9's "backtest harness / integration tests" were **not provided at all**. The central questions of this batch — Fresh Start fires only on verified-zero, reserve deployment path, `get_holdings` vs `get_holdings_verified` call sites — **cannot be verified**. P6-101's Scotty sign-off covers the wrapper sentinel, not the runner's consumption of it. | Re-send full `phase6_runner.py` and any tests. No promotion without it. |

---

## 2. VERIFIED-SENTINEL CONTRACT — UNIFORMITY CHECK (requested focus)

| Surface | Sentinel applied? | Status |
|---|---|---|
| Holdings (`get_holdings_verified`) | ✅ Yes, correct shape, includes holds | CLOSED (P6-101) at client level |
| Balance (`get_account_balance`) | ❌ Returns 0.0 on error | **OPEN — P6-125** |
| Positions (`LPM.get_positions`) | ❌ Method doesn't exist when imported; returns `{}` on error | **OPEN — P6-132/133** |
| Reconcile (`reconcile_positions`) | ❌ Fake-passes when client lacks `get_position` | **OPEN — P6-135** |
| Fresh Start call sites (runner) | ❓ Unreviewable (fragment) | **BLOCKED — P6-154** |

**The contract is NOT uniformly applied.** One of four reviewable surfaces complies.

---

## 3. CONSOLIDATED TOP-RISKS TABLE (ALL BATCHES, OPEN ITEMS)

| Rank | ID | Sev | Area | Summary | Status |
|---|---|---|---|---|---|
| 1 | P6-132/133 | CRITICAL | Positions | `get_positions` not a class method (dead code when imported); empty-on-error violates sentinel; 5-pair hardcode | NEW |
| 2 | P6-140 | CRITICAL | Execution | Live SELL not implemented → one-sided rebalance execution (buys only) | NEW |
| 3 | P6-145 | CRITICAL | Reserve | Reserve checked pre-trade not post-trade; deploy_capital bypasses reserve entirely | NEW |
| 4 | P6-127 | CRITICAL | Pricing | Live `get_price` rounds to 2dp → DOGE/XRP sizing/stops/valuation corrupted | NEW |
| 5 | P6-126 | CRITICAL | Integrity | exchange_client.py truncated / duplicate defs — repo state unverifiable | NEW |
| 6 | P6-118 | HIGH | CR-03 | Protective-order detection uses wrong field names → finds nothing in live | CONFIRMED OPEN |
| 7 | P6-114 | HIGH | CR-03 | No durable suspended-stop journal; canceled-order params discarded; non-atomic rollback | CONFIRMED OPEN |
| 8 | P6-146/148 | HIGH | Sticky holdings | RSI gate + renormalization liquidate/resize existing positions in deploy path | NEW |
| 9 | P6-151 | HIGH | Sentiment | Fresh global timestamp on preserved stale data; per-pair timestamps unused; missing-ts = "fresh" | NEW (supersedes residual of P6-121/122) |
| 10 | P6-147 | HIGH | Cooldown | 24h cooldown enforced only in emergency-recovery branch | NEW |
| 11 | P6-141 | HIGH | Execution | Fabricated fill price/size; SL sized off estimates | NEW |
| 12 | P6-125 | HIGH | Sentinel | Balance error → 0.0 (no verified flag) | CONFIRMED OPEN |
| 13 | P6-134/135/136 | HIGH | LPM | PnL double-count → false breaker; reconciliation theater; trade recording broken (CSV loses rows, DB table missing) | NEW |
| 14 | P6-138 | HIGH | Sentiment | HybridRebalancer reads wrong cache path; fabricated neutral; no freshness gate | NEW |
| 15 | P6-149/150 | HIGH | Config | 3 conflicting reserve definitions; 6-pair config vs 5-pair universes (ADA orphan) | NEW |
| 16 | P6-144 | HIGH | CR-03 | Reattach moves stop levels; failures don't raise; rollback uses stale positions | NEW |
| 17 | P6-128–131 | HIGH/MED | Wrapper/client | Stop-order serialization, reduce_only, NameError in candles, lazy live init, no fill polling | NEW |
| 18 | P6-115/116 | PARTIAL | Quantization | SLM quantizes but metadata hardcoded; adjustment branch bypasses; client undoes it | PARTIAL |
| 19 | P6-108/109 | OPEN | Rebalance | In-memory last_rebalance_time (confirmed, plus set-on-decision); allocation bounds unverifiable (allocation_engine not provided) | OPEN |
| 20 | P6-117 | PARTIAL | Orders | Open-orders endpoint plausible; signing of query-in-path unverified; no shadow parity | PARTIAL |
| 21 | P6-137/142/143/152/153 | MED/LOW | Misc | Risk limits not config-wired; retry gaps; TP null TypeError; ledger duplication | NEW |
| — | P6-101 | CLOSED | Sentinel | Holdings verified sentinel (wrapper level) — Scotty signed, isolation tested | CLOSED |

---

## 4. GO/NO-GO LIVE-SAFETY GATE TABLE (UPDATED)

| Gate | Requirement | Status | Blocking IDs |
|---|---|---|---|
| G1 | Verified sentinel uniform (holdings/balance/positions/reconcile) + Fresh Start only on verified-zero | ❌ FAIL | P6-125, 132, 133, 135, 154 |
| G2 | CR-03 suspend/reattach: real order shapes, durable journal, atomic rollback | ❌ FAIL | P6-114, 118, 144, 117 |
| G3 | Reserve respected in every alloc/rebalance/deploy path | ❌ FAIL | P6-145, 139, 149; runner unseen (154) |
| G4 | Sentiment real + fresh-gated, no fabrication, per-pair aging | ❌ FAIL | P6-151, 138; writer survey open |
| G5 | Order execution: real fills, no fabricated success, sells work or plans refused atomically | ❌ FAIL | P6-140, 141, 131, 142 |
| G6 | Price/size quantization correct for DOGE/XRP, verified live | ❌ FAIL | P6-127, 128, 115/116 |
| G7 | Allocation bounds feasible for universe; sticky holdings + cooldown honored | ❌ FAIL | P6-109 (engine unseen), 146, 147, 148, 150 |
| G8 | Ledger/audit trail durable and truthful; harness exercises live paths | ❌ FAIL | P6-136, 153; harness not provided |
| G9 | Repo integrity: reviewed files == runnable files | ❌ FAIL | P6-126, 132 (merge artifacts), 154 |

**Overall: NO-GO. Zero of nine gates pass.** Do not enable live mode; shadow mode is acceptable for continued testing except that shadow/live parity gaps (P6-117 shadow `[]`, shadow SL always-True) mean shadow results will overstate safety.

---

## 5. FILES STILL REQUIRED (cannot conclude)

1. **phase6/core/exchange_client.py — full, untruncated** (re-send; P6-126).
2. **phase6/core/phase6_runner.py — full file** (the fragment delivered covers nothing requested: Fresh Start, `_handle_fresh_start`, `_perform_daily_rebalance`, holdings call sites, reserve deployment). Hard blocker.
3. **phase6/core/allocation_engine.py** (`compute_inverse_vol_allocations`, `rebalance_plan`) — needed to close P6-109 and verify bounds feasibility for 5 (or 6?) pairs.
4. **coinbase_wrapper_FIXED.py — `_request` method (and `get_accounts`)** — to verify GET-with-query signing (P6-117) and response shapes.
5. **Backtest harness / integration tests** for the above paths (requested in item 9, not delivered) — or explicit confirmation none exist (itself a gate failure).
6. **config/capital_allocation_config.json** (referenced by withdrawal_reserve loader) — to resolve P6-149.
7. **Sentiment writer survey output**: `grep -rn "sentiment_cache" --include="*.py" .` plus crontab/systemd timers, and confirmation of what writes/wrote `~/.trading-bot/sentiment_cache.json`.

Not "ready to conclude" — the runner and exchange client gaps make conclusion impossible by definition, independent of the new CRITICALs.