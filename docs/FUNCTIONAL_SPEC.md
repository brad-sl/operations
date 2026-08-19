# Functional Specification (Draft)

> **LEGACY — not SSOT (banner 2026-08-13).**  
> Do **not** implement from this file. Cadence, Reddit-on, live TP, and runner paths here are **stale** (Jun 2026).  
> Current: `docs/SPECS_INDEX.md`, `docs/SPECS_CODE_GAP.md`, live `config/trading_config_phase6.json` + `exit_automation.json` + `regime_cash_policy.json`.  
> Profitability / P&L gaps: `reports/PLATFORM_PROFITABILITY_REVIEW_2026-08-13.md`.

**System:** Phase 6 Crypto Trading Platform  
**Status:** Draft — Pre-Production (**historical**)  
**Last Updated:** 2026-06-06  
**Owner:** crypto-orchestrator  
**Purpose:** Single source of truth for the end-to-end trading system architecture, data flows, and component responsibilities.

> **Note:** This is a living draft. It will be expanded after the first full production run and successful paper/live validation cycles.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Core Components](#2-core-components)
3. [Dependency Graph & Launch Order](#3-dependency-graph--launch-order)
4. [Primary Data Flows](#4-primary-data-flows)
5. [Glossary](#5-glossary)
6. [Current Status & Known Gaps](#6-current-status--known-gaps)
7. [Performance Dashboard Requirements](#7-performance-dashboard-requirements)
8. [Recent Core Changes (June 2026)](#8-recent-core-changes-june-2026)

---

## 1. Overview

Phase 6 is a production-grade crypto trading system targeting Coinbase Advanced Trade. It combines:

- Dynamic capital allocation with withdrawal reserves
- Sentiment-adjusted position sizing
- Native stop-loss / take-profit coordination
- Sticky rebalancing (CR-03)
- RSI technical gates + PriceHistoryManager
- Paper → live deployment path with full observability
- Backtest harness and pair selection matrix

The system emphasizes **sentiment as the first-class input** and maintains a strict separation between intelligence gathering and execution. Technical signals (RSI) provide entry gates. Capital deployment is sticky and respects existing holdings.

---

## 2. Core Components

### 2.1 Intelligence Layer (Sentiment + Technical)

| Component                        | File Path                                      | Responsibility                              | Cadence          |
|----------------------------------|------------------------------------------------|---------------------------------------------|------------------|
| X Sentiment Fetcher             | `phase6/core/sentiment/fetch_x_sentiment.py`   | Pull & cache X posts with decay             | ≤ 30 min        |
| Reddit Sentiment Fetcher        | `phase6/core/sentiment/fetch_reddit_sentiment.py` | Apify actor for Reddit threads (fast actor) | 60 min half-life |
| Sentiment Scorer                | `phase6/core/sentiment_scorer.py`              | Aggregate + time-decay scoring              | On demand       |
| PriceHistoryManager             | `phase6/core/price_history_manager.py`         | OHLCV caching + RSI computation             | On demand / 5m  |
| RSI Calculator                  | Integrated in PriceHistoryManager + runner   | 14-period RSI with gates for entry          | Per cycle       |
| Trading Intelligence Cron       | `cron/jobs.json` (job 4dcba7aa8f06)            | Generate report + deliver to Telegram       | 2× per hour     |

### 2.2 Decision & Allocation Layer

| Component                        | File Path                                      | Responsibility                              |
|----------------------------------|------------------------------------------------|---------------------------------------------|
| Allocation Engine               | `phase6/core/allocation_engine.py`             | Inverse-vol + sentiment-adjusted weights    |
| Phase 6 Runner                  | `phase6/core/phase6_runner.py`                 | Main orchestrator (5-min cycles)            |
| Rebalance Logic                 | `phase6/core/allocation_engine.py`             | Sticky rebalancing (CR-03)                  |
| Pair Selection Matrix           | `docs/PAIR_SELECTION_MATRIX.md` + runner       | Dynamic basket selection with correlation   |
| Capital Deployment              | Integrated in runner + allocation              | Redeploy freed capital per rules            |

### 2.3 Execution & Risk Layer

| Component                        | File Path                                      | Responsibility                              |
|----------------------------------|------------------------------------------------|---------------------------------------------|
| Stop Loss Manager               | `phase6/core/stop_loss_manager.py`             | Native Coinbase stop-limit orders           |
| Stop Loss Coordinator           | `phase6/core/stop_loss_coordinator.py`         | Attach/reattach SL/TP on rebalance (CR-03)  |
| Order Executor                  | `phase6/core/order_executor.py`                | Live order placement                        |
| Exchange Client                 | `phase6/core/exchange_client.py`               | Coinbase Advanced Trade wrapper (hardened)  |
| Live Portfolio Manager          | `phase6/core/live_portfolio_manager.py`        | Position tracking & capital deployment      |

### 2.4 State & Observability

- `phase6_runner_state.json`
- `TradeLedger`
- `Phase6Notifier` + error channels
- Dashboard (`serve_dashboard.py`) — real data, no placeholders
- Logs + `phase6_monitor.db`
- `MASTER_TASK_TRACKING.md` (primary durable record of tasks)

### 2.5 Backtesting & Validation

- Backtest Harness (`BACKTEST_HARNESS_DESIGN.md`)
- Full historical validation support

---

## 3. Dependency Graph & Launch Order

**Critical Rule:** Sentiment must be running and producing fresh scores before any allocation or execution decisions are made. RSI gates must pass for new entries.

```
Sentiment + Technical Layer (MUST START FIRST)
├── X + Reddit fetchers (updated actors)
├── sentiment_scorer.py (decay + aggregation)
├── PriceHistoryManager + RSI
└── Intelligence Cron (2×/hour → this Telegram chat)

Allocation Layer
├── allocation_engine.py (sticky + capital deploy)
├── pair selection matrix
├── sentiment + RSI adjusted weights
└── phase6_runner.py (orchestrator, 5m cycles)

Risk & Execution Layer
├── stop_loss_coordinator + stop_loss_manager (CR-03 suspend/reattach)
├── order_executor + exchange_client (hardened)
└── live_portfolio_manager (position-aware caching)

State & Monitoring
├── TradeLedger + state files
├── Notifier + dashboard (real holdings/PnL)
└── MASTER_TASK_TRACKING.md (primary durable record)
```

**Mandatory Launch Sequence**

1. Sentiment fetchers + scorer + cron job
2. PriceHistoryManager + RSI integration
3. Allocation engine + sentiment/RSI integration + capital deployment
4. Stop-loss coordinator + rebalance logic (CR-03)
5. Full `phase6_runner` (shadow → paper → live)
6. Dashboard + alerting + backtest validation

**External Dependencies**

- xAI (Grok) — intelligence reports & sub-agents
- Coinbase Advanced Trade API
- Apify (Reddit — fast actor)
- X API v2 (Bearer token)
- Telegram (current DM: 1617763347)

---

## 4. Primary Data Flows

### Sentiment + RSI → Trading Decision Flow

1. Fetchers populate `sentiment_cache/*.json`
2. `sentiment_scorer.py` produces decayed scores
3. `PriceHistoryManager` provides RSI values
4. `allocation_engine.py` computes weights using sentiment + RSI gates
5. Runner evaluates rebalance need every 5 minutes (position-aware)
6. On rebalance: StopLossCoordinator detaches old SL/TP → new allocation (sticky, respects holdings) → re-attach stops + deploy capital if needed
7. TradeLedger records all actions
8. Intelligence report generated 2×/hour and delivered to Telegram

### Rebalance + Stop-Loss Coordination (CR-03) + Capital Deployment

- Rebalance triggers → pause new SL/TP
- Execute rebalance (sticky — scale existing pairs preferentially)
- Re-attach stops on new positions
- Deploy freed/reserve capital only to qualifying pairs (sentiment threshold)
- Resume normal monitoring
- 24h cooldown on recently stopped-out pairs (quality gate)

---

## 5. Glossary

| Term                    | Definition                                                                 |
|-------------------------|----------------------------------------------------------------------------|
| **Sticky Rebalancing**  | CR-03 logic that coordinates rebalancing with stop-loss suspension; prefers existing holdings |
| **PAIN_SCORE**          | Internal risk metric used for alerting                                     |
| **Withdrawal Reserve**  | Minimum USD buffer that is never deployed                                  |
| **Sentiment Decay**     | Time-based weighting (X: 15-min half-life, Reddit: 60-min)                 |
| **Shadow Mode**         | Full cycle execution with no real orders                                   |
| **TradeLedger**         | Canonical record of all executed or simulated trades                       |
| **RSI Gate**            | 14-period RSI threshold that must be satisfied for new entries             |
| **Position-Aware Caching** | 10min TTL cache for holdings to avoid excessive exchange calls            |
| **Capital Deployment**  | Rules for intelligently redeploying freed capital (stronger sentiment for new pairs) |

---

## 6. Current Status & Known Gaps (as of 2026-06-06)

**Verified Working**

- Stop-loss manager + coordinator integrated into runner (CR-03 suspend/reattach working)
- Sentiment cron running at 2×/hour with correct delivery (updated actors)
- Runner cycling cleanly (no blocking errors)
- File-based `MASTER_TASK_TRACKING.md` established as source of truth
- PriceHistoryManager + RSI pipeline integrated
- Exchange client hardened + RSI gate in reports
- Dashboard shows real holdings/PnL (no placeholders)
- Capital deployment rules defined and ready for wiring

**Known Gaps / Draft Items**

- Full production run not yet completed (paper/live validation pending)
- TradeLedger signature warning still present (non-blocking)
- Comprehensive end-to-end test matrix pending (including backtests)
- Logic diagrams (Mermaid) to be added after first live validation
- Glossary to be expanded with more domain terms
- Backtest harness + pair selection matrix integration into live flow pending full validation

---

*This document will evolve. After the first successful production run, it will be promoted from Draft to v1.0 and expanded with sequence diagrams, state machines, and full API contracts.*

## 7. Performance Dashboard Requirements (Added 2026-06-02)

### 7.1 Use Case
Traders must be able to view:
- Current balances (cash + holdings)
- P&L across multiple time windows: 1 day, 7 days, 1 month, 1 quarter, 1 year

### 7.2 Scalability Requirements
- Must support at least 1,000 concurrent users
- Response time target: < 200ms for performance queries
- Avoid full ledger scans on hot path
- Prefer pre-computed snapshots + efficient indexing

### 7.3 Related Artifacts
- Handoff: `handoffs/phase6/Handoff_Performance_Dashboard.md`
- Task tracked in `MASTER_TASK_TRACKING.md`

## 8. Recent Core Changes (June 2026)

- **RSI Integration**: PriceHistoryManager + 14-period RSI with entry gates added to runner and intelligence reports.
- **Exchange Client Hardening**: Rate-limit-safe caching, position awareness (10min TTL), robust error handling.
- **Trading Intelligence Report**: Enhanced with RSI pipeline and sentiment scoring improvements.
- **Capital Deployment**: New rules for redeploying freed capital (sentiment thresholds, sticky to existing holdings).
- **Dashboard**: Full real-data implementation (D-01 to D-04 complete) — no dummy values.
- **Stop-Loss / CR-03**: Full rewrite of reattach logic; legacy stops cleaned.
- **Backtesting & Pair Selection**: Dedicated harness and matrix documents created for systematic validation.
- **MASTER_TASK_TRACKING.md**: Confirmed as single source of truth for all delegated work.
- **Sentiment Actors**: Switched to more robust/fast Apify and X implementations with fallback.

All changes are reflected in code, docs, and the durable task tracking file.