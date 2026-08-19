# LEGAL / REGULATORY ANALYSIS — ARCH Automation (Multi-Trader Platform)

**Date:** 2026-07-16
**Product:** ARCH Automation — SaaS subscription providing automated trading software that connects to user's own Coinbase Advanced account via OAuth.
**Status:** Pre-public paid analysis. **This document does not constitute legal advice.** Engage qualified securities/crypto counsel before public checkout.

---

## 1. Product Structure (for Regulatory Analysis)

| Layer | Description | Regulatory Relevance |
|-------|-------------|---------------------|
| The software | Trading automation workers (rebalancing, stop-loss, allocation) running on platform infrastructure | Not a fund — software access only |
| User connection | OAuth2 grant to user's own Coinbase Advanced account | User retains custody; platform never holds assets |
| Billing | GoHighLevel SaaS subscriptions — monthly fee for software access | No "performance fees" or profit-sharing |
| Marketing | Process claims, OAuth safety, no performance guarantees | No investment advice, no guaranteed returns |
| User onboarding | GHL funnel → checkout → OAuth connect → green runner_health | Self-directed; user configures own account |

**Key regulatory framing (non-negotiable):** ARCH Automation sells **software access**, not investment advice, custody, or pooled fund management. Users authorize the software to act on their own Coinbase account within defined scopes (trade, view — **no transfer** scope). The platform never holds user funds, never pools capital, and never guarantees returns.

---

## 2. Broker-Dealer Analysis (Securities Exchange Act of 1934 §15(a))

### 2.1 The question
Does ARCH Automation's software constitute a "broker" under Section 3(a)(4) of the Exchange Act — i.e., "any person engaged in the business of effecting transactions in securities for the account of others"?

### 2.2 Analysis
- **What is a "security"?** Most cryptocurrencies are not securities under SEC guidelines (Bitcoin, Ethereum). However, some tokens traded on Coinbase Advanced may be securities under Howey Test analysis. The CFTC treats Bitcoin and Ethereum as commodities.
- **"Effecting transactions for the account of others":** The software places trades on the **user's own account** via OAuth. The user controls which account is connected, what tiers/caps are set, and can revoke access at any time. The platform does not:
  - Solicit trades or recommend specific securities
  - Handle customer funds or securities
  - Receive transaction-based compensation (fees are flat SaaS subscription, not % of trade)
  - Exercise discretion over which specific assets to trade (user's config defines pairs and limits)
- **Software vs. broker:** Courts have distinguished between software tools that enable users to execute their own trades (automated execution tools) and brokers that effect transactions for others. The key factor is **discretion and control** — this software is rule-based within user-defined parameters.

### 2.3 Conclusion
**Low risk** of broker-dealer registration requirement, provided:
- No human discretion over individual trades
- No transaction-based compensation (commissions, spreads, performance fees)
- No holding or custody of customer assets
- No solicitation of specific securities transactions
- Clear disclaimers that the software is a tool, not a broker or advisor

### 2.4 Mitigations
- Flat subscription pricing only (no % of AUM, no trade-based fees)
- User configures all trading parameters (pairs, caps, risk levels)
- No "recommended portfolios" or "expert picks" without regulatory review
- Terms of Service explicitly state: "Software does not provide investment advice or execute trades at our discretion"

---

## 3. Commodity Trading Advisor (CTA) / Commodity Pool Operator (CPO) Analysis (CEA / CFTC)

### 3.1 CTA — The question
Does ARCH Automation constitute a "commodity trading advisor" under Section 1a(14) of the Commodity Exchange Act — i.e., provide advice regarding trading in commodity interests (including crypto derivatives like Bitcoin futures)?

### 3.2 CTA analysis
- **Crypto spot trading:** The CFTC has stated that Bitcoin and Ethereum are commodities. However, the CTA definition excludes "the publication of data or news" and "the dissemination of market information." Software that executes user-defined rules may not constitute "advice."
- **Key factors:**
  - The software does not provide **advice** — it executes user-configurable rules.
  - The software does not claim to predict markets or recommend specific trades.
  - Compensation is flat subscription, not tied to trading performance.
  - The software does not hold itself out as a trading advisor.
- **Derivatives:** If the platform only supports spot trading (which it does — Coinbase Advanced spot pairs), the CTA analysis is less relevant. If futures or options are added later, this changes.

### 3.3 CPO — The question
Does ARCH Automation operate a "commodity pool" — i.e., an investment vehicle where multiple participants pool capital for trading commodities?

### 3.4 CPO analysis
**No.** Key facts:
- Each user trades their **own** Coinbase account with their **own** capital.
- No pooling of funds between users.
- No entity-level trading account that aggregates user capital.
- No profit/loss sharing between users.
- Each user has independent OAuth access to their own account.

### 3.5 Conclusion
**Low risk** of CTA/CPO registration, provided:
- No pooled accounts or aggregated capital
- No performance-based compensation
- Spot trading only (no futures, options, or derivatives)
- No advice or recommendations
- Clear "software tool, not advisor" framing

### 3.6 Mitigations
- Explicitly state in all materials: "You trade your own account. We do not pool funds or make trading decisions on your behalf."
- No futures, options, or leveraged tokens in the product (at least without additional analysis)
- No "managed account" or "advisory" language

---

## 4. Money Transmitter / State Licensing Analysis

### 4.1 The question
Does ARCH Automation engage in "money transmission" under state laws (e.g., NY BitLicense, CA MTA, or state money transmitter acts)?

### 4.2 Analysis
- **Money transmission generally defined:** Receiving money or monetary value for transmission, or selling/issuing payment instruments.
- **Key factors:**
  - The platform never receives, holds, or transmits customer funds.
  - All funds remain in the user's Coinbase account at all times.
  - The software only places trade orders on the user's behalf via OAuth.
  - Payments are for SaaS subscription (software access), not for money transmission.
  - Coinbase holds the funds and executes the trades — Coinbase is the licensed money transmitter.

### 4.3 Conclusion
**Low risk** of money transmitter classification, provided:
- Platform never holds, receives, or transmits user funds
- No "wallet" or "custody" functionality
- Users pay for software subscription, not for transmission services
- Coinbase handles all custody and transmission

### 4.4 Mitigations
- No custodial wallets on the platform
- No ability for users to deposit funds to the platform
- All payments go through GHL/Stripe for software subscription only
- Terms explicitly state: "Funds remain in your Coinbase account. We do not custody, transmit, or hold your cryptocurrency."

---

## 5. SEC Investment Adviser Analysis (Investment Advisers Act of 1940 §202(a)(11))

### 5.1 The question
Does ARCH Automation constitute an "investment adviser" — i.e., provide advice, analyses, or reports concerning securities for compensation?

### 5.2 Analysis
- **Software vs. advice:** Automated tools that execute user-defined rules have generally been distinguished from advisory services. The software does not:
  - Provide personalized investment advice
  - Recommend specific securities
  - Hold itself out as providing advisory services
  - Charge fees based on AUM
- **Robo-advisor precedent:** True robo-advisors (Betterment, Wealthfront) register as investment advisers because they provide personalized portfolio recommendations and ongoing advice. ARCH Automation is a **rule-based execution tool**, not a robo-advisor.

### 5.3 Conclusion
**Low risk** if:
- No personalized recommendations or advice
- User configures all parameters
- No AUM-based fees
- Clear disclaimers: "We are not an investment adviser"

### 5.4 Mitigations
- No "portfolio recommendations" or "suggested allocation" features without regulatory analysis
- User must explicitly configure trading parameters
- All educational content is general (not personalized)
- Subscription fee is flat, not AUM-based

---

## 6. State-by-State Considerations

### 6.1 Approach
- **Default: US-only pilot** per ICP. Individual states may have specific requirements.
- **California:** Strong investor protection laws. No issues if no money transmission or advisory.
- **New York:** BitLicense requirement for "virtual currency business activity." ARCH Automation likely does not meet the definition because it does not receive, hold, transmit, or store virtual currency. However, any New York residents should be flagged for counsel review.
- **State money transmitter laws:** As discussed above, low risk if no custody or transmission.

### 6.2 Recommendation
- Start with national US availability (excluding any state flagged by counsel).
- If New York residents are targeted, obtain specific NY counsel review of BitLicense applicability.
- Monitor state-level developments in crypto regulation.

---

## 7. FCRA / Data Privacy Analysis

### 7.1 Fair Credit Reporting Act
- Not applicable — ARCH Automation does not collect consumer credit information or provide credit reports.

### 7.2 State Privacy Laws (CCPA, CPRA, etc.)
- **Applicable if:** ARCH Automation collects personal information from California residents (which it will — name, email, payment info, Coinbase account connection).
- **Requirements:**
  - Privacy Policy disclosing categories of personal information collected, sources, purposes, and third-party sharing.
  - Right to know, delete, and opt out of sale/sharing.
  - **Note:** ARCH Automation does not "sell" personal information for monetary or other valuable consideration.
- **Mitigation:** Standard B2B/SaaS privacy policy covering CCPA rights. No sale of personal data.

### 7.3 GDPR (if EU users are on-boarded)
- Not applicable if US-only at launch. If EU expansion is planned, GDPR compliance (DPA, data processing agreement, consent mechanisms) will be required.

---

## 8. Securities Law — Marketing / Advertising Considerations

### 8.1 SEC Rule 206(4)-1 (Marketing Rule)
- Applies to registered investment advisers. Not applicable if ARCH Automation is not an investment adviser.
- **Best practice:** Even if not subject to the rule, adopt its principles:
  - No false or misleading statements
  - No testimonials presented without required disclosures
  - No cherry-picked performance
  - Fair and balanced presentation of risks

### 8.2 FINRA Rules
- Applies to broker-dealers. Not applicable if ARCH Automation is not a broker-dealer.
- **Best practice:** Adopt advertising principles:
  - Clear, balanced, not misleading
  - Risk disclosure prominent
  - No guarantees or exaggerated claims
  - No prediction of future performance

### 8.3 CFTC Rules (if applicable)
- Applies to CTA/CPO. Not applicable if not CTA/CPO.
- **Best practice:** If crypto derivatives are added later, CFTC disclosure requirements will apply.

---

## 9. Specific Risks to Flag in Marketing

Based on the above analysis, the following must be prominently disclosed:

1. **Cryptocurrency trading risk:** Substantial risk of loss; past performance not indicative of future results.
2. **Non-custodial:** ARCH Automation does not custody, hold, or transmit user funds.
3. **Software-only:** ARCH Automation is not a broker, dealer, investment adviser, or money transmitter.
4. **No guarantees:** The software does not guarantee profits, prevent losses, or predict market movements.
5. **OAuth scope:** The platform has view + trade scope only; no transfer scope (unless explicitly added later).
6. **Coinbase dependency:** The platform depends on Coinbase availability and API access; service interruptions may affect trading.
7. **User responsibility:** The user is responsible for configuring their trading parameters and reviewing their account activity.

---

## 10. Recommended Counsel Engagement

### 10.1 Required before public paid checkout
- [ ] Confirm analysis above with qualified securities/crypto counsel
- [ ] Review draft Terms of Service
- [ ] Review draft Privacy Policy
- [ ] Review Risk Disclosures
- [ ] Review marketing copy (landing page, checkout, email sequences)
- [ ] Specifically address: (a) broker-dealer analysis, (b) CTA/CPO analysis, (c) state money transmitter analysis, (d) state-specific requirements

### 10.2 Counsel profile
- Experience with crypto/fintech regulatory matters
- Knowledge of SEC, CFTC, and state regulatory frameworks
- Recommended: crypto-native law firm (e.g., Perkins Coie, Hogan Lovells, Sullivan & Cromwell) or specialized fintech boutique

### 10.3 Estimated timeline
| Phase | Activity | Duration |
|-------|----------|----------|
| 1 | Counsel engagement and document handoff | 1 week |
| 2 | Initial review of product structure and legal analysis | 2 weeks |
| 3 | ToS/Privacy/Risk disclosure review and revision | 2 weeks |
| 4 | Marketing copy review | 1 week |
| 5 | Final sign-off | 1 week |
| **Total** | | **~7 weeks** |

---

## 11. Document Control

| Version | Date | Author | Notes |
|---------|------|--------|-------|
| 1.0 | 2026-07-16 | Legal Department | Initial regulatory analysis for pre-public paid review |

**Canonical path:** `docs/marketing/LEGAL_ANALYSIS.md`
**Related:** `docs/marketing/TERMS_OF_SERVICE.md`, `docs/marketing/PRIVACY_POLICY.md`, `docs/marketing/RISK_DISCLOSURES.md`, `docs/marketing/CLAIMS_SCREENSHOT_POLICY.md`, `docs/epics/SCALING_1000_UNIFIED_ROADMAP.md`

*This document is for internal planning purposes only and does not constitute legal advice. Engage qualified counsel before making any public offering.*