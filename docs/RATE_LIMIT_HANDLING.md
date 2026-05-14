# Rate Limit Handling (429 Errors)

**Last Updated:** 2026-04-22 14:31 PT  
**Status:** FIXED (commit bfe6b775)  
**Issue:** https://github.com/brad-sl/operations/issues/rate-limit-cascade

## Problem

### Root Cause
- **7 Phase 5 processes** all call `_fetch_all_pairs_batch()` simultaneously
- Each process batches 6 pairs into 1 API call
- **Result:** 7 batch calls in rapid succession → Coinbase 429 (Too Many Requests)

### Cascade Effect
When batch gets 429:
1. Old code falls back to **individual pair fetches**
2. Individual calls (1 pair each) trigger immediate 429
3. 7 × 6 = 42 failed requests in seconds
4. System thrashes, trading stops

**Evidence:** 2026-04-22 14:25:44 logs show cascade:
```
ERROR: Batch 1 failed: 429 Client Error
WARNING: Individual fetch BTC-USD: 429 Client Error
WARNING: Individual fetch XRP-USD: 429 Client Error
... (10+ repetitions)
```

---

## Solution

### Deployed (Commit: bfe6b775)

**File:** `phase5_multi_pair.py` - `_fetch_all_pairs_batch()` method

```python
except Exception as e:
    if '429' in str(e):
        # Rate limited: exponential backoff with jitter
        wait_time = (2 ** (chunk_idx % 3)) + uniform(0, 1)
        self.logger.warning(f"⏸️  Batch {chunk_idx} rate limited (429), retry in {wait_time:.1f}s")
        time.sleep(wait_time)
        # Retry ONCE, then move on (don't fallback to individual)
        try:
            response = self.cb_client.client.get_products(product_ids=chunk)
            # ... handle response ...
        except Exception as retry_e:
            self.logger.error(f"Batch {chunk_idx} retry failed: {retry_e}")
    else:
        # Non-429 error: skip chunk (don't fallback)
        self.logger.error(f"Batch {chunk_idx} failed: {e}")
```

### What It Does

1. **Detects 429:** Checks error message for "429"
2. **Exponential backoff:** `2^N + random(0,1)` seconds
   - Chunk 1 → 2-3s
   - Chunk 2 → 4-5s
   - Chunk 3 → 8-9s (resets)
3. **Single retry:** Waits, then retries batch ONCE
4. **No fallback:** Skips individual calls (avoids cascade)
5. **Logs clearly:** `⏸️  Batch N rate limited (429), retry in X.Xs`

### Why This Works

- **Respects Coinbase rate limits** (1-2 requests/sec per account)
- **Exponential backoff** gives API time to recover
- **Jitter** prevents thundering herd (all processes backing off at same time)
- **No fallback** prevents cascade effect

---

## Long-Term Solution

**Phase 5 Scalable** (see PHASE5_SCALABLE.md)
- **1 process** instead of 7
- **1 batch call** instead of 7 sequential calls
- **No rate limiting** (single, well-paced API call)
- **70× less memory** (12MB vs 840MB)

**Deployment:** After Phase 5.1 validation complete (expected Phase 7)

---

## Testing

### Verify Fix Is Active

```bash
# Check that import is present
grep "from random import uniform" phase5_multi_pair.py

# Check that backoff logic is present
grep "2 \*\* (chunk_idx" phase5_multi_pair.py

# Monitor logs for rate limit handling
tail -f logs/phase5_live.log | grep "429\|rate limited"
```

### Expected Behavior

**Before fix:**
```
ERROR: Batch 1 failed: 429 Client Error
WARNING: Individual fetch BTC-USD: 429 Client Error
WARNING: Individual fetch XRP-USD: 429 Client Error
WARNING: Individual fetch ETH-USD: 429 Client Error
... (cascade continues)
```

**After fix:**
```
WARNING: ⏸️  Batch 1 rate limited (429), retry in 2.3s
... (2.3s sleep) ...
✅ Batch 1/1: 6 pairs fetched | Cached: 6 prices
```

---

## Related Issues

- **GitHub Issue:** https://github.com/brad-sl/operations/issues/rate-limit-cascade
- **Commit:** `bfe6b775` (2026-04-22)
- **Files Modified:**
  - `phase5_multi_pair.py` (rate limit backoff)
  - `phase5_rate_limit_fix.py` (documentation + workarounds)

---

## Known Limitations

1. **Still 7 processes** = 7× the API load of scalable bot
   - Workaround: Use Phase5 Scalable (Phase 7)
   
2. **Coinbase free tier limits** to ~5 requests/second
   - Current: 7 batch calls = manageable (each ~50ms apart)
   - Worst case: 42 individual calls = immediate 429
   - Fix prevents worst case

3. **No request queuing** between processes
   - Workaround: Stagger process startup with random delay
   - Better fix: Phase5 Scalable with async queuing

---

## Monitoring

Watch these metrics to ensure fix is working:

```bash
# Count 429 errors (should be 0-1 per cycle, not 10+)
grep "429" logs/phase5_live.log | wc -l

# Count rate limit warnings (should show backoff happening)
grep "rate limited" logs/phase5_live.log | wc -l

# Ensure batches still complete
grep "✅ Batch" logs/phase5_live.log | wc -l

# Check process health
ps aux | grep phase5_multi_pair | grep -v grep | wc -l
```

---

## If Rate Limiting Persists

1. **Check sentiment aggregator** runs on schedule (may be hammering X API separately)
2. **Verify Coinbase API credentials** are correct (invalid auth can trigger 429s)
3. **Check for other services** using same API key
4. **Consider request rate limiting** at application level (threading.Semaphore)
5. **Escalate to Phase5 Scalable** immediately (designed for this)

---

## DO NOT FORGET

This fix addresses **immediate cascade issue** but doesn't scale.

**Phase 5 Scalable** is the **permanent solution**:
- Handles unlimited traders
- Zero redundant API calls
- Hot-swappable trader config
- Ready for production in Phase 7

See `PHASE5_SCALABLE.md` for deployment plan.
