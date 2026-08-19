# Handoff: Phase 6 dashboard — reliable composition & field population

**Date:** 2026-07-08  
**Assignee:** grok-4.5 (Hermes `delegate_task`)  
**Status:** Complete (2026-07-08)  
**Epic context:** Phase 6 ops (not SCALING-1000)

## Problem

Dashboard **renders** at `http://127.0.0.1:8502` (`serve_dashboard.py --mode live`) but **report fields show empty / `--` / $0.00** despite backend having data.

User report: "no data fields populated."

## Observed (Scotty probe 2026-07-08)

| Endpoint | Result |
|----------|--------|
| `/api/balances`, `/api/positions` | JSON with `balances` + `positions` (6 pairs); verify **`total_usd` / `total_balance` / `cash_positions` / `trading_positions`** at root |
| `/api/performance` | `status: ok`, win_ratio, periods |
| `/api/trades`, `/api/sentiment`, `/api/rsi`, `/api/rebalances`, `/api/brief`, `/api/recovery` | Return data |
| `/api/metrics` | **Hangs / >8s timeout** — likely blocks `Promise.all` in `phase6_dashboard.html` |

**UI contract:** `phase6_dashboard.html` uses `Promise.all` on 9 endpoints; header total uses `balData.total_usd` (line ~180). If missing → **$0.00**.

**Architecture:** `cached-live-data-serving` — cache-first `data/state/phase6_live_state.json`; no live exchange on page load. `enrich_live_state()` in `serve_dashboard.py` should add splits server-side.

**Stale cache note:** `phase6_live_state.json` may lag exchange (e.g. OP size); refresh via `scripts/refresh_dashboard_live_state.py` + cron — separate from composition bug.

## Scope

1. **Audit** HTML field IDs ↔ each `/api/*` response shape (single **composition contract** doc or table in handoff completion).
2. **Fix** server (`serve_dashboard.py`) and/or client (`phase6_dashboard.html`) so every visible report field gets a value or explicit empty-state reason.
3. **Fix** `/api/metrics` fast-fail (already has `DB_READ_TIMEOUT=0.35` — find why hang persists).
4. **Do not** call Coinbase from HTTP handlers.
5. **Verify:** curl matrix for all endpoints; browser check or scripted DOM assertions; optional `scripts/` isolation wrapper if you add one.

## Key files

- `serve_dashboard.py` — handlers, `fetch_balances`, `enrich_live_state`, DB views
- `phase6_dashboard.html` — `updateDashboard()`, `fetchData`, section renderers
- `data/state/phase6_live_state.json` — cache
- `phase6/core/performance_api.py`, views `v_phase6_dashboard`, `v_dashboard_metrics`
- Skill: `cached-live-data-serving` (+ `trading-bot-operations` dashboard refs)

## Success criteria

- [ ] Total balance, position table, performance, trades, sentiment, RSI, rebalances, observability metrics, brief, recovery — **populated** when backend has data
- [ ] `/api/metrics` responds in <1s or returns degraded JSON without blocking other panels
- [ ] Document field → API → source (cache vs DB) mapping in completion note
- [ ] Update `docs/MASTER_TASK_TRACKING.md` Phase 6 dashboard row with outcome

## Out of scope

- GHL / SCALING-1000
- Changing trading logic or ARCH-4 runner