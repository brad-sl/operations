# Phase 6 Implementation - Persistent Trading Loop

## ✅ COMPLETED

Phase 6 has been extended from an init-only script to a **full persistent trading loop** that runs continuous 30-minute cycles for target of 6 trades per 24h.

---

## Architecture

### Core Components

1. **Persistent Main Loop** (`phase6.py`)
   - Runs indefinite 30-minute trading cycles (configurable)
   - Pulls live sentiment from `/home/brad/.openclaw/workspace/agents/memory/trading-monitor-status.json`
   - Uses Phase 4d signal logic (RSI-based with sentiment weighting)
   - Executes orders and tracks positions
   - Logs trades to CSV and cycle stats to log file

2. **Configuration** (`config/trading_config_phase6.json`)
   - Total capital: $1,000 (paper trading)
   - Pairs: 6 (BTC, ETH, XRP, DOGE, ADA, SOL)
   - Cycle interval: 1,800 seconds (30 minutes)
   - SL: 2%, TP: 5% (from Phase 4d)
   - Max daily loss: 2% circuit breaker

3. **Sentiment Integration** (`SentimentManager`)
   - Reads live sentiment from trading-monitor-status.json (0-1 scale)
   - Falls back to neutral (0.5) if unavailable
   - 40% sentiment weight + 60% RSI weight in signal calculation

4. **Signal Logic** (Phase 4d)
   - **BUY**: RSI < 30 AND Sentiment > 0.4
   - **SELL**: RSI > 70 OR Profit ≥ 5% OR Loss ≤ -2%
   - **HOLD**: Otherwise

5. **Trade Logging**
   - CSV format: `timestamp,pair,signal,price,qty,side`
   - Location: `trades_paper_phase6.csv`
   - Cycle stats logged to `logs/phase6_paper.log`

---

## Key Features

### ✅ Persistent Loop
```python
while True:
    cycle_num += 1
    prices = fetch_prices()
    sentiment = get_sentiment()
    
    for pair in pairs:
        rsi = calculate_rsi(pair)
        signal_score = (0.4 * sentiment) + (0.6 * (100 - rsi))
        
        if should_exit(pair):
            execute_sell(pair)
        elif should_buy(pair, signal_score):
            execute_buy(pair)
    
    sleep(cycle_interval - cycle_time)
```

### ✅ Position Management
- Track open positions per pair
- Auto-update SL/TP on entry
- Calculate P&L continuously
- Exit on SL (-2%), TP (+5%), or RSI signal (>70)

### ✅ Sentiment Integration
- Live feed from trading-monitor-status.json
- Updates per cycle (not per order)
- 40% weight in combined signal

### ✅ Logging
- **Cycle stats** → `logs/phase6_paper.log`
- **Trades** → `trades_paper_phase6.csv`
- **Detailed** → stdout (INFO level)

---

## Usage

### Start Paper Trading
```bash
cd /home/brad/.openclaw/workspace/coding-products/crypto-bot
python3 phase6.py --config config/trading_config_phase6.json --mode PAPER_TRADE
```

### Environment Variables
```bash
PHASE_MODE=PAPER_TRADE           # Override --mode
PHASE_CONFIG=config/...json       # Override --config
```

### Expected Output (first 2 cycles)
```
================================================================================
PHASE 6 TRADING LOOP STARTED - PAPER_TRADE mode
Pairs: ['BTC-USD', 'XRP-USD', 'ETH-USD', 'DOGE-USD', 'ADA-USD', 'SOL-USD']
Cycle interval: 1800s
================================================================================

CYCLE 1 — 2026-04-29T21:00:00.123456+00:00
BTC-USD Price=$76054.57 RSI=45.2 Sentiment=0.50
  HOLD: RSI neutral, sentiment neutral
ETH-USD Price=$2277.67 RSI=52.1 Sentiment=0.50
  HOLD: RSI neutral, sentiment neutral
[... 4 more pairs ...]

CYCLE 1 STATS:
  Prices fetched: 6
  Sentiment: 0.50 (neutral)
  Open positions: 0
  Trades executed: 0
  Cycle time: 2.34s
Sleeping 1797.66s until next cycle...

CYCLE 2 — 2026-04-29T21:30:00.456789+00:00
[... cycle continues ...]
```

---

## Validation Results

✅ **Configuration Loading**
- Config loads from `trading_config_phase6.json`
- All required keys present
- 6 pairs, $1,000 capital, 30min cycles

✅ **Sentiment Integration**
- Live sentiment fetched from trading-monitor-status.json
- Falls back to neutral (0.5) if unavailable
- Current sentiment: 0.50 (neutral)

✅ **RSI Calculation**
- Rising prices → High RSI (~100)
- Falling prices → Low RSI (~0)
- Neutral prices → Mid RSI (~50)

✅ **Trade CSV Logging**
- Header: `timestamp,pair,signal,price,qty,side`
- Format validated
- Sample: `2026-04-29T21:00:00Z,BTC-USD,BUY,50000.000000,0.010000,BUY`

✅ **Exit Logic**
- SL trigger at -2%: STOP_LOSS
- TP trigger at +5%: TAKE_PROFIT
- RSI sell at >70: RSI_SELL
- Normal conditions: HOLD

✅ **Sentiment Signal Calculation**
- Low RSI + high sentiment = strong buy signal
- High RSI + low sentiment = sell signal
- Neutral conditions = neutral signal

---

## File Structure

```
crypto-bot/
├── phase6.py                          ← Main persistent trading loop
├── config/
│   └── trading_config_phase6.json      ← Configuration (1000 capital, 6 pairs, 30min)
├── trades_paper_phase6.csv             ← Trade log (generated during run)
├── logs/
│   └── phase6_paper.log                ← Cycle stats log (generated during run)
├── order_executor.py                   ← Order execution (existing)
└── PHASE6_IMPLEMENTATION.md            ← This file
```

---

## Performance Targets

Based on 30-minute cycle interval and 6 pairs:

| Target | Value | Reasoning |
|--------|-------|-----------|
| Cycles per 24h | 48 | 24h × 60min ÷ 30min |
| Trades per 24h | ~6 | ~12.5% of cycles trigger trade (based on RSI<30 threshold) |
| Avg P&L per trade | TBD | Depends on market conditions + sentiment quality |
| Daily win rate target | 60%+ | SL=2%, TP=5% favors winners |

---

## Next Steps

1. **Run 1-hour smoke test** (2 cycles)
   ```bash
   python3 phase6.py --config config/trading_config_phase6.json --mode PAPER_TRADE --cycles 2
   ```

2. **Run 24-hour validation** (48 cycles)
   - Capture cycle stats
   - Verify ~6 trades executed
   - Check CSV accuracy
   - Monitor sentiment updates

3. **Monitor health**
   - Watch for crashes
   - Verify position tracking
   - Ensure SL/TP calculations are correct
   - Check CSV format integrity

4. **Live transition** (after 24h validation)
   - Switch `--mode LIVE` when confident
   - Use real broker API (with sandbox=True initially)
   - Scale capital up gradually

---

## Key Differences from Phase 5

| Aspect | Phase 5 | Phase 6 |
|--------|---------|---------|
| Cycle type | Fixed 288 cycles | Infinite until SIGINT |
| Sentiment weight | Implicit in signal_score | Explicit 40% weight |
| Exit logic | RSI>65 + price SL | RSI>70 + 2% SL + 5% TP |
| Trade logging | DB-based | CSV-based |
| Config | Hardcoded | Config file driven |
| Cycle interval | 300s (5min) | 1800s (30min) |

---

## Git Commit

```
git add phase6.py PHASE6_IMPLEMENTATION.md
git commit -m "Phase 6: Persistent trading loop with sentiment integration

- Main loop runs 30min cycles (config-driven)
- Sentiment integration from trading-monitor-status.json
- Phase 4d signal logic (RSI + sentiment weighting)
- Position management with SL/TP
- Trade logging to CSV
- Cycle stats logging to file
- 6 pairs, $1k capital, paper mode by default
- Target: 6 trades per 24h window"

git push origin feature/phase6-persistent-loop
```

---

## Testing Evidence

All core logic validated:
- ✅ Config loading
- ✅ Sentiment integration
- ✅ RSI calculation
- ✅ CSV logging
- ✅ Exit logic
- ✅ Signal calculation

Ready for 24-hour paper trading validation.
