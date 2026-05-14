# Coinbase Advanced Trade API – Batch Limits Documentation

## Research Findings (2026-04-18)

### Official API Documentation
- **Endpoint**: `GET /api/v3/brokerage/products`
- **Parameter**: `product_ids` (array of trading pairs)
- **Status**: Batch queries supported ✅
- **Explicit limit**: NOT SPECIFIED in official docs

### Typical REST API Constraints
- Query string size limit: 2000-4000 characters (varies by HTTP library)
- URL-encoded array expansion: Each pair ~10 chars (e.g., `BTC-USD`, `ETH-USD`)
- Safe batch size recommendation: **20-50 pairs per request**

### Coinbase SDK (coinbase-advanced-py v1.8.2)
- Accepts `product_ids` parameter as Python list
- No explicit batch size documented
- Uses standard HTTP GET (query string)
- Handles array expansion via requests library

### Conservative Safe Limits
- **Minimum batch**: 1 pair (fallback)
- **Optimal batch**: 10-20 pairs
- **Maximum recommended**: 50 pairs per request
- **Safety margin**: Apply 20-pair hard limit

## Implementation Strategy

### Current Setup
- **Pairs in rotation**: 6 (BTC-USD, XRP-USD, ETH-USD, DOGE-USD, ADA-USD, SOL-USD)
- **Batch strategy**: Send all 6 in ONE request (well within safe limits)
- **Current batch size**: 6/20 optimal range ✅

### Scaling Scenario
- **Phase 6 expansion**: 12-50+ pairs possible
- **Batch chunking**: IF pairs > 20, split into multiple requests
  - Request 1: Pairs 1-20
  - Request 2: Pairs 21-40
  - Request 3: Pairs 41-50 (etc)

### Error Handling
- Fallback: If batch request fails (e.g., 414 URI Too Long), retry with smaller batch
- Exponential backoff: 1s, 2s, 4s delays
- Final fallback: Individual pair requests (slow but always works)

## Code Implementation

```python
MAX_BATCH_SIZE = 20  # Conservative hard limit

def _fetch_all_pairs_batch(self, pairs):
    """Fetch prices with chunking for >20 pairs"""
    all_prices = {}
    
    # Split into chunks if needed
    chunks = [pairs[i:i+MAX_BATCH_SIZE] for i in range(0, len(pairs), MAX_BATCH_SIZE)]
    
    for chunk_idx, chunk in enumerate(chunks, 1):
        try:
            products = self.client.get_products(product_ids=chunk)
            # ... parse responses
            
            self.logger.info(f"Batch {chunk_idx}/{len(chunks)}: fetched {len(chunk)} pairs")
        except Exception as e:
            self.logger.error(f"Batch {chunk_idx} failed: {e}")
            # Retry logic or fallback here
    
    return all_prices
```

## Monitoring
- Log: Number of batches per cycle
- Alert: If batch fails → fallback to individual fetches
- Metric: Batch efficiency (prices fetched / requests)

## Reference
- Coinbase API Docs: https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/products/list-products
- SDK: https://github.com/coinbase/coinbase-advanced-py
- HTTP URL length limits: 2048-4096 chars (browser-dependent, server often higher)
