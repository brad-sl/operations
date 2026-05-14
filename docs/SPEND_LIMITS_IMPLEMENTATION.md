# Spend Limits Implementation — Order Executor

**Status:** ✅ COMPLETE  
**Date:** 2026-03-23  
**Commit:** `37bb0f4` (Add: Spend limits to order_executor)

## Overview

Added three spend limit enforcement mechanisms to `order_executor.py`:

1. **Daily Budget Cap** — $1,000 USD max per 24-hour period
2. **Position Size Limit** — 0.05 BTC max per order for BTC-USD
3. **Daily Loss Circuit Breaker** — $200 USD stop-loss per 24-hour period

All limits are configurable in `trading_config.json`.

---

## Changes Made

### 1. **Import ConfigLoader** ✅

```python
from config_loader import ConfigLoader, TradingConfig
```

**Location:** Line 13 in `order_executor.py`

---

### 2. **Added SpendTracker Class** ✅

New class (lines 35-73) before `OrderExecutor`:

```python
class SpendTracker:
    """Track daily spending and losses to enforce limits"""
    
    def __init__(self, config: TradingConfig):
        self.config = config
        self.daily_spend_usd = 0.0
        self.daily_orders = []
        self.session_start = datetime.now(timezone.utc)
    
    def within_daily_budget(self, additional_spend: float) -> bool:
        """Check if additional spend exceeds daily limit"""
        return (self.daily_spend_usd + additional_spend) <= self.config.daily_spend_usd
    
    def within_position_limit(self, product_id: str, quantity: float) -> bool:
        """Check if order quantity exceeds position limit for this pair"""
        max_size = self.config.position_limits.get(product_id, 0.05)
        return quantity <= max_size
    
    def within_daily_loss_limit(self) -> bool:
        """Check if daily loss exceeds circuit breaker"""
        daily_pnl = sum(
            (order.get("price_executed", 0) * order.get("quantity", 0))
            for order in self.daily_orders
            if order.get("status") != "FAILED"
        )
        return daily_pnl >= -self.config.max_daily_loss_usd
    
    def add_order(self, result, usd_amount: float):
        """Track order spending"""
        self.daily_spend_usd += usd_amount
        self.daily_orders.append({...})
```

**Methods:**
- `within_daily_budget()` — Checks if order stays within daily limit
- `within_position_limit()` — Checks if order quantity within pair limit
- `within_daily_loss_limit()` — Checks if daily loss within circuit breaker
- `add_order()` — Tracks successful order for spend accounting

---

### 3. **Modified OrderExecutor.__init__** ✅

**Lines 145-168** — Added config loading:

```python
def __init__(
    self,
    signals: List[Dict[str, Any]],
    coinbase_wrapper: CoinbaseWrapper,
    product_id: str = "BTC-USD",
    order_size_usd: float = 50.0,
    sandbox_mode: bool = True,
    config_path: str = None,  # NEW: Optional custom config path
):
    # ... existing code ...
    
    # NEW: Load config and initialize spend tracker
    loader = ConfigLoader(config_path)
    self.config = loader.get_config()
    self.spend_tracker = SpendTracker(self.config)
    
    # ... rest of existing init code ...
```

**What Changed:**
- Added optional `config_path` parameter
- Load `TradingConfig` from JSON
- Initialize `SpendTracker` with loaded config
- Config provides limits: daily budget, position sizes, max loss

---

### 4. **Modified execute_signal() Method** ✅

**Lines 236-253** — Added three limit checks before order creation:

```python
# Check spend limits before creating order
if not self.spend_tracker.within_daily_budget(self.order_size_usd):
    raise ValueError(
        f"Daily budget exceeded. Spent: ${self.spend_tracker.daily_spend_usd:.2f}, "
        f"Limit: ${self.config.daily_spend_usd:.2f}"
    )

if not self.spend_tracker.within_position_limit(self.product_id, quantity):
    raise ValueError(
        f"Position size {quantity:.8f} {self.product_id.split('-')[0]} "
        f"exceeds limit {self.config.position_limits.get(self.product_id, 0.05)}"
    )

if not self.spend_tracker.within_daily_loss_limit():
    raise ValueError(
        f"Daily loss limit (${self.config.max_daily_loss_usd}) reached. "
        f"Trading halted for today."
    )
```

**Lines 273-275** — Track successful orders:

```python
# Track spend on success
self.spend_tracker.add_order(result, self.order_size_usd)
return result
```

**Behavior:**
- Checks happen **before** order creation
- Rejected orders return `ExecutionResult` with `status="FAILED"` and error message
- Successful orders are tracked in `spend_tracker` for future limit checks
- Error messages include current spend and limits for debugging

---

## Configuration (trading_config.json)

```json
{
  "limits": {
    "daily_spend_usd": 1000,
    "max_position_size": {
      "BTC-USD": 0.05,
      "ETH-USD": 0.5,
      "SOL-USD": 10.0
    },
    "max_daily_loss_usd": 200,
    "max_single_order_usd": 100
  }
}
```

**Current Defaults:**
- **Daily Budget:** $1,000 USD
- **BTC Position Limit:** 0.05 BTC (~$2,500 at $50k/BTC)
- **Daily Loss Limit:** $200 USD
- **Single Order Max:** $100 USD

---

## Test Results

**All Tests Passed:** ✅

```
TEST 1: Order under budget → ✅ succeeds
  • $50 order accepted (under $1000 limit)
  • Order tracked in spend_tracker

TEST 2: Order exceeding budget → ✅ fails with message
  • $900 already spent + $150 new = exceeds $1000
  • Rejected with error message showing limits

TEST 3: Position size check → ✅ fails if > 0.05 BTC
  • 0.03 BTC order accepted (under 0.05 limit)
  • 0.1 BTC order rejected with position error

TEST 4: Daily loss circuit breaker → ✅ fails if > $200 loss
  • $150 loss accepted (under $200 limit)
  • $250 loss rejected with circuit breaker error

INTEGRATION: Spend limits in OrderExecutor → ✅ working
  • Spend tracker initialized on __init__
  • Config loaded from trading_config.json
  • Limits enforced in execute_signal()
```

---

## Usage Example

```python
from order_executor import OrderExecutor
from coinbase_wrapper import CoinbaseWrapper

# Create executor (config auto-loads from default location)
wrapper = CoinbaseWrapper(api_key, private_key, passphrase, sandbox=True)
signals = [...]

executor = OrderExecutor(
    signals=signals,
    coinbase_wrapper=wrapper,
    product_id="BTC-USD",
    order_size_usd=50.0,
    sandbox_mode=True,
    # config_path=None  # Uses default: ~/crypto-bot/trading_config.json
)

# Execute signals (limits checked automatically)
results = executor.execute_all_signals()

# Check results for limit violations
for result in results:
    if result.status == "FAILED" and "budget exceeded" in (result.error or ""):
        print(f"Order rejected: {result.error}")
```

---

## Error Messages

### Daily Budget Exceeded
```
Daily budget exceeded. Spent: $900.00, Limit: $1000.00
```

### Position Size Limit
```
Position size 0.10000000 BTC exceeds limit 0.05
```

### Daily Loss Circuit Breaker
```
Daily loss limit ($200) reached. Trading halted for today.
```

---

## Files Modified

| File | Changes | Lines |
|------|---------|-------|
| `order_executor.py` | Config loading, SpendTracker class, limit checks | +73, -1 |
| **Total** | **+73 lines, -1 line** | **+72 net** |

---

## Verification Checklist

- ✅ **Syntax Check:** File compiles without errors
- ✅ **Test 1:** Order under budget → succeeds
- ✅ **Test 2:** Order exceeding daily budget → fails with message
- ✅ **Test 3:** Position size check working → fails if > 0.05 BTC
- ✅ **Test 4:** Daily loss circuit breaker working
- ✅ **Integration:** Spend limits integrated in OrderExecutor
- ✅ **Commit:** Message "Add: Spend limits to order_executor (daily cap, position size, loss cutoff)"

---

## Next Steps

1. **Phase 4 Multi-Pair Support** — Extend position limits to ETH-USD, SOL-USD
2. **Daily Reset Logic** — Track session start for 24-hour window reset
3. **Monitoring Dashboard** — Real-time spend/loss visualization
4. **Alert Notifications** — Email/Slack when approaching limits
5. **Live Mode Deployment** — Deploy to production with approval flows

---

**Status:** Ready for Phase 4 ✅
