# Handoff — FEAT-DAILY-DOSE-NEWS-2026-08 (Phase A)

**Status:** IN_PROGRESS → RUNNABLE  
**MASTER:** `FEAT-DAILY-DOSE-NEWS-2026-08`  
**Spec:** `docs/features/DAILY_DOSE_NEWS_FEED_PHASE_A_SPEC.md`  
**Date:** 2026-08-03  
**Owner:** platform  

## Goal
Phase A viability probe: rank public RSS into a short daily “dose” of significant headlines for humans (dashboard/Telegram later). **Not a trading signal.**

## What shipped (Phase A code)

| Piece | Path |
|-------|------|
| Shared RSS helper | `phase6/core/rss_feeds.py` |
| Runner | `phase6/scripts/run_daily_dose.py` |
| Paths | `DAILY_DOSE_*` in `phase6/core/paths.py` |
| Isolation test | `phase6/tests/test_isolation_daily_dose_rank.py` |
| Latest artifact | `data/state/daily_dose_latest.json` |
| History | `data/state/daily_dose_history.jsonl` |
| Telegram preview | `data/state/daily_dose_telegram_preview.txt` |

## How to run

```bash
cd /home/brad/projects/crypto-trading-bot
export OPENBLAS_CORETYPE=GENERIC   # if env requires
.venv/bin/python3 phase6/tests/test_isolation_daily_dose_rank.py
.venv/bin/python3 phase6/scripts/run_daily_dose.py --print-preview
# optional:
.venv/bin/python3 phase6/scripts/run_daily_dose.py --top 8 --window-hours 36 --positions-boost
```

## Publication process (Phase A vs later)

### Phase A (now) — **disk only**
1. **Fetch** ~9 public RSS feeds (same basket as free sentiment).  
2. **Rank** titles/summaries (relevance, source tier, event keywords, recency, novelty/dedupe).  
3. **Publish to disk:**
   - `daily_dose_latest.json` — full top-N cards (overwrite each run)  
   - `daily_dose_history.jsonl` — one summary line appended per run (probe trail)  
   - `daily_dose_telegram_preview.txt` — exact text that *would* go to Telegram  
4. **Does not:**
   - Send Telegram  
   - Hit dashboard API  
   - Write `sentiment_cache.json`  
   - Affect rebalance / allocator  

**How you “read the publication” today:** open the preview file or JSON, or run with `--print-preview`.

### Phase B (after viability OK + Brad OK)
| Step | Action |
|------|--------|
| 1 | Add `GET /api/daily_dose` on `serve_dashboard.py` reading `daily_dose_latest.json` |
| 2 | Small dashboard panel (title, source, link; hover = why) |
| 3 | Cron **1×/day** morning PT (e.g. 07:15) → `run_daily_dose.py` |
| 4 | Telegram: send preview text to Brad DM or Home **only after explicit OK** |
| 5 | Still not a trading input |

### Phase C
Filter same JSON by trader symbols on status pages.

### Recommended probe ops (this week)
| Day | Action |
|-----|--------|
| D0 | Isolation test PASS + first live run (done at handoff) |
| D1–D5 | Run once/day morning; skim preview ≤2 min |
| D5+ | Fill scorecard in spec §6.2 → viable / iterate / reject |

Optional cron later (not installed by default):
```cron
15 7 * * * cd /home/brad/projects/crypto-trading-bot && .venv/bin/python3 phase6/scripts/run_daily_dose.py >> logs/daily_dose.log 2>&1
```

## Viability scorecard (fill after ≥5 days)

See spec §6.2. Exit: Phase B / iterate weights / reject.

## Non-negotiables
- Banner on every artifact: **not a trade signal**  
- No full article body archive  
- No auto Telegram in A  
- No analyst `Type:test` auto_pickup lane  

## Next
- Brad skims live preview  
- Optional: schedule morning cron (disk only)  
- After 5 days: viability note under `reports/DAILY_DOSE_PHASE_A_VIABILITY_*.md`


## Pub cycle scripts (follow-on)
See Handoff_FEAT-DAILY-DOSE-PUB-CYCLE — edit/publish CLIs live.
