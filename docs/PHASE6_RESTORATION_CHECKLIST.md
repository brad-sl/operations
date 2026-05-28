# PHASE 6 Restoration Checklist

**Last Updated**: 2026-05-27 21:25
**Status**: Three blocked tasks unblocked after Handoff Document expansion

## Work Packages

### 1. Sentiment System Restoration
- **Kanban Task**: `t_54c884db`
- **Handoff Document**: Updated with Phase 4/5 source pointers
- **Status**: In Progress
  - ✅ X fetcher fully ported to `phase6/core/sentiment/fetch_x_sentiment.py`
  - ✅ Committed to phase-6.1 (96c6112) — references Handoff_Sentiment_System_Restoration.md
  - ⏳ Reddit fetcher pending (`fetch_reddit_sentiment.py`)
  - ⏳ Time-decay scorer (`sentiment_scorer.py`) pending
  - ⏳ Verification & integration pending

### 2. Rebalancing Logic Upgrade
- **Kanban Task**: `t_2906c1bc`
- **Handoff Document**: **Fully expanded** with detailed scope, deliverables, verification steps, and explicit Phase 4/5 references
- **Status**: ✅ **Unblocked** (now Ready)

### 3. Signal Quality Investigation
- **Kanban Task**: `t_e2f021c5`
- **Handoff Document**: **Fully expanded** with metrics, backtest requirements, and source pointers
- **Status**: ✅ **Unblocked** (now Ready)

### 4. Allocation Engine Enhancement
- **Kanban Task**: `t_7bc3e359`
- **Handoff Document**: **Fully expanded** with liquidity bias + sentiment requirements and verification criteria
- **Status**: ✅ **Unblocked** (now Ready)

### 5. Overall Parity Audit
- **Kanban Task**: `t_97948306`
- **Handoff Document**: Updated
- **Status**: Triage

**All five Handoff Documents now contain explicit pointers to original Phase 4/5 source code and clear success criteria.**

## Recent Activity
- 2026-05-27 21:10: Ported and committed X sentiment fetcher
- 2026-05-27 21:20: Expanded Handoff Documents for Work Packages 2, 3, and 4
- 2026-05-27 21:22: Unblocked `t_2906c1bc`, `t_e2f021c5`, `t_7bc3e359` via `hermes kanban unblock`