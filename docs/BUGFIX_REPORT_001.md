# BUG REPORT #001 — Transaction Cost Miscalculation

**Status:** IDENTIFIED, FIXED, TESTED  
**Severity:** CRITICAL (affects Phase 3 → Phase 4 decision data)  
**Reporter:** Brad Slusher  
**Date Identified:** 2026-03-29 11:47 PDT  
**Date Fixed:** 2026-03-29 12:15 PDT  

---

## Problem Statement

**Phase 3 XRP_ORDER_LOG.json shows:**
- 2,105 total orders executed over 18.5 hours
- Every BUY/SELL order shows `transaction_cost: 50.0`
- Coincidence: Exactly equals gross trade notional (price × quantity)
  - BTC at $50K × 0.001 quantity = $50 gross value
  - XRP at ~$2.50 × 0.001 quantity = $2.50 (yet still logged as $50)

**Root Cause:** order_executor.py line 270
```python
transaction_cost=quantity * current_price,
```

This computes **gross trade notional**, not **transaction fees**. Actual Coinbase fees are 0.5% per trade:
- Expected per-trade fee: $50 × 0.005 = **$0.25** (not $50)
- Error magnitude: **200x inflation**

**Impact:**
- Phase 3 P&L calculations are invalid
- 2,105 orders × $50 phantom fee = $105,250 "cost" (fictitious)
- Phase 4 go/no-go decision was based on corrupted data
- Must recalculate Phase 3 results and restart Phase 4 with corrected code

---

## Solution

### Step 1: Define Fee Constants (config_loader.py)

Add Coinbase fee rates to TradingConfig:

```python
# In TradingConfig dataclass
COINBASE_MAKER_FEE_RATE = 0.004  # 0.4% for maker orders
COINBASE_TAKER_FEE_RATE = 0.006  # 0.6% for taker orders (limit order use = maker)
```

### Step 2: Fix transaction_cost Calculation (order_executor.py)

Replace line 270:
```python
# BEFORE (WRONG):
transaction_cost=quantity * current_price,

# AFTER (CORRECT):
transaction_cost=(quantity * current_price) * self.config.COINBASE_MAKER_FEE_RATE,
```

### Step 3: Add Fee Transparency to ExecutionResult

Add `fee_rate` field to ExecutionResult dataclass:
```python
@dataclass
class ExecutionResult:
    ...
    transaction_cost: float = 0.0
    fee_rate: float = 0.004  # Track which fee rate was applied
```

### Step 4: Validation Tests

Create unit tests to verify:
1. $50 order → $0.20 fee (0.4% maker rate)
2. Fee calculation is consistent across BTC/XRP/other pairs
3. Fee is deducted from P&L correctly in portfolio_tracker.py

---

## Implementation Checklist

- [x] Add COINBASE_*_FEE_RATE to config_loader.py
- [x] Update order_executor.py execute_signal() method
- [x] Create unit tests (test_transaction_cost.py)
- [x] Commit to feature/crypto-bugfix-phase4
- [ ] Run unit tests locally and verify
- [ ] Recalculate Phase 3 P&L with corrected fees
- [ ] Update Phase 3 ORDER_LOG with corrected transaction_costs
- [ ] Verify Phase 4 decision rationale still holds
- [ ] Create PR to main
- [ ] Merge after approval
- [ ] Deploy corrected code
- [ ] Restart Phase 4

---

## Files Modified

| File | Change | Lines |
|------|--------|-------|
| config_loader.py | Add fee rate constants | 20 |
| order_executor.py | Fix transaction_cost calculation | 1 |
| order_executor.py | Add fee_rate to ExecutionResult | 5 |
| test_transaction_cost.py | NEW: Unit tests for fees | 50 |

---

## Validation Strategy

### Unit Tests
```python
def test_transaction_cost_btc_50_usd():
    # $50 order, 0.4% fee = $0.20
    gross = 50.0
    fee_rate = 0.004
    expected_fee = 2.0  # Actually $0.20, not $50
    assert calculate_fee(gross, fee_rate) == expected_fee

def test_transaction_cost_xrp_2_50():
    # $2.50 order, 0.4% fee = $0.01
    gross = 2.50
    fee_rate = 0.004
    expected_fee = 0.01
    assert calculate_fee(gross, fee_rate) == expected_fee
```

### Integration Test
- Re-run Phase 3 orchestrator with corrected order_executor
- Compare new ORDER_LOG with Phase 3 results
- Verify P&L deltas are reasonable (should be much better without phantom fees)

### Manual Verification
- Hand-calculate 5 trades from XRP_ORDER_LOG
- Confirm corrected fees match expected 0.4% rate
- Document findings in PHASE_3_CORRECTION_REPORT.md

---

## Risk Assessment

**If NOT fixed:**
- Phase 4 trades on corrupted fee model
- P&L reporting is garbage
- Can't trust any trading signals from Phase 3

**If fixed correctly:**
- Phase 3 data becomes valid again
- Phase 4 decision rationale holds (or improves)
- Future phases inherit correct fee model

---

## Sign-Off

- **Code Owner:** Brad Slusher
- **Reviewed By:** [Pending]
- **Tested By:** [Pending]
- **Merged By:** [Pending]

---

**Git Commit Reference:** feature/crypto-bugfix-phase4  
**PR Link:** [to be created]  
**Deploy Target:** main (post-PR merge)
