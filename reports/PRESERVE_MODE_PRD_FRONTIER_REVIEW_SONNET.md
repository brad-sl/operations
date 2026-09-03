# Independent Adversarial Review — Preserve Mode PRD (Sonnet-4)

**Date:** 2026-08-01  
**Status:** REVIEW COMPLETE  
**Reviewer:** Claude Sonnet-4 (independent session)  
**Primary target:** `docs/research/PRESERVE_MODE_PRD.md`  
**Evidence cross-checked:**  
- `data/state/paxg_drawdown_anatomy.json`  
- `reports/USD_HOLD_CONTINGENCY_BACKTEST_2026-08-01.md`  
- `docs/research/USD_HOLD_VALUE_CONTINGENCY_POLICY.md`  

**Independence note:** Fresh session, no prior exposure to other reviews. Pure adversarial stance against the PRD as written.

---

## Verdict

### **block-until-fundamentals-fixed**

The core thesis — size-controlled ballast with exchange protection — has merit. But the PRD suffers from **architecture contradictions** and **unproven dependencies** that would ship a fragile product masquerading as safety. The defaults are backwards, the math doesn't add up under realistic scenarios, and critical assumptions remain untested.

**Shadow only after:** venue probe confirms multi-stop viability, economics re-run with realistic ladder paths, and equity definitions debugged.

---

## Rights

What the PRD correctly identifies:

1. **Problem definition:** Pure USDC park creates alt-nibble temptation while losing real value 
2. **Sizing philosophy:** 20% ceiling means manageable account impact even in severe gold crashes
3. **Exchange-first safety:** Kill-bot resilience over notify-theater  
4. **Sleeve separation:** Crypto PnL ≠ gold MTM prevents scorecard confusion
5. **Truth in marketing:** No "risk-free" claims, explicit volatility warnings
6. **Backtest honesty:** Static hold ≠ ladder performance; admits gap

The behavioral thesis (reduce alt temptation during park) is probably the strongest argument for the feature.

---

## P0 Blind Spots

### Economic Reality Mismatch
The **fundamental problem:** PRD promotes "DeRisk ladder" while its own data shows this would have **locked in maximum losses** during the measured worst path.

- **Evidence:** 2026 gold crash: -28.1% peak-to-trough  
- **DeRisk S3:** Triggers at -26%, selling ~98% of position  
- **Result:** Converting paper loss to realized loss **2% before the bottom**

This isn't "de-risking" — it's **algorithmic capitulation** at exactly the wrong moment. The PRD knows this but buries it in footnotes while still offering DeRisk as a "profile choice."

### Backtest Fraud (Unintentional)
The economic justification cites static 20% PAXG returning +8.947% over 18 months. **But this backtest assumes HOLDING the gold**, not selling it in tranches during drawdowns.

The PRD offers no simulation of:
- S1/S2/S3 ladder performance during the actual measured paths
- Transaction costs from staged exits  
- Re-arming dynamics and timing luck
- Opportunity cost of sitting in cash after stages fire

**Red flag:** Success metrics lean on "static hold" while shipping a "staged exit" product.

### Venue Dependency Hell
The entire L1 pitch ("bot can be dead, exchange still protects") **completely depends** on Coinbase supporting 2-3 concurrent stop orders on PAXG-USD. This is **not confirmed**.

**If false:** Product becomes either S3-only (different risk profile) or bot-dependent stages (contradicts safety claims).

**If true:** Still need to handle partial fills, order sizing after previous stages, and gap risk.

No venue probe = no product. The PRD lists this as "open question" — should be **gate 1**.

---

## P1 Design Flaws

### State Machine Chaos
The interaction between PARK → PRESERVE → DEPLOY and the crypto sleeve is underspecified:

- When crypto crashes during Preserve: does gold auto-buy more? (equity definition unclear)
- When Deploy mode activates: cancel protection orders first or trim gold first? Race conditions
- What happens if protective orders get cancelled by non-Preserve code paths?

### Stop Loss Philosophy Incoherence  
Crypto sleeve keeps 3% adaptive SL (good for volatile assets with alpha potential).  
Gold sleeve has deep -32% emergency stop (appropriate for ballast).  
**But:** DeRisk S1 at -12% is tighter than many crypto positions. Why does "safety" get more aggressive risk management than "speculation"?

### Gold ≠ Cash Confusion
PRD correctly says "gold is not cash" but then designs entry/exit triggers around **crypto regime timing**. If gold is meant to be ballast, why does BTC bear/bull determine its lifecycle?

Either gold is:
- **Independent ballast** (set and forget, deep stops only)
- **Tactical allocation** (crypto-timed, accept trading costs)

The PRD tries to be both and succeeds at neither.

---

## P2 Secondary Issues

### Exchange Ladder Critique
Even if Coinbase supports multi-stops:
- Stop-limit gaps on potentially thin PAXG books
- HWM trail mechanics unclear when bot restarts  
- Partial fill handling that doesn't oversell remaining inventory
- Blast radius from crypto "cancel all protective orders"

### Economics Honesty
The 18m +8.9% vs USDC4% +6.1% is a **2.8% premium** over 18 months. After:
- Trading fees (0.2% RT × multiple stages)  
- Tax drag from short-term capital gains on stages
- Timing luck on re-arming

The **economic edge may be marginal or negative**. The real value prop is behavioral (less alt temptation), not mathematical alpha.

### Product Claims
Despite "truth box," the PRD still positions Preserve as "safety sleeve" and "ballast." Real ballast doesn't have staged exit ladders — that's **active management masquerading as safety**.

---

## Concrete PRD Patches

### 1. Fix Default Profile
**Current:** Hold = default, DeRisk = opt-in  
**Should be:** Only Hold until DeRisk economics proven separately  
**Better:** Remove DeRisk entirely from v1; deep emergency stop only

### 2. Honest Economics Section
Add section: "Expected Returns vs USDC+APY"
- 18m edge ≈ 2.8% before costs
- 12m edge ≈ 0% 
- **Primary benefit: behavioral** (reduce alt temptation during park)
- **Not:** compound outperformance guarantee

### 3. Equity Definition Debug
```
preserve_equity_base = 
  USDC_available_to_bot + 
  MTM_preserve_PAXG_only + 
  EXCLUDE(crypto_inventory_MTM, pending_orders_collateral)
```
Must not auto-buy gold just because crypto crashed.

### 4. Venue Probe Gate
**Gate 1:** Prove concurrent stop support before any code  
**Fallback B:** Document resilience downgrade if single-stop-only  
**Fallback C:** Block Preserve if stops don't work reliably

### 5. State Machine Clarity
```
PARK → PRESERVE arm checks:
  - crypto_util <= 30% (not still averaging down)
  - cash_available >= min_notional
  - venue_probe_passed = true

PRESERVE → DEPLOY transition:
  - cancel_protection_orders() FIRST
  - trim_ballast() SECOND  
  - clear_preserve_flags() LAST
```

---

## Test Gaps

### Pre-Shadow Requirements
1. **Venue probe:** Live test 2-3 concurrent PAXG stops on Coinbase
2. **Ladder backtest:** Simulate S1/S2/S3 on actual 2022 and 2026 paths
3. **Kill-bot test:** Confirm exchange orders survive bot death
4. **Blast radius test:** Crypto protective cancel leaves gold orders intact

### Economic Reality Check
Re-run backtest with:
- Realistic DeRisk ladder fills during actual drawdown paths
- Transaction costs (0.2% RT)
- Re-arm timing and lockout periods  
- Compare to USDC+4% APY baseline honestly

---

## Open Questions Before Code

1. **Is the product ballast or trading strategy?** Pick one.
2. **Coinbase PAXG liquidity:** Can it handle $500-2000 clips without meaningful slippage?
3. **Tax implications:** Short-term gains from stages vs hold strategy
4. **Why not just increase USDC park and call it success?** (Behavioral benefit worth complexity?)
5. **Multi-tenant:** How do sleeves work with shared Coinbase portfolio?

---

## What NOT To Do

### Don't Ship Theater
- No "bot-down safe" claims until venue probe confirms multi-stop support
- No DeRisk profile until ladder economics proven independently  
- No "safety" marketing until deep stop behavior matches safety philosophy

### Don't Confuse Categories  
- Ballast has deep stops and sits still
- Trading strategies have active management  
- Pick one; don't hybrid into complexity

### Don't Fake Economics
- USDC+APY is the real benchmark (not USDC+0%)
- Static backtest ≠ ladder backtest
- Behavioral benefits ≠ mathematical alpha

### Don't Rush Implementation
The PRD has good bones but architectural blind spots that will ship bugs. Venue probe and economics debug **before** any code enthusiasm.

---

## Summary

The PRD identifies a real problem (park boredom leads to alt mistakes) and proposes a reasonable solution framework (sized ballast with exchange protection). But the execution details are backwards:

- **DeRisk ladder would sell ballast into the measured worst crash**
- **Economic justification assumes static hold while shipping staged exit**  
- **Critical venue dependencies remain unproven**

Ship **Hold-only** with deep stop after venue probe, or don't ship at all. The current "DeRisk default" would systematically realize losses at maximum pain points — the opposite of ballast behavior.

Fix the math, prove the venue, then shadow. The behavioral thesis is worth pursuing, but not with backwards defaults and unproven infrastructure.