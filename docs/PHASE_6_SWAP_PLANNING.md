# Phase 6 Swap Strategy Planning

## Motivation: Tax Advantages

**Swaps vs. Sell/Buy:**
- **Sell/Buy:** Two taxable events (capital gains on each leg) → higher tax liability
- **Swaps:** Single taxable event (if any) → potential tax efficiency
- **Advantage:** Rebalancing without triggering gains → reduces tax burden

> Note: Not tax advice. Consult CPA for your jurisdiction.

## Coinbase Trade API Discovery

**Status:** CURSORY REVIEW COMPLETE (2026-04-20 14:51 PT)

Key findings from https://docs.cdp.coinbase.com/trade-api/welcome:
- ✅ **Supports native Coinbase wallets** (not just 3rd party)
- ✅ **3rd party wallet support** (viem, web3.py)
- ✅ **Multiple networks** (Ethereum, Base, Arbitrum, Optimism, Polygon)
- ✅ **Gas sponsorship** available
- ⏳ **Wallet authentication:** Requires deep dive (not yet understood)
- ⏳ **Integration path:** Needs research

**TODO:** Detailed documentation reading needed to understand:
1. How to authenticate/access native Coinbase wallets
2. API endpoints for token swaps
3. Integration with existing order_executor.py
4. Gas fee estimation

## Current Coinbase API Status

### v3 Advanced Trade API (Current)
- **Direct crypto-to-crypto swap:** ❌ NOT IN ADVANCED TRADE
- **USD ↔ USDC convert:** ✅ Available (v2 endpoint only)
- **Stablecoin conversions:** ✅ USD/USDC/PYUSD/EURC only
- **Limitation:** No BTC → ETH, BTC → USDC swaps via order book

### Trade API (Onchain) — The Swap Solution
- **Purpose:** DEX swaps on Ethereum, Base, Arbitrum, Optimism, Polygon
- **Auth:** ES256 JWT (same as Advanced Trade)
- **Features:** Slippage protection, gas optimization, arbitrage
- **Docs:** https://docs.cdp.coinbase.com/trade-api/welcome ✅ **BOOKMARK THIS**

### Alternatives for Phase 6

| Method | Tax Impact | Complexity | Phase |
|--------|-----------|-----------|-------|
| **Sell/Buy (order book)** | Capital gains on each leg | Low | 5.1 (NOW) |
| **Trade API swaps** | Single event (ideal) | Medium | 6 |
| **DeFi swap (Uniswap, etc.)** | Capital gains + gas fees | High | Future |
| **Wait for Coinbase native swap** | Best (if available) | TBD | TBD |

## Phase 6 Implementation Plan

### Near-term (Months 1-2)
- [ ] **DEEP RESEARCH: Trade API wallet integration**
  - Study: https://docs.cdp.coinbase.com/trade-api/welcome
  - Understand native Coinbase wallet access
  - Understand 3rd party wallet integration (viem/web3.py)
  - Understand authentication/gas sponsorship
  - Document findings
- [ ] Build dual-leg order handler (Sell BTC-USD, Buy ETH-USD atomically)
- [ ] Document tax implications per jurisdiction
- [ ] Implement swap request logging (for tax reporting)

### Medium-term (Months 3-6)
- [ ] Integrate Trade API swap endpoint
- [ ] Add swap cost analyzer (with gas fees for DeFi)
- [ ] Create tax report generator (cost basis tracking)

### Long-term (Months 6+)
- [ ] Multi-chain rebalancing (Ethereum, Arbitrum, Optimism)
- [ ] Portfolio optimization with tax-loss harvesting
- [ ] Smart order routing (best price across DEXes)

## Current Workaround (Phase 5.1)

**For now:** Use order book trading (sell/buy) — tax impact acceptable at this stage:
- Small portfolio ($1K)
- Early optimization phase
- Manual journal tracking sufficient

**Transition:** When Phase 6 rebalancing starts ($10K+), implement proper swap strategy.

## References

- **Coinbase Advanced Trade API:** https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/
- **Coinbase Trade API (Swaps):** https://docs.cdp.coinbase.com/trade-api/welcome ✅ **MAIN REFERENCE FOR PHASE 6**
- **Conversions API:** https://docs.cdp.coinbase.com/api-reference/v2/
- **Tax implications:** Consult local CPA (USA: Section 1031 may apply to like-kind exchange)

---

**Status:** PLANNING + TRADE API DISCOVERED
**Priority:** Medium (Phase 6)
**Owner:** @brad
**Last Updated:** 2026-04-20 14:51 PT
**Next Action:** Deep dive into Trade API wallet integration
