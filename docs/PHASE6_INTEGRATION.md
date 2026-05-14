# PHASE6_INTEGRATION.md

## Integration Instructions for Phase 5.1 Multi-Pair Trading Script

### Pre-Trading Loop (before main trading loop):
1. Instantiate `Phase6Initializer(cb_client, state, order_exec)`
2. Call `initializer.run()` 
3. Extract:
   - `deploy_budget = initializer.state['deploy_budget']`
   - `scenario = initializer.state['scenario']`
   - `trading_fiat = initializer.state['trading_fiat']`
   - `sl_price = initializer.state['sl_price']`
   - `tp_price = initializer.state['tp_price']`
4. **Skip trading if `initializer.state['status'] != 'READY_TO_TRADE'`**
5. Log: `Scenario: {scenario}, Trading Fiat: {trading_fiat}, Budget: {deploy_budget}`

### Main Trading Loop Updates:
- Use `deploy_budget` for position sizing / allocation across pairs
- For each pair, respect `sl_price` and `tp_price` from initializer (global or per-pair?)
- Call `order_exec.place_sl_tp(pair, sl_price, tp_price)` after entry

### Flags:
- `--dry-run`: Skip real API calls, log only
- Cycle limit: `--cycles 1` for testing

### Expected Logs:
```
Phase 6 Init Complete
Scenario: fresh_start
Trading Fiat: USDC
Deploy Budget: 1000.0
Status: READY_TO_TRADE
[INFO] Multi-pair trading active with SL/TP protection
```
