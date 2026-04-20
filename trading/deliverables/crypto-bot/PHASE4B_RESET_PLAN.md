# Phase 4B Reset & Fix — 2026-03-30 12:12 PDT

## What Was Wrong

Phase 4B v1 had three fatal flaws making the results unrealistic:

1. **Instant trades (microsecond entry→exit):** Trades were entering and exiting in microseconds with identical/simulated prices
   - Entry time: `2026-03-30T02:31:28.670850+00:00`
   - Exit time:  `2026-03-30T02:31:28.670869+00:00` (19 microseconds later)
   - Result: $3,200 "profit" on simulated $5K position

2. **Simulated prices instead of real Coinbase data:**
   ```python
   # WRONG: hardcoded prices
   current_price = 50000 if pair == 'BTC-USD' else 2.50
   exit_price = entry_price * (1 + exit_threshold)  # assumes instant favorable move
   ```

3. **Duplicate trades per signal:** 3 trades logged per entry ('fixed_signal', 'fee_aware_signal', 'pair_specific_signal')
   - All with identical P&L, timestamps within milliseconds of each other

## Status

- **Process killed:** ✅ Phase 4B halted
- **Database reset:** ✅ Deleted phase4_trades.db
- **Logs cleared:** ✅ Deleted phase4b_48h_run.log
- **Code ready for fix:** Phase 4B v1 identified 3 core issues

## What Needs Fixing (Priority Order)

### 1. **Replace Simulated Prices with Real Coinbase API Calls**
   - Current: `current_price = 50000 if pair == 'BTC-USD' else 2.50`
   - Fix: Call `coinbase_wrapper.get_current_price(pair)` every cycle
   - Verify: Real prices from Coinbase Advanced Trade API

### 2. **Implement Realistic Trade Hold Times**
   - Current: Entry → Exit in same cycle (5 minutes)
   - Fix: Keep positions open for minimum N cycles (e.g., 5-10 cycles = 25-50 minutes)
   - Implement position tracking: `{pair: {open_price, entry_time, entry_rsi, sentiment}}`
   - Exit only if: (current_price - open_price) / open_price >= exit_threshold AND hold_time >= MIN_HOLD

### 3. **Remove Duplicate Trade Logging**
   - Current: 3 identical trades logged per signal type
   - Fix: One trade per entry signal, period. Remove the loop over signal types.

### 4. **Validate Exit Logic**
   - Current: `exit_price = entry_price * (1 + exit_threshold)` (assumes moves always favorable)
   - Fix: Compare real price against entry price; exit when threshold is HIT (up or down)
   - Implement stop loss: Exit if `(current_price - open_price) / open_price <= -STOP_LOSS_PCT` (e.g., -2%)

## Implementation Plan

**File:** `/home/brad/.openclaw/workspace/operations/crypto-bot/phase4b_v1.py`

### Change 1: Import Coinbase wrapper
```python
from coinbase_wrapper import CoinbaseWrapper  # Add this

def __init__(self, ...):
    self.cb = CoinbaseWrapper()  # Add this
```

### Change 2: Fetch real prices (in `run_cycle`)
```python
# OLD:
current_price = 50000 if pair == 'BTC-USD' else 2.50

# NEW:
try:
    current_price = self.cb.get_current_price(pair)
except Exception as e:
    logger.warning(f"Failed to fetch {pair} price: {e}, using last known")
    current_price = self.last_price.get(pair, 50000)  # fallback
```

### Change 3: Track open positions (new member var)
```python
def __init__(self, ...):
    self.open_positions = {}  # {pair: {price, time, rsi, sentiment, ...}}
    self.min_hold_cycles = 5  # Hold position for at least 25 minutes
```

### Change 4: Entry signal → position open (not instant exit)
```python
if entry_approved:
    # OPEN position, don't close it immediately
    self.open_positions[pair] = {
        'entry_price': current_price,
        'entry_cycle': self.cycle_count,
        'entry_rsi': rsi_value,
        'sentiment': sentiment_score,
    }
    logger.info(f"📈 POSITION OPENED: {pair} @ ${current_price:.2f}")
```

### Change 5: Exit check (new logic)
```python
for pair in open_positions:
    pos = self.open_positions[pair]
    hold_cycles = self.cycle_count - pos['entry_cycle']
    
    if hold_cycles < self.min_hold_cycles:
        continue  # Skip exit check, position too young
    
    current_price = self.cb.get_current_price(pair)
    pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
    exit_threshold = self._get_exit_threshold(pair)
    stop_loss = -0.02  # -2%
    
    # Exit if: profit target hit OR stop loss hit
    if pnl_pct >= exit_threshold or pnl_pct <= stop_loss:
        self._log_trade(pair, pos['entry_price'], current_price, ...)
        del self.open_positions[pair]
        logger.info(f"📉 POSITION CLOSED: {pair} P&L={pnl_pct:+.2%}")
```

### Change 6: Remove signal type loop
```python
# OLD: for signal_type in ['fixed_signal', 'fee_aware_signal', 'pair_specific_signal']:
#         ... log trade

# NEW: Log ONE trade per entry signal, no loop
```

## Testing Before Relaunch

```bash
# 1. Quick validation (5 cycles = 25 minutes):
python3 phase4b_v1.py --validate

# 2. Spot-check:
#    - Verify trade hold times >= 25 minutes
#    - Verify prices are from real Coinbase API
#    - Verify only 1 trade logged per entry

# 3. If all pass, launch 48h:
python3 phase4b_v1.py --run-48h
```

## Timeline

- **Now (12:12 PDT):** Reset complete
- **Next (12:15-12:30):** Implement fixes (Change 1-6 above)
- **12:30-12:45:** Test with --validate (5 cycles)
- **12:45 (if pass):** Launch --run-48h, completion ~12:45 PDT 2026-03-31

## Expected Results (After Fix)

- **Real Coinbase prices:** ✅ Each trade uses actual market data
- **Realistic hold times:** ✅ Positions held 25+ minutes, not microseconds
- **No duplicates:** ✅ 1 trade per signal, not 3
- **Realistic P&L:** ✅ $5-50 per trade, not $3,000+
- **Win rate:** ~50% (target from Phase 4) not 99%+ (artifact of instant exits)

---

**Status:** 🔴 HALTED FOR REPAIRS
**Next step:** Implement fixes and test

