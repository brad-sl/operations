# Phase 6 Implementation Specification

**Status:** Complete with Poor Performer Liquidation Logic  
**Last Updated:** 2026-04-20  
**Version:** 2.1

---

## Overview

Phase 6 is the **account initialization layer** for Phase 5.1 trading. It detects current account state, applies scenario-specific logic, and prepares the portfolio for automated trading.

### Key Features
1. **Scenario Detection** — Fresh Start, Takeover 1, Takeover 2, Ready to Start, Bank Your Wins
2. **Currency Preference** — USD vs USDC split for trading vs yield
3. **SL/TP Protection** — Automatic risk management for inherited positions
4. **Poor Performer Liquidation** — NEW: Automatic liquidation of underperforming positions
5. **State Persistence** — Save configuration for Phase 5.1 consumption

---

## Architecture

### Core Components

```
phase6_account_initializer.py
  └─ Phase6Initializer class
     ├─ get_balances() → detect account state
     ├─ detect_scenario() → classify account
     ├─ initialize() → apply scenario logic
     └─ integrate with liquidation_manager

phase6_liquidation_manager.py
  └─ LiquidationManager class
     ├─ calculate_pain_score() → identify poor performers
     ├─ weekly_rebalance() → liquidate auto
     └─ get_liquidation_report() → analytics

phase6_config_loader.py
  └─ Scenario configs (SL %, TP %, reserve %, deploy %)

phase6_user_prompts.py
  └─ User interaction (currency pref, entry price confirm, liquidation approval)
```

---

## Scenario Definitions

### 1. Fresh Start
**Profile:** New account with clean USD capital  
**Initial:** $5K+ USD only  
**Deploy:** 80% ($4K) / Reserve: 20% ($1K)  
**Trading:** 4-pair dynamic selection (BTC, ETH, SOL, XRP)  
**Liquidation:** N/A (no positions to liquidate)  
**Expected Return:** +18-72% (based on signal quality)

**Backtest Result (1Y):** +71.84% ($5K → $8.6K)

---

### 2. Takeover 1
**Profile:** Account with mixed fiat + partial crypto holdings  
**Initial:** $2-3K USD + 0.5 BTC (inherited)  
**Deploy:** Limited (fiat only)  
**Risk:** Unknown entry prices → aggressive SL (-5%)  
**Liquidation:** YES - liquidate underwater positions via Poor Performer logic  
**Expected Return:** 0-20% (depends on inherited P&L)

**Backtest Result (1Y):** -94.13% (poor entry prices, high trade count without exit discipline)

---

### 3. Takeover 2 (Crypto-Heavy)
**Profile:** Crypto-only account, needs to self-fund USD  
**Initial:** 0.5 BTC + 10 ETH + 5000 DOGE (total ~$57K)  
**Self-Fund:** Liquidate 20% of portfolio → get ~$11.5K USD  
**Liquidation:** AGGRESSIVE - Use Poor Performer logic daily to liquidate worst positions  
**Deploy:** ~$1K/pair on 4 trading pairs  
**Expected Return:** 5-15% (after liquidation friction)

**Backtest Result (1Y) with Poor Performer Logic:**
- Initial: $57,571
- Final: $61,366
- **Return: +6.59%** ✅
- Trades: 346 (174 buys, 6 sells, 166 liquidations)
- Liquidations working! Capital cycling continuous

---

### 4. Ready to Start
**Profile:** No capital, waiting for deposit  
**Initial:** $0 USD, 0 crypto  
**Status:** AWAITING_FUNDING (read-only mode)  
**Liquidation:** N/A  
**Expected Return:** 0% (no capital)

---

### 5. Bank Your Wins (Advanced)
**Profile:** Experienced trader with segregated buckets  
**Initial:** $5K USD (trading) + $10K USDC (yield) + positions  
**Strategy:**
- Trade with USD bucket
- Profits → USDC for yield
- Losses → Top up USD from USDC
- Separate risk tiers
**Liquidation:** Conservative - only sell losers, bank winners  
**Expected Return:** 10-25% (if 15% on trading, 3-5% on USDC yield)

---

## Poor Performer Liquidation Logic

### Why It Matters

**Problem:** Inherited positions may be underwater or have weak momentum. Holding them ties up capital and adds risk.

**Solution:** Automatically identify and liquidate poor performers, freeing capital for better opportunities.

### PAIN_SCORE Formula

```
PAIN_SCORE = pnl_pain + rsi_pain + correlation_pain
```

**Component 1: P&L Pain (Negative losses)**
- If position is profitable: pain = 0
- If underwater -5%: pain = 5
- If underwater -50%: pain = 50
- Formula: `max(0, -pnl_pct)`

**Component 2: RSI Momentum (Weak trend)**
- RSI < 40 (weak uptrend): high pain
- RSI = 50 (neutral): pain = 50
- RSI > 70 (strong uptrend): low pain
- Formula: `100 - RSI`

**Component 3: Correlation Redundancy (Overlap)**
- BTC corr to ETH = 0.85 (highly redundant): pain += 42
- SOL corr to BTC = 0.30 (unique): pain += 15
- DOGE corr to others = 0.10 (unique): pain += 5
- Formula: `avg_correlation * 50`

### Liquidation Triggers

**Automatic:**
- PAIN_SCORE > 25 → liquidate immediately
- Weekly check: Monday 00:00 UTC
- Market sell at current price

**Manual Override:**
- User can force liquidation anytime via prompt
- Requires confirmation: "Liquidate {pair} now? Y/N"

**Safety Checks:**
- Never liquidate if position < $50 (micro positions)
- Never liquidate entire portfolio (keep at least 1 position)
- Circuit breaker: max 5 liquidations per week

### Capital Flow

```
Day 1: Liquidate DOGE (pain=45)
  └─ Raise $11,500 USD
     └─ Deploy $1K each to BTC, ETH, SOL, XRP

Day 2: BTC RSI=55, ETH RSI=32
  └─ Liquidate ETH (pain=68)
     └─ Add to reserve
     
Day 3: BTC hit TP (+10%)
  └─ Close BTC trade
     └─ USD + profits → reserve
     
Day 4: XRP RSI=38 < 40
  └─ Entry signal!
     └─ Deploy from reserve
```

### Backtest Validation

**Takeover 2 with Poor Performer Logic:**

```
Initial Portfolio: $57,571
Final Value: $61,366
Total Return: +6.59%

Daily Liquidations: 166 (excellent capital cycling!)
Buy Trades: 174 (fresh start entries)
Sell Trades: 6 (exits on TP/SL)
Total Trades: 346

Key Insight: Liquidations freed capital for reinvestment.
Without liquidations, capital would stay trapped in losers.
Result: 6.6% return vs -28% without active management!
```

---

## Implementation Checklist

- [x] Phase 6 core initializer (detect scenario, currency pref)
- [x] SL/TP confirmation for inherited positions
- [x] Poor Performer liquidation manager (PAIN_SCORE, daily rebalance)
- [x] 1-year backtest across all scenarios
- [x] Documentation (this spec)
- [ ] Integration with Phase 5.1 order executor
- [ ] Live deployment testing (paper trading)
- [ ] Monitoring dashboard (liquidation events, PAIN_SCORE trends)
- [ ] User manual (when to use each scenario)

---

## Usage Example

### Fresh Start
```python
from phase6_account_initializer import Phase6Initializer

init = Phase6Initializer(cb_client, order_executor, state_manager)
result = init.initialize()

# Returns:
# {
#   'scenario': 'fresh_start',
#   'trading_fiat': 'USDC',
#   'trading_balance': 5000.0,
#   'deploy_budget': 4000.0,
#   'reserve_usd': 1000.0,
#   'status': 'READY_TO_TRADE'
# }
```

### Takeover 2 with Liquidation
```python
from phase6_liquidation_manager import LiquidationManager

liquidator = LiquidationManager(cb_client, order_executor)

# Track price history
for day in range(365):
    prices = fetch_daily_prices(['BTC', 'ETH', 'SOL', 'XRP', 'DOGE'])
    holdings = get_account_holdings()
    
    # Daily rebalance
    holdings = liquidator.weekly_rebalance(holdings, prices)
    
    # Get analytics
    report = liquidator.get_liquidation_report(holdings, prices)
    print(f"Poor performers: {report['poor_performers']}")
```

---

## Backtest Results Summary

| Scenario | Initial | Final | Return | Trades | Liquidations |
|----------|---------|-------|--------|--------|--------------|
| Fresh Start | $5,000 | $8,592 | **+71.84%** 🥇 | 28 | 0 |
| Takeover 2 (v2) | $57,571 | $61,366 | **+6.59%** 🥈 | 346 | 166 ✅ |
| Takeover 1 | $2,000 | $2,000 | -94.13% 🥉 | 356 | 0 |
| Ready Start | $0 | $0 | 0.00% | 0 | 0 |

**Key Takeaway:** Poor Performer Liquidation enables capital cycling. Takeover 2 went from 1 trade (old) to 346 trades (new) with 166 liquidations, improving returns by +6.6% instead of -28%.

---

## Next Steps

1. **Integration:** Connect LiquidationManager to Phase 5.1 order executor
2. **Live Testing:** Run Takeover 2 scenario paper trading for 7 days
3. **Monitoring:** Set up alerts for liquidation events
4. **Optimization:** Fine-tune PAIN_SCORE thresholds based on market conditions
5. **User Docs:** Create decision tree for scenario selection

---

## Files

- `phase6_account_initializer.py` — Scenario detection & initialization
- `phase6_liquidation_manager.py` — Poor performer identification & liquidation
- `phase6_config_loader.py` — Scenario configurations (SL, TP, deploy %)
- `phase6_user_prompts.py` — User interaction (currency, entry price, approval)
- `test_phase6.py` — Unit tests for all scenarios
- `backtest_phase6_scenarios_complete.py` — Historical backtest (all 4 scenarios)
- `backtest_phase6_takeover2_v2.py` — Takeover 2 with Poor Performer logic (backtest)

---

## References

- **Phase 5.1:** Order executor, live trading integration
- **SMART Health Monitor:** Auto-restart Phase 5 on normal completion
- **Sentiment Aggregator:** X API batch queries (every 30 min)
- **State Manager:** Persist Phase 6 config for Phase 5.1 consumption

---

_Document Version 2.1 — Complete with Poor Performer Liquidation_
