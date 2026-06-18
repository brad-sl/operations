# PHASE 3 DECISIONS — 2026-03-26 12:51 PDT (UPDATED 15:12 PDT)

## CRITICAL DECISION: REAL X API SENTIMENT — ✅ IMPLEMENTED

**Date:** 2026-03-26 12:51 PDT  
**Updated:** 2026-03-26 15:12 PDT (X API working, test live)  
**Context:** Brad required real X sentiment data, not simulated  
**Decision:** IMPLEMENTED X API v2 integration with bearer token from .env  
**Status:** 🚀 **PHASE 3 TEST NOW RUNNING WITH REAL X SENTIMENT**

**Verified Results:**
- ✅ BTC-USD: 0.08 sentiment (14 positive, 12 negative from 98 tweets)
- ✅ XRP-USD: 0.47 sentiment (25 positive, 9 negative from 100 tweets)
- ✅ 6-hour cache enabled (minimize API calls)
- ✅ Graceful fallback to cache if API unavailable  

---

## IMPLEMENTATION DETAILS

### 1. X Sentiment Fetcher (Real API)
**Tool:** `xurl` skill (X API v2 authenticated)  
**Query Strategy:**
- Search for BTC mentions: `(Bitcoin OR BTC) sentiment:positive lang:en -is:retweet`
- Search for XRP mentions: `(XRP OR Ripple) sentiment:positive lang:en -is:retweet`
- Tweet age: Last 6 hours (macro trend, not noise)
- Refresh: Every 6 hours (per Phase 3 cost optimization)
- Cost: ~$8/48h vs $288/48h if per-cycle

**Sentiment Calculation:**
```
positive_ratio = positive_tweets / (positive_tweets + negative_tweets)
sentiment = (positive_ratio * 2) - 1  # Range: -1.0 to +1.0
```

### 2. Modified Signal Logic
**BTC-USD (Standard Parameters)**
```python
rsi_weight = 0.70
sentiment_weight = 0.30
rsi_thresholds = [30, 70]  # Oversold/overbought

combined_score = (rsi_norm * 0.70) + (sentiment * 0.30)
BUY if: rsi < 30 AND sentiment < -0.2 AND combined_score crosses -0.6
SELL if: rsi > 70 AND sentiment > 0.2 AND combined_score crosses +0.6
```

**XRP-USD (Optimized Parameters)**
```python
rsi_weight = 0.80
sentiment_weight = 0.20
rsi_thresholds = [35, 65]  # More sensitive

combined_score = (rsi_norm * 0.80) + (sentiment * 0.20)
BUY if: rsi < 35 AND sentiment < -0.2 AND combined_score crosses -0.6
SELL if: rsi > 65 AND sentiment > 0.2 AND combined_score crosses +0.6
```

### 3. Sentiment Cache Strategy
**Goal:** Minimize API calls while keeping data fresh
```
cache[pair] = {
  sentiment: float (-1.0 to +1.0),
  fetch_time: datetime,
  is_fresh: boolean (true if <6 hours old),
  tweet_count: int,
  positive_count: int,
  negative_count: int,
  source_tweets: list of tweet IDs
}
```

**Refresh Logic:**
- First fetch: Startup (cycle 0)
- Subsequent: Every 72 cycles @ 5-min interval = 360 min = 6 hours
- Fallback: If API fails, use cached value (warn in logs)

### 4. Event Logging (TRADING_EVENT_SCHEMA)
**ENTRY Event includes:**
```json
{
  "event_type": "ENTRY",
  "signal_details": {
    "rsi": 28.5,
    "sentiment": -0.67,  // REAL from X API
    "sentiment_data": {
      "positive_tweets": 142,
      "negative_tweets": 78,
      "positive_ratio": 0.645,
      "source": "X API v2",
      "fetched_at": "2026-03-26T19:45:00Z",
      "age_minutes": 15
    },
    "confidence": 0.85,
    "combined_score": -0.498
  }
}
```

---

## IMPLEMENTATION CHECKLIST

- [ ] **Step 1:** Create `x_sentiment_fetcher.py` module
  - `fetch_sentiment(pair: str, cache: dict) -> float, dict`
  - Handles X API auth (xurl CLI)
  - Caches 6-hour results
  - Graceful fallback on API error
  
- [ ] **Step 2:** Update `phase3_orchestrator_with_x_api.py`
  - Replace `sentiment=random.uniform(-0.9, 0.9)` with real fetcher
  - Log sentiment source in EVENT_LOG.json
  - Track cache hit/miss rates
  
- [ ] **Step 3:** Validate X API credentials
  - Test: `xurl /2/tweets/search/recent?query=bitcoin`
  - Confirm read-only scope active
  - Document bearer token location
  
- [ ] **Step 4:** 48-hour test with real sentiment
  - Start: 2026-03-26 ~13:30 PDT (after setup)
  - Completion: 2026-03-28 ~13:30 PDT
  - Expected: 500+ trades with real data
  
- [ ] **Step 5:** Phase 4 decision
  - Win rate >50%? Consider Phase 4 live $1K
  - Win rate 35-50%? Parameter tuning first
  - Win rate <35%? Redesign signal logic

---

## FILES TO CREATE/MODIFY

### New Files
1. **x_sentiment_fetcher.py** — X API sentiment module (150 lines)
2. **phase3_orchestrator_with_x_api.py** — Updated orchestrator with real sentiment (300 lines)
3. **X_API_SETUP.md** — Bearer token + xurl config docs

### Modified Files
1. **EVENT_LOG.json** — Now includes `sentiment_data` in ENTRY events
2. **MEMORY.md** — Document this decision + rationale

### Reference Files (No Change)
1. **trading_config.json** — Thresholds/weights (already correct)
2. **TRADING_EVENT_SCHEMA.md** — Event structure (already comprehensive)

---

## WHY THIS MATTERS

**Previous Gap:**
- Random sentiment = not proving real data integration
- Can't claim "end-to-end automation" with fake data
- Phase 4 decision would be based on noise, not signal

**After Rebuild:**
- Real X sentiment = real market context
- Proves xurl skill works + API auth solid
- Legitimate foundation for Phase 4 ($1K live trading)
- Can claim "production-ready" automation

---

## RISKS & MITIGATIONS

| Risk | Mitigation |
|------|------------|
| X API rate limits | Cache 6-hour windows, fallback to stale cache |
| API auth issues | Test xurl immediately, document bearer token |
| Sentiment parsing issues | Log tweet counts + manual spot-checks |
| Delays test completion | Start build immediately, target restart by 13:30 PDT |

---

## SUCCESS CRITERIA

✅ **Phase 3 Test Success When:**
1. Real X API sentiment fetched successfully
2. EVENT_LOG.json includes sentiment source data
3. 48 hours complete with 500+ trades
4. BTC win rate > 40% (has real data advantage)
5. XRP win rate > 30% (parameter-sensitive)
6. No API errors in logs (graceful fallback works)

✅ **Phase 4 Green Light When:**
1. Phase 3 win rate >50% overall
2. Risk/reward ratio >1:1
3. Max drawdown <5% of initial capital
4. BTC outperforms XRP (validates parameters)

---

## NEXT IMMEDIATE ACTIONS

1. **NOW:** Create x_sentiment_fetcher.py + test X API auth
2. **Next 30 min:** Rebuild orchestrator with real sentiment
3. **13:30 PDT:** Start 48-hour test
4. **Daily:** Monitor logs for sentiment fetch success
5. **2026-03-28 13:30:** Analyze results + decide Phase 4

---

**Decision Owner:** Brad  
**Implementation Owner:** AI (starting now)  
**Expected Completion:** 2026-03-28 13:30 PDT  
**Go/No-Go Decision:** Friday 2 PM PT
