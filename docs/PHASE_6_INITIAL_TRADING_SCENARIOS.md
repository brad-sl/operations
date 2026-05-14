# Phase 6: Initial Trading Scenarios & Account States

**Status:** Architecture Planning (Pre-Phase 6)  
**Document Version:** 2026-04-20 07:23 PT  
**Context:** Transition from Phase 5.1 (signal collection + weekly rebalance) → Phase 6 (live trading with account management)

---

## Overview

Phase 6 must handle **five distinct account initialization states**. Each requires different setup logic, risk posture, and capital deployment strategies.

**Critical:** The bot must detect account state at startup, validate it, and apply the correct trading ruleset without losing capital or failing to execute valid signals.

---

## Scenario 1: Fresh Start

### Account State
- **USD/USDC Balance:** ✅ Funded (e.g., $1,000–$10,000+)
- **Crypto Holdings:** ❌ None (0 BTC, 0 ETH, 0 SOL, etc.)
- **Positions:** 0 open trades

### Use Case
- New trading account, fresh funding
- No historical data to analyze
- Zero existing positions to monitor

### Phase 6 Behavior

**Startup:**
```python
{
    "scenario": "FRESH_START",
    "usd_balance": 5000.00,
    "crypto_pairs": {},  # Empty
    "reserve_usd": 1000.00,  # 20% of capital
    "deployment_budget": 4000.00,  # 80% ready to deploy
    "action": "READY_TO_TRADE",
    "signal_readiness": "WAITING_FOR_RSI+SENTIMENT"
}
```

**Trading Rules:**
1. Allocate $4,000 as deployment budget (80%)
2. Keep $1,000 as reserve (20%)
3. Wait for first RSI+sentiment entry signal
4. On first BUY signal: Deploy up to $200/pair across 4 pairs (or custom)
5. Start SL/TP monitoring immediately

**Checkpoint:**
```json
{
    "first_trade_timestamp": null,
    "positions": {},
    "unrealized_pnl": 0,
    "realized_pnl": 0
}
```

**Risk:** ⚠️ If entry signals are poor quality early, account could lose 5–10% before learning patterns. Mitigation: Start with conservative position sizing (50% of allocation in first week).

---

## Scenario 2: Takeover 1 (Partial Crypto)

### Account State
- **USD/USDC Balance:** ✅ Funded (e.g., $2,000)
- **Crypto Holdings:** ✅ Partial (e.g., 0.5 BTC, 10 ETH, 2000 DOGE)
- **Positions:** Unknown entry prices + entry dates
- **Valuation:** Some positions potentially underwater

### Use Case
- Migrating from manual trading or another bot
- Existing positions with unknown P&L
- Need to track SL/TP on inherited positions

### Phase 6 Behavior

**Startup:**
```python
{
    "scenario": "TAKEOVER_1",
    "usd_balance": 2000.00,
    "crypto_pairs": {
        "BTC-USD": {"qty": 0.5, "entry_price": null, "entry_date": null},
        "ETH-USD": {"qty": 10, "entry_price": null, "entry_date": null},
        "DOGE-USD": {"qty": 2000, "entry_price": null, "entry_date": null}
    },
    "current_prices": {"BTC": 74500, "ETH": 2300, "DOGE": 0.25},
    "current_valuations": {"BTC": 37250, "ETH": 23000, "DOGE": 500},
    "total_portfolio_usd": 62750.00,
    "action": "AUDIT_POSITIONS + RETRIEVE_ENTRY_DATA"
}
```

**Initialization Logic:**
1. Fetch current prices for all held crypto
2. Calculate unrealized P&L (if entry price known)
3. **If entry price UNKNOWN:**
   - Option A: Use current price as fallback entry (treats position as fresh entry)
   - Option B: Prompt user to provide historical entry prices
   - Option C: Use average price from Coinbase transaction history (API call)
4. Apply SL/TP immediately to all positions:
   - SL: -5% from entry (or current price if unknown)
   - TP: +10% from entry (or current price if unknown)
5. Reserve USD for margin/collateral (keep aside)

**Checkpoint:**
```json
{
    "inherited_positions": 3,
    "inherited_pnl_unrealized": 15000.00,
    "entry_prices_confirmed": 0,
    "entry_prices_estimated": 3,
    "sl_tp_applied": true,
    "monitoring_active": true
}
```

**Risk:** ⚠️ **CRITICAL** — If entry prices are wrong, SL/TP will misfire. 
- *Mitigation:* Always prompt user: "Found 0.5 BTC. Entry price? (or use current $74.5K as baseline)"
- *Fallback:* If user doesn't respond, use current price + log warning

---

## Scenario 3: Takeover 2 (Full Crypto, No USD)

### Account State
- **USD/USDC Balance:** ❌ $0
- **Crypto Holdings:** ✅ Funded (e.g., 0.5 BTC, 10 ETH, 5000 DOGE)
- **Positions:** Inherited, unknown entry prices
- **Total Portfolio Value:** Entirely in crypto ($60K+)

### Use Case
- Migrating from manual trading with profits already in crypto
- No USD buffer for new entries or collateral
- Need to rebalance to free up USD for trading

### Phase 6 Behavior

**Startup:**
```python
{
    "scenario": "TAKEOVER_2",
    "usd_balance": 0.00,
    "crypto_pairs": {
        "BTC-USD": {"qty": 0.5, "current_value_usd": 37250},
        "ETH-USD": {"qty": 10, "current_value_usd": 23000},
        "DOGE-USD": {"qty": 5000, "current_value_usd": 1250}
    },
    "total_portfolio_usd": 61500.00,
    "action": "DEPLOY_SELF-FUNDING + REBALANCE_FOR_FLOAT"
}
```

**Initialization Logic:**
1. Calculate total portfolio in USD
2. **Self-fund:** Designate 20% of portfolio as USD reserve
   - Example: $61.5K portfolio → $12.3K USD needed → Sell 0.16 BTC or 5.4 ETH
3. Execute tactical liquidation to free USD:
   - Sell from highest-correlation pair (reduce redundancy)
   - Use weekly rebalance logic to pick candidate
4. Remaining 80% becomes deployment capital + existing positions

**Checkpoint:**
```json
{
    "liquidation_executed": true,
    "btc_sold": 0.16,
    "usd_raised": 11920.00,
    "reserve_usd": 11920.00,
    "deployment_budget": 47600.00,
    "remaining_btc": 0.34,
    "monitoring_active": true
}
```

**Risk:** ⚠️ **EXTREME** — Market volatility during liquidation. If liquidation price is poor (-5%), you lose $600.
- *Mitigation:* Use limit orders instead of market orders. Wait for favorable RSI on pair to liquidate (e.g., sell when RSI > 70).

---

## Scenario 4: Ready to Start

### Account State
- **USD/USDC Balance:** ❌ $0
- **Crypto Holdings:** ❌ None
- **Reason:** Either fresh account with NO funding, or liquidated-to-cash state

### Use Case
- Deployed bot to account with zero capital
- Waiting for user to fund the account
- Emergency state (liquidated all positions)

### Phase 6 Behavior

**Startup:**
```python
{
    "scenario": "READY_TO_START",
    "usd_balance": 0.00,
    "crypto_pairs": {},
    "action": "BLOCKED_AWAIT_FUNDING",
    "monitoring": "ENABLED_READ_ONLY"
}
```

**Logic:**
1. **BLOCK trading execution** — No capital to trade with
2. **ENABLE read-only monitoring:**
   - Track price feeds
   - Calculate RSI + sentiment
   - Log signals to file (not executed)
   - Monitor account for incoming deposit
3. **Polling:** Check account balance every 5 min
4. **On deposit detected:** Transition to appropriate scenario (Fresh Start likely)

**Checkpoint:**
```json
{
    "status": "AWAITING_FUNDING",
    "polling_enabled": true,
    "signals_logged": true,
    "last_balance_check": "2026-04-20T07:24:00Z",
    "next_check": "2026-04-20T07:29:00Z",
    "reason": "zero_balance"
}
```

**Risk:** ❌ **NO TRADING RISK** — Bot is inert. Only risk is missing signals while waiting for funding.
- *Mitigation:* Log all signals to file so user can review after funding: "BTC would have BUY at $74.2K with RSI 32 + sentiment 0.65"

---

## Scenario 5: Bank Your Wins (Advanced)

### Account State
- **USD Balance:** Segregated into two buckets:
  - **YIELD_USD:** USDC earning 4–8% APY (rewards/staking vault)
  - **TRADING_USD:** Working capital for new entries
- **Crypto Holdings:** Tracked separately from interest earnings
- **Positions:** Active trades with SL/TP

### Use Case
- Profitable account looking to preserve wins
- Generate passive income from trading proceeds
- Reduce risk by keeping winners off the table

### Phase 6 Behavior

**Account Structure:**
```python
{
    "scenario": "BANK_YOUR_WINS",
    "buckets": {
        "yield_usdc": {
            "balance": 5000.00,
            "apy": 0.05,
            "vault": "lido_usdc",  # or compound, aave, etc.
            "monthly_interest": 20.83,
            "purpose": "PRESERVE_WINS"
        },
        "trading_usd": {
            "balance": 2000.00,
            "reserve_usd": 400.00,
            "deployment_budget": 1600.00,
            "purpose": "NEW_ENTRIES"
        }
    },
    "crypto_positions": {
        "BTC-USD": {"qty": 0.25, "pnl": "+2500"},
        "ETH-USD": {"qty": 5, "pnl": "+1200"}
    }
}
```

**Trading Rules:**
1. **New trades:** ONLY use trading_usd bucket (max $1,600 deployment)
2. **Winning trades:** On +10% TP hit, move proceeds to yield_usdc
   - Example: $1,000 entry → $1,100 exit → Move $1,100 to yield_usdc
3. **Losing trades:** On -5% SL hit, keep losses in trading_usd (draws from buffer)
4. **Monthly rebalance:** If yield_usdc > $10K, move to larger interest vault
5. **Quarterly harvest:** Claim interest from vault (typically auto-compounded)

**Checkpoint:**
```json
{
    "yield_usdc_earned_mtd": 20.83,
    "yield_usdc_earned_ytd": 125.00,
    "trades_banked_this_month": 3,
    "proceeds_banked": 3240.00,
    "trading_losses_absorbed": 1500.00,
    "net_flow_to_yield": 1740.00
}
```

**Risk:** ⚠️ Low — Interest is minimal (4–8% APY = ~$400/year on $5K).
- *Benefit:* Compounds over time; forces discipline (winners stay sequestered).

---

## Implementation Roadmap (by Scenario)

### Phase 5.1 (This Week)
- ✅ Scenario 1 (Fresh Start) — Primary target
- ✅ Scenario 4 (Ready to Start) — Fallback state

### Phase 6 MVP (Next 2 Weeks)
- ✅ Scenario 2 (Takeover 1) — Handle partial crypto
- ✅ Scenario 3 (Takeover 2) — Handle full crypto, no USD

### Phase 6.1 (Advanced)
- ✅ Scenario 5 (Bank Your Wins) — Vault integration + interest harvesting

---

## Initialization Checklist (Phase 6 Startup)

```python
def initialize_phase6_account():
    """Determine account scenario and apply correct rules."""
    
    # 1. Query account
    usd_balance = get_usd_balance()
    crypto_holdings = get_crypto_holdings()  # Returns {pair: qty}
    
    # 2. Determine scenario
    if usd_balance > 100 and not crypto_holdings:
        return FRESH_START
    elif usd_balance > 100 and crypto_holdings:
        return TAKEOVER_1
    elif usd_balance < 1 and crypto_holdings:
        return TAKEOVER_2
    elif usd_balance < 1 and not crypto_holdings:
        return READY_TO_START
    else:
        # Check for segregated buckets
        if has_yield_bucket() and has_trading_bucket():
            return BANK_YOUR_WINS
    
    # 3. Load scenario config
    config = load_scenario_config(scenario)
    
    # 4. Apply initialization rules
    apply_sl_tp(crypto_holdings)
    calculate_reserve_and_deployment(usd_balance)
    log_checkpoint(scenario, usd_balance, crypto_holdings)
    
    return READY_FOR_TRADING
```

---

## Validation & Guardrails

**Must-Pass Checks:**
- ✅ Reserve USD ≥ 20% of portfolio value
- ✅ Deployment budget ≤ 80% of portfolio value
- ✅ No position without SL/TP defined
- ✅ Entry prices validated or user-confirmed
- ✅ All legacy positions audited before trading new signals

**Warnings:**
- ⚠️ If entry price unknown → prompt user, don't guess
- ⚠️ If liquidation needed (Takeover 2) → use limit orders, not market
- ⚠️ If zero balance (Scenario 4) → read-only mode until funded

---

## Documentation Output

**For User:**
1. "Your account is in **TAKEOVER_1** state: 0.5 BTC + $2,000 USD. SL/TP applied. Ready to trade."
2. "Enter historic entry price for 0.5 BTC (or press ENTER to use current $74.5K)."
3. "Confirm liquidation: Sell 0.16 BTC to free up $12K USD reserve? (Y/N)"

**For Bot (Logs):**
```
[07:24:00] PHASE_6_INIT: Scenario=TAKEOVER_1
[07:24:01] USD_BALANCE: $2000.00
[07:24:02] CRYPTO_HOLDINGS: BTC=0.5, ETH=10, DOGE=2000
[07:24:03] ENTRY_PRICES: BTC=ASK_USER, ETH=UNKNOWN, DOGE=UNKNOWN
[07:24:04] SL_TP_STATUS: PENDING_ENTRY_CONFIRMATION
[07:24:05] RESERVE_USD: $400.00 (calculated)
[07:24:06] DEPLOYMENT_BUDGET: $1600.00 (calculated)
[07:24:07] STATUS: AWAITING_USER_INPUT
```

---

## Summary Table

| Scenario | USD | Crypto | Startup Action | Risk Level | Target Phase |
|----------|-----|--------|-----------------|-----------|--------------|
| **1. Fresh Start** | ✅ | ❌ | Deploy 80% | 🟡 Medium | 5.1 |
| **2. Takeover 1** | ✅ | ✅ | Audit + SL/TP | 🟡 Medium | 6 MVP |
| **3. Takeover 2** | ❌ | ✅ | Self-fund + Rebalance | 🔴 High | 6 MVP |
| **4. Ready Start** | ❌ | ❌ | Await Funding | 🟢 Low | 5.1 Fallback |
| **5. Bank Wins** | ✅ (Segregated) | ✅ | Vault + Yield | 🟢 Low | 6.1 Advanced |

---

**Document Status:** READY FOR PHASE 6 ARCHITECT & CODING BOT REVIEW ✅

Next: Code implementation per scenario + user prompts for each state.
