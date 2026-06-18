# Phase 6 Fable 5 Review — Batch 1 (Tier 1: Risk, Safety, Stop-Loss, Execution)

**Constraints I am enforcing in this review** (restated per manifest): real data only; Fresh Start = bootstrap-only on *verified* zero holdings, never on transient API errors; sticky holdings + proportional rebalancing (no unconditional rebalance away from positions on small sentiment deltas); ~$250 withdrawal reserve respected in all paths; sentiment quality gates + 24h cooldown on recently-stopped pairs; Code Isolation Testing + real-data verification before patch promotion; no live trading code changes until reviewed.

This is the first batch I have seen — there are no prior-batch findings to carry forward.

---

## Top Risks Found So Far (Batch 1)

1. **`get_holdings()` / `get_account_balance()` return empty/zero on API exceptions** — indistinguishable from genuine zero holdings. This is the exact failure mode the Fresh Start constraint prohibits. (P0)
2. **`execute_sell()` is a stub that returns `success: True`** — rebalance plans will report fabricated successful sells in live mode. Violates "real data only" and corrupts every downstream accounting assumption. (P0)
3. **Stop/limit prices rounded to 2 decimals universally** — for XRP/DOGE-class assets the stop price collapses onto (or above) entry, producing meaningless or instantly-triggering stops. (P0 for live low-price assets)
4. **Live-client initialization is dead code** — `_init_live_client()` call is unreachable (stranded after `return` statements inside `_round_size_for_product`), so live mode silently degrades to warn-and-return-False paths instead of failing loudly at startup. (P1)
5. **CR-03 suspend/detect logic doesn't match Coinbase Advanced Trade order schema** (`type` vs `order_type`, top-level `stop_price` doesn't exist) and the coordinator ignores TP orders entirely — live rebalances will fail on held funds and leave orphaned stops. (P1)
6. **SL size/price computed from spot ticker, not actual fill** — fee slippage means the stop-limit sell size can exceed actual holdings and be rejected, leaving positions unprotected while reporting `sl_attached` ambiguity. (P1)
7. **No withdrawal-reserve enforcement anywhere in the Tier-1 execution path.** (P1)
8. **HybridRebalancer fabricates a neutral baseline on first run and on cache failure** — sentiment deltas vs. a fabricated 0.0 baseline can trigger rebalancing of sticky holdings; no sentiment freshness/quality gate; no 24h-cooldown awareness; interval guard is in-memory only. (P1)

---

## Detailed Findings

---

**ID**: P6-101
**Title**: API failures in `get_holdings()`/`get_account_balance()` return empty/zero — indistinguishable from verified zero holdings (Fresh Start trigger hazard)
**Category**: Bug / Safety
**Priority**: High
**Severity**: P0-Critical
**File(s)**: phase6/core/exchange_client.py (`get_holdings`, `get_account_balance`)
**Evidence**:
```python
except Exception as e:
    logger.error(f"Failed to fetch live holdings: {e}")
    return {}
...
except Exception as e:
    logger.error(f"Failed to fetch live balance: {e}")
    return 0.0
```
Also: in live mode with `real_client is None`, `get_holdings()` returns `{}` without even attempting `_ensure_live_client()`.
**Impact on live system**: A transient Coinbase outage, rate-limit, or auth blip makes the bot believe it holds nothing. Any consumer implementing Fresh Start, sticky-holdings checks, orphan-stop verification (`verify_reconciliation` treats `holdings.get(...)==0` as zero balance → flags real stops as "orphans"), or proportional rebalancing will act on fabricated zero-state. Directly violates the "Fresh Start must only trigger on verified zero holdings, never on transient API errors" constraint.
**Recommended Fix**: Raise a typed exception (e.g., `ExchangeDataUnavailable`) or return a sentinel (`None`) on fetch failure; never coerce errors to `{}`/`0.0`. Require callers (Fresh Start gate, verify_reconciliation) to distinguish "verified empty" from "unknown". Add a `verified: bool` wrapper or a `get_holdings_verified()` API.
**Effort**: Medium
**Dependencies**: All callers of `get_holdings`/`get_account_balance` must be audited in later batches (runner, Fresh Start logic).
**Backlog Placement**: New Kanban task — "Tier 1 Safety: typed errors for account/holdings fetch (Fresh Start guard)" — top of Risk/Safety column.

---

**ID**: P6-102
**Title**: `execute_sell()` stub returns `success: True` — fabricated fills propagate into rebalance results
**Category**: Bug / Safety
**Priority**: High
**Severity**: P0-Critical
**File(s)**: phase6/core/order_executor.py (`execute_sell`, `execute_rebalance_plan`)
**Evidence**:
```python
def execute_sell(self, pair: str, size: float) -> Dict[str, Any]:
    self.logger.info(f"[SELL] {pair} size={size} (stub implementation)")
    return {"success": True, "order_id": f"sell-stub-{secrets.token_hex(8)}", ...}
```
`execute_rebalance_plan` calls it for SELL legs and records the fabricated success. Additionally, it passes `usd_amount` into the `size` parameter (unit confusion).
**Impact on live system**: A live rebalance plan with SELL→BUY sequencing will (a) never free USD via sells, (b) report sells as successful so downstream accounting/ledgers record phantom liquidity, (c) attempt BUYs with funds that don't exist. Violates "real data only" — these are fabricated order results outside any labeled isolation test.
**Recommended Fix**: Make `execute_sell` return `success: False, error: "not_implemented"` (fail loudly) in live mode, or hard-block any plan containing SELL legs until implemented. Fix the units (`usd_amount` → convert to base size via real price/holdings). Gate behind Code Isolation Testing before promotion.
**Effort**: Medium
**Dependencies**: P6-101 (real holdings needed to size sells); withdrawal reserve check (P6-107).
**Backlog Placement**: Kanban "Execution Engine" — promote to top: "Implement real execute_sell + block fabricated SELL success".

---

**ID**: P6-103
**Title**: Universal 2-decimal rounding of stop/limit prices breaks stops on sub-dollar assets
**Category**: Bug / Correctness
**Priority**: High
**Severity**: P0-Critical
**File(s)**: phase6/core/stop_loss_manager.py (`attach_stop_loss`, `attach_take_profit`); phase6/core/exchange_client.py (`place_stop_limit_sell` fallback `round(stop_price*0.995, 2)`)
**Evidence**:
```python
stop_price = round(entry_price * (1 - pct), 2)
limit_price = round(stop_price * 0.995, 2)
```
For DOGE at $0.12 with 3% SL: stop = round(0.1164, 2) = **0.12 = entry price** (instant/invalid stop). For XRP at $0.52: stop = 0.50, limit = round(0.4975, 2) = 0.50 → stop == limit, zero slippage buffer, likely unfilled stop-limit in a fast move.
**Impact on live system**: Stops on low-priced assets are either rejected, trigger immediately, or have no fill buffer — positions effectively unprotected or churned. Also `_round_size_for_product` exists but is never applied to `qty` in `place_stop_limit_sell`, so base-size precision violations can reject orders (XRP requires whole-unit handling per the code's own assumption).
**Recommended Fix**: Fetch per-product `price_increment`/`base_increment` from Coinbase product metadata and quantize stop/limit/size to those increments. Validate `stop_price < entry_price` and `limit_price < stop_price` post-rounding; refuse placement otherwise.
**Effort**: Medium
**Dependencies**: Product-metadata fetch in exchange client; isolation test with real product specs.
**Backlog Placement**: Kanban "Stop-Loss Hardening" — new task "Per-product price/size quantization for SL/TP".

---

**ID**: P6-104
**Title**: Live client initialization is unreachable dead code stranded inside `_round_size_for_product`
**Category**: Bug
**Priority**: High
**Severity**: P1-Major
**File(s)**: phase6/core/exchange_client.py (`__init__`, `_round_size_for_product`)
**Evidence**:
```python
def _round_size_for_product(self, product_id: str, qty: float) -> str:
    ...
    else:
        return f"{qty:.2f}"

    if not self.shadow_mode:
        self._init_live_client()   # unreachable
```
`__init__` never calls `_init_live_client()`. Live mode relies entirely on `_ensure_live_client()`, which logs a warning and returns False on missing credentials — unlike `_init_live_client`, which raises.
**Impact on live system**: A live deployment with missing/bad credentials starts "successfully" and then silently no-ops on every order (`{"success": False, "error": "No live client"}`), while shadow-style behavior (e.g., `cancel_order` returning False, `get_open_orders` returning `[]`) masks the failure. Combined with P6-101, this can cascade into false zero-holdings states. Also `_ensure_live_client` omits `private_key.replace("\\n", "\n")` and `sandbox=False`, diverging from `_init_live_client`.
**Recommended Fix**: Move the live-init call into `__init__` (fail fast at construction in live mode); delete the unreachable block; consolidate `_ensure_live_client` and `_init_live_client` into one code path with identical key handling.
**Effort**: Low
**Dependencies**: None.
**Backlog Placement**: Kanban "Exchange Client Cleanup" — immediate hotfix candidate (after isolation test).

---

**ID**: P6-105
**Title**: CR-03 protective-order detection/suspension doesn't match Coinbase Advanced Trade order schema; coordinator ignores TP orders
**Category**: Correctness / Bug
**Priority**: High
**Severity**: P1-Major
**File(s)**: phase6/core/stop_loss_manager.py (`detect_active_protective_orders`, `verify_reconciliation`); phase6/core/stop_loss_coordinator.py (`suspend_protective_orders`)
**Evidence**:
- Manager checks `order.get("type")` and top-level `order.get("stop_price")`; Coinbase Advanced Trade list-orders responses use `order_type` and nest stop parameters under `order_configuration.stop_limit_stop_limit_gtc.stop_price` — neither key matches.
- Coordinator checks `order.get("order_type")` (different key than the manager) and **only** cancels stop-style orders; TP limit sells are never suspended.
- Live `get_open_orders` returns raw Coinbase order dicts, so in live mode detection will likely classify all `SELL` + `LIMIT` orders as TP and detect zero SLs.
**Impact on live system**: During rebalance: open TP limit-sells keep base balance on hold → rebalance SELLs fail with insufficient funds; stop orders that aren't detected become orphans after positions change → `verify_reconciliation` may flag failures (good) but the system has already mis-traded. Two modules disagreeing on field names guarantees at least one is wrong against the live API.
**Recommended Fix**: Build a single normalization layer in the exchange client that maps raw Coinbase orders to a canonical schema (`order_id, product_id, side, order_type, stop_price, limit_price, base_size`) and have both manager and coordinator consume only the canonical form. Coordinator must suspend both SL and TP. Verify against real open-order payloads (real-data verification per constraints) before promotion.
**Effort**: Medium
**Dependencies**: P6-104 (working live client) for real-data verification.
**Backlog Placement**: Kanban "CR-03 Stop Suspend/Reattach" — new blocking subtask "Canonical order schema + TP suspension".

---

**ID**: P6-106
**Title**: SL size/price computed from post-fill spot ticker, not actual fill — stop size can exceed holdings
**Category**: Correctness
**Priority**: High
**Severity**: P1-Major
**File(s)**: phase6/core/order_executor.py (`execute_buy`)
**Evidence**:
```python
price = self.exchange.get_price(pair)
size = usd_amount / price if price > 0 else 0.0
sl_attached = self.stop_loss_manager.attach_stop_loss(pair, price, size)
```
**Impact on live system**: Actual filled base size = (usd_amount − fees)/fill_price, which is ~0.6%+ less than the estimate (taker fee + slippage). The stop-limit sell is placed for more base than held → Coinbase rejects it → position unprotected (logged only as `[PARTIAL]`). If `get_price` returns 0.0 (its failure mode), `size=0` and a zero-size stop is attempted. Entry price used for the SL is also the post-fill ticker, not the fill price, skewing the SL distance.
**Recommended Fix**: After a successful buy, fetch the order by `order_id` (fills endpoint) to get `filled_size` and `average_filled_price`; attach the SL with those real values. If fill data unavailable, use `get_holdings()` delta as fallback. Treat SL-attach failure as an alertable event (retry queue / kill-switch flag), not just a warning.
**Effort**: Medium
**Dependencies**: Exchange client needs `get_order(order_id)`/fills support; P6-103 quantization.
**Backlog Placement**: Kanban "Execution Engine" — "Use real fill data for SL attachment".

---

**ID**: P6-107
**Title**: No withdrawal-reserve (~$250) enforcement in any Tier-1 execution path
**Category**: Safety / Architecture
**Priority**: High
**Severity**: P1-Major
**File(s)**: phase6/core/order_executor.py (`execute_buy`, `execute_rebalance_plan`); phase6/core/rebalancing/hybrid_rebalancer.py (`generate_rebalance_plan`)
**Evidence**: `execute_buy` places `place_market_buy(pair, usd_amount)` with no check of available USD vs. reserve; `generate_rebalance_plan` allocates `target_weights * total_capital` with no reserve carve-out; no reference to any reserve constant anywhere in the batch.
**Impact on live system**: A rebalance plan or sequence of buys can spend the cash buffer below the $250 withdrawal reserve — direct violation of a standing constraint, and removes the operational safety margin for withdrawals/fees.
**Recommended Fix**: Add a `ReserveGuard` (single source of truth, config-driven, default $250): `deployable = max(0, usd_balance - reserve)`; clamp every BUY leg and total plan notional to `deployable`; refuse plans that would breach it and log the clamp. Enforce at OrderExecutor level (last line of defense), not only at planner level.
**Effort**: Medium
**Dependencies**: P6-101 (trustworthy balance reads).
**Backlog Placement**: Kanban "Risk/Safety" — new task "ReserveGuard enforcement in executor + planner" (blocking for live).

---

**ID**: P6-108
**Title**: HybridRebalancer fabricates neutral sentiment baselines and lacks freshness/quality gates and cooldown awareness
**Category**: Correctness / Safety
**Priority**: High
**Severity**: P1-Major
**File(s)**: phase6/core/rebalancing/hybrid_rebalancer.py (`_load_sentiment`, `evaluate`)
**Evidence**:
```python
if previous_sentiment is None:
    previous_sentiment = {k: 0.0 for k in current_sent}  # first run baseline
...
logger.warning("Sentiment cache missing, neutral scores")
return {sym: 0.0 for sym in universe}
```
No timestamp/staleness check on the cache; no source-quality gate; no 24h-cooldown check for recently stopped pairs.
**Impact on live system**: (a) First run after restart: deltas = |current_score − 0.0|; any pair with sentiment ≥ 0.15 crosses the hard threshold and (given the weak AI filter, see P6-110) can trigger a rebalance of *existing sticky holdings* off a fabricated baseline — violating both "real data only" and "sticky holdings". (b) A missing/corrupt cache fabricates 0.0 for all pairs, which against a real previous baseline manufactures large deltas. (c) Stale cached scores pass silently. (d) Recently-stopped pairs are not excluded for 24h.
**Recommended Fix**: Persist and load real previous sentiment (durable file/DB) — if no verified prior baseline exists, return `should_rebalance=False, reason="no baseline"` rather than fabricating one. On cache load: validate timestamp freshness (configurable max age) and quality flags; treat stale/missing as "no signal — hold" rather than 0.0. Inject a cooldown registry of recently-stopped pairs and zero out / exclude their triggers for 24h.
**Effort**: Medium
**Dependencies**: Sentiment cache schema (need files from sentiment tier); cooldown registry (likely later batch).
**Backlog Placement**: Kanban "Rebalancing" — "Sentiment baseline durability + freshness gate + cooldown integration" (blocking for live rebalancer).

---

**ID**: P6-109
**Title**: `generate_rebalance_plan` unconditionally rebalances to target weights — no sticky-holdings / proportional dampening
**Category**: Architecture / Safety
**Priority**: High
**Severity**: P1-Major
**File(s)**: phase6/core/rebalancing/hybrid_rebalancer.py (`generate_rebalance_plan`)
**Evidence**:
```python
target_usd = {k: v * total_capital for k, v in target_weights.items()}
...
action = "BUY" if diff > 0 else "SELL"
```
Any existing position not in `target_weights` gets `tgt=0` → never appears in the loop (it iterates `target_usd`), so it's silently ignored — but positions *in* targets are sold/bought to exact target with only a $25 dust filter. A single 0.15 sentiment delta can therefore drive full reallocation away from held positions.
**Impact on live system**: Violates the sticky-holdings + proportional-rebalancing constraint: small sentiment deltas → full-magnitude SELLs of existing positions. Also note positions absent from `target_weights` are never explicitly held *or* sold — ambiguous behavior that should be an explicit "sticky hold".
**Recommended Fix**: Implement proportional adjustment: move only a configurable fraction (e.g., 25–50%) of the gap per cycle, scale move size by signal magnitude/confidence, never SELL below a sticky floor on existing positions absent a hard risk trigger (stop/drawdown), and explicitly enumerate held-but-untargeted pairs as `HOLD` for audit logs.
**Effort**: Medium
**Dependencies**: P6-108 (trustworthy deltas), allocation engine (later batch — please include it).
**Backlog Placement**: Kanban "Rebalancing" — "Proportional/sticky rebalance plan generator".

---

**ID**: P6-110
**Title**: AI filter is near-vacuous (passes by construction when any threshold fired) and interval guard is non-durable
**Category**: Correctness
**Priority**: Medium
**Severity**: P2-Moderate
**File(s)**: phase6/core/rebalancing/hybrid_rebalancer.py (`_ai_filter`, `evaluate`)
**Evidence**: `volatility_ok` is hardcoded `True`; `drawdown_ok = drawdown < threshold*1.5` (a drawdown that *triggered* the hard threshold still counts as "ok" up to 12%); so confidence is ≥ 2/3 ≈ 0.67 > 0.6 whenever sentiment fired — the filter effectively always passes. Separately, `self.last_rebalance_time` is in-memory only and is set in `evaluate()` even if the caller never executes the plan.
**Impact on live system**: The "second layer" gate provides no real protection (false sense of safety in review docs/logs). Process restart resets the 24h interval guard → rebalances can occur far more frequently than `min_rebalance_interval_hours`, compounding P6-108/P6-109. Setting the timestamp at decision time (not execution time) means a failed execution blocks retries for 24h.
**Recommended Fix**: Persist `last_rebalance_time` durably (file/DB) and set it only after confirmed execution (caller callback `mark_executed()`). Wire `volatility_ok` to real ATR/regime inputs (ATRCalculator/RegimeDetector exist and are unused here); make `drawdown_ok` strictly `drawdown < drawdown_threshold`.
**Effort**: Low
**Dependencies**: P6-108.
**Backlog Placement**: Kanban "Rebalancing" — "Durable rebalance timestamp + real AI-filter inputs".

---

**ID**: P6-111
**Title**: `get_recent_prices` cache-hit path raises UnboundLocalError (`datetime` imported inside function after use) and uses `.seconds` instead of `.total_seconds()`
**Category**: Bug
**Priority**: High
**Severity**: P1-Major
**File(s)**: phase6/core/exchange_client.py (`get_recent_prices`)
**Evidence**:
```python
if cache_key in self._price_cache:
    cached_time, cached_data = self._price_cache[cache_key]
    if (datetime.now() - cached_time).seconds < 300:   # datetime not yet bound
...
try:
    import requests
    from datetime import datetime, timedelta, timezone   # local import AFTER use
```
Because `datetime` is assigned later in the same function scope, the cache-hit reference is an unbound local → `UnboundLocalError` on every second call within any window. The exception escapes (cache check is outside the `try`). Also `.seconds` wraps for deltas ≥ 1 day.
**Impact on live system**: Any consumer (ATR/regime/correlation feeds) calling `get_recent_prices` twice crashes its calling loop or, if callers blanket-catch, silently loses price history — degrading risk signals built on real data. The "rate-limit aware" cache never functions.
**Recommended Fix**: Move `datetime` imports to module top; use `.total_seconds()`; add a unit test that calls twice with a warm cache (Code Isolation Testing).
**Effort**: Low
**Dependencies**: None.
**Backlog Placement**: Kanban "Exchange Client Cleanup" — quick fix, same PR as P6-104.

---

**ID**: P6-112
**Title**: OrderExecutor retry logic never fires for buys — exchange client swallows exceptions into `{"success": False}` dicts
**Category**: Correctness
**Priority**: Medium
**Severity**: P2-Moderate
**File(s)**: phase6/core/order_executor.py (`_retry_with_backoff`, `execute_buy`); phase6/core/exchange_client.py (`place_market_buy`)
**Evidence**: `_retry_with_backoff` retries only on raised exceptions; `place_market_buy` catches all exceptions and returns `{"success": False, "error": ...}` — which `_retry_with_backoff` treats as a successful call and returns immediately on attempt 1.
**Impact on live system**: The advertised 3-attempt exponential backoff is dead for the live buy path; transient rate-limits/timeouts cause immediate plan-leg failure. Misleading robustness claims in logs (`max_retries=3`).
**Recommended Fix**: In `_retry_with_backoff`, treat `result.get("success") is False` as retryable for transient error classes (`rate_limit`, `timeout`), or let the exchange client raise typed exceptions and retry at the executor. Pick one error-propagation convention across the stack.
**Effort**: Low
**Dependencies**: Align with P6-101 typed-error work.
**Backlog Placement**: Kanban "Execution Engine" — "Unify error propagation + make retries effective".

---

**ID**: P6-113
**Title**: SL + TP both placed for full position size — second order rejected on held funds (no OCO); `reduce_only` likely invalid for spot
**Category**: Correctness
**Priority**: Medium
**Severity**: P2-Moderate
**File(s)**: phase6/core/stop_loss_manager.py (`attach_stop_loss`, `attach_take_profit`); phase6/core/exchange_client.py (`place_stop_limit_sell`)
**Evidence**: Both `attach_stop_loss` and `attach_take_profit` sell the full `size`; Coinbase spot puts base size on hold for the first open sell, so the second placement fails on insufficient available balance (no OCO/bracket support is used). Additionally `"reduce_only": True` in `stop_limit_stop_limit_gtc` is not a supported spot order field and may cause `INVALID_ORDER_CONFIGURATION` rejections of the stop itself.
**Impact on live system**: Either the TP or the SL silently fails on every position that attempts both, leaving one leg of protection missing; if `reduce_only` triggers rejection, *no* stop is ever placed live despite shadow tests passing (shadow path never exercises the schema).
**Recommended Fix**: Remove `reduce_only`; verify the exact `stop_limit_stop_limit_gtc` body against the live API with a 1-unit isolation test (real-data verification before promotion). Decide a protection policy: SL-only native + TP managed in software, or split size between SL/TP, or use Coinbase trigger-bracket orders if available.
**Effort**: Medium
**Dependencies**: P6-105 canonical schema work; live API verification window.
**Backlog Placement**: Kanban "Stop-Loss Hardening" — "Validate live stop-limit schema + SL/TP hold-conflict policy".

---

**ID**: P6-114
**Title**: Coordinator's "atomic" rollback re-attaches against *new* target positions with no record of original suspended orders, and tolerates silent reattach failures
**Category**: Architecture / Safety
**Priority**: High
**Severity**: P1-Major
**File(s)**: phase6/core/stop_loss_coordinator.py (`suspend_protective_orders`, `suspend_reattach_context`)
**Evidence**:
```python
self._suspended_orders = {p: [] for p in pairs}   # discards canceled order details
...
except Exception as exc:
    ...
    self.reattach_protective_orders(new_positions)  # rollback uses NEW positions
```
Also: in the success path, `reattach_protective_orders` results with `status: "failed"`/`"skipped"` are merely logged — no exception, no alert, context exits "successfully".
**Impact on live system**: If the rebalance fails mid-way, restoration is computed from intended *post*-rebalance positions (which may not exist) instead of the original stop parameters (price/size) that were canceled — original protection is unrecoverable. If reattach partially fails after a successful rebalance, positions are left live and unprotected with only an INFO log. Note also `entry_price: 0.0` from `get_enriched_positions` is falsy, so reattach silently bases SLs on `current_price` — entry-relative stops drift after rebalances.
**Recommended Fix**: Record full canceled-order parameters (stop/limit price, size, product) at suspend time; on rollback, restore *those* orders against actual current holdings. After reattach, run `verify_reconciliation` inside the context and raise/alert on any `failed`/`skipped` pair or orphan. Make "position live without protection" a paged P0 operational alert.
**Effort**: Medium
**Dependencies**: P6-105 (canonical order schema to capture original params), P6-106 (real fill prices for entry).
**Backlog Placement**: Kanban "CR-03 Stop Suspend/Reattach" — "True restore-from-snapshot rollback + post-reattach verification" (blocking for live).

---

**ID**: P6-115
**Title**: Shadow exchange never mutates simulated balances/positions on buys — shadow tests can't validate sticky holdings, reserve, or reconciliation
**Category**: Correctness / Testing
**Priority**: Medium
**Severity**: P2-Moderate
**File(s)**: phase6/core/exchange_client.py (`place_market_buy` shadow path, `_positions`, `_balances`, shadow `get_open_orders`)
**Evidence**: Shadow `place_market_buy` only appends to `_order_log`; `_positions` and `_balances["USD"]` are never updated; shadow `get_open_orders` returns `[]` so CR-03 detection/suspension is untestable in shadow.
**Impact on live system**: Indirect but important: the shadow harness — the system's primary pre-live verification per constraints — cannot exercise reserve enforcement, sticky holdings, hold-conflict (P6-113), or CR-03 detection logic. Bugs like P6-105/P6-113 sail through shadow and first manifest in live.
**Recommended Fix**: Make shadow mode stateful: debit USD (incl. simulated fee), credit positions, track open SL/TP orders in `_order_log`-backed `get_open_orders`, support `cancel_order` against them. This is explicitly an isolation-test fixture (clearly labeled simulated data), consistent with constraints.
**Effort**: Medium
**Dependencies**: None; unblocks isolation testing for P6-105/107/113/114.
**Backlog Placement**: Kanban "Testing Infrastructure" — "Stateful shadow exchange (balances, positions, open orders)".

---

**ID**: P6-116
**Title**: Duplicate `get_open_orders` definitions; first (stub) silently shadowed by second
**Category**: Code Quality
**Priority**: Low
**Severity**: P3-Nit
**File(s)**: phase6/core/exchange_client.py
**Evidence**: Two `def get_open_orders(...)` definitions; Python keeps only the later one. The earlier "live stub" body and its log line are dead code that misleads readers/auditors about live behavior. Also `__import__('secrets')` in `place_market_buy` despite top-level `import secrets`.
**Impact on live system**: None functionally today, but high audit-confusion risk; a future refactor reordering methods would silently swap real implementation for the stub.
**Recommended Fix**: Delete the stub definition and the `__import__` indirection; add a lint rule (e.g., `pylint` `function-redefined`) to CI.
**Effort**: Low
**Dependencies**: Bundle with P6-104/P6-111 cleanup PR.
**Backlog Placement**: Kanban "Exchange Client Cleanup".

---

**ID**: P6-117
**Title**: RegimeDetector trend check overwrites volatility regime label after adjustments were applied
**Category**: Correctness
**Priority**: Low
**Severity**: P3-Nit
**File(s)**: phase6/core/risk/regime_detector.py (`detect`)
**Evidence**: The final trend block sets `result["regime"] = "TRENDING"` unconditionally (for both up and down 3% MA divergence), overwriting `HIGH_VOL`/`HIGH_CORR` labels while keeping their adjustments — label and adjustments become inconsistent; also up- vs down-trend are indistinguishable.
**Impact on live system**: Downstream consumers keying off `regime` will misclassify high-vol trending markets; logging/audit trail becomes misleading.
**Recommended Fix**: Return a regime *set*/flags (`{"HIGH_VOL", "TRENDING_UP"}`) or precedence-ordered composite; distinguish trend direction.
**Effort**: Low
**Dependencies**: Consumers of `detect()` (later batches).
**Backlog Placement**: Kanban "Risk Engine polish".

---

**ID**: P6-118
**Title**: Correlation circuit-breaker "reserve redeploy" action has no reserve-floor guard
**Category**: Safety
**Priority**: Low
**Severity**: P3-Nit
**File(s)**: phase6/core/risk/correlation_circuit_breaker.py
**Evidence**: Actions specify `reserve_redeploy_pct: 0.15` with no reference to the $250 withdrawal-reserve floor; whether the consumer respects it is unverifiable from this batch.
**Impact on live system**: If the action consumer redeploys from the cash reserve, it can breach the withdrawal-reserve constraint.
**Recommended Fix**: Document and enforce that "reserve redeploy" means redeploying the *risk-reduction proceeds*, never the withdrawal reserve; route through the ReserveGuard from P6-107.
**Effort**: Low
**Dependencies**: P6-107; need the consumer of these actions (later batch).
**Backlog Placement**: Kanban "Risk/Safety" — fold into ReserveGuard task acceptance criteria.

---

## Immediate P0/P1 Summary

| ID | Issue | Why it matters now |
|---|---|---|
| P6-101 | API errors → fabricated zero holdings/balance | Fresh Start / reconciliation can fire on transient errors — direct constraint violation |
| P6-102 | `execute_sell` fabricates success | Live rebalance corrupts accounting; fabricated data |
| P6-103 | 2dp price rounding | Stops on XRP/DOGE-class assets are broken or instant |
| P6-104 | Live init dead code | Live mode silently degrades instead of failing fast |
| P6-105 | Order schema mismatch + TP not suspended | CR-03 will fail against real Coinbase responses |
| P6-106 | SL sized from ticker, not fills | Stop rejection → unprotected positions |
| P6-107 | No $250 reserve enforcement | Standing constraint not implemented anywhere in Tier 1 |
| P6-108 | Fabricated sentiment baselines, no freshness/cooldown | Spurious rebalances of sticky holdings |
| P6-109 | Unconditional rebalance to targets | Sticky-holdings constraint violated by design |
| P6-111 | `get_recent_prices` crashes on cache hit | Risk-signal price feeds break in production loops |
| P6-114 | Non-atomic rollback, silent reattach failures | Positions left unprotected after failed rebalance |

**Go/no-go view**: This batch is **not live-safe**. P6-101/102/103 are hard blockers; P6-105/106/107/114 are blockers for any live rebalance involving protective orders.

---

## Files Needed Next

To close out cross-cutting findings I specifically need (in addition to the planned tiers):
- The **Fresh Start / bootstrap** logic and the **runner/orchestrator** that calls `get_holdings()` (to confirm P6-101 blast radius).
- `coinbase_wrapper_FIXED.py` (`_request`, `get_accounts`) to verify schema assumptions in P6-105/P6-113.
- The **allocation engine** and any consumer of `CorrelationCircuitBreaker` actions and `RegimeDetector` output.
- The **sentiment cache writer** (schema + timestamps) for P6-108.
- Any **durable state / ledger** module (last_rebalance_time, suspended-order snapshots).

**Please provide Batch 2.**