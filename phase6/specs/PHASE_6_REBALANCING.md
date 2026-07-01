# Phase 6 Rebalancing Specification (Current Implementation)

**Status:** Active Production System (ARCH + Hybrid)  
**Last Updated:** 2026-07-01 (Major rewrite to reflect implemented system)  
**Version:** 3.0 (Current)  
**Previous:** v1.0 (2026-04-21, correlation-weekly focused)

---

## Overview

Phase 6 rebalancing is a **signal-driven, daily (time + hybrid) process** that combines:
- Time-scheduled rebalances (e.g., 09:00 and/or 21:00).
- Hybrid threshold triggers (sentiment deltas, volatility, drawdown).
- ARCH-1 evaluation (Proposals from real RSI + sentiment) + ARCH-2 Allocator (RotationStrategy "catch-the-wave" or RebalanceStrategy).
- Risk overlays (withdrawal reserve, SL suspend/reattach, correlation circuit breaker).

It has evolved significantly from the original correlation-matrix weekly strategy. The system emphasizes real data pipelines, modular ARCH components, continuous risk management, and observability via intelligence briefs and logs.

Rebalancing is **not** purely periodic correlation-based. It is responsive to signals while respecting minimum intervals and hard risk guards.

---

## Current High-Level Flow

1. **Runner Cycle** (every ~60s in `phase6/core/phase6_runner.py`):
   - `_should_rebalance(now)` — time-based (daily_rebalance_times from config).
   - `_evaluate_hybrid_rebalance()` — HybridRebalancer check.
   - If either true → `_perform_daily_rebalance()`.

2. **Pre-Rebalance Refresh**:
   - RSI/price history update (prefers decoupled 15m RSI cache).
   - Load strategic brief (`intel_strategic_brief.json`) for Polymarket regime, high-SL-risk pairs, etc.
   - Sentiment via `load_sentiment_scores()` (X primary + conditional Reddit).

3. **Evaluation (ARCH-1)** (when `use_new_allocator`):
   - `evaluate_universe(basket, sentiment, rsi_values)` → list of Proposals (ROTATE_IN/OUT, scores, reasons).

4. **Decision (ARCH-2 + Hybrid)**:
   - Allocator (RotationStrategy or RebalanceStrategy) using proposals + inverse-vol base + drawdown checks + cooldowns.
   - HybridRebalancer for additional threshold gates.
   - Withdrawal reserve enforcement.
   - SL coordinator `suspend_reattach_context()` wrapper.

5. **Execution**:
   - Build TradePlan → `_execute_trade_plan` → OrderExecutor (market buys/sells via Coinbase).
   - Update TradeLedger, last_rebalance_date, positions.
   - Re-attach SLs on context exit.

6. **Post**:
   - Log via `log_rebalance_event` (rebalance_history JSONL).
   - Telegram digest.
   - Dashboard cache + state persist.

---

## Key Components

| Component                  | Location                                      | Role |
|----------------------------|-----------------------------------------------|------|
| **Phase6Runner**           | `phase6/core/phase6_runner.py`               | Orchestrates time checks, hybrid eval, full rebalance, SL context, brief consumption, ARCH-4 path |
| **HybridRebalancer**       | `phase6/core/rebalancing/hybrid_rebalancer.py` | Sentiment delta (0.15), vol spike (0.25), drawdown (0.08), min 24h. Rule-based AI filter. Replaces pure corr rebalancing |
| **Allocator (ARCH-2)**     | `phase6/core/allocator.py`                   | RotationStrategy (exit weak on low score/drawdown, redeploy to strong; cooldowns, min deltas). RebalanceStrategy (inverse-vol + proposal tilt) |
| **Evaluation (ARCH-1)**    | `phase6/core/evaluation.py`                  | `evaluate_universe()` produces Proposals from SignalGenerator + OpportunityScanner + real sentiment/RSI |
| **Allocation Engine**      | `phase6/core/allocation_engine.py`           | `compute_inverse_vol_allocations()`, `rebalance_plan()` |
| **Opportunity Scanner**    | `phase6/core/opportunity_scanner.py`         | Extends basket scoring with momentum, sentiment velocity, diversification |
| **Stop Loss Coordinator**  | `phase6/core/stop_loss_coordinator.py`       | Wraps rebalance in suspend/reattach context for stable SL management |
| **Withdrawal Reserve**     | Enforced in `_perform_daily_rebalance`       | `enforce_withdrawal_reserve()` before any deploy |
| **Correlation Risk**       | `phase6/core/risk/correlation_circuit_breaker.py`, `rolling_correlation.py` | High-corr (>0.85) → reduce 30% positions + redeploy 15% to reserve. Regime detector optional use |
| **Rebalance Logger**       | `phase6/core/rebalance_logger.py`            | JSONL appends to `data/state/rebalance_history/` |
| **Intelligence Integration**| `phase6/scripts/generate_trading_intelligence_report.py` | Feeds Polymarket bias, sentiment, proposals into briefs consumed by rebalance |

---

## Triggers and Frequency

- **Primary Time Schedule**: Config `scheduler.daily_rebalance_times` (e.g. ["09:00"], ["09:00", "21:00"]).
- **Hybrid Signals**: `HybridRebalancer.evaluate()` on sentiment deltas, vol, drawdown. Min interval 24h by default.
- **Manual/Force**: `data/state/force_rebalance.flag` or `_force_next_rebalance`.
- **Fresh Start Path**: Special deployment logic on first run with no positions.
- **Not**: Strict "every 7 cycles" or pure weekly correlation matrix.

Daily frequency is the norm in production configs, with signal/hybrid overlays for responsiveness.

---

## Data and Signal Integration

- **Sentiment**: Canonical `load_sentiment_scores()` (rich X metadata + damping, conditional Reddit from DB). Aged via half-life in scorer.
- **RSI**: Decoupled 15m refresher cache (preferred) or on-the-fly from price_history (15m granularity).
- **Polymarket / Regime**: Loaded from `intel_strategic_brief.json` (risk_on_bias, high_sl_risk_pairs, etc.) before rebalance.
- **Prices/History**: `price_history.json` for drawdown series, ATR, momentum.
- **Proposals**: Real data only from `evaluate_universe` (no synthetic).
- **Current Positions**: Via `LivePortfolioManager.get_enriched_positions()`.

Full dynamic basket (11-12 pairs) from `global_settings.pairs` or `phase_6_specific.opportunity_pool`.

---

## Risk and Guardrails (Evolved from Old Spec)

- Withdrawal reserve enforcement before deployment.
- Drawdown exits in RotationStrategy (price series trailing DD > threshold → force exit + force re-eval).
- SL Coordinator suspend/reattach (CR-03) around order changes.
- Correlation Circuit Breaker (high corr >0.85 flags reduction + reserve redeploy).
- Cooldowns on rotations.
- Min move USD and min score delta gates to control churn.
- Regime detector (optional corr input).

These are active in the ARCH path and _perform_daily_rebalance.

---

## Configuration

Primary: `trading_config_phase6.json` (or limited variant).

Relevant sections:
- `global_settings`: pairs / opportunity_pool (dynamic basket), use_new_allocator (ARCH-4 flag), total_capital.
- `scheduler`: daily_rebalance_times (list, supports multiple).
- `withdrawal_reserve`: min_reserve_usd, max_deployable_usd, alert_pct, reserve_breach_action.
- `phase_6_specific`: opportunity_pool, correlation_threshold (legacy?).
- Risk/SL params in other sections.

HybridRebalancer has its own DEFAULT_CONFIG (sentiment_delta_threshold=0.15, etc.) overridable via passed config.

---

## Logging, Monitoring & Observability

- Structured: `log_rebalance_event()` → `data/state/rebalance_history/default.jsonl`.
- Reports: Intelligence reports + `intel_strategic_brief.json` (consumed pre-rebalance).
- Telemetry: Telegram digests ("Daily Rebalance Complete (ARCH-4)"), dashboard caches (p1_metrics, recovery_state).
- TradeLedger for executed trades with reasons.
- Runner logs with ARCH-4 proposal/plan details.
- Isolation tests capture rebalance paths.

---

## Gap Analysis: Original Spec vs Current Implementation

### Original Spec (v1.0, ~April 2026)
- **Core Idea**: Weekly correlation-aware rebalancing as primary overlay.
- **Trigger**: Every 7 cycles (~weekly). Correlation matrix on 30-cycle window. Avg corr > 0.7 → identify clusters.
- **Algorithm**: Shift 50% of high-corr pair allocations to reserve → re-deploy from reserve weighted by sentiment score (>0.55).
- **Frequency Justification**: Backtest showed weekly optimal (+21.5% P&L, best Sharpe/MDD vs monthly/daily) in bearish period; avoids fee drag of daily.
- **Config**: Hardcoded REBALANCE_CONFIG (frequency_cycles=7, high_corr_threshold=0.7, rebalance_shift_percent=0.5, sentiment_deploy_factor=0.2).
- **Integration**: Direct `_rebalance_if_needed()` in old phase5_multi_pair.py main loop (after RSI, before order_executor).
- **Monitoring**: Specific rebalance JSON (avg_correlation, high_corr_pairs, allocations_before/after, reserve levels). Daily summary text with capital shifted, sentiment weighting.
- **Risk**: Corr spike → heavy reserve shift; uncorrelated → max deploy; sentiment flip → defensive reserve.
- **Expected**: ~52 rebalances/year, 0.4% fee drag, rebalancing contributes ~18% of returns.

### Current Implementation (v3.0, July 2026)
- **Core Idea**: Hybrid signal-driven rebalancing within a full ARCH pipeline. Daily time-based + threshold triggers. Correlation is a supporting risk layer, not the main driver.
- **Triggers**:
  - Time-scheduled (config daily_rebalance_times, e.g. 09:00/21:00).
  - HybridRebalancer: sentiment_delta >=0.15, vol_spike, drawdown >=0.08 + min 24h interval + rule AI filter.
  - ARCH-4: evaluate_universe proposals drive Allocator decisions.
- **Algorithm**:
  - Pre-refresh data (RSI cache, brief with Polymarket).
  - Proposals from real sentiment + RSI + scanner.
  - Allocator Rotation (catch-the-wave with DD exits, cooldowns, min deltas) or Rebalance (inverse-vol + tilt).
  - Plan deltas → execute with OrderExecutor inside SL suspend context.
  - Withdrawal reserve enforced first.
- **Frequency**: Daily (or forced), with hybrid gates. Not locked to weekly or 7-cycle.
- **Config**: trading_config_phase6.json (scheduler, withdrawal_reserve, use_new_allocator, dynamic opportunity_pool). Hybrid defaults in code.
- **Integration**: Deep in Phase6Runner `_run_cycle` / `_perform_daily_rebalance`. ARCH layers, brief consumption, SL coordination, TradeLedger.
- **Monitoring**: JSONL rebalance history, intelligence briefs (Polymarket + sentiment + proposals), ARCH-4 digests, dashboard metrics, isolation test logs.
- **Risk Layers** (expanded): Reserve enforcement, DD in strategies, corr circuit breaker (>0.85 → reduce/redeploy), SL re-attach, cooldowns, min moves.
- **Basket**: Dynamic 11-12 pair opportunity_pool (config-driven).
- **Data Discipline**: All via paths.py canonicals, real caches/DB, no synthetic in hot paths.

### Specific Gaps / Differences
1. **Correlation Role**: Old = primary trigger (0.7 threshold, 30-cycle matrix, cluster shifts). Current = demoted to risk circuit breaker (0.85 threshold, position reduction + reserve redeploy). Rolling correlation module exists but not central to rebalancer. Hybrid docstring explicitly says "replaces pure correlation rebalancing".

2. **Frequency & Trigger**: Old = fixed weekly (every 7 cycles). Current = time-scheduled daily + hybrid signal thresholds + manual force. More responsive.

3. **Core Drivers**: Old = corr matrix + sentiment redeploy. Current = RSI + multi-source sentiment (via evaluate_universe) + inverse-vol + drawdown/vol/sentiment deltas in Hybrid/Allocator.

4. **Architecture**: Old = procedural function in legacy loop. Current = modular ARCH-1 (evaluate) + ARCH-2 (Allocator strategies) + HybridRebalancer + runner orchestration. Pluggable, isolation-testable.

5. **Risk & Guards**: Old had basic corr/reserve/sentiment rules. Current adds withdrawal reserve enforcement, SL suspend/reattach (CR-03), trailing DD exits, cooldowns, min score deltas, opportunity scanner diversification.

6. **Data & Observability**: Old assumed simple prices_history + sentiment. Current integrates decoupled RSI pipeline, intel_brief (Polymarket regime bias), aged sentiment, TradeLedger, briefs in reports, rebalance JSONL + dashboards.

7. **Basket & Config**: Old fixed 5 pairs + hardcoded config. Current dynamic 12-pair pool, config-driven scheduler/reserve/ARCH flags.

8. **Implementation Status**: Old was "Ready for Implementation" into phase5_multi_pair.py. Current is running in production Phase6Runner with ARCH-4 path (use_new_allocator), live order execution, and hardening tasks (CR series).

### What's Missing from Old Spec (Relative to Current)
- The exact correlation-on-7-cycles algorithm and 30-cycle window logic (largely replaced).
- Weekly-only assumption and specific backtest numbers as primary justification.
- Direct `_rebalance_if_needed` in a simple loop.

### What's Been Added (Beyond Old Spec)
- ARCH evaluation + allocator stack.
- Hybrid threshold + AI filter rebalancer (sentiment/vol/DD primary).
- Daily time scheduling + force mechanisms.
- Pre-rebalance data refresh + strategic brief consumption (Polymarket).
- Withdrawal reserve, SL coordinator integration, drawdown-aware rotation.
- Correlation as circuit breaker (higher threshold).
- Full data flow hygiene (paths, caches, DB).
- Rich observability (reports, briefs, influence, JSONL logs).
- Dynamic basket and config-driven flexibility.
- Production hardening (freshness guards, dedup, re-attach stability).

### Advantages of Current Approach
- **Responsiveness + Discipline**: Daily scheduling with signal/hybrid gates + min intervals avoids both stagnation and excessive churn/fee drag.
- **Better Risk Management**: Multi-layered (reserve, DD exits, SL re-attach, corr breaker, cooldowns) vs single corr threshold.
- **Richer Signals**: Real RSI pipeline + X/Reddit sentiment + Polymarket regime + opportunity scanner vs basic sentiment weighting.
- **Modularity & Testability**: ARCH components + isolation tests make it easier to validate and evolve (vs monolithic old loop).
- **Observability**: Briefs and reports give context (why rebalance now? regime bias? high-SL pairs?) far beyond old rebalance JSON.
- **Production Readiness**: Withdrawal enforcement, SL stability, dynamic baskets, live execution path.
- **Evolvability**: Easy to toggle ARCH-4, add more regime inputs, or adjust thresholds via config.

The old correlation-weekly design provided valuable backtest evidence for avoiding daily fee drag, but live implementation prioritized signal quality, continuous risk, and architectural cleanliness.

---

## References & Related Docs

- `phase6/core/phase6_runner.py` (rebalance logic, ARCH-4)
- `phase6/core/rebalancing/hybrid_rebalancer.py`
- `phase6/core/allocator.py` (strategies)
- `phase6/core/evaluation.py`
- `phase6/core/allocation_engine.py`
- `docs/DATA_FLOW_AND_LOCATIONS.md` + `phase6/core/paths.py`
- `phase6/core/risk/correlation_circuit_breaker.py`, `rolling_correlation.py`
- `phase6/core/stop_loss_coordinator.py`
- Config: `trading_config_phase6.json`
- Intelligence report generator
- Isolation tests (test_isolation_allocator.py, rebalance path tests, etc.)
- Archive of older rebalance specs for history

_This document now accurately reflects the running Phase 6 rebalancing system. The original spec is preserved in the .bak file._