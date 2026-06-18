# Handoff: FABLE5-P6-115 (P0-Critical)

**Title**: Hardcoded `:.2f` price formatting in wrapper breaks stop-limit and limit orders for sub-dollar assets (XRP, DOGE)

**From**: Fable 5 Batch 2 review (2026-06-10)

**Objective**: All price and size formatting for orders (especially stops) must be quantized to the product's `quote_increment` and `base_increment`. Never use fixed `:.2f`.

**Must Do**:
- In `coinbase_wrapper_FIXED.py` (and any shadow path in `phase6/core/exchange_client.py`): Replace all `f\"{price:.2f}\"` and `f\"{qty:.8f}\"` with quantization using real (or cached) product metadata.
- Add helper `quantize_price(product_id, price)` and `quantize_size(product_id, size)`.
- Fetch `/api/v3/brokerage/products/{product_id}` once (cache it) for `quote_increment`, `base_increment`, `price_increment`.
- After quantization, validate `stop_price < entry_price` (after rounding) and refuse placement if violated; fail loud with clear log.
- Update `place_stop_limit_sell`, `place_limit_buy`, `place_market_buy/sell` (for consistency), and StopLossManager's price calculations.
- Add Code Isolation Test `scripts/test_fable5_p6_115_product_quantization.py` using realistic product metadata for BTC, DOGE, XRP, SOL (hardcode snapshots from real calls if needed) that proves stops are still valid distance from entry.
- Use `decimal.Decimal` + `ROUND_DOWN` / appropriate rounding for sells.

**Must Not Do**:
- Do not hardcode 2 decimal places for prices or 8 for sizes across all products.
- Do not place or "succeed" a stop whose quantized value would be invalid or zero-buffer on low-price assets.

**Files in scope**:
- coinbase_wrapper_FIXED.py (place_* methods)
- phase6/core/exchange_client.py (shadow + calls to wrapper, get_product_metadata/round helpers — they already have some but are not used in live wrapper path)
- phase6/core/stop_loss_manager.py (attach_stop_loss price math)
- phase6/core/order_executor.py (if it does sizing for SLs)

**Deliverables**:
1. Quantization helpers + product metadata fetch/caching in the wrapper.
2. Updated all placement methods to use quantized values + validation.
3. Isolation test with DOGE/XRP examples (stop remains strictly below entry with correct granularity).
4. Updated MASTER + handoff reference.
5. New Kanban card.
6. Scotty shadow verification (test against product snapshots + shadow placement parity).

**Success Criteria**:
- For DOGE at $0.12 entry + 3% SL: quantized stop < 0.12 and respects the product's quote_increment (typically 0.0001).
- Same test for XRP ~$0.50.
- Placement methods reject (fail loud) when quantization would produce invalid stop.
- Existing P6-001/P6-103 verification still passes.

**Standing Constraints**:
- Real data (product metadata).
- Code Isolation Testing + real-data verification before promotion.
- Scotty integration reviewer sign-off required.

**References**:
- Fable 5 Batch 2: P6-115 (top risk).
- Prior P6-103 (2dp in StopLossManager).
- coinbase_wrapper_FIXED.py lines for formatting.

**Priority**: P0-Critical (now ranked highest live-safety risk by Fable 5; 2/5 universe pairs unprotected).