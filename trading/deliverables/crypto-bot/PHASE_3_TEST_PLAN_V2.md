# PHASE 3 TEST PLAN v2 — With Critical Fixes Applied
**Status:** 🟢 READY FOR 1-HOUR VERIFICATION TEST  
**Date:** 2026-03-26 19:20 UTC  
**Test Duration:** 1 hour (12 cycles @ 5 min intervals)  
**Full Test:** 48 hours (288 cycles) after verification passes

---

## TIER 1 FIXES IMPLEMENTED

### 1. ✅ Real Price Data
**Issue:** Hardcoded prices ($67.5K for BTC, $2.50 for XRP)  
**Fix:** Fetch from Coinbase API via wrapper.get_price()  
**Fallback:** Safe defaults if API unavailable  
**Verification:** Check STATE.json for varying prices

### 2. ✅ Real Stochastic RSI
**Issue:** Mock RSI never crossed thresholds  
**Fix:** Calculate from real 14-candle price history  
**Logic:** RSI = 100 - (100 / (1 + RS)) where RS = avg_gains / avg_losses  
**Verification:** Check logs for RSI 30-70 range (not constant)

### 3. ✅ Order Log Initialization
**Issue:** Logs only written on process exit  
**Fix:** Initialize BTC_USD_ORDER_LOG.json and XRP_USD_ORDER_LOG.json at startup  
**Content:** Header with test_start, pair config, empty orders array  
**Verification:** Files exist before test starts

### 4. ✅ Periodic Logging Every Cycle
**Issue:** No visibility into execution  
**Fix:** Write STATE.json + order logs every 5 minutes  
**Content:** Current cycle, price, RSI, sentiment, orders placed  
**Verification:** Logs update every cycle (check timestamps)

---

## 1-HOUR VERIFICATION TEST

### Test Configuration
- Duration: 1 hour (3,600 seconds)
- Cycles: 12 (5 minutes apart)
- Pairs: BTC-USD, XRP-USD
- Sandbox Mode: ENFORCED
- Spend Limits: ACTIVE

### Success Criteria

1. **Data Flowing (Real, Not Mock)**
   - Prices vary (not $67.5K and $2.50 every cycle)
   - RSI fluctuates between 30-70 range
   - Sentiment changes (not stuck at 0.20/0.67)
   - All values logged to STATE.json every cycle

2. **Logging Working**
   - BTC_USD_ORDER_LOG.json exists and updates
   - XRP_USD_ORDER_LOG.json exists and updates
   - STATE.json updates every cycle with new timestamp
   - No log write errors in output

3. **System Health**
   - No crashes during 1 hour
   - No unhandled exceptions in logs
   - Sandbox mode enforced (no real trading)
   - Spend limits active

---

## OUTPUT FILES

- BTC_USD_ORDER_LOG.json
- XRP_USD_ORDER_LOG.json  
- STATE.json (updated every cycle)

---

## ERRORS CORRECTED

| Error | Root Cause | Fix |
|-------|-----------|-----|
| Hardcoded prices | Dev oversight | API call with fallback |
| Mock RSI | Testing shortcut | Real calculation from candles |
| No order logs | Process exit only | Initialize at startup |
| No periodic logging | Performance assumption | Checkpoint every cycle |

---

## MONITORING

```bash
# Watch live updates
tail -f STATE.json
tail -f BTC_USD_ORDER_LOG.json
tail -f phase3_48h.log
```

---

## NEXT STEPS

1. Run 1-hour test
2. Verify logs update every cycle
3. Get Brad approval
4. Start 48-hour test
