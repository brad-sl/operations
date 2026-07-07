# Handoff: ANALYST-OPT R2 — Production compare + brief + weekly cron

**Date:** 2026-07-07  
**Status:** Complete

## Delivered

1. **Production baseline** (`production_period_baseline.py`)
   - Pack-window **overlap** with `trades/phase6_trades.jsonl` + rebalance history
   - **Since go-live** metrics (first trade → today): return vs `total_usd`, trade counts
   - Real ledger only — no fabricated P&L

2. **Leaderboard** `--compare-production`
   - `production`, `production_since_go_live`, `vs_production` on `analyst_scenario_leaderboard_latest.json`
   - ARCH-4 scenarios clipped to pack `date_range` when OHLCV exists

3. **Brief integration**
   - `optimization_brief.py` → intelligence report section + `intel_strategic_brief.json` → `optimization`

4. **Weekly job**
   - `run_analyst_opt_weekly.py` + `.sh`
   - Hermes cron `e039d96c4732` — Sun 04:00 PT, `no_agent`, deliver local
   - Learnings dedup (removed 17 dupes on first run)

## Verified (2026-07-07)

- Weekly run: `OPT-20260707-200726`, winner `rebalance_7d`
- Production since go-live: **return_pct ≈ -28.23%**, equity **$717.74** (vs $1000 config)
- Pack `r1` OHLCV ends **2026-04-19**; live starts **2026-06-06** → **overlap none** until OHLCV refresh

## Deployment decisions

| Signal | Meaning |
|--------|---------|
| `vs_production` with overlap | Same-calendar beats/loses for shadow candidates |
| Overlap none | Use since-go-live for **real** P&L; scenario rank is **OHLCV window only** |
| Brief `deployment_hint` | Never auto-live; shadow + gap gates |

## Next (R3)

- Auto-ingest winning scenarios to proposals when gates pass
- **Extend OHLCV** through live period so overlap comparisons become apples-to-apples