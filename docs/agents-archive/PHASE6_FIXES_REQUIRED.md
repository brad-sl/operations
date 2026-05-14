# Phase 6 Critical Fixes - Implementation Guide

## IMMEDIATE (Before Any Testing)

### 1. Fix Mock Objects in phase6.py
**Lines 156-165** - Replace with real dependency injection:

```python
# REMOVE THIS:
cb_client = Mock()
cb_client.get_account_history.return_value = []
state_obj = Mock()
order_exec = Mock()

# USE THIS INSTEAD (inject from caller):
def __init__(self, cb_client, state, order_exec, config, mode='PAPER_TRADE'):
    # Accept real instances as parameters
```

**Impact:** Currently bot gets empty data and can't trade.

---

### 2. Fix API Method Mismatches
**Problem:** Code calls methods that don't exist in coinbase_wrapper.py

**Fixes:**

| Code Calls | Actually Exists | Action |
|-----------|-----------------|--------|
| `get_account_history()` | ❌ NO | Use `get_orders()` or implement wrapper |
| `get_current_price(pair)` | ❌ NO | Implement in wrapper (use Coinbase market data API) |
| `place_sl_tp(pair, sl, tp)` | ❌ NO | Implement using two `place_limit_sell()` calls |

**Implementation:**
```python
# Add to coinbase_wrapper.py:

def get_current_price(self, product_id: str) -> float:
    """Get current market price for product."""
    response = self._request('GET', f'/products/{product_id}/ticker')
    return float(response.get('price', 0))

def place_sl_tp(self, product_id: str, qty: float, 
                sl_price: float, tp_price: float) -> Dict[str, Any]:
    """Place SL at sl_price and TP at tp_price for qty shares."""
    sl_order = self.place_limit_sell(product_id, qty * 0.5, sl_price)
    tp_order = self.place_limit_sell(product_id, qty * 0.5, tp_price)
    return {'sl': sl_order, 'tp': tp_order}
```

---

### 3. Create Missing Dependencies
**phase6_user_prompts.py** is imported but doesn't exist (line 18 of phase6_account_initializer.py).

**Option A: Implement Interactive Prompts** (if user interaction OK):
```python
# phase6_user_prompts.py
def get_user_currency_preference() -> str:
    """Ask user USD or USDC."""
    while True:
        choice = input("Trading currency (USD/USDC): ").upper()
        if choice in ('USD', 'USDC'):
            return choice

def confirm_entry_price(pair: str, price: float) -> float:
    """Let user override detected entry price."""
    confirmed = input(f"Confirm {pair} entry @ ${price}? (y/n): ")
    if confirmed.lower() == 'y':
        return price
    else:
        new_price = float(input("Enter new price: "))
        return new_price

# ... implement others
```

**Option B: Use Config Defaults** (RECOMMENDED for automation):
```python
# Remove imports from phase6_account_initializer.py
# Replace interactive calls with config lookups:

trading_fiat = self.config.get('trading_fiat', 'USDC')
# No prompts - use config
```

**Recommendation:** Use Option B (config-driven, no prompts).

---

### 4. Implement StateManager
**All files depend on `state.get_state()` and `state.update_state(state)` but StateManager doesn't exist.**

```python
# state_manager.py
import json
from pathlib import Path
from typing import Dict, Any

class StateManager:
    """Manages trading state persistence."""
    
    def __init__(self, state_file: str = 'phase6_state.json'):
        self.state_file = Path(state_file)
        self._state = self._load()
    
    def _load(self) -> Dict[str, Any]:
        """Load state from disk or return empty."""
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {}
    
    def get_state(self) -> Dict[str, Any]:
        """Get current state."""
        return self._state.copy()
    
    def update_state(self, state: Dict[str, Any]) -> bool:
        """Save state to disk."""
        try:
            self._state = state
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            return True
        except Exception as e:
            logging.error(f"State save failed: {e}")
            return False
```

---

### 5. Standardize API Signatures
**Current mess:**
- `phase6.py`: `place_sl_tp(pair, sl_price, tp_price)` - 3 params
- `phase6_account_initializer.py`: `place_sl_tp(pair, qty, sl_price, tp_price)` - 4 params

**Decision:** Use 4-param version (need qty for split orders):
```python
def place_sl_tp(self, pair: str, qty: float, sl_price: float, tp_price: float) -> bool:
    """Place SL and TP orders."""
```

**Update phase6.py lines 86, 104-105:**
```python
# BEFORE:
self.order_exec.place_sl_tp('default_pair', sl_price, tp_price)

# AFTER:
qty = deploy_budget / entry_price  # Calculate qty
self.order_exec.place_sl_tp('default_pair', qty, sl_price, tp_price)
```

---

## SHOULD FIX (Reliability & Robustness)

### 6. Add Configuration Validation
```python
# In phase6_config_loader.py:

@dataclass
class ScenarioConfig:
    reserve_pct: float
    deploy_pct: float
    self_fund_pct: float
    sl_pct: float
    tp_pct: float
    min_reserve_usd: float
    
    def __post_init__(self):
        """Validate configuration."""
        assert 0 <= self.reserve_pct <= 1, "reserve_pct must be 0-1"
        assert 0 <= self.deploy_pct <= 1, "deploy_pct must be 0-1"
        assert self.reserve_pct + self.deploy_pct <= 1, "reserve + deploy > 1"
        assert self.sl_pct < self.tp_pct, "SL must be below TP"
        assert self.min_reserve_usd > 0, "min_reserve_usd must be positive"
```

---

### 7. Add Error Handling in Liquidation Manager
```python
# phase6_liquidation_manager.py line 160-180:

def liquidate_position(self, pair: str, qty: float, price: float) -> bool:
    """Execute liquidation of a position."""
    if not self.can_liquidate_safely(pair, qty, price):
        return False
    
    try:
        order = self.order_exec.place_market_sell(pair, qty)
        if not order or order.get('status') != 'FILLED':
            logger.error(f"Order not filled: {order}")
            return False
        
        usd_raised = qty * price
        logger.info(f"Liquidated {pair}: {qty} @ ${price} = ${usd_raised:.2f}")
        
        # Clean up tracking
        if pair in self.entry_prices:
            del self.entry_prices[pair]
        
        return True
    
    except Exception as e:
        logger.error(f"Liquidation failed for {pair}: {e}", exc_info=True)
        return False
```

---

### 8. Connect Liquidation Manager to Phase 6 Main Loop
**Currently liquidation_manager is orphaned - never called from phase6.py.**

Add to main trading loop:
```python
from phase6_liquidation_manager import LiquidationManager

# In Phase6Initializer.__init__:
self.liquidation_manager = LiquidationManager(
    cb_client=cb_client,
    order_executor=order_exec,
    min_position_usd=50.0
)

# After placing any order:
filled_price = order['price']  # Get from filled order
self.liquidation_manager.update_entry_price(pair, filled_price)

# Daily (in main loop):
updated_holdings = self.liquidation_manager.weekly_rebalance(
    holdings=current_holdings,
    current_prices=current_prices
)
```

---

## VERIFICATION CHECKLIST

Before deploying to live:

- [ ] All API methods implemented and tested with sandbox account
- [ ] State file persists correctly across restarts
- [ ] Mock objects removed from phase6.py
- [ ] phase6_user_prompts.py either implemented or removed
- [ ] StateManager working with state persistence
- [ ] All three modules (phase6.py, account_init, liquidation) connected
- [ ] 24-hour paper trade test shows clean logs (no API errors)
- [ ] Entry prices tracked and liquidation trigger fires on test data
- [ ] Config validation catches invalid scenarios
- [ ] Error handling catches and logs all exceptions

---

## Testing Sequence

1. **Unit Tests** (mock the APIs):
   ```bash
   python -m pytest tests/test_phase6.py -v
   python -m pytest tests/test_liquidation.py -v
   ```

2. **Integration Test** (with sandbox):
   ```bash
   python phase6.py --config trading_config_phase6.json --mode PAPER_TRADE --log-level DEBUG
   # Monitor for 24 hours
   ```

3. **Live Pilot** (1% capital):
   ```bash
   python phase6.py --config trading_config_phase6.json --mode LIVE --log-level INFO
   # Monitor for 1 week, increase capital only after success
   ```

---

## Go/No-Go Decision

**CURRENT:** ❌ NO-GO (critical issues)
- [ ] All 11 critical issues fixed
- [ ] All 6 minor issues addressed
- [ ] 24-hour paper trade test passed
- [ ] Code review re-done and approved

**THEN:** ✅ GO (proceed to live)
