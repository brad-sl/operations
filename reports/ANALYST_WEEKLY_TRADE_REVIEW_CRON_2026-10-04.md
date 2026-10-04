# Analyst weekly 7d trade review — ship receipt

**Date:** 2026-10-04  
**Brad GO:** Sunday analyst review of prior 7d trades + Membership Sizing Matrix rulebook + return-improvement suggestions  
**Job:** `phase6-analyst-weekly-trade-review` (`6752ed0b0dec`)  
**Memory:** continuity ON + durable notepad (`last_scorecard`, `open_suggestions`, `matrix_notes`, `go_queue`)  
**Matrix scope:** rulebook not stone — weekly must review role_law / add-risk / block_max / inconsistencies · id `6752ed0b0dec` · `0 17 * * 0` PT  

## Why

Dashboard path is mending (green 1D/7D/14D/30D, Exit WR ~38% on longer book) but still **treading water** vs ~5%/mo deposit-adj growth. Need a standing analyst loop that:

1. Reviews **actual 7d fills** (not vibes)
2. May **quest outside** trade history (matrix, funnel, OPT, tax)
3. Delivers **ranked suggestions** every Sunday without Brad in the research path

## What shipped

| Layer | Path |
|-------|------|
| Fact pack core | `phase6/core/analyst_weekly_trade_review.py` |
| CLI | `scripts/phase6/run_analyst_weekly_trade_review.py` |
| Isolation tests | `scripts/phase6/test_isolation_analyst_weekly_trade_review.py` (5/5) |
| Cron wrapper | `phase6/scripts/run_analyst_weekly_trade_review_cron.sh` |
| Hermes thin | `~/.hermes/scripts/run_analyst_weekly_trade_review.sh` |
| Facts state | `data/state/analyst_weekly_trade_review_latest.json` |
| Facts report | `reports/ANALYST_WEEKLY_TRADE_REVIEW_LATEST.md` |
| Agent report (on fire) | `reports/ANALYST_WEEKLY_TRADE_REVIEW_AGENT_LATEST.md` |

## Cron shape

- **no bare no_agent card** as primary — agent composes suggestions (skills attached)
- Script runs first → rebuilds grounded fact pack
- Continuity on → week-over-week dedupe
- Deliver **telegram**; failures also TG
- Workdir = crypto-trading-bot

## Live fact pack snapshot (ship time)

- Primary B/S **14/13** · realized ~**$4.79** · WR **60%** (window primary exits w/ pnl)
- Process tax stamped **$0** on this pack pass (taxonomy; dig further in agent pass)
- Same-day buy+sell pair-days: **4**
- Seed themes: tryout funnel ejects (~8), tryout churn
- Path **sideways** · goal **STABILIZE** · regime **flat**

## Guardrails

- Measure / suggest only  
- No config writes, no orders, no `live_apply` flips  
- Thin N → no edge claims  
- Process tax vs alpha miss separated in brief  

## Improvements (optional next)

1. Wire util% more robustly from NAV snapshot keys (card showed util None once)  
2. Auto-append novel P0s to `analyst_proposed_backlog.json` with dedupe (off by default in prompt)  
3. Mid-week **no_agent** fact-only refresh if Sunday agent ever fails  
4. Tie suggestions → membership sizing matrix `inconsistent` / `block_max` filters  

## Manual run

```bash
cd /home/brad/projects/crypto-trading-bot
python scripts/phase6/run_analyst_weekly_trade_review.py --days 7
python scripts/phase6/run_analyst_weekly_trade_review.py --tg-card --load-latest
# Force agent fire:
hermes cron run 6752ed0b0dec
```
