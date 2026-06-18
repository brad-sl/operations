# Phase 5 BRD — Crypto Trading Bot: Live Trading + Smart Allocation
**Version:** 1.0  
**Date:** 2026-04-01  
**Status:** APPROVED FOR DEVELOPMENT  
**Approach:** Conservative — phased, well-tested, regression-safe

---

## Executive Summary

Phase 5 transitions the bot from paper trading validation (Phase 4b) to live trading on Coinbase Advanced Trade with a lightweight multi-trader framework and three allocation modes. The guiding principle is **progressive complexity** — we ship the simplest working version first, validate it thoroughly before adding features, and maintain full regression test coverage at every step.

---

## Scope

**In Phase 5:**
- Live trading on Coinbase Advanced Trade (two configurable pairs per trader)
- Three allocation modes: Smart Allocation, Even Spread, Manual Allocation
- Standalone rebalancer module (Mode B — separate pool, no conflict with intraday bot)
- Light multi-trader framework (SQLite, manual config, no OAuth)
- Real cash balance reads from Coinbase (USD or USDC)
- Compound Trading Engine (gains to top-performing pair)
- Per-trader position tracking, P&L ledger, and audit logs
- Dashboard: Dynamic Portfolio tile, Compound Growth, Rebalance History

**Not in Phase 5:**
- Cross-exchange trading (Phase 6)
- OAuth / self-serve onboarding (Phase 6)
- Approval gating per trade (on-demand, post-Phase 5)
- >2 pairs per trader (Phase 6)
- Dynamic Account Rebalancing between active intraday trades (Phase 6)

---

## Allocation Modes

### Mode 1: Smart Allocation *(default)*
**Automatically calculates starting trade amounts based on:**
- Asset volatility profile (lower volatility → higher base allocation)
- Liquidity and daily trading volume (higher volume → more reliable execution)
- Thematic tier risk score (memecoins capped lower than infrastructure tokens)

**Benefits achieved:**
- Balances risk across pairs proportionally rather than arbitrarily
- Reduces concentration in any single high-risk asset
- Adapts to the actual characteristics of each pair — not guesswork

**Market risks avoided:**
- Overexposure to a single volatile asset causing outsized drawdowns
- Illiquid pairs that can't execute trades cleanly at target prices
- Silent portfolio drift that erodes returns over time

*Technical method: inverse-volatility weighting within tier caps, bounded by per-coin floor (4%) and ceiling (15%), normalized to 100%.*

---

### Mode 2: Even Spread
Split capital equally across all active trading pairs.

- Simple, maximum diversification by construction
- No data inputs required — works immediately on any pair set
- Best for users who want to start quickly without configuring allocation logic
- Slight disadvantage: treats a high-liquidity pair the same as a low-liquidity one

---

### Mode 3: Manual Allocation
The investor specifies a percentage for each pair. Percentages must sum to 100%.

- Full control for experienced traders
- Useful when a trader has a strong conviction about a specific pair
- The system validates that percentages sum to 100% before accepting
- No automation — user owns the allocation decision entirely

---

## Phase 5 Rollout Plan (4 Weeks)

### Week 1 — Foundation
**Goal:** Get the data layer right before touching trades.

- [ ] Set up SQLite schema: `traders`, `trader_pairs`, `positions`, `daily_pnl`, `rebalance_events`, `compound_events`
- [ ] Implement `allocation_engine.py` with all three modes (Smart, Even Spread, Manual)
- [ ] Implement real Coinbase balance reader: `get_cash_balance(trader_id, account_type)` → USD float
- [ ] Auto-scale logic: `effective_capital = min(configured_capital, real_balance / num_pairs)`
- [ ] Unit tests: allocation engine (all three modes), balance reader (mocked), auto-scale logic
- [ ] Dry-run mode: all trading calls print intent but do NOT execute

**Acceptance criteria:**
- All three allocation modes produce weights that sum to 1.0
- Balance reader returns a real number from Coinbase sandbox
- Dry-run mode logs every intended trade without placing orders
- All unit tests pass

---

### Week 2 — Core Bot Wiring
**Goal:** Live order execution with safety rails.

- [ ] Wire `allocation_engine` output into bot startup — `CAPITAL_PER_PAIR` no longer hard-coded
- [ ] Implement `coinbase_wrapper.place_order()` for live mode (remove sandbox block)
- [ ] Implement daily loss cap enforcement (per-pair, hard halt)
- [ ] Implement stop-loss and take-profit checks (already exist in smoke test — promote to live path)
- [ ] Implement Compound Trading Engine: on trade close with profit → allocate gain to top-performing pair
- [ ] Integration test: place one real sandbox order, verify fill, verify P&L accounting
- [ ] All existing unit tests still pass (regression check)

**Acceptance criteria:**
- One real limit order placed and filled in Coinbase sandbox
- P&L calculation matches expected value (fee model correct)
- Daily loss cap halts trading when threshold hit
- Compound allocation fires on profitable close and updates ledger

---

### Week 3 — Multi-Trader + Rebalancer
**Goal:** Run two traders independently; add standalone rebalancer.

- [ ] Multi-trader loop: single bot process iterates all `active` traders per cycle
- [ ] Per-trader log namespacing (no log interleaving)
- [ ] Standalone rebalancer module: checks drift vs. target, proposes moves, executes if `dry_run=False`
- [ ] Fee guard: rebalancer skips moves where expected gain < 0.8% round-trip cost
- [ ] 24h minimum interval between rebalances enforced
- [ ] Dashboard: Dynamic Portfolio tile (current weights, target, drift %)
- [ ] Integration test: two-trader scenario, one rebalance event fires and logs correctly
- [ ] Regression test suite run in full

**Acceptance criteria:**
- Two traders run independently, no state leakage between them
- Rebalancer fires when drift exceeds threshold, skips when fee guard blocks
- Dashboard tile shows correct weights and drift
- Full regression suite passes

---

### Week 4 — Hardening + Go/No-Go
**Goal:** Production-ready, observable, safe to flip to real money.

- [ ] Telegram kill switch: `/stop` command halts bot cleanly
- [ ] Telegram trade alerts: message on every OPEN/EXIT with pair, price, P&L
- [ ] Dashboard: Compound Growth widget, Rebalance History log
- [ ] Log rotation and archival (prevent unbounded log growth)
- [ ] End-to-end test: 48h dry-run with two real traders, two pairs each, rebalancer active
- [ ] Go/No-Go review: win rate ≥ 50%, no crashes, P&L accounting accurate, all alerts firing

**Go/No-Go criteria:**
- 48h dry-run completes with zero crashes
- Win rate ≥ 50% on paper trades
- Every trade has a corresponding Telegram alert
- Kill switch tested and confirmed working
- All regression tests pass
- Brad reviews and approves

---

## Risk Controls (Phase 5 Defaults)

| Control | Default | Configurable |
|---|---|---|
| Stop loss | -2% per trade | ✅ per trader/pair |
| Daily loss cap | $50 per pair | ✅ per trader/pair |
| Max single rebalance | 30% of total capital | Fixed Phase 5 |
| Max allocation per pair | 60% | ✅ |
| Min allocation per pair | 4% (Smart mode) | Fixed |
| Rebalance min interval | 24 hours | ✅ |
| Fee guard | Skip if gain < 0.8% | Fixed |
| Approval threshold | None (auto) | Optional future |

---

## Testing Strategy

**Unit tests** (Week 1):
- `test_smart_allocation()` — weights sum to 1.0, no coin exceeds 15%
- `test_even_spread()` — equal weights, correct USD split
- `test_manual_allocation()` — validation rejects percentages ≠ 100%
- `test_auto_scale()` — scales down when balance < configured capital

**Integration tests** (Week 2–3):
- `test_sandbox_order_placement()` — real Coinbase sandbox API call
- `test_pnl_accounting()` — fee-inclusive P&L matches hand calculation
- `test_daily_loss_cap()` — halts correctly on breach
- `test_two_trader_isolation()` — no state bleed between traders

**Regression gate** (each week):
- All prior tests must pass before new features are merged
- Any new feature adds at least one new test

**Go/No-Go gate** (Week 4):
- 48h dry-run with full logging
- Manual review of P&L ledger for accuracy
- Telegram alerts confirmed working
- Kill switch confirmed working

---

## Open Items (Awaiting Brad)

- [ ] Which 2 trading pairs for Phase 5? *(TBD — Brad to provide)*
- [ ] Cash account: USD or USDC?
- [ ] Starting capital per pair (or use full available balance with auto-scale)?
- [ ] Rebalance cadence: daily at fixed time, or threshold-only?
- [ ] Allocation mode default: Smart Allocation or Even Spread to start?
