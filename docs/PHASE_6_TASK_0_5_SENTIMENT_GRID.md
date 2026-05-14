# Phase 6 Task 0.5: Sentiment Grid Test

**Status:** Ready to Execute  
**Priority:** HIGH (validates 15% uplift hypothesis)  
**Prerequisite:** None (can run parallel to Task 0)  
**Duration:** ~15-30 minutes

---

## Objective

Validate decay half-life parameters for multi-source sentiment aggregation before coding Phase 6 integration.

**Historical Data:** +15.5% absolute uplift with multi-source (21.5% → 37% ROI)  
**Goal:** Find optimal decay parameters to maximize win-rate and Sharpe ratio

---

## Test Grid

### Twitter/X Half-Life
- 15 minutes (fast decay, high weight on fresh data)
- 30 minutes (baseline, current Phase 5.1 assumption)
- 60 minutes (slower, captures 1-2 hour price moves)

### Reddit Half-Life
- 1 hour (faster than original 6hr, more reactive)
- 2 hours (medium, balances freshness + robustness)
- 4 hours (original v1 design, slower consensus)

### News Half-Life (Optional)
- 1 hour (if NewsAPI integrated)
- 2 hours (conservative)

---

## Backtest Parameters

**Script:** `archived/sentiment_backtest.py`

**Command:**
```bash
cd /home/brad/.openclaw/workspace/operations/crypto-bot

python3 archived/sentiment_backtest.py \
  --period 365 \
  --grid decay \
  --twitter-half-life 15,30,60 \
  --reddit-half-life 60,120,240 \
  --output-dir config/sentiment_grid_results_$(date +%Y%m%d)
```

**Inputs:**
- Real historical data: 2025-04-20 to 2026-04-20 (1 year, bearish market)
- Initial capital: $1,000
- Pairs: BTC, ETH, SOL, XRP, DOGE, ADA
- Sentiment sources: X API + Reddit (mock data for grid test)
- Reserve: 20% USD

**Outputs:**
- `sentiment_grid_results/decay_15m_60m.json` (Twitter 15min, Reddit 60min)
- `sentiment_grid_results/decay_15m_120m.json`
- `sentiment_grid_results/decay_15m_240m.json`
- `sentiment_grid_results/decay_30m_60m.json` (baseline)
- `sentiment_grid_results/decay_30m_120m.json`
- `sentiment_grid_results/decay_30m_240m.json`
- `sentiment_grid_results/decay_60m_60m.json`
- `sentiment_grid_results/decay_60m_120m.json`
- `sentiment_grid_results/decay_60m_240m.json`

---

## Expected Outputs (Per Scenario)

```json
{
  "decay_params": {
    "twitter_half_life_minutes": 30,
    "reddit_half_life_minutes": 120,
    "news_half_life_minutes": null
  },
  "backtest_period": "2025-04-20 to 2026-04-20",
  "metrics": {
    "total_trades": 312,
    "winning_trades": 198,
    "losing_trades": 114,
    "win_rate_pct": 63.5,
    "total_pnl_dollars": 370.45,
    "total_pnl_pct": 37.0,
    "avg_win_dollars": 12.50,
    "avg_loss_dollars": -8.75,
    "max_win_dollars": 45.20,
    "max_loss_dollars": -22.10,
    "sharpe_ratio": 1.62,
    "max_drawdown_pct": -4.1,
    "profit_factor": 1.43
  },
  "sentiment_stats": {
    "avg_twitter_weight": 0.45,
    "avg_reddit_weight": 0.38,
    "avg_cache_weight": 0.17,
    "correlation_agreement": 0.78,
    "sentiment_threshold_buy": 0.55,
    "sentiment_threshold_sell": 0.45
  }
}
```

---

## Decision Matrix

After running grid (9 scenarios):

| Twitter HL | Reddit HL | Win% | Sharpe | PnL% | Decision |
|-----------|----------|------|--------|------|----------|
| 15m | 60m | ? | ? | ? | Too fast? |
| 15m | 120m | ? | ? | ? | Balanced |
| 15m | 240m | ? | ? | ? | Weighted to Reddit |
| 30m | 60m | ? | ? | ? | Baseline |
| 30m | 120m | **?** | **?** | **?** | **Expected optimal** |
| 30m | 240m | ? | ? | ? | Original v1 |
| 60m | 60m | ? | ? | ? | Similar halves |
| 60m | 120m | ? | ? | ? | Slower X |
| 60m | 240m | ? | ? | ? | Most conservative |

**Selection Criteria:**
1. **Primary:** Highest Sharpe ratio (risk-adjusted returns)
2. **Secondary:** Win-rate > 60%
3. **Tertiary:** Profit factor > 1.4
4. **Tie-breaker:** Lowest max drawdown

---

## Analysis After Grid Test

**Questions to Answer:**

1. **Does multi-source beat X-only?**
   - Expected: Yes (validate 15% uplift hypothesis)
   - Pass threshold: 35%+ ROI on real 2025-2026 data

2. **Which decay parameters optimal?**
   - Expected: Twitter 30m or 60m, Reddit 1-2hr
   - Validate: Sharpe ratio > 1.60

3. **Sentiment threshold impact?**
   - BUY signal: Sentiment > 0.55 vs > 0.60
   - Impact on false positives

4. **Correlation agreement?**
   - If X & Reddit agree (>0.75): Confidence boost
   - If disagree (<0.50): Reduce position size

5. **Reserve allocation?**
   - Dynamic sizing: bullish >0.6 (30% reserve), neutral 0.4-0.6 (15% reserve)
   - Impact on Sharpe

---

## Phase 6 Integration (If Validated)

**If grid test passes (Sharpe > 1.60, Win% > 60%, PnL > 35%):**

1. Implement optimal decay parameters in Phase 6
   - `sentiment_decay_model.py` with grid-tested half-lives
   - Post-fetch weighting in sentiment_aggregator.py

2. Restore multi-source fetching (X + Reddit)
   - Parallel queries (no dependencies)
   - Fallback to cached sentiment if source fails

3. Add sentiment thresholds to phase5_multi_pair.py
   - BUY: RSI<30 AND Sentiment>0.55
   - SELL: RSI>70 OR Sentiment<0.45
   - Scale position size based on sentiment agreement

4. Dynamic allocation weighting
   - Bullish sentiment (>0.6): Increase per-pair capital
   - Neutral (0.4-0.6): Baseline 16.7% per pair
   - Bearish (<0.4): Hold in reserve, reduce exposure

---

## Success Criteria

✅ **Phase 0.5 Complete:**
- Grid test executed (all 9 scenarios)
- Results documented in config/sentiment_grid_results/
- Optimal parameters identified (Sharpe > 1.60)
- Win-rate validated (> 60%)
- PnL uplift confirmed (> 35% on real 2025-2026 data)
- Decision log updated with findings

✅ **Ready for Phase 6 Integration:**
- If Sharpe > 1.60 AND Win% > 60% AND PnL > 35%
- Proceed to Task 0 (Rebalancing) + Task 0.5A (Code integration)

❌ **If Grid Test Underperforms:**
- Document findings
- Option A: Adjust grid range (broader half-life search)
- Option B: Keep X-only for Phase 6 (defer multi-source to Phase 7)
- Option C: Return to v1 design (6hr Reddit half-life)

---

## Execution

**Owner:** Coding Agent (run backtest script)  
**Review:** Brad (validate results + make Phase 6 decision)  
**Estimated Runtime:** 15-30 min (9 scenarios × 2-3 min each)  
**Storage:** config/sentiment_grid_results_{date}/  

**Ready to spawn?** (Brad's approval)

---

**Source:** Historical data (2026-04-16 session) showed +15.5% uplift with multi-source  
**Hypothesis:** Optimal decay parameters can achieve 35%+ ROI (vs 21.5% baseline)  
**Phase 6 Gate:** Results determine whether to restore multi-source or stay X-only
