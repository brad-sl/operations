# Phase 5 Refactor: Safety Core (v3 Robust)
## Architecture Overview

### Core Components
1. **position_state_manager.py** (New)
   - Persistent JSON state: `/home/brad/.openclaw/workspace/operations/crypto-bot/state/position_state.json`
   - Per-pair state: `{entry_price, entry_qty, sl_order_id, sl_price, entry_time}`
   - **Methods**:
     | Method | Purpose |
     |--------|---------|
     | `load_state()` | Load all positions |
     | `save_state()` | Persist state atomically |
     | `update_position(pair, entry_price, qty, sl_id, sl_price, timestamp)` | Record new/open position |
     | `clear_position(pair)` | Remove closed position |
     | `validate_all(cb_client)` | Startup + periodic: Sync actual balances vs expected. Check SL status. Clear closed. Adjust mismatches. |
     | `get_position(pair)` | Safe state query |

2. **phase5_v3_robust.py** (Refactored main bot)
   - **Startup**:
     - Load config → pairs, sl_pct=2.0
     - Init `CoinbaseAdvancedClient(test_mode=not live)`
     - Init `PositionStateManager()`
     - `state_manager.validate_all(cb_client)` → Logs mismatches, clears ghost positions
   - **Main Loop** (per cycle, per pair):
     ```
     1. Fetch current price (batch)
     2. VALIDATE position:
        - actual_base_balance = get_balance(base_asset)  # BTC for BTC-USD
        - expected = state.get(pair, {}).entry_qty
        - IF expected > 0 AND actual ≈ 0: clear_position(pair), log "Ghost position closed (SL?)"
        - IF |actual - expected| > 1%: log WARNING, set expected = actual
     3. Compute RSI (live history), sentiment (cache)
     4. Signal: BUY (RSI<30 + sent>0.5), SELL (RSI>70 + sent<-0.5), HOLD
     5. EXECUTE:
        - BUY (no position): place_market_buy(quote_size=capital_per_pair*0.5)
          - Poll order → FILLED? → get_fills() → avg_entry_price/qty
          - SL_price = avg_entry * (1 - config.sl_pct/100)
          - place_stop_limit_sell(base_size=qty, stop_price=SL_price, limit_price=SL_price*0.995)
          - update_position(pair, avg_entry, qty, sl_order_id, SL_price, now)
        - SELL (position open): place_market_sell(base_size=expected_qty) → clear_position()
     ```
   - **Error Handling**: Skip pair on API failure/mismatch. No blind trades.
   - **State Sync**: Every 5 cycles, full `validate_all()`

### Coinbase API Usage (Official SDK: coinbase.rest.RESTClient)
| Action | Method |
|--------|--------|
| Balances | `client.get_accounts()` → parse currency.available |
| Market Buy | `client.market_order_buy(product_id, quote_size="$50")` |
| Market Sell | `client.market_order_sell(product_id, base_size="0.01")` |
| Order Status | `client.get_order(order_id)` |
| Fills | `client.get_fills(product_id=pair, order_id=...)` |
| **Stop-Loss** | Custom `place_stop_limit_order()`: POST /orders w/ `stop_limit_stop_limit_gtc` |

### Stop-Loss Implementation
```
POST /api/v3/brokerage/orders
{
  "client_order_id": "...",
  "product_id": "BTC-USD",
  "side": "SELL",
  "order_configuration": {
    "stop_limit_stop_limit_gtc": {
      "base_size": "0.015",
      "limit_price": "63700",  // SL_price * 0.995 (slippage)
      "stop_price": "63700"    // entry * (1-0.02)
    }
  }
}
```
- Coinbase executes server-side. Bot only tracks `order_id`.
- On validate: `get_order(sl_order_id).status == "FILLED" → clear_position()`

### File Structure Changes
```
operations/crypto-bot/
├── phase5_v3_robust.py     ← Main executable (replaces phase5_multi_pair.py)
├── position_state_manager.py ← New state layer
├── state/                   ← New dir (gitignored)
│   └── position_state.json
├── config/trading_config_phase5.json (unchanged)
├── coinbase_advanced_client.py (extended w/ stop orders)
└── coinbase_wrapper.py (deprecated)
```

### Why These Changes?
| Feature | Before | After | Benefit |
|---------|--------|-------|---------|
| Position Tracking | None | JSON + balance sync | No double-buy, detects SL fills |
| Pre-Trade Safety | Blind | Actual balance check | Prevents overspend/mismatch trades |
| Stop-Loss | Client-side (fragile) | Server-side Advanced Order | Survives bot restarts/crashes |
| Startup Safety | None | Full validation | Recovers from downtime |

## Testing Checklist
### Unit (pytest recommended)
- [ ] `PositionStateManager`: load/save/update/clear/validate (mock CB client)
- [ ] RSI calc (live history append)
- [ ] Signal logic edge cases (RSI=29/71, sent=0.49/-0.51 → HOLD)

### Integration (sandbox=True)
1. [ ] Startup: Create mock position → validate clears (balance=0)
2. [ ] Mismatch: expected=0.01 BTC, actual=0.009 → adjust + log
3. [ ] BUY → poll fill → place SL → state has sl_order_id
4. [ ] Next cycle: validate SL status=FILLED → clear
5. [ ] SELL open position → clear state
6. [ ] Ghost: state has position, balance=0 → clear + log

### Live (sandbox=False, $10 max)
- [ ] Dry-run 3 cycles → no trades (confirm validation)
- [ ] Manual BUY one pair → SL placed + tracked
- [ ] Wait SL trigger → auto-clear on validate

### Risk Mitigations
- Test_mode: max $10/trade
- Balance check: Never trade > actual USD
- SL slippage: limit_price = stop * 0.995
- State atomic: JSON backup on write
- Logs: Full audit trail (order_ids, prices, balances)

## Migration
```
rm phase5_multi_pair.py  # Backup first
cp phase5_v3_robust.py phase5_multi_pair.py  # Symlink/rename for cron
mkdir -p state/
chmod 600 state/position_state.json  # Secure
```
