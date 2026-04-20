# PHASE 3 TEST — Critical Questions to Answer

**Test Duration:** 48 hours (2026-03-26 13:00 PDT → 2026-03-28 13:00 PDT)  
**Pairs:** BTC-USD + XRP-USD  
**Config:** Real Stochastic RSI (Coinbase) + X Sentiment (6h cache) + TRADING_EVENT_SCHEMA logging

---

## QUESTION 1: Are the RSI Trading Signals Set Correctly?

### What We're Testing
- **BTC thresholds:** 30/70 (standard)
- **XRP thresholds:** 35/65 (optimized for volatility)
- **RSI calculation:** Real Stochastic RSI from 14-candle history (5-min candles)

### Success Metrics
| Metric | Target | Why It Matters |
|--------|--------|----------------|
| **BTC signal frequency** | 1-2 trades per 6 hours | Threshold not too tight or loose |
| **XRP signal frequency** | 0.5-1 trades per 6 hours | Wider thresholds = fewer but higher-conviction trades |
| **False signal rate** | <20% (enters then immediately reverses) | Thresholds need refinement if >20% |
| **RSI crossing patterns** | Visible clusters when oversold/overbought | Confirms RSI is oscillating realistically |

### Data to Collect
```json
{
  "rsi_analysis": {
    "btc_usd": {
      "total_cycles": 576,
      "oversold_crossings": 0,
      "overbought_crossings": 0,
      "rsi_min": 0.0,
      "rsi_max": 100.0,
      "rsi_avg": 50.0,
      "rsi_std_dev": 15.5,
      "signal_count": 0,
      "signal_frequency_per_6h": 0.0,
      "false_signal_pct": 0.0
    },
    "xrp_usd": { /* same */ }
  }
}
```

### Evaluation Criteria
- ✅ **PASS:** Both pairs generate 0.5-2 signals/6h with <20% false signals
- ⚠️ **MARGINAL:** One pair good, one bad (needs parameter tuning)
- ❌ **FAIL:** No signals or >30% false signals (thresholds broken)

---

## QUESTION 2: Is the Polling Frequency Optimal?

### What We're Testing
- **Current:** 5-minute cycle interval (per spec)
- **Execution:** 576 cycles over 48 hours
- **Stochastic RSI:** Calculated every cycle from 14-candle window

### Success Metrics
| Metric | Target | Why It Matters |
|--------|--------|----------------|
| **CPU usage** | <5% average | System sustainable for long-term |
| **Memory growth** | <100MB over 48h | No memory leaks |
| **Event log size** | <50MB (1000+ events) | Storage overhead acceptable |
| **API call overhead** | <10s/cycle | Non-blocking, doesn't delay execution |

### Data to Collect
```json
{
  "performance_metrics": {
    "total_cycles": 576,
    "total_runtime_hours": 48.0,
    "avg_cycle_duration_ms": 0.0,
    "max_cycle_duration_ms": 0.0,
    "cycles_under_1s": 0,
    "cycles_over_5s": 0,
    "memory_start_mb": 0.0,
    "memory_end_mb": 0.0,
    "memory_growth_mb": 0.0,
    "cpu_avg_pct": 0.0,
    "api_calls_total": 0,
    "api_call_errors": 0,
    "event_log_size_mb": 0.0,
    "uptime_pct": 100.0
  }
}
```

### Evaluation Criteria
- ✅ **PASS:** All cycles complete <5s, memory stable, no API errors
- ⚠️ **MARGINAL:** Some cycles slow or minor memory drift (optimize later)
- ❌ **FAIL:** Timeouts, crashes, or memory explosion (reduce frequency to 10m)

### Post-Test Decision
- If **PASS:** Keep 5-minute interval for Phase 4
- If **MARGINAL:** Increase to 10-minute interval, re-test
- If **FAIL:** Switch to 15-minute interval minimum

---

## QUESTION 3: Does X Sentiment Improve Win Rate, and by How Much?

### What We're Testing
- **Baseline:** RSI-only signals (30/70 thresholds)
- **Improvement:** RSI + X sentiment (BTC: 70/30 weights, XRP: 80/20 weights)
- **Hypothesis:** Real X sentiment reduces false signals, improves win rate by 5-15%

### Success Metrics
| Metric | Target | Why It Matters |
|--------|--------|----------------|
| **Win rate with sentiment** | >45% for BTC, >40% for XRP | Proves sentiment helps |
| **Win rate improvement** | +5% to +15% vs RSI-only | Quantifies sentiment value |
| **Average trade duration** | 20-60 min | Not too quick (noise) or too slow (holding losers) |
| **Profit factor** | >1.2 (wins > losses) | Sustainable edge |

### Data to Collect
```json
{
  "sentiment_impact": {
    "btc_usd": {
      "trades_total": 0,
      "trades_with_sentiment": 0,
      "trades_with_positive_sentiment": 0,
      "trades_with_negative_sentiment": 0,
      "trades_neutral_sentiment": 0,
      "win_rate_pct": 0.0,
      "win_rate_with_positive_sentiment_pct": 0.0,
      "win_rate_with_negative_sentiment_pct": 0.0,
      "avg_win_usd": 0.0,
      "avg_loss_usd": 0.0,
      "profit_factor": 0.0,
      "sentiment_accuracy": 0.0
    },
    "xrp_usd": { /* same */ }
  }
}
```

**Sentiment Accuracy Calculation:**
```
success_with_positive_sentiment = wins when sentiment > +0.5
success_with_negative_sentiment = wins when sentiment < -0.5
sentiment_accuracy = (success_with_positive_sentiment + success_with_negative_sentiment) / total_trades
```

### Evaluation Criteria
- ✅ **PASS:** BTC >45% WR, XRP >40% WR, profit_factor >1.2
- ⚠️ **MARGINAL:** One pair good, sentiment helps but modest gain (<5%)
- ❌ **FAIL:** Win rate <35% or sentiment uncorrelated with wins

### Post-Test Decision
- If **PASS:** Use sentiment in Phase 4 (add X API creds immediately)
- If **MARGINAL:** Keep sentiment, but explore alternative sources (CryptoPanic, etc.)
- If **FAIL:** Disable sentiment, focus on RSI tuning

---

## QUESTION 4: Does the Sentiment Polling Frequency Need Adjustment?

### What We're Testing
- **Current:** 6-hour refresh per pair (cache strategy)
- **Reasoning:** Crypto sentiment is macro trend, not minute-by-minute noise
- **Alternative:** 2h, 4h, 12h, 24h refresh cycles

### Success Metrics
| Metric | Target | Why It Matters |
|--------|--------|----------------|
| **Sentiment staleness impact** | <2% accuracy loss per hour | Data freshness acceptable |
| **API call cost** | <$8 per 48h (16 calls) | Sustainable for production |
| **Cache hit rate** | >90% | Minimal API calls |
| **Sentiment relevance** | Sentiment correlates with price action ±6h | Timing matters |

### Data to Collect
```json
{
  "sentiment_polling": {
    "refresh_interval_hours": 6,
    "total_fetches": 0,
    "successful_fetches": 0,
    "failed_fetches": 0,
    "cache_hits": 0,
    "cache_hit_rate_pct": 0.0,
    "avg_sentiment_score": 0.0,
    "sentiment_volatility": 0.0,
    "sentiment_trend": "bullish|bearish|neutral",
    "correlation_with_price_action": {
      "btc_sentiment_lag_optimal_hours": 0,
      "xrp_sentiment_lag_optimal_hours": 0
    },
    "api_costs_usd": 0.0
  }
}
```

### Evaluation Criteria
- ✅ **PASS:** Sentiment stable, cache hit >85%, cost <$8, correlation positive
- ⚠️ **MARGINAL:** Sentiment drifts, maybe increase refresh to 4h
- ❌ **FAIL:** Sentiment worthless (>12h lag), consider daily refresh or alternative source

### Post-Test Decision
- If **PASS:** 6h interval optimal, lock in for Phase 4
- If **MARGINAL:** Adjust to **4-hour** interval, re-test 24h
- If **FAIL:** Switch to **daily (24h)** sentiment, focus on intraday RSI signals

---

## CONSOLIDATED TEST REPORT (Due 2026-03-28 13:00 PDT)

```json
{
  "phase_3_test_results": {
    "test_date": "2026-03-26 13:00 PDT to 2026-03-28 13:00 PDT",
    "duration_hours": 48.0,
    "pairs_tested": ["BTC-USD", "XRP-USD"],
    
    "question_1_rsi_signals": {
      "status": "PASS|MARGINAL|FAIL",
      "btc_signal_quality": 0.0,
      "xrp_signal_quality": 0.0,
      "recommendation": "Keep | Tune Thresholds | Redesign"
    },
    
    "question_2_polling_frequency": {
      "status": "PASS|MARGINAL|FAIL",
      "cpu_usage_pct": 0.0,
      "memory_stability": "Stable|Drift|Leak",
      "recommendation": "Keep 5m | Switch to 10m | Switch to 15m"
    },
    
    "question_3_sentiment_impact": {
      "status": "PASS|MARGINAL|FAIL",
      "btc_win_rate_with_sentiment": 0.0,
      "xrp_win_rate_with_sentiment": 0.0,
      "sentiment_value_pct_improvement": 0.0,
      "recommendation": "Use Sentiment | Research Alternatives | Disable"
    },
    
    "question_4_sentiment_frequency": {
      "status": "PASS|MARGINAL|FAIL",
      "optimal_refresh_hours": 6,
      "cache_efficiency": 0.0,
      "recommendation": "Keep 6h | Switch to 4h | Switch to 24h"
    },
    
    "go_nogo_phase_4": "GO | NO-GO | CONDITIONAL",
    "phase_4_conditions": "If all PASS",
    "priority_next_steps": [
      "1. Fix any FAIL items before Phase 4",
      "2. Add X API credentials (if using sentiment)",
      "3. Setup OAuth2 for live trading",
      "4. Final security audit"
    ]
  }
}
```

---

## TEST MONITORING (Every 12 Hours)

**Friday 1 AM PT:** Quick check
- Process running? ✅
- EVENT_LOG.json growing? ✅
- Errors in logs? ❌

**Friday 1 PM PT:** Interim report
- Trades executing? ✅
- Win rate trend visible? ✅
- Any timeouts? ❌

**Friday 1 PM PT:** Final analysis
- All 4 questions answered
- Consolidated report generated
- Phase 4 go/no-go decision ready

---

## SUCCESS DEFINITION

✅ **Phase 3 COMPLETE when:**
1. All 4 questions have measurable answers
2. Consolidated report populated with data
3. Clear recommendation for Phase 4

❌ **Phase 3 FAILED if:**
- Test crashes before completion
- Majority of questions unanswerable (missing data)
- Win rate <30% (strategy broken)
