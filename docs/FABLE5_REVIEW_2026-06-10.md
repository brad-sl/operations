# Fable 5 External Code Review — Phase 6 (2026-06-10)

**Model**: anthropic/claude-fable-5 (via OpenRouter → Amazon Bedrock)
**Total cost for Batch 0**: ~$0.98 (28.7k prompt + 14k completion tokens, ~3k reasoning)
**Status**: Batch 0 (Tier 0 — Core Runtime) complete. Output truncated at max_tokens; key P0 findings captured below. Remaining Batch 0 analysis + Batches 1-6 pending on request.

**Package used**: `reviews/Phase6_Fable5_Code_Review_Package/` (MANIFEST, BATCH_PLAN, review_driver.py)

**Process followed**:
- Reviewer fed strict rubric + standing constraints (real data only, Fresh Start bootstrap-only, sticky rebalancing from actual holdings, withdrawal reserve, sentiment aging + quality gates, Code Isolation Testing, durable tracking).
- Tier 0 files supplied as Batch 0.
- Model required to surface top risks immediately + request next batch.

## Top Findings from Batch 0 (Critical — P0)

### P6-001 (Highest — Block live rebalancing)
**Title**: Currency-key + unit mismatch corrupts the entire daily rebalance pipeline (coin quantities treated as USD; "BTC" vs "BTC-USD" keys)
**Category**: Bug / Correctness
**Priority**: High | **Severity**: P0-Critical
**Files**: phase6_runner.py (_perform_daily_rebalance / norm_positions), exchange_client.py (get_enriched_positions), deploy_capital.py, allocation_engine.py (rebalance_plan)

**Core Issue**: `get_enriched_positions()` returns data keyed by bare currency ("BTC", "DOGE") with `amount` = coin quantity. The runner treats `amount` as USD dollars and feeds mismatched keys ("BTC" vs "BTC-USD") into sentiment lookups, `deploy_capital`, and `rebalance_plan`.

**Consequences**:
- Sentiment always falls back to 0 for existing positions (gates bypassed).
- Existing holdings re-treated as "new pairs".
- Every rebalance generates plans to fully sell the book + buy the "-USD" twins.
- Invalid `product_id="BTC"` orders in live; wild sizing errors driven by high-unit coins like DOGE/XRP.

**Impact**: Direct capital loss via churn, broken sticky rebalancing, nonsense order sizes on every daily cycle.

**Fix Recommendation**: Normalize at the boundary to `-USD` keys using `value_usd` only. Add strong assertions before any allocation/rebalance call. Isolation test: enriched holdings matching targets → zero moves.

**Backlog**: **Immediate — do not run another live rebalance until fixed.** (S effort + S for tests)

### P6-002
**Title**: Withdrawal reserve enforcement is dead code (NameError swallowed, rebalance always continues)
**Priority**: High | **Severity**: P0-Critical

**Evidence**: Undefined `reserve_check` in f-string → NameError caught → logs "skipped" → rebalance proceeds. Check also called with empty targets, and `new_capital` can include reserve dollars.

**Impact**: The documented ~$250 withdrawal reserve can actually be spent. Standing constraint violated in the main path.

**Fix**: Fix the f-string, pass real data to `enforce_withdrawal_reserve`, compute hard `deployable = usd_balance - reserve`, block on violation with proper early return + test.

**Backlog**: Immediate — before next live rebalance (XS–S).

### P6-003
**Title**: `cancel_order` is an empty placeholder — stop-loss suspension is a silent no-op
**Priority**: High | **Severity**: P0-Critical
**File**: exchange_client.py

**Evidence**: `def cancel_order(...)` body is only the docstring (returns `None`). Stop-loss coordinator / suspend paths rely on it for CR-03 stop management.

**Impact**: Rebalance SELLs can fail "insufficient available" because old stops still hold the base. Protective order state becomes inconsistent, risking unprotected positions or duplicate stops.

**Fix**: Implement real `/batch_cancel`, return explicit bool, treat failures as hard (abort rebalance + alert). Verify via `get_open_orders`.

**Backlog**: Immediate — gates all live rebalancing (S effort).

### P6-004 (and related)
**Title**: Fresh Start can trigger on transient API failure — exceptions coerced to "zero holdings"
**Priority**: High | **Severity**: P0-Critical

**Evidence**: `LivePortfolioManager.refresh()` swallows all exceptions → `positions = {}`. `get_holdings` returns `{}` on error or missing client. Runner treats this as "no positions" → `_handle_fresh_start()`.

**Impact**: A single 5xx or transient unavailability at startup with real cash in account causes full duplicate basket deployment on top of invisible existing positions.

Additional notes from model reasoning:
- `self._force_next_rebalance = True` hardcoded → every restart (including crash loops) forces immediate rebalance.
- Fresh Start path uses synthetic volatilities (hardcoded 0.65) and deploys full cash (bypassing deployable calculations and the 250 reserve threshold).
- SELL execution doesn't check success before counting as executed.
- State writes non-atomic in multiple places.

**Fixes needed**: Distinguish verified-empty from unknown/error (raise/return sentinel instead of swallowing). Guard the force flag. Use real ATR/vol data. Respect withdraw reserve + deployable cash everywhere. Add success checks on order results.

## Systemic Patterns Noted (Partial)
- Multiple points where real vs. synthetic data boundaries are blurred or exceptions hide reality.
- Key/representation drift between Coinbase response shapes and internal FIXED_UNIVERSE / sentiment maps.
- Safety-critical paths (reserve, stop suspension, Fresh Start guard) are either broken or easily bypassed by errors.
- Hardcoded "force" behaviors that amplify restart storms.

## Positive Observations (from this batch)
- Clean separation of shadow/live in the exchange client.
- Good use of dataclasses for signals.
- Intent around capital-deployment logic and emergency recovery paths is clearly visible and mostly well-commented.
- `deploy_capital` has the right shape of thresholds and quality gates (once the upstream data it receives is fixed).

## Immediate Recommended Actions
1. Do **not** run live rebalancing until P6-001 and P6-002 are addressed and Code-Isolation-Tested.
2. Fix the key-normalization boundary + assertions first (biggest blast radius).
3. Implement real `cancel_order` + make callers treat failures seriously.
4. Hardening around Fresh Start detection (verified empty only).
5. After fixes, request full Batch 1 (risk / hybrid_rebalancer / stop_loss_manager + coordinator) from Fable 5.

Remaining Batch 0 content was truncated (max_tokens). We can request continuation of Tier 0 or move straight to Batch 1 (the safety-critical risk/SL/rebalance files) as user directs.

Raw response saved: `reviews/Phase6_Fable5_Code_Review_Package/fable5_batch0_response.md` + full JSON.

Next: Ingest these P0s into `MASTER_TASK_TRACKING.md` + create handoff docs for the immediate blockers (on user approval). Ready to fire Batch 1 on command.