# Phase 4b — X-Sentiment Integration Specification

**Status:** 🟠 PLANNED (after Phase 4 completion on 2026-03-31)  
**Duration:** 48 hours (2026-04-02 ~ 2026-04-04)  
**Critical Rule:** X-Sentiment is **NOT optional**, **NOT synthesized**, and **NOT to be removed**.

---

## Why This Document Exists

**Problem:** X-Sentiment code has been lost/omitted from the codebase multiple times:
- Phase 3 design doc included it; phase3_v4.py lacked real X API integration
- Phase 4 v5 harness has NO sentiment at all (just mock P&L)
- Root cause: No explicit, locked specification tying code to requirements

**Solution:** This document is the **single source of truth** for X-Sentiment. It will be:
1. Referenced in every Phase 4b commit message
2. Linked in code comments (no developer can ignore it)
3. Backed by a separate code file (x_sentiment_fetcher.py) that is version-locked
4. Validated in Phase 4b acceptance criteria

---

## Phase 4b Objective

**Determine:** Does real X API sentiment improve win rate over pure threshold-based strategy?

**Hypothesis:** Adding X-Sentiment to the winning Phase 4 strategy will:
- Increase win rate by 5-15% (compared to Phase 4 baseline)
- Improve entry signal quality (sentiment confirms or refutes RSI signal)
- Reduce whipsaws (sentiment filter prevents false positives)

---

## X-Sentiment Data Source & Integration

### Real Data Only (MANDATORY)

**Data Source:** X API v2 (formerly Twitter API)  
**Authentication:** Bearer token (stored in .env, NOT hardcoded)  
**Endpoint:** Search tweets for BTC/XRP sentiment  
**Query Examples:**
```
BTC: "BTC" OR "bitcoin" -is:retweet lang:en
XRP: "XRP" OR "ripple" -is:retweet lang:en
```

**Cache Strategy:** 1-hour window (minimize API calls, maintain freshness) — NEW as of 2026-03-29
  - Updated from 6-hour to 1-hour cadence to capture sentiment dynamics
  - sentiment_scheduler.py runs hourly via cron: `0 * * * *`
  - Every Phase 4b cycle fetches the latest sentiment (within 1-hour freshness window)

### No Synthesized Data

❌ **NOT allowed:**
- Deterministic sentiment based on UTC hour (e.g., "US hours = bullish")
- Mock/random sentiment values
- Hardcoded sentiment per pair
- Sentiment that repeats every 24 hours

✅ **REQUIRED:**
- Real tweets fetched from X API v2
- Sentiment extracted via NLP (e.g., TextBlob, VADER, or SentimentTransformer)
- Timestamp-matched to trade cycle
- Logged with source tweet IDs for audit

---

## Implementation Requirements

### File Structure (LOCKED)

```
operations/crypto-bot/
├── x_sentiment_fetcher.py          (NEW) Standalone X API client + sentiment NLP
├── phase4b_v1.py                   (NEW) Orchestrator + integration
├── PHASE4B_X_SENTIMENT_SPECIFICATION.md  (THIS FILE)
├── X_SENTIMENT_INTEGRATION_CHECKLIST.md  (NEW)
└── X_SENTIMENT_AUDIT_LOG.md        (NEW) Real tweet IDs + timestamps
```

### x_sentiment_fetcher.py (Mandatory Requirements)

```python
class XSentimentFetcher:
    """
    MANDATORY: Fetch REAL sentiment from X API v2.
    NEVER synthesize, mock, or use hardcoded values.
    """
    
    def __init__(self, bearer_token: str):
        """Initialize with real X API bearer token."""
        self.bearer_token = bearer_token  # From .env
        self.cache = {}  # 6-hour cache per pair
        
    def fetch_sentiment(self, pair: str, max_results: int = 100) -> dict:
        """
        Fetch real tweets for pair (BTC or XRP).
        
        Returns:
        {
            'pair': 'BTC-USD',
            'sentiment_score': -0.15,  # -1.0 (bearish) to +1.0 (bullish)
            'tweet_count': 87,
            'cached': False,
            'timestamp': '2026-04-02T14:30:00Z',
            'source_tweet_ids': ['123456', '123457', ...]  # Audit trail
        }
        
        RULES:
        - Use real X API (not mock)
        - Return real sentiment from tweets (not random/hardcoded)
        - Cache 6 hours per pair
        - Log tweet IDs for reproducibility
        - Handle API errors gracefully (return None, do not crash)
        """
        
    def _extract_sentiment(self, tweets: List[str]) -> float:
        """
        Calculate sentiment from real tweets.
        
        Options (pick one):
        1. TextBlob (simple, lightweight): -1.0 to +1.0
        2. VADER (financial optimized): -1.0 to +1.0
        3. SentimentTransformer (accurate, slower): -1.0 to +1.0
        
        RULE: Must be deterministic per tweet set.
        If you fetch the same tweets tomorrow, you get the same sentiment.
        """
```

### phase4b_v1.py (Mandatory Integration)

```python
class Phase4bWithSentiment:
    """
    Phase 4b harness: Winner strategy + X-Sentiment integration.
    
    MANDATORY RULES:
    1. Use real X API sentiment (never synthesized)
    2. Sentiment influences entry signal confidence (not exit threshold)
    3. Exit still uses Phase 4 winner threshold, but gated by sentiment
    4. All trades logged with sentiment_score, tweet_count, source_ids
    """
    
    def __init__(self, winning_strategy: str, bearer_token: str):
        """
        winning_strategy: 'fixed', 'fee_aware', or 'pair_specific' (from Phase 4)
        bearer_token: Real X API bearer token (from .env)
        """
        self.sentiment_fetcher = XSentimentFetcher(bearer_token)
        self.winning_strategy = winning_strategy
        
    def run_cycle(self):
        """
        For each pair:
        1. Fetch real X sentiment (real API, not mock)
        2. Generate entry signal (RSI + sentiment confirmation)
        3. If entry triggered, use Phase 4 winner threshold to exit
        4. Log sentiment_score, tweet_count, source_ids in trades table
        """
        
    def _generate_entry_signal(self, pair: str, sentiment: dict) -> bool:
        """
        Entry logic: RSI threshold ONLY triggers if sentiment confirms.
        
        Example:
        - RSI crosses BUY threshold AND sentiment_score > -0.2 → ENTRY
        - RSI crosses BUY threshold BUT sentiment_score < -0.3 → HOLD (wait for confirmation)
        
        This filters false positives using real sentiment.
        """
```

### Database Schema Update (LOCKED)

Add to `trades` table:

```sql
ALTER TABLE trades ADD COLUMN sentiment_score REAL;
ALTER TABLE trades ADD COLUMN sentiment_tweet_count INTEGER;
ALTER TABLE trades ADD COLUMN sentiment_source_ids TEXT;  -- JSON array of tweet IDs
ALTER TABLE trades ADD COLUMN sentiment_cached BOOLEAN DEFAULT 0;
```

Every trade must have these fields populated (or NULL if sentiment API fails).

---

## Validation Checklist (X-Sentiment Integrity)

### Before Phase 4b Starts

- [ ] X API bearer token loaded from .env (not hardcoded in code)
- [ ] x_sentiment_fetcher.py implemented with real X API calls
- [ ] Sentiment extraction method chosen (TextBlob/VADER/Transformer) and documented
- [ ] Cache logic: 6-hour window, expires cleanly
- [ ] Error handling: API failures do NOT crash the test (graceful fallback)
- [ ] Audit trail: Every sentiment fetch logs source tweet IDs to file

### During Phase 4b Run

- [ ] Every cycle: X sentiment actually fetched from X API (check logs for API calls)
- [ ] Sentiment scores vary realistically: NOT repeating, NOT constant per pair
- [ ] Cache hits logged separately from fresh fetches
- [ ] Tweet counts reasonable (10-200 tweets per cycle for each pair)
- [ ] Timestamp matches entry signal timestamp (reproducibility)

### After Phase 4b Completion

- [ ] X_SENTIMENT_AUDIT_LOG.md contains all sentiment fetches with:
  - Timestamp, pair, sentiment_score, tweet_count, source_ids
  - Cache hit/miss indicator
  - Any API errors (gracefully handled)
- [ ] Trades table populated with sentiment_score, sentiment_tweet_count, sentiment_source_ids
- [ ] Can reproduce sentiment for any trade by looking up source_ids
- [ ] No synthetic/hardcoded/mock sentiment anywhere in data

---

## Code Review Checklist (Anti-Loss Measures)

**Before committing phase4b_v1.py, verify:**

```
[ ] import XSentimentFetcher from x_sentiment_fetcher.py (not inline)
[ ] XSentimentFetcher initialized with .env bearer token
[ ] bearer_token NEVER hardcoded, NEVER defaults to mock
[ ] fetch_sentiment() called every cycle (check logging)
[ ] Sentiment score used in _generate_entry_signal() logic
[ ] Trades table populated with sentiment_* columns
[ ] Docstring on every function references this spec (PHASE4B_X_SENTIMENT_SPECIFICATION.md)
[ ] Comment at top of file: "X-Sentiment is REAL (X API), NOT synthesized"
[ ] Commit message includes: "X-Sentiment integration per PHASE4B_X_SENTIMENT_SPECIFICATION.md"
```

---

## Timeline (Phase 4b)

| Date | Milestone | Owner |
|------|-----------|-------|
| 2026-03-31 14:15 PT | Phase 4 completes, winner identified | Auto |
| 2026-03-31 15:30 PT | Write phase4b_v1.py + x_sentiment_fetcher.py | Brad/AI |
| 2026-04-01 | Code review + validation checklist | Brad |
| 2026-04-02 14:00 PT | Phase 4b starts (48-hour run) | Auto |
| 2026-04-04 14:00 PT | Phase 4b completes | Auto |
| 2026-04-04 15:00 PT | Final report: sentiment impact vs Phase 4 | Brad/AI |

---

## Success Criteria (Phase 4b)

✅ **Test passes if:**
1. At least 100+ real X sentiment fetches (one per cycle, real API)
2. Sentiment scores vary (not constant, not repeating hourly pattern)
3. Tweet counts vary by pair/cycle (10-200 range, realistic)
4. Win rate improves 5-15% over Phase 4 winner (statistically significant)
5. X_SENTIMENT_AUDIT_LOG.md fully populated with source tweet IDs
6. Zero synthetic/mock/hardcoded sentiment in any data

⚠️ **Test fails if:**
- Sentiment is constant/repeating (indicates synthesis/mock)
- Tweet counts always same for a pair (mock data)
- API error rate >5% (indicates unstable integration)
- No source tweet IDs logged (can't audit)
- Code uses hardcoded sentiment values anywhere

---

## Anti-Loss Strategy (PERMANENT)

### 1. Specification Lock
This document (PHASE4B_X_SENTIMENT_SPECIFICATION.md) is the **immutable source of truth**.
- Linked in every commit message
- Referenced in code comments
- Required reading before touching X-sentiment code

### 2. Code Lock
x_sentiment_fetcher.py is a **standalone, importable module**.
- Cannot be inlined into phase4b_v1.py (prevents accidental loss)
- Documented independently (separate code review checklist)
- Tested in isolation before integration

### 3. Audit Lock
X_SENTIMENT_AUDIT_LOG.md logs every sentiment fetch.
- Timestamp, pair, sentiment_score, tweet_count, source_ids
- Proves real API integration (not mock)
- Reviewable proof of X-Sentiment integrity

### 4. Data Lock
Trades table schema includes sentiment_* columns.
- Every trade has sentiment metadata (cannot be dropped)
- Source tweet IDs stored (reproducibility)
- Phase 4b final report validates sentiment was real

### 5. Commit Lock
Every Phase 4b commit must reference this spec.
```
Example: "phase4b: X-Sentiment integration (PHASE4B_X_SENTIMENT_SPECIFICATION.md, real X API, bearer token from .env)"
```

---

## References & Related Files

**Phase 4 (Threshold Test):**
- PHASE4_TEST_EXECUTION_PLAN.md
- PHASE4_VALIDATION_CHECKLIST.md
- GITHUB_PHASE4_TASKS.md
- COINBASE_FEE_RESEARCH.md

**Phase 3 (Design History):**
- PHASE_3_DECISIONS_2026_03_26.md
- PHASE_3_TEST_QUESTIONS.md
- x_sentiment_fetcher.py (referenced design, needs implementation)

**Phase 4b (X-Sentiment):**
- PHASE4B_X_SENTIMENT_SPECIFICATION.md (THIS FILE)
- x_sentiment_fetcher.py (NEW, standalone module)
- phase4b_v1.py (NEW, orchestrator + integration)
- X_SENTIMENT_INTEGRATION_CHECKLIST.md (NEW, code review)
- X_SENTIMENT_AUDIT_LOG.md (NEW, real sentiment audit trail)

---

## Final Note

**This specification is non-negotiable.** X-Sentiment is real, sourced from X API v2, and locked into the test design. Any deviation (synthesis, hardcoding, omission) will be caught at code review, commit message validation, and final audit.

**If X-Sentiment is missing or fake in Phase 4b, the entire test is invalid and must be rerun.**

Version: 1.0  
Date: 2026-03-29  
Author: Brad + AI  
Status: LOCKED
