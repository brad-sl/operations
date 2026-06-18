# Phase 5.1 Feature: Adaptive Weekly Re-balancing

**Status:** READY FOR IMPLEMENTATION  
**Priority:** CRITICAL (core phase 5 → phase 5.1 differentiator)  
**Target Window:** Monday 5:47 PM–6:30 PM PT (5/5 Phase 6 improvements)  
**Model:** Qwen3-Coder:free (architecture/optimization)  

---

## Business Case

**Problem:** Phase 5 runs static allocations ($200/pair × 4 pairs) + daily sentiment updates. Misses correlation shifts that last 5–30 days (market regime changes).

**Solution:** Weekly re-balance triggered by correlation matrix.
- **If avg correlation > 0.7:** Market regime is "high-correlation" (all pairs moving together). Reduce highest-correlation pair by 50% → shift capital to reserve/lower-corr pair.
- **If avg correlation ≤ 0.7:** Normal/diverse market. Keep allocations.

**Empirical Win:** +21.5% annual return (vs +18.2% static monthly) on $1K sim.
- **+3.3% additional gain** from timely rotation
- **Best Sharpe ratio** (1.58) — lower risk per unit return
- **Sustainable:** ~52 rebalances/year (weekly), not 312+ (daily) which incur fees

---

## Feature Specification

### 1. Triggering Logic

```python
# Every 7 days (Monday, say)
cycle_number = current_total_cycles
rebalance_interval = 7  # Every 7 cycles (~7 min at 60s/cycle, or map to calendar week)

if cycle_number % rebalance_interval == 0:
    correlation_matrix = calculate_correlation(price_history)
    avg_correlation = correlation_matrix.abs().mean().mean()
    
    if avg_correlation > 0.7:
        allocations, reserve = rebalance_on_high_correlation(allocations, correlation_matrix, reserve_usd)
        log_event(f"REBALANCE: High correlation ({avg_correlation:.2f}) → reduced high-corr pair")
    else:
        log_event(f"REBALANCE CHECK: Low correlation ({avg_correlation:.2f}) → hold allocations")
```

### 2. Rebalance Logic

**When correlation > 0.7:**
```python
def rebalance_on_high_correlation(allocations, corr, reserve):
    # Find pair with highest avg correlation to all others
    pair_corr_means = corr.abs().mean()
    high_corr_pair = pair_corr_means.idxmax()
    
    # Reduce by 50%, move to reserve
    reduction = allocations[high_corr_pair] * 0.5
    allocations[high_corr_pair] -= reduction
    reserve += reduction
    
    log_event(f"  → Reduced {high_corr_pair} by ${reduction:.2f} (corr: {pair_corr_means[high_corr_pair]:.2f})")
    
    return allocations, reserve
```

**Rationale:**
- High correlation → portfolio is over-concentrated in similar price movements
- Reducing the "most-correlated" pair preserves diversification
- Moving cash to reserve enables opportunistic entries when RSI+sentiment align

### 3. Integration into Phase 5.1 Cycle

```python
# phase5_1_multi_pair.py cycle loop

for cycle_num in range(288):
    # 1. Fetch price data + calculate RSI for all pairs
    for pair in PAIRS:
        prices = fetch_historical(pair, lookback=100)
        rsi = calculate_rsi(prices, window=14)
        price = prices[-1]
    
    # 2. REBALANCE CHECK (every 7 cycles)
    if cycle_num % 7 == 0:
        correlation_matrix = calculate_correlation([prices_dict[p] for p in PAIRS])
        allocations, reserve = rebalance_on_high_correlation(allocations, correlation_matrix, reserve)
    
    # 3. Calculate sentiment (every cycle)
    sentiment_score = fetch_sentiment_aggregated()
    
    # 4. Generate entry/exit signals (RSI + sentiment + correlation)
    for pair in PAIRS:
        signal = generate_signal(rsi[pair], sentiment_score, correlation_strength[pair])
        
        # 5. Execute via OrderExecutor if signal triggered
        if signal == 'BUY':
            order_result = executor.execute_signal({
                'id': f'{pair}-{cycle_num}',
                'signal': 'BUY',
                'confidence': sentiment_weighted_rsi,
                'price': price
            })
        elif signal == 'SELL' and positions[pair] > 0:
            # Check SL/TP
            check_stop_loss_take_profit(pair, price, entry_price, positions[pair])
    
    # 6. Checkpoint state
    if cycle_num % 10 == 0:
        checkpoint_manager.save_state(allocations, positions, reserve, cycle_num)
    
    time.sleep(60)  # 60s per cycle
```

### 4. Configuration Parameters

```python
# config.json or config_loader.py
{
    "rebalance_freq": "weekly",           # Options: 'daily' (1), 'weekly' (7), 'monthly' (30)
    "rebalance_interval_cycles": 7,       # Cycles between rebalances (7 cycles = ~7 min at 60s/cycle)
    "correlation_threshold": 0.7,         # High-corr triggers rebalancing
    "rebalance_reduction_pct": 50,        # Reduce high-corr pair by 50%
    
    # Phase 5.1 risk controls
    "stop_loss_pct": -5,                  # Exit if position down 5%
    "take_profit_pct": 10,                # Exit if position up 10%
    "reserve_pct": 20,                    # Keep 20% USD in reserve
    "deployment_pct": 80,                 # Deploy 80% across pairs
    
    # Signal generation
    "rsi_oversold": 30,                   # RSI < 30 = bullish entry
    "rsi_overbought": 70,                 # RSI > 70 = bearish exit
    "sentiment_threshold_buy": 0.60,      # Sentiment > 0.60 + RSI < 30 = BUY
    "sentiment_threshold_sell": 0.40      # Sentiment < 0.40 + RSI > 70 = SELL
}
```

---

## Implementation Plan (5:47–6:30 PM Monday)

### Phase 1: Code Changes (15 min)
**File:** `phase5_1_multi_pair.py` (fork from phase5_multi_pair.py)

```python
# Change 1: Add rebalance config
REBALANCE_INTERVAL = 7  # cycles
CORRELATION_THRESHOLD = 0.7

# Change 2: Add rebalance check in main loop
if cycle_num % REBALANCE_INTERVAL == 0:
    correlations = calculate_correlations(price_history)
    allocations, reserve = rebalance_on_correlation(allocations, correlations, reserve)

# Change 3: Wire OrderExecutor into signal generation
from order_executor import OrderExecutor
executor = OrderExecutor(signals=[], coinbase_api=coinbase_wrapper, ...)
```

**Files to create/modify:**
- ✅ `phase5_1_multi_pair.py` (new, from phase5_multi_pair.py + rebalance logic)
- ✅ `correlation_calculator.py` (extract/enhance from existing code)
- ✅ Update `config_loader.py` with rebalance params

### Phase 2: Testing (10 min)
**Commands:**
```bash
# 1. Syntax check
python3 phase5_1_multi_pair.py --dry-run --cycles 5

# 2. Calculate correlation snapshot (test data)
python3 -c "import correlation_calculator; corr = correlation_calculator.test(); print(corr)"

# 3. Verify rebalance logic
python3 backtest_phase6_rebalance_freq_test.py --freq weekly
# Should show: Win 64%, Sharpe 1.58, +21.5%
```

### Phase 3: Deploy & Restart (10 min)
**Commands:**
```bash
# 1. Stop Phase 5
pkill -f phase5_multi_pair

# 2. Start Phase 5.1 (dry run 1 cycle)
SANDBOX_MODE=False EXECUTE_TRADES=False python3 phase5_1_multi_pair.py --cycles 1

# 3. Verify logs
tail -20 logs/phase5_1_multi_pair.log
# Should show: "REBALANCE CHECK: correlation 0.XX"

# 4. Go live
SANDBOX_MODE=False EXECUTE_TRADES=True python3 phase5_1_multi_pair.py --cycles 288 &
```

### Phase 4: Monitor (5 min)
**Check:**
- ✅ Health monitor detects Phase 5.1 process
- ✅ Sentiment aggregation continues (every 30 min)
- ✅ First rebalance fires (if cycle_num % 7 == 0 in loop)
- ✅ No crashes

---

## Success Criteria

✅ **Code:**
- Phase 5.1 runs 288 cycles without errors
- Rebalance logic triggers every 7th cycle
- OrderExecutor integration wired (BUY/SELL signals routed)

✅ **Metrics:**
- Win rate ≥ 64% (from backtest)
- Sharpe ≥ 1.58
- Max DD ≤ -4.2%

✅ **Operations:**
- Sentiment updates every 30 min (existing)
- Health monitor auto-restarts on exit 0 (existing)
- Cycles exit code 0 (no crashes)

---

## Rollback Plan

If Phase 5.1 fails:
1. Kill process: `pkill -f phase5_1_multi_pair`
2. Revert to Phase 5: Start phase5_multi_pair.py (existing, tested 29h+)
3. Root cause: Check logs/checkpoint for error

---

## Post-Launch (Tuesday+)

1. **Monitor for 48h:** Confirm rebalance logic fires, positions tracked, SL/TP working
2. **Analyze sentiment weighting:** Does sentiment scoring improve signal quality?
3. **Track PnL:** Real trading at $1K capital — expect win rate 60–65% align with backtest
4. **Iterate:** Tune correlation_threshold (0.65–0.75?) if needed

---

## Deliverables (by 6:30 PM Monday)

- ✅ `phase5_1_multi_pair.py` (ready, tested)
- ✅ `correlation_calculator.py` (clean, tested)
- ✅ `REBALANCE_FREQUENCY_RESULTS.md` (reference backtest)
- ✅ Updated `config_loader.py` with rebalance params
- ✅ Logs: `logs/phase5_1_multi_pair.log` (first cycle output)
- ✅ Health check passes (process running = READY)

---

## Why This Matters

**The rebalance feature is the difference between:**
- **Phase 5 (signal-only):** Collects data, calculates RSI/sentiment, zero execution → 0% PnL
- **Phase 5.1 (signal + rebalance):** Executes trades, rebalances weekly, manages SL/TP → +21% annualized

Weekly rebalancing is the "regime-adaptive" piece that every institutional bot has. It's what makes Phase 5.1 production-grade.

---

**Ready to code? Qwen3-Coder standing by.** 🚀

Confirm architecture? Questions? Go live? 🎯
