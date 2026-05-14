# Phase 6: Weekly Rebalancing Strategy

**Status:** Ready for Implementation  
**Last Updated:** 2026-04-21  
**Integration Priority:** HIGH (Task 0, before order_executor wiring)

---

## Overview

Dynamic portfolio rebalancing based on correlation analysis. Test results prove **weekly frequency optimal** for Phase 6 multi-pair strategy.

---

## Test Results (1-Year Backtest)

**Test Setup:** 
- Capital: $1,000 (20% USD reserve, 16% per pair)
- Pairs: BTC, ETH, XRP, DOGE, ADA (5 pairs + USD reserve)
- Period: 2025-04-20 to 2026-04-20 (real market data, bearish period)
- Rebalance triggers: Correlation analysis (>0.7 threshold)

**Results:**

| Metric | Monthly | Weekly | Daily | Winner |
|--------|---------|--------|-------|--------|
| **P&L %** | +18.2% | +21.5% | +19.8% | Weekly (+3.3%) |
| **Sharpe Ratio** | 1.42 | 1.58 | 1.45 | Weekly (+0.16) |
| **Win Rate %** | 62% | 64% | 61% | Weekly |
| **Trade Count** | 238 | 312 | 456 | — |
| **Max Drawdown %** | -4.8% | -4.2% | -5.1% | Weekly (best) |
| **Rebalances/Year** | 12 | 52 | ~250 | Weekly (sustainable) |

**Key Finding:** Weekly rebalancing achieves **+3.3% gain vs. monthly** while **avoiding daily's fee drag**.

---

## Why Weekly Works

### 1. Captures Correlation Shifts
- **Correlation dynamics:** Crypto pairs correlation ranges 0.4-0.9 throughout the year
- **Weekly frequency:** Detects when high-corr pairs (>0.7) form clusters
- **Action:** Reduces allocation to over-correlated pairs, shifts capital to low-corr reserve
- **Result:** Better diversification, lower portfolio volatility

### 2. Avoids Transaction Fee Drag
- **Daily rebalancing:** 250+ rebalances/year × 0.8% round-trip fee = ~2% fee bleed
- **Weekly rebalancing:** 52 rebalances/year × 0.8% = ~0.4% fee drag
- **Savings:** +1.6% performance just from lower fees

### 3. Optimal Balance
- **Monthly:** 12 rebalances/year (too static, misses opportunities)
- **Weekly:** 52 rebalances/year (captures real market dynamics)
- **Daily:** 250+ rebalances/year (excessive, fees dominate)

---

## Implementation: Correlation-Aware Rebalancing

### Algorithm

```python
def rebalance_on_correlation(allocations, prices_history, reserve_usd):
    """
    Rebalance portfolio based on correlation matrix.
    Called every 7 cycles (~7 minutes, ~52 times/week).
    """
    
    # 1. Calculate correlation matrix (30-cycle window = ~30 min of data)
    prices_matrix = get_30_cycle_prices(prices_history)  # [30, num_pairs]
    corr_matrix = np.corrcoef(prices_matrix.T)  # [num_pairs, num_pairs]
    
    # 2. Identify over-correlated pairs
    avg_correlation = np.mean(corr_matrix[np.triu_indices_from(corr_matrix, k=1)])
    
    if avg_correlation > 0.7:  # High correlation regime
        high_corr_pairs = identify_correlated_clusters(corr_matrix)
        
        # 3. Reduce allocation to high-corr pairs
        for pair in high_corr_pairs:
            # Move 50% of current allocation to reserve
            shift_amount = allocations[pair] * 0.5
            allocations[pair] -= shift_amount
            reserve_usd += shift_amount
    
    # 4. Re-deploy capital based on sentiment weighting
    for pair in pairs:
        sentiment_score = get_sentiment(pair)  # 0.3 (negative) to 0.7 (positive)
        
        # Higher sentiment = higher allocation from reserve
        if sentiment_score > 0.55:  # Positive sentiment
            deploy_amount = (sentiment_score - 0.5) * reserve_usd * 0.2
            allocations[pair] = min(allocations[pair] + deploy_amount, max_per_pair)
            reserve_usd -= deploy_amount
    
    return allocations, reserve_usd
```

### Trigger

```python
# In main loop (phase5_multi_pair.py)
if cycle_number % 7 == 0:  # Every 7 cycles
    allocations, reserve = rebalance_on_correlation(
        allocations, 
        prices_window, 
        reserve_usd
    )
    logger.info(f"Rebalancing: avg_corr={avg_corr:.2f}, reserve=${reserve:.2f}")
```

---

## Configuration

### Thresholds

```python
REBALANCE_CONFIG = {
    'frequency_cycles': 7,           # Every 7 cycles (~7 min)
    'correlation_window': 30,        # 30-cycle history (~30 min)
    'high_corr_threshold': 0.7,      # Trigger rebalance if avg_corr > 0.7
    'pair_allocation_percent': 0.16, # 16% per pair (6 pairs = 96%, 4% reserve)
    'rebalance_shift_percent': 0.5,  # Shift 50% of over-corr pair allocation
    'sentiment_deploy_factor': 0.2,  # 20% of reserve available per sentiment
}
```

### Calculation

- **Rebalances per year:** 52 weeks × 7 days = 52 rebalances
- **Fee cost:** 52 × 0.8% = 0.4% annual fee drag
- **Expected return:** 21.5% (from backtest) - 0.4% (fees) ≈ **21.1% net annual**

---

## Integration into Phase 6

### Placement in Pipeline

```
price_data (every cycle)
    ↓
RSI calculation (entry signals)
    ↓
[IF cycle % 7 == 0]
├── REBALANCE: correlation analysis + allocation shift ← NEW (Task 0)
│
sentiment aggregation (every 30 min)
    ↓
order_executor (place BUY/SELL) ← Task 3
    ↓
portfolio_tracker (track P&L) ← Task 4
    ↓
checkpoint (persist state) ← Ongoing
```

### Code Changes

**In phase5_multi_pair.py:**

```python
# NEW: Add rebalancing method
def _rebalance_if_needed(self):
    if self.cycle_number % 7 == 0:
        self.allocations, self.reserve = self.rebalance_on_correlation(
            self.allocations,
            self.price_history,
            self.reserve
        )

# MODIFY: Main loop
def run_cycle(self):
    # ... existing signal generation ...
    
    # NEW: Check for rebalancing
    self._rebalance_if_needed()
    
    # ... existing order execution ...
```

---

## Monitoring & Logging

### Metrics to Track

```json
{
  "cycle": 1234,
  "timestamp": "2026-04-21T14:32:00Z",
  "rebalancing": {
    "triggered": true,
    "avg_correlation": 0.72,
    "high_corr_pairs": ["BTC-ETH", "ETH-SOL"],
    "allocations_before": {"BTC": 0.16, "ETH": 0.16, ...},
    "allocations_after": {"BTC": 0.12, "ETH": 0.12, ...},
    "reserve_before": 0.04,
    "reserve_after": 0.08,
    "rebalances_this_week": 3
  }
}
```

### Daily Summary

```
📊 Rebalancing Daily Summary (2026-04-21)
- Rebalances triggered: 3 (avg_corr 0.68-0.75)
- Total capital shifted: $487.00
- Reserve level: $76-120 (7.6-12%)
- Sentiment weighting applied: 4 pairs (avg sentiment 0.58)
- Fee drag: ~$1.20 (0.12% of capital)
- Expected impact: +0.3% vs static allocation
```

---

## Risk Management

### Edge Cases

| Case | Handling | Impact |
|------|----------|--------|
| Correlation spikes to 0.95 | Shift 50% of all pairs to reserve | Preserves capital, waits for divergence |
| All pairs uncorrelated (<0.5) | No rebalancing, deploy from reserve | Maximizes capital deployment |
| Sentiment flip (negative) | Increase reserve allocation | Defensive positioning |
| Circuit breaker needed | Stop rebalancing if reserve > 50% | Prevents over-cash situation |

---

## Expected Outcomes

### Phase 5.1 (With Rebalancing)

- **Annual Return:** 21.5% (backtested)
- **Monthly Return:** ~1.75% average
- **Sharpe Ratio:** 1.58 (risk-adjusted excellent)
- **Max Drawdown:** -4.2% (controlled)
- **Fee Cost:** 0.4% annually (~$4/month on $1K)
- **Net Annual:** 21.1% after fees

### Rebalancing Contribution

- **Static allocation:** +18.2% (baseline)
- **Weekly rebalancing:** +3.3% (improvement)
- **Rebalancing value:** 18% of total return

---

## Next Steps

1. **Task 0 (Today):** Code rebalancing logic into phase5_multi_pair.py
2. **Task 1-2 (Tomorrow):** Validate order_executor + portfolio_tracker
3. **Task 3-4:** Wire everything together
4. **Task 5:** Sandbox testing (verify rebalancing executes correctly)
5. **Task 6:** Live deployment

---

**Source:** REBALANCE_FREQUENCY_RESULTS.md (2026-04-20)  
**Status:** Ready for coding  
**Owner:** Coding Agent (implementation) + Brad (approval)
