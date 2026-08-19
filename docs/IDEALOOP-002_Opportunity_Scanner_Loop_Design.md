# IDEALOOP-002: Proactive Opportunity Scanner + Basket/Pair Expansion Loop Design (Starter)

**Status:** Design Phase (Skeleton)  
**Date:** 2026-06-12  
**Owner:** Scotty  
**Related Documents:**  
- Ideas/Trading_Bot_Loops_Continuous_Improvement_Ideas_2026-06-09.md (Idea #2, prob 75/100)  
- docs/IDEALOOP-005_Shadow_AB_Experimentation_Loop_Design.md (guardrail)  
- docs/BACKTEST_HARNESS_DESIGN.md (style)  
- MASTER_TASK_TRACKING.md  

## 1. Purpose
Periodic (daily/30m-1h) scanner using multi-source data (RSI/vol from pipeline, X/Reddit sentiment via Apify, volume/liquidity). Scores candidates (new or under-allocated pairs) on momentum, sentiment velocity, vol-adjusted historical edge, correlation to current basket. Ranks and proposes small test allocation or basket addition with tilt. Validates with quick historical slice + paper (gated by recovery rules/quality). Applies if passes.

Addresses documented gap: "No proactive scanner (RSI + sentiment + volatility)".

## 2. High-Level Requirements
- Extend existing signal pipeline (RSI refresher, sentiment).
- Scoring: momentum + sentiment velocity/acceleration + edge + diversification.
- Proposal with test allocation size.
- Validation: historical sim + paper window with cooldowns.
- Update dynamic basket logic via controlled rebalance.
- Log decisions durably.

## 3. Architecture (High Level)
Data Pull (price/RSI/sentiment) → Scorer (multi-factor) → Ranker + Proposal → Validator (backtest slice + paper via #5) → Gated Apply (basket update + rebalance).

## 4. Core Components (Starter)
- Scanner script (extend scripts/refresh_rsi_prices.py or new in scripts/ideas/).
- Scoring module.
- Proposal output to state or handoff.

## 5. Success Criteria (Starter)
- Scanner runs on current basket + surfaces at least 1-2 candidates with scores.
- First proposal logged.
- Tracked in MASTER.

**Note:** Full implementation only after #5 guardrail + handoff. Leverage current 4-pair activity and price_history/rsi_cache for initial scoring. Parallel to #1.

See loops doc for full details.

## Future Work (added 2026-06-13)
- POOL-CYCLING-001: Separate Pool Cycling script — **SHADOW implemented 2026-08-08**
  (`phase6/core/pool_cycling.py`, `scripts/phase6/run_pool_cycling_shadow.py`).
  Live `global_settings.pairs` apply remains OFF. See MASTER `POOL-CYCLING-001`.
