# RSI Warm-Start Bootstrap System

## Problem

Phase 5 bot needs ~15 cycles (~75 minutes) to accumulate enough price history for RSI(14) calculation. During this warm-up period, **no trade signals can fire**, even if market conditions are ideal.

**Impact**: 
- 24h Phase 5 test wastes first 75 min with no signal opportunities
- Faster validation → earlier approval for Phase 6
- Restarts mean another 75-min warm-up delay

## Solution

**Pre-seed RSI history** from 60 days of historical data. Signals fire immediately on cycle 1.

## Quick Start

### 1. Generate Bootstrap (First Time Only)

```bash
cd operations/crypto-bot

# Generate price history + RSI for all 6 pairs
python3 bootstrap_rsi_history.py

# ✅ Creates: price_history_bootstrap.json (with 14-price buffers + RSI values)
```

### 2. Start Bot (Uses Bootstrap Automatically)

```bash
# Bot loads bootstrap on startup and fires signals from cycle 1
python3 phase5_multi_pair.py --cycles 288
```

### 3. Check Bootstrap Status

The logs will show:

```
✅ Loaded bootstrap RSI history for BTC-USD (14 prices)
✅ Loaded bootstrap RSI history for XRP-USD (14 prices)
...
🚀 Warm-started 6/6 pairs. RSI signals ready on cycle 1.
```

## Docker Workflow

### Generate Bootstrap in Docker

```bash
# Build image
docker build -t crypto-bot:latest .

# Generate bootstrap (one-time or periodic refresh)
docker run -it --rm \
  -v $(pwd):/app \
  -e COINBASE_API_KEY=$COINBASE_API_KEY \
  crypto-bot:latest \
  python3 bootstrap_rsi_history.py

# Creates: ./price_history_bootstrap.json
```

### Run Bot with Bootstrap

```bash
# Bot uses bootstrap automatically
docker compose up --build

# Or if bootstrap exists:
docker run -d \
  -v $(pwd):/app \
  -e SANDBOX_MODE=True \
  crypto-bot:latest \
  python3 phase5_multi_pair.py --cycles 288
```

## What Bootstrap Does

### File Generated: `price_history_bootstrap.json`

```json
{
  "BTC-USD": {
    "prices": [67500, 67600, 67650, ..., 72000],  // 14 most recent prices
    "rsi": 62.5,                                    // Pre-calculated RSI(14)
    "fetched_at": "2026-04-18T22:04:35Z",          // When generated
    "data_points": 60,                              // Days of history used
    "pair": "BTC-USD"
  },
  "XRP-USD": { ... },
  ... 6 pairs total
}
```

### Phase5 Bot Integration

1. **On startup**: Checks for `price_history_bootstrap.json`
2. **If found**: Loads last 14 prices per pair → initializes `self.price_history`
3. **First cycle**: RSI calculated on pre-loaded buffer
4. **Signal fired**: If RSI + sentiment align (no waiting)

### Without Bootstrap

```
Cycle 1:   price_history[BTC-USD] = [67500]        → RSI pending
Cycle 2:   price_history[BTC-USD] = [67500, 67600] → RSI pending
...
Cycle 15:  price_history[BTC-USD] = [...14 prices] → RSI ready ✅
Cycle 16:  First signal possible
```

### With Bootstrap

```
Startup:   price_history[BTC-USD] = [67450, 67500, ..., 72000] (14 prices)
Cycle 1:   RSI calculated on buffer → Signal ready ✅
```

**Time saved**: 14 cycles × 5 min = 70 minutes 🚀

## Regenerate Bootstrap

Bootstrap uses 60 days of historical data (CoinGecko free API). Regenerate anytime:

```bash
python3 bootstrap_rsi_history.py
```

Typical refresh times:
- **Local**: ~2-3 seconds (6 pairs × API calls, sequential)
- **Docker**: ~5 seconds (network latency)

### Recommended Schedule

- **Weekly**: Refresh bootstrap (keeps price history recent)
- **Monthly**: Full regenerate (historical accuracy)
- **Pre-deployment**: Always regenerate before Phase 5 test

## Troubleshooting

### Bootstrap File Missing

```
ℹ️  No bootstrap file found. RSI will warm up over 15 cycles.
```

**Fix**: Generate bootstrap before starting bot
```bash
python3 bootstrap_rsi_history.py
```

### Bootstrap Load Failed

```
WARNING: Failed to load bootstrap: ...
```

**Possible causes**:
1. Corrupted JSON → delete & regenerate
2. Wrong file path → check current directory
3. Missing pairs → regenerate with current config

**Fix**:
```bash
rm price_history_bootstrap.json
python3 bootstrap_rsi_history.py
```

### CoinGecko API Rate Limited

```
ERROR: CoinGecko API error: 429 Too Many Requests
```

**Fix**: Wait 1 min, then retry (free tier limit: ~10-50 calls/min)
```bash
sleep 60 && python3 bootstrap_rsi_history.py
```

## Performance Impact

### Storage

- **Bootstrap file**: ~2KB (6 pairs × JSON)
- **Memory**: +0.1MB (loaded into `self.price_history` dict)

### Startup Time

- **Without bootstrap**: Cycle 1 starts immediately
- **With bootstrap**: Cycle 1 starts immediately (no delay)

### Load Time

- File load: <1ms
- No performance penalty

## Implementation Details

### RSI Calculation

Standard RSI(14) formula:
```
RS = avg_gain(14) / avg_loss(14)
RSI = 100 - (100 / (1 + RS))
```

- Uses 60 days of daily close prices
- Calculates average gain/loss over 14-day window
- Extracts last 14 prices for live updates

### Data Source

**CoinGecko API** (free, no auth):
- Historical daily OHLCV data
- Covers all 6 pairs
- 60-day lookback (market context)

## Next Steps

1. **Generate bootstrap**: `python3 bootstrap_rsi_history.py`
2. **Start bot**: `python3 phase5_multi_pair.py --cycles 288`
3. **Monitor logs**: Watch for "🚀 Warm-started" message
4. **Validate**: First cycle should show RSI values (not "pending")

## Advanced

### Custom Bootstrap Path

```python
# In phase5_multi_pair.py, modify _load_bootstrap_rsi_history():
bootstrap_file = os.getenv('BOOTSTRAP_PATH', 'price_history_bootstrap.json')
```

### Skip Bootstrap (Force Cold Start)

```bash
rm price_history_bootstrap.json
python3 phase5_multi_pair.py --cycles 288
```

### Inspect Bootstrap

```bash
cat price_history_bootstrap.json | python3 -m json.tool
# Or:
jq '.["BTC-USD"]' price_history_bootstrap.json
```
