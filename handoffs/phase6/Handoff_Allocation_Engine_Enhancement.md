# Handoff Document: Allocation Engine Enhancement

**Work Package**: 4  
**Priority**: High  
**Status**: Blocked → Ready (after this document)

## Objective
Enhance the allocation engine with **liquidity bias** and **sentiment awareness** so capital allocation favors high-liquidity pairs with positive sentiment momentum while respecting withdrawal reserves and proportional scaling preferences.

## Original Source Code (Phase 4/5)
- `phase6/core/allocation_engine.py` (current implementation)
- Original trading document allocation logic and capital allocation rules
- Phase 5 portfolio manager and rebalancing reports
- `live_portfolio_manager.py`

## Scope & Boundaries

### Must Do
- Add liquidity scoring (volume, spread, market depth proxy) to allocation weights
- Incorporate time-decayed sentiment scores into allocation decisions
- Respect "proportional scaling to existing holdings" rule (no constant new pair injection)
- Maintain withdrawal reserve buffers
- Update allocation tests

### Must Not Do
- Change core risk rules or position sizing formulas without tests
- Introduce new trading pairs without explicit user approval

## Expected Deliverables
1. Enhanced `phase6/core/allocation_engine.py` (or dedicated `enhanced_allocator.py`)
2. `phase6/scripts/test_allocation_enhancement.py`
3. Updated allocation report or example output in `reports/`
4. Changes committed to `phase-6.1`
5. Checklist entry updated

## Git Requirements
- Commit message must reference `Handoff_Allocation_Engine_Enhancement.md`
- Work stays on `phase-6.1` branch

## Verification
- Allocation weights shift measurably when sentiment or liquidity changes
- Existing holdings are scaled proportionally
- Withdrawal reserves are never breached in test scenarios
- All output files land in designated permanent directories

## Notes
Task was blocked by missing detailed Handoff. This document supplies the required structure, source pointers, and success criteria.