# Phase 5 v4 SL Integration

## Status
Files ready, need manual edit of `phase5_v4_with_sl.py`

## Files Created

1. **`sl_placement_module.py`** ✅
   - `SLPlacement` class for placing stop-limit orders
   - Methods: `place_stop_limit_sell()`, `get_sl_price()`, `check_sl_order_status()`
   - Reusable for manual SL updates or bot integration

2. **`set_stop_loss_utility.py`** ✅
   - Standalone utility for manual SL management
   - Usage examples:
     ```bash
     # Single pair SL
     python3 set_stop_loss_utility.py --pair BTC-USD --entry-price 62500 --qty 0.00257 --sl-pct 0.02
     
     # Batch update all positions from state
     python3 set_stop_loss_utility.py --batch-update
     
     # List active positions
     python3 set_stop_loss_utility.py --list-positions
     ```

3. **`phase5_v4_with_sl.py`** (in progress)
   - Copy of v3-lite with SL module imported
   - Needs: Enhanced `_execute_trade()` method
   
## Required Edit

In `phase5_v4_with_sl.py`, replace the `_execute_trade` method (line 281-300) with:

```python
def _execute_trade(self, pair, signal, price):
    """Execute live trade on Coinbase if signal triggers + place SL"""
    if signal != "TRADE" or not self.cb_client:
        return None
    try:
        order_size = (self.capital_per_pair / price) * 0.5
        self.logger.info(f"🔥 LIVE TRADE: {pair} @ ${price:.4f}")
        try:
            order = self.cb_client.create_market_order(
                product_id=pair,
                side="BUY",
                quote_size=self.capital_per_pair * 0.5
            )
            order_id = order.get('id')
            self.logger.info(f"✅ BUY Order placed: {order_id}")
            
            # Place stop-loss order
            if order_id and self.sl_placer:
                try:
                    entry_qty = order_size
                    sl_price = price * (1 - 0.02)  # 2% SL
                    
                    success, sl_order_id, error = self.sl_placer.place_stop_limit_sell(
                        pair, entry_qty, sl_price
                    )
                    
                    if success:
                        # Record position with SL
                        self.POSITION_MANAGER.update_position(
                            pair=pair,
                            entry_price=price,
                            entry_qty=entry_qty,
                            sl_order_id=sl_order_id,
                            sl_price=sl_price,
                            timestamp=datetime.utcnow().isoformat() + 'Z'
                        )
                        self.logger.info(f"✅ SL Order placed: {sl_order_id} @ ${sl_price:.2f}")
                    else:
                        self.logger.warning(f"⚠️  SL placement failed: {error}")
                except Exception as sl_e:
                    self.logger.warning(f"⚠️  SL placement exception: {sl_e}")
            
            return order
        except Exception as e:
            self.logger.warning(f"Order failed: {e}")
            return None
    except Exception as e:
        self.logger.error(f"Trade error {pair}: {e}")
        return None
```

## Testing Checklist

- [ ] Test `set_stop_loss_utility.py --list-positions`
- [ ] Test `set_stop_loss_utility.py --pair BTC-USD --entry-price 62500 --qty 0.00257 --sl-pct 0.02`
- [ ] Verify SL order placed in Coinbase Advanced Orders API
- [ ] Test `phase5_v4_with_sl.py` on next trading cycle
- [ ] Verify SL triggers on simulated price drop

## Deployment Path

1. Apply manual edit to v4
2. Run v4 in parallel with v3-lite for 2-3 cycles
3. Verify SL orders place correctly after buys
4. Verify SL orders fill when triggered
5. Swap v4 as primary (replace v3-lite)
