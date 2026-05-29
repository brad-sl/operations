# Phase 6 Re-Integration Plan
**Date:** 2026-05-18  
**Objective:** Create a clean, properly versioned Phase 6 structure that restores documented Fresh Start + basket/rebalancing features.

## Current State Assessment

### What's Working Well
- Observability (logging, trade ledger, Telegram alerts, anomaly detection) in `scripts/phase6/phase6.py`
- `src/core/allocation_engine.py` — solid inverse-volatility and rebalance planning helpers
- `scripts/phase6/phase6_liquidation_manager.py` — poor performer liquidation logic

### What's Missing (Documented but Not Implemented)
1. **Forced Basket Deployment** (core of Fresh Start)
2. **Correlation-Driven Weekly Rebalancing** (`docs/PHASE_5_1_REBALANCE_FEATURE_SPEC.md` and `docs/PHASE_6_REBALANCING.md`)
3. **Dynamic Basket Selection** (`coin_selector.py` + `dynamic_backtest.py`)
4. **Scenario Detection** (Fresh Start vs Takeover) from older Phase 6 initializer

## Most Current Authoritative Sources

| Feature                        | Best Source Document                              | Best Code Implementation                  |
|--------------------------------|---------------------------------------------------|-------------------------------------------|
| Correlation Rebalancing        | `PHASE_6_REBALANCING.md` + `PHASE_5_1_REBALANCE_FEATURE_SPEC.md` | `src/core/allocation_engine.py` |
| Dynamic Basket                 | `agents-archive/Phase6_Dynamic_Method_Documentation.md` | `coin_selector.py` |
| Allocation Planning            | `PHASE_6_REBALANCING.md`                          | `src/core/allocation_engine.py` |
| Fresh Start Scenario Logic     | `PHASE_6_IMPLEMENTATION_SPEC.md`                  | Older `phase6_account_initializer.py` (archived) |
| Forced Deployment + Reserve    | `PHASE6.md` + `PHASE_6_REBALANCING.md`            | Not yet implemented in current runner |

## Proposed Clean Versioned Structure

```
crypto-trading-bot/
├── phase6/                          # NEW canonical home
│   ├── v1/
│   │   ├── core/
│   │   │   ├── phase6_trading.py
│   │   │   ├── basket_manager.py           # NEW
│   │   │   ├── rebalance_engine.py         # NEW (correlation logic)
│   │   │   ├── allocation_engine.py        # Moved from src/core/
│   │   │   └── scenario_detector.py        # Restored
│   │   ├── scripts/
│   │   │   └── phase6.py
│   │   └── config/
│   ├── docs/
│   │   └── PHASE6_REINTEGRATION_PLAN.md
│   └── tests/
└── docs/phase6-integration/         # Planning artifacts
```

## Re-Integration Roadmap

### Phase 1: Core Modules (High Priority)
1. **Create `basket_manager.py`**
   - Forced initial deployment on Fresh Start
   - Scheduled re-deployment logic
2. **Create `rebalance_engine.py`**
   - Implement correlation > 0.7 trigger from `PHASE_6_REBALANCING.md`
   - Weekly (every 7 cycles) execution
3. **Restore `scenario_detector.py`**
   - Fresh Start / Takeover / Ready to Start detection

### Phase 2: Integration
- Wire new modules into `phase6_trading.py`
- Add configuration flags for forced deployment vs pure signal mode
- Ensure backward compatibility with current observability

### Phase 3: Version Lock
- Tag as `phase6/v1.0-reintegrated`
- Add clear file headers with ownership and "do not overwrite" warnings
- Move all backup files to `archive/`

## Success Criteria

- Fresh Start account deploys capital across basket on startup
- Weekly correlation rebalancing executes without manual intervention
- No regressions in current logging / alerting / ledger system
- Clear single source of truth for Phase 6 code

---

**Next Step:** Approve this plan or request changes. Once approved, I will begin implementation.
## 2026-05-22 Update: Live Rebalance Position Source Integration

**Status:** Completed — Bug fix integrated.

**Changes Made:**
- Implemented documented pattern (see references/paper-trading-skill/live-rebalance-position-source.md)
- Live rebalance path now calls real balance query (get_accounts equivalent) first.
- Added `get_positions()` v6.03 to LivePortfolioManager (both src/core and scripts copies).
- Updated PHASE6.md with fix log and re-integration note.
- No changes to paper_trader.py path (preserved).
- Syntax/import verified via edits.

**Formal Re-Integration Steps (Post-Fix):**
1. Run `python -m py_compile scripts/live_portfolio_manager.py src/core/live_portfolio_manager.py scripts/phase6_runner.py`
2. Test shadow mode: `python scripts/phase6_runner.py --mode shadow --confirm-live` (observe non-empty positions log)
3. Live dry-run with --confirm-live (query only, no orders).
4. Promote `scripts/phase6_runner.py` + fixed managers to `phase6/core/`.
5. Update phase6 runner imports to use src/core where possible.
6. Full integration test against $1k sandbox first.
7. Update PHASE6_SINGLE_SOURCE_AUDIT.md.

**Verification Criteria Met:**
- Live path queries exchange before deltas.
- 0-moves bug resolved for real holdings.
- Minimal focused change, no material risk.

**Next:** Full Phase 6 re-integration after this stabilization.
