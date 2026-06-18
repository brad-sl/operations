# Phase 6 Live Readiness Checklist
**Date:** 2026-06-10 | **Status:** All Fable-5-identified live blockers addressed with code changes + Code Isolation Tests (CIT). Paper GO previously granted; final live gate pending user credentials + one last clean paper artifact.

## Summary of Resolved Blockers (Live NO-GO items)

### 1. P6-127 — Live get_price 2dp rounding (Critical, capital risk)
- **Fix:** Live `get_price` path (`exchange_client.py`) always returns full-precision float from Coinbase public `/v2/prices/.../spot` (float(data["data"]["amount"])). No rounding or .2f anywhere in the live return path.
- **Metadata for low-priced assets:** Full accurate table (DOGE 0.00001 price / 1.0 base, XRP, ADA 0.0001/1.0, etc.) in BOTH `phase6/core/exchange_client.py` and `coinbase_wrapper_FIXED.py`.
- **Quantization policy:** Applied ONLY at order construction time (stop_limit, market paths if needed) using `_quantize_*` + product metadata. Prices for valuation/rebalance use raw floats.
- **Evidence:** `scripts/test_fable5_live_p6_127_full_precision_price.py` — PASS. Metadata verified for ADA+DOGE, quantization examples for sub-cent stops.

### 2. P6-155 — ADA base_increment metadata
- **Fix:** Exact entry added: `{"price_increment": 0.0001, "base_increment": 1.0}` for ADA-USD in both active tables.
- **Evidence:** Test above + explicit verification in runner output. Synced between wrapper and unified client.

### 3. P6-157 — Buy/sell/rebalance quantization on all live paths (stop + market + execution)
- **Fix:** 
  - Stop-limit paths already using `_quantize_size`/`_quantize_price` + metadata (prior wave).
  - Market buy (quote_size USD) inherently safe.
  - Unified `_quantize_*` helpers available on client.
  - `order_executor.execute_rebalance_plan` delegates to client's methods (now all metadata-aware).
  - Runner rebalance paths flow through the client (no bypass).
- **Evidence:** `scripts/test_fable5_live_p6_157_market_quantization.py` — PASS. Confirms metadata + quantize on paths used by rebalance.

### 4. P6-158 / CR-03 durability + live init hardening
- **Fix / Evidence:**
  - Private-key newline normalization in `_ensure_live_client` AND `_init_live_client` (P6-144 prior).
  - CR-03 `stop_loss_coordinator.suspend_reattach_context` actively used in `phase6/core/phase6_runner.py` for daily rebalance (and Fresh Start window).
  - Coordinator works in "live" mode simulation (factory + context exercised).
- **Evidence:** `scripts/test_fable5_live_cr03_durability.py` — PASS (shadow + live-mode simulation). Context proven atomic.

### 5. G4 funding constraint tightness in live runner
- **Fix (prior + confirmed):** `withdrawal_reserve` block in `config/trading_config_phase6.json` (min_reserve + explicit max_deployable). Runner `_perform_daily_rebalance` reads config, computes projected targets, calls `enforce_withdrawal_reserve(..., target_allocations_usd=...)`, and uses `deployable_cash` guard.
- **Evidence:** Isolation tests from previous waves (P6-148, P6-152) + 60-tick post-gate paper run showing `(capped)` + dynamic post-fill telemetry.

## Additional Guardrails in Place
- Sentinel / verified-zero / error handling never returns bare {} (P6-151/001).
- Rebalance keys always -USD + value_usd (P6-001).
- Reserve projected + cap enforced before allocations.
- Sentiment aging + quality gates (60m half-life + recovery cooldown) in canonical path.
- Fresh Start only on explicit verified zero.

## Code Isolation Tests (all run in this session, real data expectations, no fakes)
- P6-127/P6-155 full precision + metadata: PASS
- P6-157 market/rebalance quantization: PASS
- CR-03 / durability context in live sim: PASS
- Prior supporting tests (reserve cap, key normalization, rebalance plan robustness, sentinel leak, etc.) remain green.

## Next / Remaining (user-controlled)
- Run extended paper harness (recommend 100+ ticks) with the riders from final Fable 5 (P6-159–162) if desired — these are paper-only for evidence quality.
- Final user live gate: review this checklist + latest paper artifact + the delta Fable 5 reports.
- Provide real OPENROUTER / Coinbase credentials only when ready for the first small live paper validation (or shadow-live with sandbox if supported).
- Once user signs off: flip a runner to mode="live" with keys and monitor first cycles closely.

## Sign-off (Scotty, crypto-orchestrator)
**All Fable-5 + prior live-capital-risk blockers that were in-scope (P6-127, P6-155, P6-157, CR-03/P6-158, G4 live tightness) now have:**
- Concrete code fixes.
- Dedicated passing Code Isolation Tests.
- Traces through the actual runner/order_executor/client paths used in production.
- No fabricated data in any test or evidence.
- Changes committed to permanent locations with diffs.

The system is in its strongest-ever state for a go-live decision.

**Live capital exposure still requires:**
- Your explicit "ok to go live".
- Credentials injection.
- At minimum a clean extended paper run (if not already).

All prior MASTER constraints (real data, sticky holdings, withdrawal reserve, sentiment aging + cooldown even in recovery, Code Isolation + shadow before any change) have been respected.

Ready for final user decision.

— Scotty 2026-06-10
