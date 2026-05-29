# Task: CR-04 – Logging & Observability Parity

**Status:** Ready  
**Priority:** Medium  
**Labels:** observability, logging

## Objective
Ensure Phase 6 has operational visibility at least as good as mature Phase 5 runs.

## Description
Phase 5 had very granular logging during live trading. Phase 6 has good structure but needs richer per-cycle and per-rebalance reporting.

## Scope
- Review logging patterns in key Phase 5 files
- Enhance structured logging in Phase 6 runner and supporting modules
- Improve per-cycle summaries and rebalance reporting

## Implementation Guide

1. Audit logging in `phase5_multi_pair_minimal.py` and `phase5_1_live_final.py`.
2. Define standard log event types for Phase 6.
3. Add cycle summary logging (positions before/after, capital, moves).
4. Improve Telegram digest quality.
5. Ensure logs are easily searchable for debugging.

## Files Involved
- **Modify:** `phase6/core/phase6_runner.py`, supporting modules

## Acceptance Criteria
- Clear per-cycle and per-rebalance logs
- Improved Telegram summaries
- Easier to debug issues from logs

## Estimated Effort
3–5 hours

## Dependencies
None