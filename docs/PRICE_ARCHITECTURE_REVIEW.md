# Price Fetching Architecture Review & Fix Plan

**Date:** 2026-04-23  
**Status:** Critical Issues Identified - Ready for Implementation

---

## Executive Summary

The crypto-bot price fetching system has **cascading failures** due to misaligned API calls and poor separation of concerns:

1. **Broken Coinbase Integration**: `phase5_multi_pair.py` calls `self.cb_client.get_products(product_ids=chunk)`, but `CoinbaseAdvancedClient` only has `get_batch_prices()` and `get_price()` methods. ❌
2. **API Downtime & Rate Limits**: Coinbase Pro API returns 503 (deprecated/unavailable), CoinGecko hits 429 rate limits. ❌
3. **Fallback Architecture Issues**: System falls back to hardcoded prices only after exhausting both APIs, losing real price data.
4. **Duplicate Code**: `price_wrapper.py` has good fallback logic but `phase5_multi_pair.py` tries to reinvent the wheel with broken batch fetching.

---

## Current Code Issues

### Issue 1: Invalid API Call in `phase5_multi_pair.py` (Line ~125)

**Problem:**
```python
response = self.cb_client.get_products(product_ids=chunk)  # ❌ Method doesn't exist
```

**What exists in `CoinbaseAdvancedClient`:**
- `get_batch_prices(product_ids: List[str])` ✓ Works
- `get_price(product_id: str)` ✓ Works
- No `get_products()` method ✗

**Impact:** AttributeError on every batch fetch attempt, fallback loop cascades into rate-limit wall.

---

### Issue 2: Coinbase Pro API Deprecated (503 Service Unavailable)

**Evidence from logs:**
```
Price Fetch Error: Pair=BTC-USD, Source=Coinbase Pro API, 
Error=503 Server Error: Service Unavailable for url: 
https://api.pro.coinbase.com/products/BTC-USD/ticker
```

**Root Cause:** Coinbase deprecated the Pro API. It should NOT be the primary source.

**Current Fallback Order (WRONG):**
1. Coinbase Pro API (deprecated, returns 503) → FAIL
2. CoinGecko → hits 429 rate limits
3. Hardcoded prices → stale data

---

### Issue 3: CoinGecko Rate Limiting (429 Too Many Requests)

**Evidence from logs:**
```
Price Fetch Error: Pair=SOL-USD, Source=CoinGecko API, 
Error=429 Client Error: Too Many Requests for url: 
https://api.coingecko.com/api/v3/simple/price
```

**Root Cause:** Hitting CoinGecko API endpoint 6 times per cycle (once per pair) without request batching.

**Solution:** Batch all pairs into a single CoinGecko request:
- Current (WRONG): 6 requests per cycle
- Fixed (RIGHT): 1 request per cycle with all 6 pairs

---

### Issue 4: Unused `price_wrapper.py` in Main Loop

`phase5_multi_pair.py` has good fallback logic in `_fetch_all_pairs_batch()`, but the main trading loop in `_process_pair()` uses:

```python
price = self.price_wrapper.get_price(pair)  # ✓ Works with fallbacks
```

But earlier in the same function:
```python
response = self.cb_client.get_products(product_ids=chunk)  # ❌ Broken batch
```

**Result:** Mixed usage patterns → hard to debug, inconsistent pricing.

---

## Recommended Architecture

### Principle: Single Source of Truth for Price Fetching

**New Design:**
```
phase5_multi_pair.py
    ↓
    uses
    ↓
PublicExchangePriceWrapper (with rate-limit aware batching)
    ↓
    ├─ Batch all pairs into ONE CoinGecko request (1 API call/cycle)
    ├─ Fallback to Binance public API (if needed)
    └─ Hardcoded fallback for emergency
```

**Benefits:**
- ✓ Single entry point for all pricing logic
- ✓ Avoids Coinbase Pro API (deprecated)
- ✓ Batches CoinGecko requests (reduce rate limiting)
- ✓ Respects Binance public API (no auth needed)
- ✓ No duplicate code between modules

---

## Implementation Plan

### Phase 1: Patch `price_wrapper.py`

**Add batch price fetching:**
```python
def get_prices_batch(self, pairs: List[str]) -> Dict[str, float]:
    """Fetch ALL prices in ONE request to avoid rate limits"""
    # Single CoinGecko call with all pairs
    # Fall back to Binance if needed
    # Return dict {pair: price}
```

### Phase 2: Rewrite `_fetch_all_pairs_batch()` in `phase5_multi_pair.py`

**Current (broken):**
```python
def _fetch_all_pairs_batch(self):
    response = self.cb_client.get_products(product_ids=chunk)  # ❌ Doesn't exist
```

**Fixed:**
```python
def _fetch_all_pairs_batch(self):
    return self.price_wrapper.get_prices_batch(self.pairs)  # ✓ Use wrapper
```

### Phase 3: Update `_process_pair()` to use cached prices

**Current:** Calls `price_wrapper.get_price()` for every pair (6 API calls)

**Fixed:** Call `_fetch_all_pairs_batch()` once per cycle, cache results, use cache in `_process_pair()`

### Phase 4: Remove Coinbase Advanced Trade API price fetching

- Keep it for order execution only (CoinbaseAdvancedClient stays)
- Remove price-fetching attempts from there
- Document separation: "Use CoinGecko/Binance for prices, Coinbase only for orders"

---

## Expected Outcomes

**Before Fix:**
- 503 errors from Coinbase Pro API
- 429 rate limits from CoinGecko
- Fallback to hardcoded stale prices
- System running on stale data or failures

**After Fix:**
- All prices from CoinGecko (1 batched request/cycle) ✓
- Fallback to Binance public API if needed ✓
- Fallback to hardcoded only in true emergency ✓
- Real prices flowing every 5 minutes ✓
- No rate limit errors ✓

---

## Files to Modify

1. **price_wrapper.py** → Add `get_prices_batch()` method
2. **phase5_multi_pair.py** → Fix `_fetch_all_pairs_batch()`, update cycle loop
3. **coinbase_advanced_client.py** → Remove unused price-fetching code (if any)
4. **Documentation** → Update PRICE_FETCHING.md with new architecture

---

## Testing Plan

1. Run price wrapper test: `python3 price_wrapper.py`
2. Validate batch fetch returns all 6 prices in one request
3. Restart phase5_multi_pair.py and validate logs show real prices
4. Monitor for 429 errors (should see 0)
5. Check 5-minute cycle sees fresh prices

---

## Risk Assessment

**Risk Level:** LOW (Price fetching only, no order logic changed)

- All changes are additive (new methods, not replacing core logic)
- Fallback chain maintains safety (always have a price)
- No changes to order execution (Coinbase Advanced Trade API stays untouched)

**Rollback Plan:**
- If new wrapper breaks: comment out `_fetch_all_pairs_batch()`, revert to per-pair `price_wrapper.get_price()` calls

