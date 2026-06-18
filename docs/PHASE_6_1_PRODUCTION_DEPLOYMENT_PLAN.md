# Phase 6.1 Production Deployment Plan

**Phase:** 6.1 (Capital Allocation, Withdrawal Reserves, Sticky Rebalancing, CR-03)
**Status:** Planning Stage
**Target Environment:** Production (Coinbase Advanced Trade)
**Last Updated:** 2026-05-26
**Owner:** crypto-orchestrator

---

## 1. Executive Summary

This plan covers full production deployment of Phase 6.1 features:
- Capital Allocation engine (dynamic % deployment + reserve system)
- Withdrawal Reserves (min_reserve_usd protection)
- Sticky Rebalancing (CR-03 coordination layer)
- CR-03 (Rebalance + SL/TP suspension + re-attach workflow)

Deployment path: Paper → Sandbox → Limited Live (10%) → Full Production.

---

## 2. System Dependencies (Master List)

**Critical ordering note:** Sentiment system **must launch first** — multiple downstream components (allocation, rebalancing decisions, signal quality) depend on fresh sentiment scores.

### 2.1 Core Dependency Graph

```
Sentiment Layer (highest priority)
├── fetch_x_sentiment.py          (X/Twitter, 30-min cadence, Bearer token)
├── fetch_reddit_sentiment.py     (Apify actor, 60-min half-life)
├── sentiment_scorer.py           (load_sentiment_scores, time-decay, get_sentiment_adjusted_weights)
├── sentiment_cache/*.json
└── Cron: twice-daily-trading-intelligence → now 0,30 * * * * (delivers to this chat)

Allocation & Decision Layer
├── allocation_engine.py          (compute_inverse_vol_allocations, rebalance_plan)
├── sentiment-adjusted weights    (from scorer)
└── phase6_runner.py              (orchestrator, 5-min cycle)

Risk & Execution Layer
├── stop_loss_manager.py
├── stop_loss_coordinator.py
├── order_executor.py
├── exchange_client.py            (Coinbase Advanced Trade)
├── live_portfolio_manager.py
└── trade_ledger.py

State & Observability
├── phase6_runner_state.json
├── TradeLedger (log_trade signature)
├── Phase6Notifier + error_notifier.py
├── phase6_monitor.db
└── dashboard (serve_dashboard.py)

Infrastructure & Config
├── .env                          (xAI + Coinbase credentials)
├── cron/jobs.json                (sentiment job + any others)
├── config.yaml / trading_config_phase6.json
├── logs/ (phase6_runner.log, error.log)
└── kanban.db + MASTER_TASK_TRACKING.md (file-based source of truth)
```

### 2.2 Launch Order (Mandatory)

1. Sentiment fetchers + scorer + cron job (this chat delivery)
2. Allocation engine + sentiment scorer integration
3. Stop-loss coordinator + rebalance logic
4. Full phase6_runner (shadow → paper → live)
5. Dashboard + monitoring

### 2.3 External Service Dependencies

- **xAI / Grok** — for intelligence reports and subagent work (creds in .env)
- **Coinbase Advanced Trade API** — execution + stop-limit orders
- **Apify** — Reddit sentiment scraping
- **X API v2** — Twitter sentiment (Bearer token)
- **Telegram** — delivery target (current DM chat 1617763347)

---

## 3. Environment & Infrastructure

### 2.1 Environments

| Environment | Purpose | Credentials | Capital | Monitoring |
|-------------|---------|-------------|---------|------------|
| Local dev | Development & unit tests | None | Simulated | Console |
| Paper trade | Existing internal mode | Live keys | Zero risk | File + dashboard |
| Sandbox | Coinbase sandbox | Sandbox keys | Sandbox USD | Full stack |
| Staging | Pre-prod validation | Live keys | 1-5% | Full + alerts |
| Production | Live trading | Live keys | 10% → 50% ramp | Full + on-call |

### 2.2 Required Secrets (Production)

All secrets loaded via environment variables only. Never commit.

```
export COINBASE_API_KEY="..."
export COINBASE_API_SECRET="..."
export COINBASE_PASSPHRASE="..."          # if required
export PHASE6_STATE_DIR="/var/lib/crypto-bot/phase6/state"
export PHASE6_LOG_DIR="/var/log/crypto-bot/phase6"
export SLACK_WEBHOOK_URL="..."            # for alerts
export PROMETHEUS_PUSHGATEWAY="..."       # optional
```

**Secret Rotation Policy:** Rotate API keys every 90 days. Store previous key for 7-day overlap window.

### 2.3 Host Requirements (Production)

- Ubuntu 22.04+ or Debian 12+
- Python 3.10+
- 4 vCPU / 8 GB RAM minimum (recommend 8 vCPU / 16 GB)
- 100 GB SSD (state + logs + backtests)
- Docker or systemd service management
- UFW or cloud firewall (allow only outbound to coinbase.com + monitoring)

---

## 3. Monitoring Stack

### 3.1 Core Metrics (Prometheus + Grafana recommended)

- `phase6_cycle_duration_seconds`
- `phase6_pain_score{ pair }`
- `phase6_capital_deployed_pct`
- `phase6_reserve_usd`
- `phase6_liquidation_events_total`
- `phase6_rebalance_operations_total`
- `phase6_api_errors_total{ endpoint }`
- `phase6_state_write_latency_seconds`

### 3.2 Alerting Rules (Critical)

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| High PAIN_SCORE | > 30 for 3+ cycles | Critical | Pager + Slack |
| Capital > 80% deployed | > 80% for 2 cycles | Warning | Slack |
| Reserve below min | < min_reserve_usd | Critical | Immediate stop |
| API error rate > 5% | 5min window | Critical | Pager |
| Stuck rebalance | Rebalance > 30min | Critical | Pager |
| State corruption | JSON schema fail | Critical | Auto-stop + restore |

### 3.3 Logging

Structured JSON logs to file + stdout.

```
{
  "ts": "2026-05-26T14:22:11Z",
  "level": "INFO",
  "component": "capital_allocator",
  "event": "allocation_decision",
  "pair": "BTC-USD",
  "deploy_pct": 0.65,
  "reserve_pct": 0.35,
  "pain_score": 18.4
}
```

Log rotation: 100 MB per file, keep 14 days.

---

## 4. Step-by-Step Deployment

### Phase A: Pre-Deployment Validation (Local + CI)

1. Run full test suite for state manager + liquidation logic.
2. Verify all Phase 6.01 checklist items are marked complete.
3. Remove all `unittest.mock` objects from production path.
4. Confirm `numpy`, `coinbase-advanced-py` (or wrapper) installed.
5. Run config validator: `reserve_pct + deploy_pct <= 1.0`, `sl_pct < tp_pct`.

### Phase B: Sandbox Deployment (24-48h)

1. Provision Coinbase sandbox account.
2. Load sandbox credentials into environment.
3. Deploy latest Phase 6.1 code to sandbox host.
4. Run in `PAPER_TRADE` mode for 24h with production-like config.
5. Monitor PAIN_SCORE, capital flow, rebalance events.
6. Verify state persistence across simulated restarts.

### Phase C: Limited Live (Staging)

1. Use live API keys with conservative config:
   - `initial_deploy_pct`: 0.10 (10%)
   - `min_reserve_usd`: 500
   - `max_pain_score`: 25
2. Run for 48-72h in observe-only mode (no new orders first 24h).
3. Gradually enable trading at 2-5% of allocation.
4. Daily review meetings.

### Phase D: Production Ramp

| Week | Allocation | Conditions | Monitoring |
|------|------------|------------|------------|
| 1 | 10% | Stable sandbox + staging | Every 2h |
| 2 | 25% | No critical alerts, healthy metrics | Every 4h |
| 3-4 | 40% | 7+ days clean run | Daily summary |
| 5+ | 50-70% | Full confidence | Normal on-call |

Rollback trigger at any stage: >2 critical alerts or >5% drawdown in 24h.

---

## 5. Rollback Strategy

### Automatic Rollback Triggers

- State file corruption detected
- >3 consecutive API failures on critical endpoints
- Reserve falls below `min_reserve_usd` for >2 cycles
- Rebalance operation exceeds 45 minutes

### Manual Rollback Steps

1. `systemctl stop crypto-bot-phase6` (or equivalent)
2. Close all open orders via Coinbase web UI (emergency liquidation if needed)
3. Restore state from latest valid backup:
   `cp /var/lib/crypto-bot/phase6/state/STATE.json.bak TIMESTAMP.json`
4. Switch to `PAPER_TRADE` mode
5. Investigate root cause before re-enabling live

### Emergency Contacts

- Primary on-call: [TBD]
- Secondary: [TBD]
- Coinbase support ticket escalation path documented in runbook

---

## 6. Post-Deployment Operations

### Daily

- Review overnight liquidation and rebalance events
- Check reserve levels
- Verify state file size and last modified time
- Backup state to S3 or offsite storage

### Weekly

- Analyze capital allocation efficiency
- Review PAIN_SCORE distribution
- Audit CR-03 rebalance success rate
- Update Grafana dashboards if new metrics added

### Monthly

- Full performance review vs backtest
- Security audit of API keys and access
- Capacity planning (host resources)
- Plan 6.2 enhancements

---

## 7. Success Criteria

Deployment considered successful when:

- Zero critical alerts for 14 consecutive days at 50%+ allocation
- Capital allocation engine keeps reserve ≥ min_reserve_usd 99.5% of time
- CR-03 rebalance operations complete in <15 minutes average
- State persistence survives 100% of simulated host restarts
- All Phase 6.1 features exercised in production with documented results

---

## 8. References

- `PHASE_6_01_DEPLOYMENT_CHECKLIST.md`
- `PHASE_6_01_RELEASE_NOTES.md`
- `PHASE_6_DECISION_LOG.md` (Capital Allocation strategy section)
- `phase6/tasks/reconciliation/CR-03*.md` (full CR-03 breakdown)
- `data/state/STATE.json` (example state structure)

---

**Document saved to:** `/home/brad/projects/crypto-trading-bot/docs/PHASE_6_1_PRODUCTION_DEPLOYMENT_PLAN.md`

Ready for kanban_complete.
---

## 8. RSI Signal Pipeline Restoration (Added 2026-06-04)

**Status**: Integrated into `phase6_runner.py`

### Overview
Restored RSI as the **primary signal driver** per the original Phase 6.01 architecture documented in `TRADING_BOT_DOCS.md`.

### Components Added
- `phase6/core/price_history_manager.py` — Rolling price history with persistence
- Integration in `Phase6Runner._update_price_history_and_calculate_rsi()`
- RSI values (`rsi` dict) now written to `phase6_live_state.json` every cycle

### Signal Philosophy
- **Primary**: RSI (14-period)
- **Secondary**: Sentiment as conviction multiplier (not hard AND gate)
- Graceful degradation when NumPy/RSI unavailable

### Files Modified
- `phase6/core/phase6_runner.py`
- `run_sentiment_system.py` (enhanced to surface RSI)

### Validation
- Runner continues to function in shadow/live mode
- `phase6_live_state.json` now contains `"rsi": { "BTC-USD": xx.xx, ... }`
- Trading Intelligence Report can now consume fresh RSI values

**Commit**: `f08c6d3` — "feat: Integrate PriceHistoryManager + RSI calculation into Phase6Runner"



## 9. Smoke Test & SL Verification Integration (Added 2026-06-17)

**Smoke test script**: `scripts/run_shadow_rebalance_cycle.py`

### Standard Deployment Procedure Update
Before every major deployment (paper, sandbox, staging, production ramp):
1. Run `python scripts/run_shadow_rebalance_cycle.py`
2. Verify:
   - suspend_reattach_context is entered ([CR-03] logs)
   - SL attachment is exercised for any buys (post-fix in order_executor)
   - Allocator produces a sensible plan using current RSI + Sentiment
   - No crashes in coordinator or executor
3. Review output for:
   - Which pairs are sold/bought
   - Re-attach confirmations
   - Any warnings from stop price adjustments

### Full End-to-End Smoke (Optional but Recommended for Live)
User-approved: Place a **small live test trade** ($10-25) on a low-conviction pair (e.g. current weakest), 
validate:
- Order fills
- SL attaches automatically (check logs + Coinbase UI)
- Position appears in state
- Then liquidate the test position (via runner or manual)
- Confirm SL was suspended/reattached cleanly during liquidation

Command for full smoke (when ready):
  python scripts/run_shadow_rebalance_cycle.py --live-smoke --amount 15

This test is now **mandatory gate** before any capital-increasing deployment.

### Files Updated
- phase6/core/order_executor.py (SL attach after buy)
- phase6/core/exchange_client.py (improved get_open_orders + new get_open_stop_orders)
- phase6/core/stop_loss_coordinator.py (better stop filtering)
- scripts/run_shadow_rebalance_cycle.py (the smoke runner)
- This doc

**Last verified**: 2026-06-17 via shadow run (see logs in this execution).
