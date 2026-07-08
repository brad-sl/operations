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

# 2026-07-04 P1-04 Closure (metadata + telemetry remaining blockers)
**Task**: t_f9086ae7 P1-04: Finish remaining Live_Readiness_Blockers (metadata, telemetry) not covered by P0s.

**Audit + Resolution**:
- Product metadata: Fully dynamic via public /products API in exchange_client.py + coinbase_wrapper_FIXED.py (synced 11-pair fallbacks + identical dynamic logic post P0-02/P1 updates). Verified fetches for all basket pairs (ADA price_inc 0.0001 base~1e-8, DOGE 1e-5/0.1, XRP 0.0001/1e-6 etc).
- get_price (P6-127): Live path returns raw float(data["data"]["amount"]) -- full precision confirmed (e.g. ADA 0.17705 with 5+ decimals, no round(2) anywhere in return). Shadow sim separate.
- Quantization (P6-157): All live paths (place_market_buy quote via quote_inc, place_market_sell base via base_inc, place_stop_limit_sell base+prices, execute_rebalance via executor->client) use get_product_metadata + _quantize_*/public quantize_size/price (Decimal ROUND_DOWN). Executor buy/sell compute size then quantize. No bypasses.
- Wrapper synced to prevent drift.
- Telemetry/observability: 
  - Proposals from evaluate_universe (full metadata: rsi, sentiment, vol, etc) -> runner _last_proposals, persist_proposals_to_db (with accepted flag), _write_dashboard_cache (arch4.proposals_summary + p1_metrics).
  - [OBS] logs: proposals_generated=N accepted=M acceptance_rate=X% utilization=Y% per cycle.
  - DB: proposals, rebalances, trades, sl_metrics, replay_parity, recovery.
  - Utilization/accept in state + cache.
  - Performance facts via trade_ledger + DB views (calc offloaded).
- Evidence: verify_p1_04_metadata_telemetry.py (dynamic 11, prec fetches, quant examples, obs sim 11 props), runner cycle sims, live fetches in logs. Artifacts in kanban workspace t_f9086ae7/.

**Status**: RESOLVED for metadata/telemetry scope. P6-127/155/157 addressed (core quant was P0-02). No remaining meta/tele blockers from 2026-06-10 list (reserve/SL covered in P0-04/05).

See MASTER 2026-07-03/04 entries + kanban t_f9086ae7 for full logs/evidence.
Updated: 2026-07-04
