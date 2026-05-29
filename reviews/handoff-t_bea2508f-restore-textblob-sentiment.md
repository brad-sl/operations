# Handoff Document: Restore TextBlob Sentiment Analysis (t_bea2508f)

**Task:** t_bea2508f — Restore proper TextBlob sentiment analysis in Phase 6 X/Reddit fetchers  
**Assignee:** crypto-analyst  
**Priority:** 10 (High)  
**Created:** 2026-05-28

## Objective
Replace the current crude engagement-weighted + keyword-list sentiment scoring in Phase 6 with the original TextBlob polarity analysis that existed in the Phase 4 implementation. The goal is to produce meaningful positive/neutral/negative signals instead of pure engagement proxies.

## Background
- Original implementation (Phase 4) used `TextBlob(text).sentiment.polarity` to generate real sentiment scores.
- During the Phase 6 port, this was replaced with:
  - `calculate_sentiment()` → engagement-weighted average only
  - Apify fallback → hardcoded positive/negative word lists
- `sentiment_scorer.py` correctly applies time decay, but the raw scores it receives are low-quality.

## Reference Implementation
- `archived/apify_reddit_scraper.py`
- `archived/apify_reddit_cli_scraper.py`
- Look for the `calculate_sentiment` function that calls `TextBlob(text).sentiment.polarity`

## Scope
1. Update `phase6/core/sentiment/fetch_x_sentiment.py`
   - Modify `calculate_sentiment()` (or add a new function) to use TextBlob polarity on post text.
   - Keep engagement as a secondary signal or remove it.
2. Update `phase6/core/sentiment/fetch_reddit_sentiment.py` (if it exists and uses similar logic).
3. Ensure the cache format remains compatible (`sentiment` float in [-1.0, 1.0]).
4. Add basic error handling for TextBlob failures.
5. Update any related tests.

## Success Criteria
- `load_sentiment_scores()` returns scores derived from actual text polarity (not just engagement).
- Positive posts increase score, negative posts decrease score in a meaningful way.
- No regression in time-decay behavior.
- Cache continues to work with existing `sentiment_scorer.py`.
- At least one test case validates polarity-based scoring.

## Constraints & Preferences
- Use TextBlob as the primary analysis component (matches original design).
- Keep the solution lightweight — no heavy LLM calls unless explicitly justified.
- Prefer clean, maintainable code over micro-optimizations.
- Document any trade-offs (e.g. TextBlob accuracy vs speed).

## Files to Modify
- `phase6/core/sentiment/fetch_x_sentiment.py` (primary)
- `phase6/core/sentiment/fetch_reddit_sentiment.py` (if applicable)
- `phase6/core/sentiment/sentiment_scorer.py` (review only — should not need changes)
- Add/update tests in `tests/` or `phase6/tests/`

## Out of Scope
- Changing the decay formula or weighting in `sentiment_scorer.py`
- Rebuilding the entire data pipeline
- Adding new data sources

## Verification Steps
1. Run the fetcher manually and inspect cache values.
2. Compare scores before/after on the same posts.
3. Run `load_sentiment_scores()` and verify combined scores behave as expected.
4. Execute any existing sentiment-related tests.

## Notes
- TextBlob must be installed (`pip install textblob`).
- The polarity output is already in the correct range [-1.0, 1.0].

---
**Owner:** crypto-analyst  
**Review Status:** Ready for implementation