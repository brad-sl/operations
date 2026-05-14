# Trading Event Schema — Standardized Nomenclature & Metrics

**Purpose:** Define what matters for post-execution analysis. Eliminate noise, focus on tradable events.

---

## Core Principle

**Only log actual trade events (ENTRY/EXIT/OUTCOME), not every signal.**

Not every signal generates a trade. Not every cycle matters. We care about:
1. When did we enter? (price, reason, risk)
2. When did we exit? (price, reason, P&L)
3. Did we win or lose? (amount, %)

---

## Event Types

### 1. ENTRY Event
**Triggered:** RSI + sentiment crosses BUY/SELL threshold

```json
{
  "event_type": "ENTRY",
  "event_id": "BTC_20260325_001",
  "timestamp": "2026-03-25T08:23:45.123Z",
  "product_id": "BTC-USD",
  "side": "LONG",  // or "SHORT"
  "entry_price": 67523.50,
  "entry_quantity": 0.01,
  "entry_value_usd": 675.24,
  
  "signal_details": {
    "rsi": 28.5,  // Below 30 threshold
    "rsi_threshold_lower": 30,
    "sentiment": -0.65,  // Bearish
    "sentiment_weight": 0.30,
    "combined_score": -0.42,  // Normalized signal strength
    "confidence": 0.85,  // 0-1, how confident in the signal
    "signal_age_seconds": 120  // How fresh is sentiment data
  },
  
  "risk_parameters": {
    "stop_loss_price": 66750,  // Predetermined stop
    "stop_loss_amount_usd": 50,  // Risk per trade
    "stop_loss_pct": 1.15,  // % below entry
    "position_size_pct": 2.0,  // % of account
    "max_slippage_pct": 0.5  // Expected slippage
  },
  
  "market_context": {
    "market_price_usd": 67523.50,
    "bid_ask_spread": 0.42,
    "volume_24h": 28500000,
    "volatility_pct": 1.8  // Recent 1h vol
  }
}
```

---

### 2. EXIT Event
**Triggered:** Stop loss, take profit, timeout, or manual close

```json
{
  "event_type": "EXIT",
  "event_id": "BTC_20260325_001_EXIT",
  "entry_event_id": "BTC_20260325_001",  // Link back to entry
  "timestamp": "2026-03-25T09:15:32.456Z",
  "product_id": "BTC-USD",
  "side": "LONG",
  
  "exit_price": 67650.00,
  "exit_quantity": 0.01,
  "exit_value_usd": 676.50,
  
  "exit_reason": "TAKE_PROFIT",  // or STOP_LOSS, TIMEOUT, REBALANCE, MANUAL
  "exit_reason_details": "Price hit take_profit_target +1.8%",
  
  "duration_seconds": 3147,  // Time in trade (52 minutes)
  "bars_held": 52,  // # of 1-min candles (approx)
  
  "market_context": {
    "market_price_at_exit": 67650.00,
    "volatility_at_exit_pct": 2.1,
    "order_fill_quality": "FULL"  // or PARTIAL, CANCELLED
  }
}
```

---

### 3. OUTCOME Event
**Triggered:** When EXIT completes (P&L calculated)

```json
{
  "event_type": "OUTCOME",
  "event_id": "BTC_20260325_001_OUTCOME",
  "entry_event_id": "BTC_20260325_001",
  "exit_event_id": "BTC_20260325_001_EXIT",
  "timestamp": "2026-03-25T09:15:45.789Z",
  "product_id": "BTC-USD",
  
  "trade_result": "WIN",  // or LOSS, BREAKEVEN
  
  "entry_price": 67523.50,
  "exit_price": 67650.00,
  "price_move": 126.50,  // Exit - Entry
  "price_move_pct": 0.1873,  // (Exit - Entry) / Entry × 100
  
  "pnl_usd": 1.27,  // (Exit - Entry) × Quantity
  "pnl_pct": 0.1873,  // Same as price_move_pct for now
  "pnl_bps": 18.73,  // Basis points (for small %s)
  
  "fees": {
    "entry_fee_usd": 0.07,  // Maker/taker fees
    "exit_fee_usd": 0.07,
    "total_fees_usd": 0.14
  },
  
  "net_pnl": {
    "gross_pnl_usd": 1.27,
    "total_fees_usd": 0.14,
    "net_pnl_usd": 1.13,  // After fees
    "net_pnl_pct": 0.1672  // After fees %
  },
  
  "risk_reward": {
    "risk_amount_usd": 50.0,  // Stop loss amount
    "reward_amount_usd": 1.13,  // Net P&L
    "risk_reward_ratio": 0.0226,  // Reward / Risk (bad!)
    "note": "This trade risked $50 to make $1.13"
  },
  
  "quality_metrics": {
    "signal_confidence": 0.85,
    "was_signal_fresh": true,  // Sentiment <6h old
    "time_in_trade_seconds": 3147,
    "bars_to_target": 52,
    "slippage_vs_signal_price": 0.0023,  // Entry price deviation
    "exit_vs_target": 0.0045  // Exit price vs take-profit target
  }
}
```

---

## Derived Metrics (Post-Analysis)

### Trade-Level Metrics
```json
{
  "win_rate_pct": 45.5,  // Wins / Total trades
  "avg_win_usd": 8.50,
  "avg_loss_usd": -12.75,
  "best_trade_usd": 35.00,
  "worst_trade_usd": -50.00,
  "largest_win_pct": 2.34,
  "largest_loss_pct": -1.85,
  
  "profit_factor": 1.32,  // Gross wins / Gross losses
  "expectancy_usd": 2.15,  // Avg P&L per trade
  
  "consecutive_wins": 3,
  "consecutive_losses": 2,
  "max_drawdown_usd": -127.50,
  "max_drawdown_pct": -3.2
}
```

### Strategy-Level Metrics
```json
{
  "total_trades": 11,
  "winning_trades": 5,
  "losing_trades": 6,
  "breakeven_trades": 0,
  
  "total_gross_pnl_usd": 42.50,
  "total_fees_usd": 1.54,
  "total_net_pnl_usd": 40.96,
  
  "sharpe_ratio": 1.85,  // Risk-adjusted return
  "sortino_ratio": 2.40,  // Downside risk-adjusted
  "calmar_ratio": 0.32,  // Return / Max drawdown
  
  "exposure_time_pct": 32.5,  // % of time in positions
  "avg_hold_time": "47 minutes",
  
  "best_pair": "XRP-USD",  // Which performed better
  "worst_pair": "BTC-USD"
}
```

### Pair Comparison
```json
{
  "BTC_USD": {
    "trades": 3,
    "wins": 1,
    "losses": 2,
    "win_rate_pct": 33.3,
    "total_pnl_usd": -8.42,
    "avg_trade_pnl_usd": -2.81
  },
  "XRP_USD": {
    "trades": 8,
    "wins": 4,
    "losses": 4,
    "win_rate_pct": 50.0,
    "total_pnl_usd": 49.38,
    "avg_trade_pnl_usd": 6.17
  }
}
```

---

## Event Log Structure (JSON)

```json
{
  "session_id": "phase3_48h_20260325",
  "account": "SANDBOX",
  "start_time": "2026-03-24T20:03:00Z",
  "end_time": "2026-03-26T20:03:00Z",
  
  "events": [
    {
      "event_type": "ENTRY",
      "event_id": "BTC_20260325_001",
      "timestamp": "2026-03-25T08:23:45.123Z",
      "product_id": "BTC-USD",
      // ... entry details ...
    },
    {
      "event_type": "EXIT",
      "event_id": "BTC_20260325_001_EXIT",
      "entry_event_id": "BTC_20260325_001",
      "timestamp": "2026-03-25T09:15:32.456Z",
      // ... exit details ...
    },
    {
      "event_type": "OUTCOME",
      "event_id": "BTC_20260325_001_OUTCOME",
      "entry_event_id": "BTC_20260325_001",
      "exit_event_id": "BTC_20260325_001_EXIT",
      "timestamp": "2026-03-25T09:15:45.789Z",
      // ... outcome details (P&L) ...
    }
  ],
  
  "summary": {
    "total_events": 33,  // 11 trades × 3 events per trade
    "entry_events": 11,
    "exit_events": 11,
    "outcome_events": 11,
    "total_net_pnl_usd": 40.96,
    "win_rate_pct": 45.5
  }
}
```

---

## What This Eliminates

❌ **NOT logging:**
- Every signal (only actual trades)
- HOLD signals (no trade activity)
- Partial fills or order details (only final fills matter)
- Tick-level data (too noisy)
- Intermediate checkpoints (end result matters)

❌ **NOT tracking:**
- What could have been
- Hypothetical scenarios
- Sentiment staleness (tracked but not obsessed over)

---

## What This Enables

✅ **Actual analysis:**
- Win rate by pair (BTC vs XRP)
- Risk/reward ratio (is this even worth trading?)
- Sharpe ratio (risk-adjusted returns)
- Max drawdown (worst-case scenario)
- Whether parameters (30/70 vs 35/65) actually work

✅ **Phase 4 decision:**
- "Win rate was 45.5% with avg loss > avg win? Don't go live."
- "Win rate 65% with risk/reward >2:1? Consider Phase 4."
- "XRP outperformed BTC 6:1? Test different parameters."

---

## Implementation Notes

**For the orchestrator:**
1. Track ENTRY when RSI+sentiment crosses threshold (BUY/SELL, not HOLD)
2. Track EXIT when stop loss or take profit hits
3. Calculate OUTCOME (P&L) when exit completes
4. Link all 3 events via `entry_event_id`

**For post-analysis:**
1. Parse events chronologically
2. Calculate derived metrics
3. Compare pairs, parameters, confidence levels
4. Make Phase 4 go/no-go decision

---

## Additional Metrics Worth Tracking (Optional)

- **Sharpe Ratio:** Risk-adjusted returns (higher = better)
- **Sortino Ratio:** Like Sharpe but only penalizes downside (more relevant for trading)
- **Calmar Ratio:** Return / Max drawdown (consistency measure)
- **Profit Factor:** Total wins / Total losses (>1.5 is healthy)
- **Exposure Time:** % of time in a position (vs sitting idle)

---

## Example: Analyzing the Results

**If we see:**
```
BTC: 3 trades, 1 win, 2 losses, -$8.42 total
XRP: 8 trades, 4 wins, 4 losses, +$49.38 total
```

**Conclusion:**
- XRP parameters (35/65, 80%/20%) work better than BTC (30/70, 70%/30%)
- Should we go live? "Not with 45% win rate + losses > wins. Need >50% + risk/reward >1:1"
- What's next? "Test XRP parameters more, consider aggressive position sizing, OR adjust risk/reward targets"

---

**This schema is production-ready. Update the orchestrator to log these events instead of every signal.**
