# Sentiment System Specification

**Version:** 1.0  
**Status:** Draft  
**Date:** 2026-05-29  
**Owner:** Crypto Trading Bot Team

## 1. Purpose

This document defines the **Sentiment System** as a standalone, reusable feature. It provides normalized sentiment scores for multiple cryptocurrency pairs by combining signals from X (Twitter) and Reddit.

The system is designed to be called by multiple downstream consumers (backtesting, paper trading, live trading, monitoring, and dashboards) without duplication of logic.

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Sentiment System                          │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐     ┌──────────────────────────────┐  │
│  │ X Sentiment      │     │ Reddit Sentiment             │  │
│  │ fetch_x_         │     │ fetch_reddit_                │  │
│  │ sentiment.py     │     │ sentiment.py                 │  │
│  └────────┬─────────┘     └──────────────┬───────────────┘  │
│           │                              │                   │
│           └──────────────┬───────────────┘                   │
│                          ▼                                   │
│                 ┌──────────────────────┐                     │
│                 │   Sentiment Scorer   │                     │
│                 │ sentiment_scorer.py  │                     │
│                 └──────────┬───────────┘                     │
│                            │                                 │
│                 ┌──────────▼──────────┐                      │
│                 │   Sentiment Cache   │                      │
│                 │  + Decay / Staleness│                      │
│                 └─────────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

## 3. Core Components

| Component                    | File                                      | Responsibility |
|-----------------------------|-------------------------------------------|----------------|
| X Sentiment Fetcher         | `phase6/core/sentiment/fetch_x_sentiment.py` | Fetch and score X/Twitter signals |
| Reddit Sentiment Fetcher    | `phase6/core/sentiment/fetch_reddit_sentiment.py` | Apify + Direct JSON fallback |
| Direct Reddit Fetcher       | `phase6/core/sentiment/direct_reddit_fetcher.py` | Clean fallback implementation |
| Sentiment Scorer            | `phase6/core/sentiment/sentiment_scorer.py` | Combine, normalize, apply decay |
| Cache / Aggregator          | `phase6/core/sentiment/sentiment_cache.py` (future) | Unified storage & staleness |
| Entry Point / CLI           | `phase6/scripts/fetch_sentiment.py` (future) | Unified CLI for all consumers |

## 4. Public Interface

All downstream systems should interact with the sentiment system through a single, stable interface.

### Recommended Calling Pattern (Future)

```python
from phase6.core.sentiment import get_sentiment_scores

scores = get_sentiment_scores(
    pairs=["BTC-USD", "ETH-USD", "SOL-USD"],
    max_age_minutes=60
)
```

### Current Interim Interface

Until the unified entry point is built, consumers may import directly from:

- `sentiment_scorer.load_sentiment_scores()`
- `RedditSentimentFetcher().fetch_pair_sentiment()`
- `XSentimentFetcher().fetch_pair_sentiment()`

## 5. Data Model

### Sentiment Score Output

```json
{
  "BTC-USD": {
    "score": 0.42,
    "confidence": 0.75,
    "source_breakdown": {
      "x": 0.55,
      "reddit": 0.28
    },
    "timestamp": "2026-05-29T18:00:00Z",
    "age_minutes": 12
  }
}
```

### Rules
- `score`: Normalized value between `-1.0` and `1.0`
- `confidence`: 0.0 – 1.0 (based on volume + signal strength)
- All timestamps must be in UTC (ISO 8601)

## 6. Naming & Consistency Rules

- All files related to sentiment live under `phase6/core/sentiment/`
- Fetchers are named `fetch_<platform>_sentiment.py`
- Public functions use `get_` or `load_` prefixes
- Cache files use the pattern `<platform>_sentiment_cache.json`
- Never duplicate sentiment logic across files

## 7. Multi-Pair Efficiency Requirements

- The system must support fetching sentiment for 5–20 pairs in a single call efficiently.
- Rate limiting and request batching must be respected (especially for Reddit).
- Parallel fetching is allowed but must include proper backoff.

## 8. Fallback & Error Handling

1. **Reddit**:
   - Primary: Apify actor
   - Fallback: Direct Reddit JSON API (`DirectRedditFetcher`)
   - Final fallback: Return `0.0` with low confidence

2. **X/Twitter**:
   - Primary path only (no fallback defined yet)

3. **General**:
   - Never raise unhandled exceptions to callers
   - Always return a valid score object (even if neutral)

## 9. Caching & Staleness

- Default maximum age: **60 minutes**
- Scores older than the threshold should trigger a refresh
- Cache must support per-pair staleness

## 10. Logging & Observability

- All fetchers must log at minimum:
  - Start of fetch
  - Number of posts/signals retrieved
  - Final score per pair
  - Which source was used (Apify vs Direct)
- Use structured logging where possible

## 11. Integration Points

This system is intended to be consumed by:

- Phase 6 Backtester (`phase6_backtest.py`)
- Phase 6 Runner (`phase6_runner.py`)
- Capital allocation engine
- Monitoring / alerting systems
- Future dashboard

---

**Next Steps After Spec Approval**
1. Clean up `fetch_reddit_sentiment.py` to match this spec
2. Improve `DirectRedditFetcher` reliability
3. Build unified entry point (`get_sentiment_scores`)