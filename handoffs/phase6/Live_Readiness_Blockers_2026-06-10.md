# Live Readiness Blockers Resolution Plan (2026-06-10)

**Goal**: Clear every Fable 5 / prior "NO-GO for live" item so the system is ready for a final gate before real capital.

**Live Blockers (from cumulative Fable 5 + prior reviews)**

1. **P6-127 — Live `get_price` rounding (Critical)**
   - Risk: DOGE/XRP/ADA prices rounded to 2dp → wrong stop prices, position values, rebalance amounts.
   - Fix: Ensure public API path always returns full float precision. Quantization only at order time.
   - Evidence required: Isolation test calling (mocked) live get_price for low-priced assets, asserts ≥6 decimals retained. No 2dp return in live path.

2. **P6-155 — ADA base_increment metadata (High)**
   - Fix: Add accurate ADA-USD entry in both active metadata locations (wrapper + exchange_client).
   - Typical values: price_increment 0.0001, base_increment 0.01 (or verified from product endpoint).

3. **P6-157 — Buy/sell/rebalance quantization on *all* live paths (Critical)**
   - Current state: STOP path in exchange_client + wrapper is good (quantized, no reduce_only).
   - Missing/audit required: `place_market_buy`, `place_market_sell`, `execute_rebalance_plan`, any limit orders.
   - Fix: Unify quantize calls using live product metadata for every order type that touches live client.
   - Runner / order_executor must not bypass quantize.

4. **P6-158 + CR-03 durability (High)**
   - Private key normalization coverage across every init path (done in exchange_client).
   - CR-03: Confirm stop_loss_coordinator is active in live rebalance path (runner already wraps daily rebalance).
   - Need: Atomic suspend → rebalance → reattach evidence (isolation test that exercises the context in live mode).

5. **G4 funding constraint tightness in *live* code (Medium-High)**
   - Harness was fixed for cap + projected targets.
   - Ensure runner `_perform_daily_rebalance` and deploy paths always pull `max_deployable_usd` + use enforce_withdrawal_reserve with projected targets before any allocation.

6. **Supporting**
   - Full live-path E2E in shadow "live" mode (mode="live" but no keys or with sandbox).
   - Signed isolation + real-structure tests for every blocker.
   - Updated MASTER + Kanban cards.
   - Final paper re-run (with riders) + optional scoped Fable 5 live-gate review.

**Process Rules (standing)**:
- Code Isolation Test before every patch that affects live paths.
- Real data / no fake prices or holdings.
- All changes tracked in MASTER + tight handoffs.
- No promotion of cards until shadow evidence + isolation pass.
- Scotty (crypto-orchestrator) reviewer sign-off before any claim of "live ready".

Deliverables:
- Patches + new/updated isolation tests for 1-5.
- Single "Live Readiness Checklist" document with links.
- Updated MASTER_TASK_TRACKING.md with Live Readiness section.
- Kanban cards (or MASTER entries) for each major blocker.
- Ready for user "go" on final paper gate + live capital decision.

**Owner**: Scotty (execute, test, document, handoff to user for final live key decision).
# End of plan
