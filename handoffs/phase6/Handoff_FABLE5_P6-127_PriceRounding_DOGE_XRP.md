# Handoff: FABLE5-P6-127 (P0-Critical)

**Title**: Live get_price rounds to 2dp — corrupts sizing, stops, valuation for DOGE/XRP

**From**: Fable 5 Batch 3 (#4 new CRITICAL)

**Objective**: Return full-precision prices from live path. Quantization only at order construction time per product increments.

**Files**:
- phase6/core/exchange_client.py (get_price live path)
- coinbase_wrapper_FIXED.py (any price calls)
- phase6/core/order_executor.py, stop_loss_manager.py (consumers)
- Tests

**Must Do**:
- Remove any round(..., 2) in price return paths.
- Use full float/Decimal from API response.
- Isolation test showing DOGE/XRP prices have correct precision and don't lose digits.
- Update stop attachment and sizing to quantize only at the end.

**Success**: Realistic shadow + live-equivalent prices; test passes; Scotty sign-off.

**Created**: 2026-06-10.