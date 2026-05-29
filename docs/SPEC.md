# Crypto Trading Bot — Unified Specification

**Status:** Phase 6 Active (Dynamic Basket + Risk Engine + Unified Signals)  
**Date:** 2026-05-15  
**Owner:** Orchestrator + Development Team  
**Purpose:** Single source of truth (Functional + Development + Operational)

---

## 1. Functional Specification

### 1.1 System Purpose
A modular, persistent, multi-pair cryptocurrency trading system that:
- Runs in **paper, backtest, or live** mode
- Combines technical signals (RSI) with sentiment data
- Performs daily rebalancing with risk controls
- Maintains full auditability and recoverability

### 1.2 Core Capabilities (Current - Phase 6)
- Daily rebalance using inverse-volatility + dynamic basket selection with correlation hedging
- Native Stop-loss / Take-profit order attachment via RiskEngine
- Unified signal consumer integrating sentiment + technical signals from reports.db
- Phase6 daily rebalance scheduler with timezone-aware triggers
- Paper trading with full P&L tracking and ledger
- Telegram reporting and monitoring
- Risk management: position sizing, SL/TP validation, poor performer liquidation

### 1.3 Out of Scope (Phase 6)
- High-frequency trading
- Machine learning model training
- Multi-exchange routing

---

## 2. Development Specification

### 2.1 Architecture

```
src/
├── core/          # Pure domain logic (portfolio, risk, execution)
├── sim/           # Paper trading & simulation
├── reporting/     # Logging, dashboards, alerts
└── utils/
```

### 2.2 Module Responsibilities

| Module                      | Responsibility                              | Key Classes / Functions                  |
|----------------------------|---------------------------------------------|------------------------------------------|
| `allocation_engine.py`     | Portfolio allocation calculations           | `compute_inverse_vol_allocations()`, `rebalance_plan()` |
| `live_portfolio_manager.py` | Position tracking & reconciliation         | `LivePortfolioManager`                   |
| `stop_loss_manager.py`     | SL/TP attachment and monitoring             | `StopLossManager`                        |
| `exchange_client.py`       | Exchange abstraction                        | `CoinbaseExchangeClient`                 |
| `paper_trader.py`          | Simulated execution                         | `PaperTrader`                            |
| `report_generator.py`      | Periodic and event-driven reports           | `generate_daily_report()`                |

### 2.3 Data Naming Conventions (Mandatory)

| Concept                    | Canonical Name       | Type                  | Notes |
|---------------------------|----------------------|-----------------------|-------|
| Total deployable capital  | `total_capital`      | float                 | Base currency (USD) |
| Current available cash    | `cash`               | float                 | — |
| Trade size in dollars     | `usd_amount`         | float                 | — |
| Target allocation weights | `target_weights`     | dict[str, float]      | pair → weight |
| Rebalance instruction     | `rebalance_plan`     | list[dict]            | Contains action, pair, usd_amount |
| Paper trade record        | `paper_trade`        | dict                  | See schema below |
| Portfolio snapshot        | `portfolio_state`    | dict                  | Stored in `paper_portfolio.json` |

#### Paper Trade Schema

```json
{
  "timestamp": "2026-05-14T14:30:00Z",
  "action": "BUY",
  "pair": "ETH-USD",
  "usd_amount": 166.67,
  "price": 2450.50,
  "note": "Daily rebalance - Fresh Start"
}
```

### 2.4 Code Style Rules
- All public functions use `snake_case`
- Classes use `PascalCase`
- Configuration keys use `snake_case`
- Constants are `UPPER_SNAKE_CASE`

---

## 3. Operational Specification

### 3.1 Running Modes

| Mode   | Flag       | Trade Execution | Logging          | Use Case                |
|--------|------------|------------------|------------------|-------------------------|
| Shadow | `--mode shadow` (default) | None             | Intended actions | Safe testing            |
| Paper  | `--paper`  | Simulated        | CSV + JSON       | Strategy validation     |
| Live   | `--mode live --confirm-live` | Real orders     | Real + audit     | Production              |

### 3.2 Scheduled Jobs
- `crypto-monitor` — runs every 6 hours, posts to Telegram
- Rebalance runs at `09:00` (America/Los_Angeles) by default

### 3.3 State & Recovery
- `data/state/paper_portfolio.json`
- `data/state/paper_trades.csv`
- `phase6_state.json` (rebalance date persistence)

### 3.4 Alerting
- Telegram bot: `@TheHermesMachineBot`
- Critical errors, large drawdowns, and daily summaries are reported

---

## 4. Phase 6 Status and Current Gaps (Updated 2026-05-15)

**Current Status:** LIVE (minimal runner) — full production runner (`phase6_runner.py` / Phase6DirectTrader) in development. Per PHASE6.md and Kanban tasks in PHASE_6_TASKS.md.

**Live Setup:**
- Runner: operations/crypto-bot/run_phase6_live_final.py (PID 433244, $1000 real capital)
- Active Basket (hard-coded): BTC-USD, ETH-USD, SOL-USD, XRP-USD, DOGE-USD
- Daily Rebalance: Configurable at 09:00 America/Los_Angeles (config/trading_config_phase6.json)
- State: phase6_state.json + portfolio_state.json

**New Profiles / Components (Implemented):**
- RiskEngine (position sizing, native SL/TP attachment, circuit breaker)
- LivePortfolioManager (reconciliation, P&L tracking)
- MultiPairAnalyzer (proactive scanner)
- UnifiedSignalConsumer (reads reports.db for signals)
- Phase6DirectTrader (core trader class)
- CorrelationCalculator / DynamicBasketSelector (partially; full dynamic pending)

**Completed in Phase 6:**
- Minimal live trading loop with Fresh Start + idle
- Config-driven scheduler skeleton
- Core risk and portfolio modules

**Remaining Gaps (from PHASE6.md):**
1. No daily rebalance scheduler — only runs once on start
2. No dynamic basket logic — hard-coded basket
3. No signal-driven decisions — ignores UnifiedSignalConsumer
4. No native SL/TP attachment on new positions
5. No reporting / Telegram digests on each cycle
6. No proactive scanner (RSI + sentiment + volatility)

**Kanban / Next Priorities (referencing PHASE_6_TASKS.md + PHASE6.md):**
1. Integrate scheduler + dynamic basket + signal consumer into phase6_runner
2. Add native SL/TP enforcement and cycle reporting
3. Enable proactive scanner and full correlation hedging
4. Production supervisor + systemd service + comprehensive backtesting
5. Live validation with risk controls

See PHASE6.md for full quick facts, intended architecture, and maintenance schedule.

## 5. Next Development Priorities (Legacy)

1. Complete paper trading loop with synthetic sentiment
2. Add backtesting framework (`run_backtest.py`)
3. Implement real sentiment signal consumer
4. Add correlation-aware rebalancing
5. Production supervisor + systemd service

---

*This document is the single source of truth. All agents and developers must reference and update it.*