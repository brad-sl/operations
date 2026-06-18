# Handoff: FABLE5-P6-103 (P0-Critical)

**Title**: Universal 2-decimal rounding of stop/limit prices breaks stops on sub-dollar assets

**From**: Fable 5 Batch 1 review (2026-06-10)

**Objective**: Stop and limit prices (and sizes) must be quantized to the per-product price_increment and base_increment from Coinbase. Never use fixed 2dp for all assets.

**Must Do**:
- Add product metadata fetch in exchange_client (or cache from `get_product` / list products) for `price_increment`, `base_increment`.
- In `phase6/core/stop_loss_manager.py` and `exchange_client.place_stop_limit_sell` (and attach_tp equivalents): 
  - Fetch or use quantized values.
  - Compute stop_price = round_to_increment(entry * (1-pct), price_increment)
  - Enforce `stop_price < entry_price` and `limit_price < stop_price` after quantization.
  - Apply base_increment for size/qty.
- Validate before placement; refuse and alert if the quantized stop would be invalid (e.g., DOGE/XRP case).
- Update `_round_size_for_product` (or rename) to be the canonical consumer of increments.
- Add Code Isolation Test with real or realistic product specs for BTC, DOGE, XRP, SOL: proves correct stop > entry distance and correct increments.
- Use real product data in the test (pull via exchange or hardcode from snapshot).

**Must Not Do**:
- Do not hardcode 2 decimal places or round every price/size to .2f.
- Do not place stops that violate increment rules or produce stop == entry.

**Files in scope**:
- phase6/core/stop_loss_manager.py
- phase6/core/exchange_client.py (place_stop_limit_sell, any rounding helpers, _round_size_for_product)
- phase6/core/order_executor.py (if it sizes SLs)

**Deliverables**:
1. Product increment metadata support + fetch helper in exchange_client.
2. Quantized attach_stop_loss / place_stop_limit_sell paths.
3. Validation + refusal for invalid quantized prices.
4. Isolation test script with realistic product snapshots.
5. MASTER + Kanban + Scotty verification.

**Success Criteria**:
- For a $0.12 DOGE entry + 3% SL: quantized stop is strictly < 0.12 and respects the product price_increment (typically 0.0001 or better).
- Same for XRP at ~$0.50: proper buffer maintained.
- Test passes with real increment data; no more 2dp-only logic.
- Stops survive shadow-to-real parity on product rules.

**Standing Constraints**: Real data (product metadata from exchange preferred). Code Isolation Testing required. Scotty shadow review.

**References**:
- Fable 5 Batch 1 P6-103 + interactions with P6-106 (real fills) and P6-105 (schema).

**Priority**: P0-Critical for any universe containing sub-$1 assets (current FIXED_UNIVERSE does).