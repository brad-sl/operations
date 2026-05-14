# Dynamic RSI Visual Guide

This guide contains visual representations of the dynamic RSI strategy. See embedded charts below.

---

## Chart 1: Downtrend Scenario (40/60 Thresholds)

When market drops more than 2% in 24 hours → DOWNTREND detected.

```
Price: 📉 Falling (e.g., $67,500 → $64,000)

RSI Zone:      20 ─┬─────────────────────────── OVERSOLD
                  │    ↗ Buy at 40
                  │       
              40 ─┼─────────────────── BUY THRESHOLD (moved from 30)
                  │
              50 ─┼─────────────────── NEUTRAL
                  │
              60 ─┼─────────────────── SELL THRESHOLD (moved from 70)
                  │       
                  │    ↘ Sell at 60
                  │       
             80 ─┴─────────────────────────── OVERBOUGHT

Thresholds: 40/60 (instead of 30/70)
Position: 75% size
```

**Why?** In a downtrend, price keeps falling. Waiting for RSI 30 is too patient — you miss the bounce. Moving to 40 catches the rebound earlier.

---

## Chart 2: Uptrend Scenario (20/80 Thresholds)

When market rises more than 2% in 24 hours → UPTREND detected.

```
Price: 📈 Rising (e.g., $67,500 → $71,000)

RSI Zone:      20 ─┬─────────────────────────── BUY AT 20 (aggressive)
                  │    ↗ Early entry
                  │
              40 ─┼──────────────────────────── NEUTRAL
                  │
              60 ─┼────────────────────────────
                  │
              80 ─┼──────────────────────────── SELL AT 80 (let it run)
                  │       
                  │    ↘ Exit when momentum fades
                  │       
            100 ─┴─────────────────────────────

Thresholds: 20/80 (instead of 30/70)
Position: 125% size
```

**Why?** In an uptrend, RSI stays high (60-90). Waiting for 70 is too conservative — you sell too early. Moving to 80 lets winners run.

---

## Chart 3: Sideways Scenario (30/70 Thresholds)

When price moves less than 2% in 24 hours → SIDEWAYS detected.

```
Price: ➡️ Flat (e.g., $67,000 → $67,500)

RSI Zone:      30 ─┬─────────────────────────── BUY AT 30
                  │    ↗ 
                  │
              50 ─┼──────────────────────────── NEUTRAL
                  │       
                  │    ↘
              70 ─┴───────────────────────────── SELL AT 70

Thresholds: 30/70 (standard)
Position: 100% size
```

**Why?** In a range-bound market, price oscillates. Standard 30/70 thresholds work perfectly.

---

## Decision Tree

```
Start
  │
  ▼
24h Price Change?
  │
  ├─ < -2% ──────▶ DOWNTREND ──▶ Thresholds: 40/60, Size: 75%
  │
  ├─ -2% to +2% ─▶ SIDEWAYS ───▶ Thresholds: 30/70, Size: 100%
  │
  └─ > +2% ──────▶ UPTREND ────▶ Thresholds: 20/80, Size: 125%
  │
  ▼
Check Sentiment (60% weight)
  │
  ▼
Check RSI (40% weight)
  │
  ▼
Calculate Weighted Signal
  │
  ▼
Signal < Buy Threshold? ──▶ BUY
Signal > Sell Threshold? ──▶ SELL
Otherwise ──────────────────▶ HOLD
```

---

## ATR/Position Sizing Chart

| ATR (% of price) | Volatility | Position Size | Color on Chart |
|------------------|------------|---------------|----------------|
| > 5% | Very High | 50% | 🔴 Red Zone |
| 3-5% | Moderate | 75% | 🟡 Yellow Zone |
| < 3% | Low | 100% | 🟢 Green Zone |

**Example:** 
- BTC at $67,500 with ATR $2,025 (3%) → Position: 75%
- BTC at $67,500 with ATR $5,400 (8%) → Position: 50%

---

## Comparison: Static vs Dynamic

| Metric | Static (30/70) | Dynamic | Improvement |
|--------|----------------|---------|-------------|
| Win Rate | 45% | 58% | +13 pts |
| Total P&L | $217 | $486 | +124% |
| Sharpe | 0.61 | 1.04 | +70% |
| Max Drawdown | -45% | -32% | -34% |

---

## Key Takeaways

1. **Dynamic thresholds = more trades in trending markets**
2. **Sentiment adds 25% to P&L** (60% weight in signal)
3. **Reduce position in high volatility** (ATR > 5% = half size)
4. **Check regime every 6 hours** (not per cycle — avoids whipsaw)

---

*See also: DYNAMIC_RSI_STRATEGY.md (technical), DYNAMIC_RSI_FOR_TRADERS.md (beginner), DYNAMIC_VS_STATIC_BACKTEST.json (data)*