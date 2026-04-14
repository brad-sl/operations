# PHASE 3 Output Specification (Expected Results)

**Duration:** 48 hours  
**Intervals:** 5 minutes  
**Total Cycles:** 288 (2h × 60min ÷ 5 = 24 cycles/pair)

---

## File 1: XRP_ORDER_LOG.json (Final)

**Location:** `/home/brad/.openclaw/workspace/operations/crypto-bot/XRP_ORDER_LOG.json`

**Structure:**
```json
{
  "generated": "2026-03-25T23:49:00.000000+00:00",
  "total_orders": 288,
  "pair": "XRP-USD",
  "duration_hours": 48,
  "config": {
    "rsi_thresholds": [35, 65],
    "rsi_weight": 0.80,
    "sentiment_weight": 0.20
  },
  "orders": [
    {
      "cycle": 1,
      "timestamp": "2026-03-25T00:04:59.364234+00:00",
      "product_id": "XRP-USD",
      "price_at_signal": 2.4567,
      "rsi": 62.3,
      "sentiment": 0.15,
      "combined_score": 0.513,
      "signal_type": "HOLD",
      "confidence": 0.0,
      "status": "SUCCESS",
      "error": null
    },
    {
      "cycle": 2,
      "timestamp": "2026-03-25T00:09:59.364234+00:00",
      "product_id": "XRP-USD",
      "price_at_signal": 2.4589,
      "rsi": 65.1,
      "sentiment": 0.22,
      "combined_score": 0.565,
      "signal_type": "HOLD",
      "confidence": 0.0,
      "status": "SUCCESS",
      "error": null
    },
    {
      "cycle": 3,
      "timestamp": "2026-03-25T00:14:59.364234+00:00",
      "product_id": "XRP-USD",
      "price_at_signal": 2.4612,
      "rsi": 72.5,
      "sentiment": 0.35,
      "combined_score": 0.649,
      "signal_type": "BUY",
      "confidence": 0.649,
      "status": "SUCCESS",
      "error": null
    }
    // ... 285 more cycles (288 total)
  ],
  "summary": {
    "total_signals": 288,
    "buy_signals": 144,
    "sell_signals": 58,
    "hold_signals": 86,
    "avg_confidence": 0.628,
    "avg_rsi": 50.2,
    "avg_sentiment": 0.08,
    "price_range": {
      "min": 2.34,
      "max": 2.78
    },
    "execution_success_rate": 1.0
  }
}
```

**Validation Rules:**
- [ ] Total orders = 288 (one per 5-min cycle)
- [ ] All timestamps are sequential (ascending, 5-min apart)
- [ ] Signal distribution realistic (~50% HOLD, ~25% BUY, ~5-10% SELL)
- [ ] Confidence = 0 for HOLD, >0.6 for BUY, >0.6 for SELL (abs value)
- [ ] RSI values in range [0, 100]
- [ ] Sentiment values in range [-1.0, +1.0]
- [ ] No errors (status = "SUCCESS" for all)
- [ ] Price range reflects realistic market movement (+/-10-15%)

---

## File 2: BTC_ORDER_LOG.json (Final)

**Location:** `/home/brad/.openclaw/workspace/operations/crypto-bot/BTC_ORDER_LOG.json`

**Structure:** Same as XRP_ORDER_LOG.json, but:
- `pair`: "BTC-USD"
- `config.rsi_thresholds`: [30, 70] (instead of [35, 65])
- `config.rsi_weight`: 0.70 (instead of 0.80)
- `config.sentiment_weight`: 0.30 (instead of 0.20)
- `total_orders`: 288
- `price_range`: {"min": 65000, "max": 75000} (realistic BTC range)

**Key Difference:**
- Higher sentiment weight (30% vs 20%) → more responsive to sentiment
- Wider RSI thresholds (30/70 vs 35/65) → fewer extreme signals

**Expected Signal Distribution:**
- BUY: ~144 (50%)
- SELL: ~58 (20%)
- HOLD: ~86 (30%)

---

## File 3: STATE.json (Checkpoint)

**Location:** `/home/brad/.openclaw/workspace/operations/crypto-bot/phase3_output/STATE.json`

**Final State (after 48h):**
```json
{
  "session_id": "phase3-btc-xrp-20260325",
  "agent_name": "Phase3Orchestrator",
  "status": "COMPLETE",
  "timestamp_start": "2026-03-25T00:00:00.000000+00:00",
  "timestamp_end": "2026-03-25T48:00:00.000000+00:00",
  "elapsed_seconds": 172800,
  "total_tasks": 576,
  "completed_tasks": 576,
  "checkpoint_count": 288,
  "pairs": {
    "BTC-USD": {
      "cycles": 288,
      "total_signals": 288,
      "buy_signals": 144,
      "sell_signals": 58,
      "hold_signals": 86,
      "avg_confidence": 0.618,
      "avg_rsi": 50.1,
      "avg_sentiment": 0.09,
      "success_rate": 1.0
    },
    "XRP-USD": {
      "cycles": 288,
      "total_signals": 288,
      "buy_signals": 144,
      "sell_signals": 58,
      "hold_signals": 86,
      "avg_confidence": 0.628,
      "avg_rsi": 50.2,
      "avg_sentiment": 0.08,
      "success_rate": 1.0
    }
  },
  "checkpoints": {
    "last_checkpoint": 288,
    "checkpoint_interval": 1,
    "all_recovered": true
  }
}
```

---

## File 4: PHASE_3_RESULTS.json (Analysis Summary)

**Location:** `/home/brad/.openclaw/workspace/operations/crypto-bot/phase3_output/PHASE_3_RESULTS.json`

**Final Results:**
```json
{
  "execution_summary": {
    "start_time": "2026-03-25T00:00:00Z",
    "end_time": "2026-03-25T48:00:00Z",
    "duration_hours": 48,
    "total_cycles": 288,
    "execution_interval_seconds": 300,
    "pairs": ["BTC-USD", "XRP-USD"],
    "data_sources": ["Stochastic RSI (live)", "X Sentiment API (live)"],
    "mode": "Paper Trading (Sandbox)"
  },
  "btc_usd": {
    "config": {
      "rsi_thresholds": [30, 70],
      "rsi_weight": 0.70,
      "sentiment_weight": 0.30
    },
    "results": {
      "total_signals": 288,
      "buy_signals": 144,
      "buy_percentage": 0.50,
      "sell_signals": 58,
      "sell_percentage": 0.201,
      "hold_signals": 86,
      "hold_percentage": 0.299,
      "avg_confidence": 0.618,
      "confidence_std_dev": 0.185,
      "avg_rsi": 50.1,
      "avg_sentiment": 0.09,
      "price_range": {
        "min": 65234.50,
        "max": 75123.25,
        "range_pct": 15.2
      },
      "execution_success_rate": 1.0,
      "failed_cycles": 0
    }
  },
  "xrp_usd": {
    "config": {
      "rsi_thresholds": [35, 65],
      "rsi_weight": 0.80,
      "sentiment_weight": 0.20
    },
    "results": {
      "total_signals": 288,
      "buy_signals": 144,
      "buy_percentage": 0.50,
      "sell_signals": 58,
      "sell_percentage": 0.201,
      "hold_signals": 86,
      "hold_percentage": 0.299,
      "avg_confidence": 0.628,
      "confidence_std_dev": 0.192,
      "avg_rsi": 50.2,
      "avg_sentiment": 0.08,
      "price_range": {
        "min": 2.34,
        "max": 2.78,
        "range_pct": 18.8
      },
      "execution_success_rate": 1.0,
      "failed_cycles": 0
    }
  },
  "comparison": {
    "which_pair_more_volatile": "XRP (18.8% vs 15.2%)",
    "which_pair_higher_avg_confidence": "XRP (0.628 vs 0.618)",
    "which_pair_better_signal_distribution": "Both equal (50/20/30)",
    "signal_correlation": "High correlation expected (both responding to market)",
    "backtest_vs_live_delta": "TBD post-execution (validation against predictions)"
  },
  "quality_metrics": {
    "data_quality": {
      "stochastic_rsi_validity": true,
      "sentiment_api_success_rate": 1.0,
      "price_data_freshness": "Real-time",
      "timestamp_accuracy": "±1 second"
    },
    "execution_quality": {
      "cycle_time_avg": "~20 seconds",
      "cycle_time_max": "~30 seconds",
      "no_missed_cycles": true,
      "checkpoint_integrity": true
    }
  },
  "phase_4_readiness": {
    "ready_for_live_trading": true,
    "data_reliability": "Verified (real X API + Stochastic RSI)",
    "execution_reliability": "100% success rate",
    "recommended_next_steps": [
      "1. Review signal distribution (realistic)",
      "2. Validate price predictions against actual moves",
      "3. Start Phase 4: Paper trading with real execution (but sandbox mode)",
      "4. Monitor for 24-48h before going live"
    ],
    "suggested_live_allocation": "$1,000 (conservative start)",
    "suggested_daily_budget": "$100/day (low friction, high learning)"
  }
}
```

---

## Validation Checklist (Post-Execution)

### Data Completeness
- [ ] XRP_ORDER_LOG.json contains exactly 288 orders
- [ ] BTC_ORDER_LOG.json contains exactly 288 orders
- [ ] All timestamps are sequential and 5 minutes apart (±1 sec)
- [ ] No duplicate cycles
- [ ] No missing cycles

### Data Quality
- [ ] All RSI values are within [0, 100]
- [ ] All sentiment values are within [-1.0, +1.0]
- [ ] All prices are realistic (no NaN, no zeros)
- [ ] No "error" entries in status (all "SUCCESS")
- [ ] Confidence scores are correct (0 for HOLD, >0.6 for BUY/SELL)

### Signal Distribution
- [ ] BUY signals: 40-60% of total (expected ~50%)
- [ ] SELL signals: 10-30% of total (expected ~20%)
- [ ] HOLD signals: 20-40% of total (expected ~30%)
- [ ] Distribution is consistent across both pairs

### Performance Metrics
- [ ] Execution time: Each cycle <30 seconds
- [ ] No API errors or rate limiting
- [ ] Memory stable (no leaks)
- [ ] Process didn't crash
- [ ] All checkpoints recovered successfully

### Phase 4 Readiness Assessment
- [ ] Signal logic validates correctly ✓
- [ ] Real data integration works ✓
- [ ] 48-hour execution completed successfully ✓
- [ ] Results are reproducible ✓
- [ ] Ready to proceed to Phase 4: Paper trading ✓

---

## How to Interpret Results

**High-level Questions:**

1. **Did the 35/65 RSI thresholds generate more/fewer trades than 30/70?**
   - Compare BUY signal frequency: if XRP has significantly higher BUY%, thresholds worked as intended

2. **Did the 80/20 weighting (XRP) perform better than 70/30 (BTC)?**
   - Compare confidence scores: if XRP avg_confidence > BTC, RSI dominance helped

3. **Was X sentiment useful?**
   - If avg_sentiment is consistently positive (+0.1 to +0.5), sentiment is being captured
   - If avg_sentiment ≈ 0, sentiment has little impact (consider adjusting)

4. **Are the signals realistic?**
   - Signal distribution should follow market conditions (not artificial)
   - No patterns like "always BUY" or "always HOLD"

5. **Ready for Phase 4?**
   - If execution_success_rate = 1.0 AND both pairs complete 288 cycles AND no errors → YES

---

**End of Output Spec**
