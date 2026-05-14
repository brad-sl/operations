# Phase 6 Dynamic Trading Engine — Live Deployment Guide

**Version:** 2026-05-08  
**Purpose:** Complete checklist and component inventory so the entire system can be deployed or recreated on a new host with minimal friction.

---

## 1. Prerequisites

- Ubuntu 24.04 LTS (or Debian-based) host with Tailscale (recommended for secure access)
- Python 3.11+ with venv or conda environment
- Node.js 22+ and pnpm/npm (for OpenClaw gateway + agents)
- SQLite (for unified `reports.db`)
- Access to Coinbase Advanced Trade API keys (or equivalent exchange)
- Git repository cloned to both local and remote locations

---

## 2. Core Components Inventory

| Component                           | File/Path (typical)                        | Purpose                                      | Criticality |
|-------------------------------------|--------------------------------------------|----------------------------------------------|-----------|
| **MultiPairAnalyzer**               | `multi_pair_analyzer.py`                   | 5-layer scoring + dynamic pair discovery     | High      |
| **Phase 6 Account Initializer**     | `phase6_account_initializer.py`            | Replaces static Fresh Start with dynamic     | High      |
| **RiskEngine**                      | `risk_engine.py`                           | Position sizing, drawdown protection         | High      |
| **LivePortfolioManager**            | `live_portfolio_manager.py`                | Order execution, position tracking           | High      |
| **Multi-Pair Orchestrator**         | `multi_pair_orchestrator.py`               | Main trading loop + reallocation scheduler   | High      |
| **Unified Reports DB**              | `~/.trading-bot/reports.db`                | Single source of truth for pairs & signals   | High      |
| **Historical Data Collector**       | `historical_data_collector.py`             | OHLCV + volume ingestion                     | Medium    |
| **Backtest Runner**                 | `ca_backtest_runner.py`, `backtest_6mo.py` | Validation & regression testing              | Medium    |
| **OpenClaw Main Agent**             | This workspace + sessions                  | Orchestration, monitoring, alerts            | Medium    |
| **Adspirer Integration** (optional) | Adspirer plugin                            | Paid media performance tracking (future)     | Low       |

---

## 3. Step-by-Step Deployment

### Step 1: Repository Sync
```bash
# Local
git clone <repo-url> trading-bot-phase6
cd trading-bot-phase6
git checkout phase6-dynamic

# Remote / Prod
git clone <repo-url> trading-bot-phase6
cd trading-bot-phase6
git checkout phase6-dynamic
git pull --rebase
```

### Step 2: Environment Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# (numpy, pandas, ta-lib, sqlite-utils, ccxt or coinbase-advanced-py, etc.)
```

### Step 3: Database Initialization
```bash
python -c "
from phase6_account_initializer import initialize_unified_db
initialize_unified_db()
"
```

### Step 4: Configure Dynamic Initialization (Key Change)
Edit `config_phase6.json` or environment:
```json
{
  "initialization_mode": "dynamic",
  "analyzer": "MultiPairAnalyzer",
  "reallocation_interval_hours": 5,
  "scoring_layers": ["rsi11", "sentiment_proxy", "volatility_band", "momentum_roc"],
  "top_n_pairs": 3,
  "risk_per_trade_pct": 1.0,
  "daily_loss_cap_pct": 5.0,
  "max_drawdown_kill_pct": 15.0
}
```

Run the updated initializer:
```bash
python phase6_account_initializer.py --mode takeover --capital 1000 --paper
```

### Step 5: Shadow Mode Validation (48 hours recommended)
```bash
python phase6_account_initializer.py --shadow 48h
# Monitor via OpenClaw trading-monitor agent or dashboard
```

### Step 6: Go Live
```bash
python multi_pair_orchestrator.py --live --capital 1000
# or via systemd service / cron + OpenClaw agent
```

---

## 4. Recommended OpenClaw Integration

- Use dedicated `trading-monitor` agent (30-minute heartbeat) for P/L, open positions, and anomaly alerts.
- Store all trade events + analyzer scores in the unified SQLite DB for reporting and future ML.
- Set up daily cron: `healthcheck:trading-performance` + weekly backtest regression.

---

## 5. Rollback Plan

If issues arise:
1. `phase6_account_initializer.py --mode fresh-start` (legacy static allocation)
2. Kill live orchestrator
3. Restore from last known-good `reports.db` snapshot

---

**Document Owner:** Orchestration Agent  
**Last Updated:** 2026-05-08

## Pending Items (Post-Implementation)

- [ ] Confirm exact repository URL and current branch
- [ ] Run final git status + push after code changes
- [ ] Add CI regression test referencing this backtest
- [ ] 48h shadow mode confirmation on live account
- [ ] Update trading engine defaults in `phase6_account_initializer.py` and `multi_pair_orchestrator.py`
- [ ] Add `Phase6_Dynamic_Method_Documentation.md` and this file to repo root