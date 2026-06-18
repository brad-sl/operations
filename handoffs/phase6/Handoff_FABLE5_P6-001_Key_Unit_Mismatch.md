# FABLE5 Review Handoff: P6-001 — Currency-Key + Unit Mismatch (P0-Critical)

**Task ID**: FABLE5-P6-001  
**Priority**: P0-Critical (blocks all live rebalancing)  
**Parent**: Fable 5 External Review 2026-06-10  
**Handoff Date**: 2026-06-10  
**Assigned To**: crypto-engineer (primary fixer) + Scotty integration review  
**Source**: Fable 5 Batch 0 review (anthropic/claude-fable-5)

---

## Objective
Normalize position data at the Coinbase boundary so that the entire daily rebalance / deploy_capital / allocation pipeline works with consistent `-USD` pair symbols and **USD values only** (never coin quantities). This is the highest-leverage bug found — every rebalance currently plans nonsense full liquidations and produces invalid orders.

---

## Current State / Evidence (from Fable 5)
- `exchange_client.py:get_enriched_positions()` returns `{ "BTC": {"amount": 0.004, "value_usd": 420}, "DOGE": ... }` (bare currency + coin qty).
- `phase6_runner.py:_perform_daily_rebalance` does:
  ```python
  norm_positions[k] = float(v.get("amount", v.get("usd_value", 0.0)))
  ```
- `sentiment_scores`, `FIXED_UNIVERSE`, `candidate_pairs` all use "BTC-USD".
- Result: Sentiment lookup always 0.0 for current holdings; existing positions treated as new pairs; rebalance_plan unions mismatched keys → full SELL every position + BUY for the twin; `product_id="BTC"` (invalid); DOGE unit counts (e.g. 800) massively over-weight the math.
- Standing constraint violation: completely destroys sticky rebalancing from actual observed holdings.

Affected files (primary):
- phase6/core/phase6_runner.py (especially `_perform_daily_rebalance` and norm_positions block)
- phase6/core/exchange_client.py (get_enriched_positions + callers)
- phase6/scripts/deploy_capital.py
- phase6/core/allocation_engine.py (rebalance_plan)

Secondary ripple: signal_generator, live_portfolio_manager, any place that consumes positions.

---

## Must Do
- At the **data boundary only** (in or immediately after get_enriched_positions or a new normalize_positions() helper), convert to the canonical form:
  ```python
  norm_positions = {f"{cur}-USD": float(data.get("value_usd", 0.0)) for cur, data in enriched.items()}
  ```
- Add hard runtime assertions right after normalization (before any allocation/rebalance call):
  - All keys end with "-USD"
  - sum(values) ≈ portfolio total value (± small tolerance, e.g. 1%)
  - No bare currencies left
- Create (or update existing) **Code Isolation Test** (in scripts/ or phase6/tests/) that feeds realistic enriched position fixtures and asserts:
  - Same holdings → zero-move rebalance plan
  - Correct USD values flow into deploy_capital() and rebalance_plan()
- Ensure the normalized dict (USD values, -USD keys) is what gets passed to `_handle_fresh_start`, deploy_capital, signal decisions, sentiment gating, etc.
- Preserve the distinction between "value_usd" and raw amount everywhere downstream.
- Update any comments/logs that claim "inverse vol from real data" once the data is actually correct.
- Update MASTER_TASK_TRACKING.md and close the Kanban card only after a clean isolation test + runner dry-run shows sensible plans.

---

## Must Not Do / Touch
- Do **not** "fix" by changing FIXED_UNIVERSE or sentiment keys to bare currencies.
- Do **not** start calling the exchange more frequently to "work around" this.
- Do **not** touch stop-loss, dashboard, or unrelated risk code in this task.
- Do **not** normalize using `amount` (coin qty) under any circumstance in the rebalance path.
- Do **not** skip the isolation test with real-structure fixtures.

---

## Expected Deliverables
- Clean normalized boundary in exchange_client.py (or a small dedicated normalizer module).
- Updated phase6_runner.py (the norm_positions block + assertion calls).
- New/updated isolation test script that proves the bug is gone (must pass before promotion).
- Any minimal fixes in deploy_capital.py or allocation_engine.py if they hard-assume the old shape (document the change location).
- Entry in logs or the runner's state dump proving normal positions now use -USD + usd values.
- Updated handoff status + MASTER_TASK_TRACKING entry.

---

## Success Criteria (verifiable)
1. `curl` or runner cache now shows positions with keys like "BTC-USD" and values in USD (not coin counts).
2. Isolation test (dedicated script) passes: feed current holdings that already match a target → rebalance plan = empty (no churn).
3. When holdings are deliberately different, plan only adjusts the delta (sticky behavior restored).
4. No "BTC" bare-currency in any planning or sentiment path during a full dry-run of `_perform_daily_rebalance`.
5. Fable 5-style review comment or manual audit confirms P6-001 closed.

---

## Constraints & Requirements
- Follow user's standing rules strictly: real data, sticky from actual exchange holdings, Code Isolation Testing discipline, no fake/placholder data.
- Risk of live rebalance with current code is extreme (full book churn + bad sizing every cycle). Fix first.
- Work in `phase6/` and supporting scripts only. Keep changes minimal and auditable.
- After change, run the existing validate_canonical_sentiment_paper.py style checks if appropriate, plus the new isolation test.

---

## Validation Method (for Scotty + user)
- Run the new isolation test and share output.
- Start the phase6 runner (or the live harness) and inspect a full `_perform_daily_rebalance` simulation or shadow cycle.
- Check logs for normalized "BTC-USD" usage and absence of previous error patterns.
- Scotty will perform final review + shadow test readiness check before any live rebalance is re-enabled.

---

## Notes & Warnings for Sub-Agent
- This is the #1 finding from the expensive Fable 5 review — treat it with the highest urgency.
- Previous "partial sentiment fix" work is sitting on top of this broken data layer; the aged sentiment and deployment work cannot be trusted until this is resolved.
- The model explicitly said: "**Immediate — do not run another live rebalance until fixed.**"
- Look for similar key-drift patterns in other files while you are here (but scope changes only to fixing this class of bug).
- Document any other related representation issues you find.

**Handoff complete. Start by reading the current implementation of `get_enriched_positions` and `_perform_daily_rebalance`.**

---

**Scotty Integration Review Task (self-assigned)**: After the engineer delivers, I will:
- Review the diff + isolation test output
- Run a full shadow pass using the review_driver or direct harness
- Confirm no regressions in Fresh Start vs rebalance paths
- Update tracking + promote the card only after evidence
- Decide whether to feed Batch 1 to Fable 5 immediately after
