# Capital Allocation Engine Implementation Report
**Phase 6.1 spec v1.1 - Permanent Output**

**Date:** 2026-05-26  
**Implementer:** crypto-engineer (kanban t_2a725c72)  
**Status:** Complete

## Summary
Implemented the Capital Allocation recurring job as a standalone, schedulable Python package under permanent directory structure:
- Code: `/home/brad/projects/crypto-trading-bot/src/capital_allocation/`
- Reports: `/home/brad/projects/crypto-trading-bot/reports/`

## Deliverables
1. `src/capital_allocation/__init__.py` - Package initializer and public API
2. `src/capital_allocation/recurring_job.py` - Core recurring job implementation (executable as script or imported)
3. This report in `/reports/`

## Key Features (per spec v1.1)
- Loads versioned config from permanent `config/capital_allocation_config.json`
- Uses existing `allocation_engine.py` primitives (inverse vol weighting, static allocation planning, rebalance plan generation)
- Fetches simulated/real portfolio state from persistent state file
- Computes volatility-aware target weights with min/max bounds and reserve % handling
- Generates actionable rebalance plans with USD move amounts
- Logs to permanent `logs/capital_allocation/`
- Produces timestamped JSON reports in `/reports/`
- Designed for cron scheduling (example: weekly Monday run) or integration into multi-pair orchestrator

## Integration Notes
- Can be invoked via `python -m capital_allocation.recurring_job` or direct function call
- State persists across runs for continuity
- Ready for extension with real Coinbase balance fetcher and order execution hooks
- Aligns with Phase 6 multi-pair rebalancing and poor-performer liquidation goals

## Verification
- Linting passed (no syntax errors)
- All paths use permanent directories only (no scratch workspace pollution)
- Compatible with existing Phase 5/6 allocation_engine

**Next recommended steps (out of scope for this task):**
- Wire into phase6 orchestrator or cron scheduler
- Add real volatility data source
- Unit tests in phase6/tests/

This completes the assigned kanban task.