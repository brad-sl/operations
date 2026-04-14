# PHASE 3 Validation Checklist (Pre-Launch)

**Status:** Ready for Testing  
**Created:** 2026-03-24 19:30 PT

---

## Pre-Launch Validation (Use Before Starting Phase 3)

### 1. Configuration ✓
- [ ] `trading_config.json` loads without errors
  ```bash
  python3 -c "from config_loader import ConfigLoader; c = ConfigLoader.load('/home/brad/.openclaw/workspace/operations/crypto-bot/trading_config.json'); print('✅ Config valid')"
  ```
- [ ] X API key is valid and authorized
- [ ] Coinbase sandbox mode is ENFORCED (cannot access live)
- [ ] Spend limits are locked in code (see `phase3_orchestrator_v2.py` line 146)
- [ ] Position size caps are set per pair

### 2. Data Sources (Critical)
- [ ] Stochastic RSI calculation verified:
  - [ ] Get 14 candles from Coinbase API
  - [ ] Calculate RSI(14) manually and verify
  - [ ] Compare to expected RSI range (0-100)
  - [ ] Stochastic normalization works correctly
  
- [ ] X sentiment API returns valid scores:
  - [ ] X API key works (test with `xurl` or similar)
  - [ ] Sentiment scores are in range (-1.0 to +1.0)
  - [ ] Fetch returns valid JSON with score
  
- [ ] Price data is live:
  - [ ] Coinbase API returns current prices
  - [ ] Prices update every 1-5 minutes
  - [ ] No stale data in cache
  
- [ ] All timestamps are ISO 8601 UTC:
  - [ ] `datetime.now(timezone.utc).isoformat()` format
  - [ ] No local timezone mixing

### 3. Signal Generation (Logic Verification)

**BTC-USD (Baseline):**
```
Signal = 70% RSI (normalized 0-1) + 30% Sentiment (-1 to +1)

Example:
  - RSI = 35 → RSI_norm = 0.35
  - Sentiment = +0.2
  - Combined = (0.35 * 0.70) + (0.2 * 0.30) = 0.245 + 0.06 = 0.305
  - Signal = HOLD (not >0.6)

Test cases:
  - [ ] RSI=80, Sentiment=0.5 → BUY (should be >0.6)
  - [ ] RSI=20, Sentiment=-0.5 → SELL (should be <-0.6)
  - [ ] RSI=50, Sentiment=0 → HOLD (should be ~0.35)
```

**XRP-USD (Optimized):**
```
Signal = 80% RSI + 20% Sentiment

Test cases:
  - [ ] RSI=70, Sentiment=0.5 → BUY (0.56 + 0.1 = 0.66 > 0.6 ✓)
  - [ ] RSI=30, Sentiment=-0.5 → SELL (0.24 - 0.1 = 0.14 NOT <-0.6, so HOLD)
  - [ ] RSI=35 (threshold), Sentiment=0.5 → BUY or HOLD? (test boundary)
```

Validation:
- [ ] Signal logic matches spec (70/30 and 80/20)
- [ ] Confidence scores are correct (abs(combined_score))
- [ ] Threshold logic: BUY (>0.6), SELL (<-0.6), HOLD (else)
- [ ] Edge cases tested (threshold boundaries)

### 4. Execution Profile

- [ ] Cycle time < 30 seconds
  - [ ] Fetch RSI: ~5s (Coinbase API call)
  - [ ] Fetch sentiment: ~3s (X API call)
  - [ ] Generate signal: <1s (calculation)
  - [ ] Log result: <1s (file write)
  - [ ] Total: ~10s per pair, 20s parallel ✓

- [ ] Parallel execution working:
  - [ ] BTC-USD and XRP-USD run concurrently (ThreadPoolExecutor)
  - [ ] No serialization (blocking waits)
  - [ ] Both complete before next 5-minute interval

- [ ] Sleep logic correct:
  - [ ] Cycle takes 20s → sleep 280s until next 5-min mark
  - [ ] Cycle takes >300s → no sleep, move to next cycle
  - [ ] Timestamps reflect actual execution (not artificial delays)

### 5. Sandbox Mode (Safety Critical)

- [ ] Coinbase sandbox API is active:
  - [ ] All orders go to sandbox, not live account
  - [ ] Spend limits enforced (code check: line 146 `assert self.config.sandbox_mode`)
  - [ ] No real money at risk
  - [ ] Can't accidentally trigger real trades

Test:
```bash
python3 -c "
from phase3_orchestrator_v2 import Phase3Orchestrator
o = Phase3Orchestrator('/home/brad/.openclaw/workspace/operations/crypto-bot/trading_config.json')
print(f'Sandbox mode: {o.config.sandbox_mode}')
assert o.config.sandbox_mode, 'FAIL: Sandbox not enforced!'
print('✅ Sandbox enforced')
"
```

### 6. Checkpointing

- [ ] STATE.json written every cycle:
  - [ ] File created if not exists
  - [ ] Cycle count increments
  - [ ] Timestamp updated
  - [ ] BTC + XRP results logged

- [ ] MANIFEST.json tracks outputs:
  - [ ] Lists all files generated so far
  - [ ] Updates each cycle
  - [ ] Survives process restart

- [ ] RECOVERY.md is human-readable:
  - [ ] Contains instructions to restart from checkpoint
  - [ ] Lists last successful cycle
  - [ ] Shows resumption command

Test restart:
```bash
# Kill process mid-execution
pkill -f "phase3_orchestrator_v2"

# Check checkpoint files exist
ls -la /home/brad/.openclaw/workspace/operations/crypto-bot/phase3_output/

# Verify RECOVERY.md
cat /home/brad/.openclaw/workspace/operations/crypto-bot/phase3_output/RECOVERY.md

# Restart from checkpoint
# (TBD: implement resumption logic)
```

### 7. Order Logging

- [ ] XRP_ORDER_LOG.json appends correctly:
  - [ ] New orders added to `orders` array
  - [ ] Not overwriting existing data
  - [ ] Valid JSON structure after each append
  - [ ] Timestamp format: ISO 8601 UTC

- [ ] BTC_ORDER_LOG.json appends correctly:
  - [ ] Same validation as XRP

Example valid entry:
```json
{
  "timestamp": "2026-03-25T23:48:13.364234+00:00",
  "product_id": "BTC-USD",
  "signal_type": "BUY",
  "confidence": 0.75,
  "price_at_signal": 68500.50,
  "rsi": 75.2,
  "sentiment": 0.5,
  "status": "SUCCESS"
}
```

Validation:
- [ ] All required fields present
- [ ] Numeric fields are valid numbers (not strings)
- [ ] Timestamps parse as datetime
- [ ] 576 total entries after 48h (288 per pair)

### 8. Performance & Stability

- [ ] Memory usage stable over time:
  - [ ] Start: ~150-200 MB
  - [ ] After 10 cycles: ~200-250 MB (same)
  - [ ] No memory leaks (check with `ps` or `top`)

- [ ] No API rate limit errors:
  - [ ] X API: Rate limits are 300 req/15min (45/cycle is OK)
  - [ ] Coinbase: Rate limits are 10 req/sec (2 req/cycle is OK)
  - [ ] Monitor logs for 429 errors

- [ ] Graceful error handling:
  - [ ] If X API fails → sentiment defaults to 0.0, continue
  - [ ] If Coinbase fails → log error, retry next cycle
  - [ ] Process doesn't crash on single API failure

### 9. Output Validation

After 48-hour run, verify:

- [ ] XRP_ORDER_LOG.json
  - [ ] 288 entries (1 per 5-min cycle)
  - [ ] All timestamps are sequential (ascending)
  - [ ] Signal distribution: ~50% BUY, ~20% SELL, ~30% HOLD
  - [ ] Confidence average: 0.60-0.65

- [ ] BTC_ORDER_LOG.json
  - [ ] 288 entries (1 per 5-min cycle)
  - [ ] Same validation as XRP

- [ ] PHASE_3_RESULTS.json
  - [ ] Contains summary stats
  - [ ] Comparison between BTC and XRP
  - [ ] Recommendation: "ready_for_phase_4": true/false

---

## Quick Test: 2-Hour Dry Run

Before committing to 48-hour execution, run a 2-hour test:

```bash
# Create test config (same as main but 2-hour duration)
cp trading_config.json trading_config_test.json
# Edit trading_config_test.json to set end_time = now + 2 hours

# Run test
python3 phase3_orchestrator_v2.py --config trading_config_test.json

# Verify:
# - No crashes
# - Checkpoint files created
# - Order logs have ~24 entries (2h @ 5min intervals = 24 cycles)
# - Signal distribution reasonable
```

---

## Sign-Off (Before Launch)

**System Ready for 48-Hour Execution?**
- [ ] All 9 sections validated ✓
- [ ] 2-hour test passed ✓
- [ ] Brad approval obtained ✓

**Approval:**
- [ ] Brad: ______________________  Date: __________
- [ ] Approved for launch ✓

---

## Execution Start

When ready, run:
```bash
cd /home/brad/.openclaw/workspace/operations/crypto-bot
python3 phase3_orchestrator_v2.py
```

This will:
1. Load real config
2. Verify sandbox mode
3. Start 48-hour loop
4. Execute every 5 minutes
5. Log all results
6. Create checkpoint files
7. Finalize after 48h
