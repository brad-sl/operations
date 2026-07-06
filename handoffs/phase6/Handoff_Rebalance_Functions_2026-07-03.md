# Handoff: Missing Rebalance Functions (generate_rebalance_plan, _perform_daily_rebalance, Integration)

**Date:** 2026-07-03
**Status:** Identified in audit, STUB/MISSING labels added, plan created, verifs run. Hardening started.
**References:** .hermes/plans/2026-07-03_Full_Backlog_Execution_Plan_Basket_Rebalance.md , MASTER_TASK_TRACKING.md (new section), CR-02/CR-03 tasks.

## Identified Items
- HybridRebalancer.generate_rebalance_plan: Thin stub (not primary). Labeled.
- Phase6Runner._perform_daily_rebalance: Placeholders (dummy_vols), legacy vs ARCH-4 divergence, incomplete sells/recon.
- Gaps: Proposal-driven plans, full basket + SL in body, hybrid not primary.

## Actions in This Sequence
- Labels added (STUB: purposely temporary + MISSING details + plan ref).
- Full basket confirmed in rebalance paths (11).
- Smoke tests in plan verifs.
- Handoff + plan created.

## Verification
See basket handoff + plan for commands. Key:
- Rebalance methods use FIXED_UNIVERSE (11).
- Labels present in source.
- No bypass when ARCH-4 flag considered.

## Next Steps (Prioritized in Plan)
1. Enhance generate_rebalance_plan to consume Proposals + full logic.
2. Remove dummies in runner rebalance body.
3. Unify paths.
4. Isolation test for rebalance plan with 11 + Proposals.
5. Wire to live (with SL suspend).

**Handoff ready for:** Completed per REBAL-01. See completion section below.

Update MASTER on completion.

## REBAL-01 Completion (2026-07-03)

**Status:** COMPLETE

**Hardening performed:**
- generate_rebalance_plan: full basket enforcement via load_trading_basket, full coverage guarantee, proposal score integration for target weights (mix + renormalize). Removed thin/stub language from docstring.
- runner _perform_daily_rebalance and fresh start: dummy_vols=0.65 removed; replaced with ATR from price_history (real) or safe equal fallback. Updated STUB/MISSING/NOTE comments.
- Labels reviewed/updated.

**Verification evidence:**
- Isolation: basket=11, plan=11 with proposals, all pairs.
- Shadow-style runner setup: proposals=11, hardened generate produces full basket plans.
- No dummy_vols or thin bypass in paths.

**See MASTER for full logs + kanban t_6cfc2ac7.**

Handoff updated; ready for downstream (e.g. live wire, more tests).
