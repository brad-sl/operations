# Fable 5 Batch 0 Response (Tier 0 - Core)

Timestamp: 2026-06-10 15:56

# Phase 6 Code Review — Batch 0 (Tier 0: Core Runtime & Decision Loop)

Reviewed: `phase6_runner.py`, `deploy_capital.py`, `signal_generator.py`, `allocation_engine.py`, `live_portfolio_manager.py`, `exchange_client.py`

This batch contains **multiple P0 findings that would lose money or place wrong orders in live mode**. The daily rebalance path in particular is, as written, not safe to run live. Findings follow, ranked by severity.

---

**ID**: P6-001
**Title**: Currency-key + unit mismatch corrupts the entire daily rebalance pipeline (coin quantities treated as USD; "BTC" vs "BTC-USD" keys)
**Category**: Bug / Correctness
**Priority**: High
**Severity**: P0-Critical
**File(s)**: `phase6_runner.py` (`_perform_daily_rebalance`, norm_positions block); `exchange_client.py` (`get_enriched_positions`); `deploy_capital.py`; `allocation_engine.py` (`rebalance_plan`)
**Evidence**: `get_enriched_positions()` returns `{ "BTC": {"amount": <coin qty>, "value_usd": ...} }` — keyed by **currency**, not pair. The runner then does:
```python
norm_positions[k] = float(v.get("amount", v.get("usd_value", 0.0)))
```
This extracts `amount` (**coin quantity**, e.g. `0.004` BTC or `800` DOGE) and treats it as **dollars** in `total_cash`, `deploy_capital`, and `rebalance_plan`. Worse, keys are `"BTC"` while `sentiment_scores`, `candidate_pairs`, and `FIXED_UNIVERSE` use `"BTC-USD"`. Consequences:
1. Sentiment lookups for existing positions always return the `0.0` default (sentiment gates silently bypassed for held assets).
2. `deploy_capital` sees `"BTC-USD" not in ["BTC", ...]` → existing holdings are re-selected as "new pairs".
3. `rebalance_plan` unions `"BTC"` (current) and `"BTC-USD"` (target) → plans a **full SELL of every existing holding** (target 0) plus a BUY of the "-USD" twin, every rebalance.
4. Sell legs are issued with `product_id="BTC"` — an invalid product — so behavior in live is a mix of rejected orders and nonsense sizing, with DOGE/XRP (high unit counts) wildly over-weighted in the math.
**Impact on live system**: Every daily rebalance computes targets from garbage units, attempts to liquidate the whole book, and bases capital math on coin counts instead of USD. Direct capital loss via churn, mis-sized orders, and broken sticky rebalancing.
**Recommended Fix**: Normalize once at the boundary: build `norm_positions = {f"{cur}-USD": data["value_usd"] for cur, data in enriched.items()}`. Add an assertion layer (`assert all(k.endswith("-USD"))`, `assert sum(values) ≈ portfolio_usd ± tolerance`) before calling `deploy_capital`/`rebalance_plan`. Add an isolation test: enriched fixtures → plan must produce zero moves when holdings already match targets.
**Confidence**: High
**Estimated Effort**: S (fix) + S (tests)
**Dependencies / Preconditions**: None
**Suggested Backlog Placement**: **Immediate — do not run another live rebalance until fixed.**

---

**ID**: P6-002
**Title**: Withdrawal reserve enforcement is dead code — NameError swallowed by except, then rebalance proceeds
**Category**: Bug / Security-Risk
**Priority**: High
**Severity**: P0-Critical
**File(s)**: `phase6_runner.py` `_perform_daily_rebalance` (reserve block)
**Evidence**:
```python
if not info.get("allowed", True):
    logger.warning(f"[HARDENING] Withdrawal reserve violation: {reserve_check}")
    return
except Exception as e:
    logger.warning(f"[HARDENING] Withdrawal reserve check skipped: {e}")
```
`reserve_check` is undefined. The exact moment a violation is detected, the f-string raises `NameError`, the `except` logs "check skipped," and **the rebalance continues**. The protective `return` is unreachable. Additionally, the check is called with `target_allocations_usd={}` (nothing to evaluate) and `new_capital=min(rebalance_cap, cash)` later includes reserve dollars — so the $250 reserve can actually be deployed.
**Impact on live system**: The standing-constraint withdrawal reserve (~$250) is not enforced at all on the daily rebalance path; reserve funds can be spent into positions.
**Recommended Fix**: Replace `{reserve_check}` with `{info}`; pass real target allocations; compute `deployable = max(0, usd_balance - min_reserve_usd)` and cap `new_capital` by it; add a unit test asserting the function returns early on violation (the bug would have been caught by any test of the violation branch).
**Confidence**: High
**Estimated Effort**: XS–S
**Dependencies / Preconditions**: `enforce_withdrawal_reserve` semantics (request file in Batch 1)
**Suggested Backlog Placement**: **Immediate — before next live rebalance.**

---

**ID**: P6-003
**Title**: `cancel_order` is an empty placeholder — stop-loss suspension cannot actually cancel anything
**Category**: Bug / Security-Risk
**Priority**: High
**Severity**: P0-Critical
**File(s)**: `exchange_client.py` (`cancel_order`)
**Evidence**:
```python
def cancel_order(self, order_id: str) -> bool:
    """Cancel a specific order by ID. Placeholder."""
def get_open_orders(self, pair: str = None) -> list:
```
The method body is only a docstring → returns `None`. If `StopLossManager.suspend_active_protective_orders` / the coordinator rely on this (strongly implied by CR-03 wiring), suspension is a silent no-op. On Coinbase, open stop-limit sells **hold the base currency** — rebalance SELLs will then fail with insufficient available balance, or the system will believe stops were removed/re-attached when the old ones remain (risking duplicate stops or unprotected positions depending on the coordinator's bookkeeping).
**Impact on live system**: The entire suspend→trade→re-attach safety choreography is built on a function that does nothing; rebalance order failures and inconsistent protective-order state are near-certain in live.
**Recommended Fix**: Implement against `/api/v3/brokerage/orders/batch_cancel`, return explicit `bool`, and have callers treat `None`/`False` as hard failure (abort rebalance body, alert via notifier). Verify cancel via `get_open_orders` before proceeding.
**Confidence**: High (no-op is certain; downstream usage to confirm in Batch 1)
**Estimated Effort**: S
**Dependencies / Preconditions**: `stop_loss_manager.py`, `stop_loss_coordinator.py` (Batch 1)
**Suggested Backlog Placement**: **Immediate — gates all live rebalancing.**

---

**ID**: P6-004
**Title**: Fresh Start can trigger on transient API failure — exceptions are coerced into "zero holdings"
**Category**: Bug / Security-Risk
**Priority**: High
**Severity**: P0-Critical
**File(s)**: `live_portfolio_manager.py` (`refresh`), `exchange_client.py` (`get_holdings`, `get_account_balance`), `phase6_runner.py` (`run`)
**Evidence**: `refresh()` does `except Exception: self.positions = {}`; `get_holdings()` returns `{}` both when there are genuinely no holdings, when `real_client` is None, and on API errors. `run()` then does `if not has_positions: self._handle_fresh_start()`. Standing constraint: *Fresh Start is bootstrap-only (truly zero holdings)*. A startup API hiccup with ≥$800 cash sitting in the account triggers a full duplicate basket deployment on top of unseen existing positions.
**Impact on live system**: Double-deployment of capital, reserve blown, duplicate exposure — a single 5xx from Coinbase at startup is enough.
**Recommended Fix**: Distinguish "verified empty" from "unknown": `get_holdings()` should raise or return `None` on error; `refresh()` must propagate failure; Fres