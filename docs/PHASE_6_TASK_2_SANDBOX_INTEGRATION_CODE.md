# Phase 6 Task 2: Sandbox Integration Code

## Integration Points

### 1. Add Import (top of phase5_multi_pair.py)

```python
try:
    from order_executor import OrderExecutor
    ORDER_EXECUTOR_AVAILABLE = True
except ImportError:
    ORDER_EXECUTOR_AVAILABLE = False
    OrderExecutor = None
```

### 2. Add Trade Logging Setup (__init__ method)

```python
# Trade logging for audit trail
self.trades_csv = os.path.join(os.path.dirname(__file__), 'trades_sandbox.csv')
self.trades_executed = []

# Sandbox configuration
self.order_size_usd = self.config.get('order_size_usd', 25.0)  # Conservative for sandbox
self.sandbox_trading = os.getenv('SANDBOX_TRADING', 'True').lower() == 'true'

self.logger.info(f"Sandbox Trading: {self.sandbox_trading}, Order Size: ${self.order_size_usd:.2f}")
```

### 3. Add Trade Logging Method

```python
def _log_trades_to_csv(self, results):
    """Log trade execution results to CSV for audit trail"""
    import csv
    
    try:
        file_exists = os.path.exists(self.trades_csv)
        
        with open(self.trades_csv, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'timestamp', 'pair', 'signal', 'order_id', 'status', 
                'quantity', 'price_executed', 'transaction_cost', 'error'
            ])
            
            if not file_exists:
                writer.writeheader()
            
            for result in results:
                writer.writerow({
                    'timestamp': result.timestamp,
                    'pair': getattr(self, 'current_pair', 'unknown'),
                    'signal': result.signal_type,
                    'order_id': result.order_id or 'N/A',
                    'status': result.status,
                    'quantity': result.quantity,
                    'price_executed': result.price_executed or 'N/A',
                    'transaction_cost': result.transaction_cost,
                    'error': result.error or ''
                })
                
                self.trades_executed.append({
                    'order_id': result.order_id,
                    'status': result.status,
                    'pnl': result.transaction_cost
                })
        
        self.logger.info(f"✅ Trades logged to {self.trades_csv} ({len(results)} records)")
    
    except Exception as e:
        self.logger.error(f"Trade logging error: {e}")
```

### 4. Modify _process_pair() to Use OrderExecutor

Replace the existing _process_pair() method with:

```python
def _process_pair(self, pair, cycle):
    """Process individual trading pair with OrderExecutor integration"""
    self.current_pair = pair  # Track for logging
    
    try:
        # Use batch-fe tched price
        price_attr = pair + "_price"
        price = getattr(self, price_attr, None)
        
        if price is None or price <= 0:
            self.logger.warning(f"Price missing for {pair}, skipping")
            return "HOLD"
        
        # Update metrics
        if self.pair_price_gauge:
            try:
                self.pair_price_gauge.labels(pair=pair).set(price)
            except Exception:
                pass
        
        # Calculate indicators
        rsi = self._calculate_rsi(pair)
        sentiment = self._get_sentiment(pair)
        
        # Determine signal
        signal = self._determine_trade_signal(pair, price, rsi, sentiment)
        
        self.logger.info(f"C{cycle} {pair}: ${price:.2f} | RSI={rsi:.0f} | Sentiment={sentiment:.2f} | Signal={signal}")
        
        # Execute via OrderExecutor if signal is not HOLD
        if signal in ["BUY", "SELL"] and ORDER_EXECUTOR_AVAILABLE and self.sandbox_trading:
            try:
                self.logger.info(f"📤 Submitting {signal} signal to OrderExecutor...")
                
                # Create executor instance
                executor = OrderExecutor(
                    signals=[{
                        "id": f"cycle-{cycle}-{pair}",
                        "signal": signal,
                        "confidence": 0.85,
                        "timestamp": datetime.now().isoformat()
                    }],
                    coinbase_wrapper=self.cb_client,  # Pass Coinbase wrapper
                    product_id=pair,
                    order_size_usd=self.order_size_usd,
                    sandbox_mode=self.sandbox_trading
                )
                
                # Execute
                results = executor.execute_all_signals()
                
                # Log results
                for result in results:
                    if result.status != "SKIPPED":
                        self.logger.info(
                            f"✅ Order {result.order_id}: {result.status} | "
                            f"Qty={result.quantity:.8f} @ ${result.price_executed:.2f} | "
                            f"Cost=${result.transaction_cost:.2f}"
                        )
                    else:
                        self.logger.info(f"⏭️  Signal {result.signal_type} skipped (HOLD)")
                
                # Log to CSV
                self._log_trades_to_csv(results)
                
            except Exception as e:
                self.logger.error(f"OrderExecutor error for {pair}: {e}", exc_info=True)
                self.logger.info("Falling back to manual signal (no order placed)")
        
        return signal
        
    except Exception as e:
        self.logger.error(f"Error processing {pair}: {e}")
        return "HOLD"
```

### 5. Sandbox Configuration in config/trading_config_phase5.json

Add these fields to global_settings:

```json
{
  "global_settings": {
    "order_size_usd": 25.0,
    "sandbox_trading": true,
    "pairs": ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD"],
    "total_capital": 750
  }
}
```

### 6. Environment Variables for Sandbox

```bash
export SANDBOX_MODE=True
export SANDBOX_TRADING=True
export ALLOW_PAPER_TRADING=True
```

---

## Execution Flow (Sandbox)

```
CYCLE N
├─ Fetch batch prices
├─ For each pair:
│  ├─ Get RSI, Sentiment
│  ├─ Determine signal (BUY/SELL/HOLD)
│  ├─ If BUY/SELL and sandbox_enabled:
│  │  ├─ Create OrderExecutor instance
│  │  ├─ Execute via Coinbase Advanced Trade (sandbox mode)
│  │  ├─ Get results (order_id, status, price, quantity)
│  │  └─ Log to trades_sandbox.csv
│  └─ Return signal
├─ Weekly rebalancing check (every 7 cycles)
└─ Next cycle (5 min interval)
```

---

## Testing Checklist

- [ ] Sandbox mode enabled (SANDBOX_MODE=True)
- [ ] OrderExecutor imported successfully
- [ ] Trade logging working (check trades_sandbox.csv)
- [ ] 10+ trades executed without crashing
- [ ] P&L calculated correctly
- [ ] Order IDs tracked and logged
- [ ] All order statuses captured
- [ ] Error handling working (one intentional failure test)
- [ ] 24h validation complete
- [ ] Ready for live migration

---

## Files Modified

- `phase5_multi_pair.py`: Add OrderExecutor integration in _process_pair()
- `config/trading_config_phase5.json`: Add order_size_usd, sandbox_trading settings
- `trades_sandbox.csv`: NEW - Trade execution audit log (append mode)

---

## CSV Output Format

```csv
timestamp,pair,signal,order_id,status,quantity,price_executed,transaction_cost,error
2026-04-21T20:05:30.123456,BTC-USD,BUY,ord-12345,FILLED,0.00277185,57653.21,159.84,
2026-04-21T20:10:45.654321,ETH-USD,HOLD,N/A,SKIPPED,0.0,N/A,0.0,
2026-04-21T20:15:12.789012,SOL-USD,BUY,ord-12346,FILLED,1.41893932,142.50,202.20,
```

---

**Status:** Ready for integration. When you proceed, I will:
1. Add imports
2. Update __init__() with sandbox config
3. Integrate OrderExecutor into _process_pair()
4. Add trade logging
5. Commit as Task 2
6. Run 24h sandbox validation
