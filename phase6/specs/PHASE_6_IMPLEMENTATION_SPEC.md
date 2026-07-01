# Phase 6 Implementation Specification (Current Production State)

**Status:** Active Production System (ARCH Architecture)  
**Last Updated:** 2026-07-01 (Major rewrite to match implemented system)  
**Version:** 3.0 (Current)  
**Previous:** v2.1 (2026-04-20, focused on initializer + PAIN_SCORE liquidation)

---

## Overview

Phase 6 is the **production autonomous trading runtime** for the crypto-orchestrator bot. It orchestrates signal generation, evaluation, allocation, execution, risk management (stop-loss), and rebalancing on top of real market data, sentiment, and regime signals.

It supports two primary operating modes:
- **Fresh Start**: Clean deployment from available USD cash when no (or verified-zero) open positions exist.
- **Takeover / Daily Rebalance**: Respect existing holdings, perform ongoing rotation and rebalancing while enforcing risk controls.

The system has evolved from an early "account initialization + periodic liquidation" design into a modular, data-driven trading platform built around **ARCH** (isolated, testable components).

All logic emphasizes:
- Real data only (via canonical loaders for sentiment, RSI, prices).
- Strict data flow and path hygiene (see `phase6/core/paths.py` + `docs/DATA_FLOW_AND_LOCATIONS.md`).
- Isolation testing for core paths.
- Integration with intelligence reporting and influence attribution.

---

## Current High-Level Architecture

```
Phase6Runner (core orchestrator)
├── Mode: shadow | live (explicit, no defaults)
├── Fresh Start gate (has_open_positions() tri-state: None/False/True)
├── Daily Rebalance (time-driven or triggered)
│
├── Data Refresh Layer
│   ├── PriceHistoryManager + RSI pipeline
│   ├── load_sentiment_scores() (X primary + conditional Reddit)
│   ├── Polymarket regime bias (via intelligence brief)
│   └── Strategic brief (intel_strategic_brief.json)
│
├── ARCH-1: Evaluation
│   └── evaluate_universe() → list[Proposal]
│       (SignalGenerator + OpportunityScanner + real sentiment/RSI)
│
├── ARCH-2: Allocator / Decision
│   ├── Allocator (RotationStrategy "catch-the-wave", RebalanceStrategy)
│   └── HybridRebalancer
│
├── Execution & Risk
│   ├── OrderExecutor
│   ├── StopLossManager + StopLossCoordinator (suspend/reattach)
│   └── Withdrawal reserve enforcement
│
├── Observability
│   ├── TradeLedger
│   ├── generate_trading_intelligence_report.py
│   ├── intel_strategic_brief.json
│   └── Influence stack (X + Reddit + Polymarket)
│
└── Persistence
    └── data/state/ (JSON) + data/phase6.db (shared)
```

Key entrypoint: `phase6/core/phase6_runner.py`

---

## Key Implemented Components

| Component                        | Location                                      | Responsibility |
|----------------------------------|-----------------------------------------------|----------------|
| **Phase6Runner**                 | `phase6/core/phase6_runner.py`               | Central orchestrator; Fresh Start vs Takeover; daily rebalance loop; data refresh; SL coordination |
| **Allocator (ARCH-2)**           | `phase6/core/allocator.py`                   | RotationStrategy (catch-the-wave with drawdown exits, cooldowns) + RebalanceStrategy (inverse-vol + scores) |
| **Evaluation (ARCH-1)**          | `phase6/core/evaluation.py`                  | `evaluate_universe()` → unified Proposal list from real signals + sentiment |
| **Opportunity Scanner**          | `phase6/core/opportunity_scanner.py`         | Proactive scoring of basket + candidates using RSI, sentiment, momentum |
| **Hybrid Rebalancer**            | `phase6/core/rebalancing/hybrid_rebalancer.py` | Core rebalance decision and execution orchestration |
| **Sentiment Scorer**             | `phase6/core/sentiment_scorer.py`            | X primary (rich metadata + damping), conditional Reddit from DB, aging |
| **Stop Loss Coordinator**        | `phase6/core/stop_loss_coordinator.py` (and manager) | SL application, suspend/reattach around rebalances, recovery |
| **Order Executor**               | `phase6/core/order_executor.py`              | Actual trade execution with retries |
| **Live Portfolio Manager**       | `phase6/core/live_portfolio_manager.py`      | Holdings, positions, has_open_positions() sentinel logic |
| **Signal Generator**             | `phase6/core/signal_generator.py`            | RSI + sentiment → signals |
| **Config Loader**                | `phase6/core/config_loader.py`               | trading_config_phase6.json (global_settings, phase_6_specific, scheduler, risk, withdrawal_reserve) |
| **Intelligence Reports**         | `phase6/scripts/generate_trading_intelligence_report.py` | Aggregates X/Reddit/Polymarket + proposals + brief |
| **Trade Ledger**                 | `phase6/core/trade_ledger.py`                | Structured trade logging |
| **Paths & Data Flow**            | `phase6/core/paths.py` + `docs/DATA_FLOW_AND_LOCATIONS.md` | Canonical locations, drift prevention |

Legacy files (original initializer + PAIN_SCORE) are in `phase6/archive/scripts_phase6_old/`.

---

## Scenario Handling (Current Implementation)

### Fresh Start
- Triggered when `portfolio.has_open_positions()` returns False (verified zero holdings).
- Deploys available USD cash (after reserve) into the dynamic basket using current Proposals (from evaluate_universe).
- Uses real RSI + sentiment + ATR/vol scaling.
- Wrapped in `stop_loss_coordinator.suspend_reattach_context()`.
- Logs to TradeLedger with reason "fresh_start".
- Config-driven basket (global_settings.pairs or phase_6_specific.opportunity_pool).

### Takeover / Existing Holdings
- Detected when positions exist.
- Respects current holdings.
- Performs daily rebalance: evaluates current basket, generates proposals, runs Allocator/HybridRebalancer.
- Applies SL re-attach logic.
- Enforces withdrawal reserve before deployment.
- Continuous rotation (catch-the-wave) + lighter rebalancing.

**No longer a separate "Phase6Initializer" class with user prompts.** Scenario detection is a simple, robust tri-state gate inside the runner (`None` → skip/safety; `False` → Fresh Start; truthy → Takeover).

---

## ARCH Architecture (Current)

- **ARCH-0 / Current Rebalance Path**: The active production path (runner daily rebalance + allocator).
- **ARCH-1 Evaluation**: Unified `evaluate_universe()` producing first-class Proposals (eliminates scattered logic).
- **ARCH-2 Allocator**: Pluggable strategies consuming Proposals. Replaces ad-hoc deploy/rebalance logic.
- Emphasis on isolation testing (`test_isolation_*.py` files) with real caches/data.

---

## Data Flow & Persistence

See `docs/DATA_FLOW_AND_LOCATIONS.md` for full rules (enforced via `paths.py`).

Key live state:
- `data/state/phase6_live_state.json`
- `data/state/phase6_runner_state.json` (last_rebalance_date)
- `data/state/price_history.json`, `rsi_cache.json`
- Sentiment caches under `data/state/`
- `data/phase6.db` (shared sentiment_scores, rsi_values)
- `data/state/intel_strategic_brief.json` (Polymarket + other context)
- `data/state/opportunity_proposals.jsonl`

All code must:
- Derive paths via `phase6/core/paths.py`
- Use relative paths or PROJECT_ROOT
- Reference DATA_FLOW doc in headers

---

## Configuration

Primary: `trading_config_phase6.json` (or `config/trading_config_phase6.json`)

Sections (from code):
- `global_settings`: pairs, total_capital, max_deployable_usd, use_new_allocator
- `phase_6_specific`: opportunity_pool
- `scheduler`: daily_rebalance_times
- `risk_management`, `withdrawal_reserve` (min_reserve_usd)
- Other risk/SL params

Loaded centrally via `ConfigLoader`.

---

## Integration Points

- **Intelligence & Observability**: Full reports include sentiment (aged), Polymarket regime bias, proposals, influence stack.
- **SL / Risk**: Coordinator wraps rebalance execution; re-attach logic for stops.
- **Hermes / Cron**: Runs via thin launchers or direct; supports no_agent scripts.
- **Testing**: Heavy isolation tests for evaluation, allocator, rebalance paths, Fresh Start parity.
- **Backtests**: Multiple comparison tests (Phase 5 vs 6, rotation, etc.).

---

## Advantages of Current Implementation (vs Early Design)

- **Modularity**: ARCH layers + isolated components enable independent testing and iteration.
- **Real Data Discipline**: Canonical loaders, shared DB, strict paths prevent drift and synthetic data issues.
- **Better Risk Management**: Continuous SL coordination + drawdown-aware rotation + reserve enforcement vs periodic PAIN_SCORE liquidation.
- **Richer Signals**: Multi-source sentiment + Polymarket regime + RSI + opportunity scanning.
- **Observability**: Intelligence briefs, TradeLedger, influence attribution.
- **Flexibility**: Config-driven dynamic baskets, pluggable allocator strategies, shadow/live modes.
- **Production Hardening**: Data refresh guards, suspend/reattach, retry logic, withdrawal reserve.

---

## Gap Analysis: Original Spec vs Current Reality

**Original Spec (v2.1, Apr 2026)** focused on:
- Dedicated `phase6_account_initializer.py` + `phase6_liquidation_manager.py`.
- Explicit scenario classes with user prompts (currency pref, approvals).
- PAIN_SCORE-based weekly/daily poor-performer liquidation.
- Backtest tables centered on initialization + liquidation friction.
- Tighter coupling to Phase 5.1 executor.

**Current Gaps / Changes** (what the old spec no longer describes accurately):

1. **Initialization Layer** — Old dedicated initializer largely replaced by lightweight guard in Phase6Runner. Fresh Start/Takeover still conceptually present but implemented as a simple, robust `has_open_positions()` check with direct deployment logic.

2. **Liquidation / Poor Performers** — PAIN_SCORE engine is archived. Risk is now handled via StopLossCoordinator (continuous), Allocator drawdown exits, and rebalance-time SL suspend/reattach. No more standalone weekly liquidation manager.

3. **User Interaction** — User prompts and manual scenario selection largely removed or moved to external (Hermes/Telegram). System is more autonomous.

4. **Architecture** — Shift to ARCH (evaluation + allocator) + HybridRebalancer. Much more modular and testable than the original monolithic initializer/manager design.

5. **Signals & Intelligence** — Original spec barely mentioned sentiment. Current system has sophisticated multi-source sentiment, aging, Polymarket regime bias, strategic briefs, and influence stack.

6. **Data & Config Hygiene** — Strong new standards (paths.py + DATA_FLOW doc) that did not exist in the early spec.

**What Survives / Is Retained**:
- Fresh Start vs Takeover conceptual distinction.
- Capital cycling / reserve concepts.
- SL/TP protection for positions.
- Focus on real performance in backtests and isolation tests.

**Advantages Gained by Current Design** (as listed above): higher modularity, better risk controls in live conditions, richer decision inputs, stronger observability, and drift resistance.

**Legacy Status**: Early initializer and PAIN_SCORE code lives in `phase6/archive/`. Do not use for new development.

---

## Next Steps / Open Areas (as of 2026-07-01)

- Full promotion of ARCH-4 allocator path (use_new_allocator flag).
- Continued hardening of rebalance + SL coordination (CR tasks).
- More direct use of specific Polymarket probabilities in proposals/allocator.
- Ongoing data flow audits per DATA_FLOW_AND_LOCATIONS.md.
- Integration of more regime signals if available.

---

## References

- `phase6/core/phase6_runner.py`
- `phase6/core/allocator.py`, `evaluation.py`, `opportunity_scanner.py`
- `docs/DATA_FLOW_AND_LOCATIONS.md`
- `phase6/core/paths.py`
- `phase6/core/sentiment_scorer.py` (see updated SENTIMENT_SYSTEM_SPEC.md)
- Isolation tests in `phase6/tests/`
- Intelligence report generator
- Archive for historical initializer/liquidation logic

_This document now reflects the live, running Phase 6 system. The v2.1 draft is preserved in .bak._