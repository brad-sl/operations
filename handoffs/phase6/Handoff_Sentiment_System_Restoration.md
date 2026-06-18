# Handoff Document: Sentiment System Restoration (Phase 6)

**Work Package**: 1  
**Priority**: Highest  
**Status**: Ready for Implementation

## Objective

Restore the full sentiment system from Phase 4/5 into Phase 6 with separate X and Reddit fetchers and proper time-based decay.

## Original Source Code (Phase 4/5)

- `fetch_x_sentiment.py` — X (Twitter) sentiment fetcher using X API v2 Bearer token
- `fetch_reddit_sentiment.py` — Reddit sentiment fetcher using Apify actor
- `sentiment_aggregator_v2.py` (if exists) — Combined scoring logic
- `run_sentiment_cron.sh` — Scheduling script
- Caches: `x_sentiment_cache.json`, `reddit_sentiment_cache.json`

## Scope & Boundaries

### Must Do
- Port X fetcher to `phase6/core/sentiment/fetch_x_sentiment.py`
- Port Reddit fetcher to `phase6/core/sentiment/fetch_reddit_sentiment.py`
- Implement time decay:
  - X posts: 15-minute half-life
  - Reddit posts: 60-minute half-life
- Keep X and Reddit as **separate modules**
- X fetcher should run no more frequently than every 30 minutes

### Must Not Do
- Combine X and Reddit into a single fetcher
- Run X sentiment more frequently than every 30 minutes without approval

## Expected Deliverables

1. `phase6/core/sentiment/fetch_x_sentiment.py`
2. `phase6/core/sentiment/fetch_reddit_sentiment.py`
3. `phase6/core/sentiment/sentiment_scorer.py` (with decay logic)
4. Updated `PHASE6_RESTORATION_CHECKLIST.md`

## Git Requirements

- Commit all changes to the `phase-6` branch
- Use clear commit messages referencing this Handoff Document

## Verification

- Both fetchers produce valid output independently
- Time decay is correctly applied in the scorer
- No data written to scratch directories