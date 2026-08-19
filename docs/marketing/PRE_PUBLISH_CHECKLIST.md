# PRE-PUBLISH CLAIM CHECKLIST — ARCH Automation

**Version:** 1.0 (Draft — Subject to Legal Review)
**Date:** 2026-07-16
**Purpose:** Run this checklist before publishing any marketing asset — landing page, checkout, email, SMS, social, ad, affiliate material, or partner communication.

**Not this checklist:** Engineering security, authz/RLS, secrets, rate limits, and data-handling posture before a **public URL or real users** — use the shared gate:
`/home/brad/projects/_shared/security/PUBLIC_EXPOSURE_SECURITY_PRIVACY_CHECKLIST.md`
(Hermes skill: `public-exposure-security-review`). Run **both** when shipping a public product funnel.

---

## Instructions

1. Print or open this checklist for each new asset before publishing.
2. Check every item. If any item is "No" or "N/A without justification," the asset must not be published until fixed.
3. Sign off at the bottom and file in the Message Approval Log.

---

## Section A: Performance Claims

| # | Check | Pass | Fail | N/A | Notes |
|---|-------|:----:|:----:|:---:|-------|
| A1 | Contains no guaranteed returns language ("guaranteed," "risk-free," "safe," "no downside") | | | | |
| A2 | Contains no fixed-percentage ROI claims ("X% monthly," "earn X%") | | | | |
| A3 | Contains no "AI never loses" or similar invincibility claims | | | | |
| A4 | Contains no invented backtest numbers or simulated performance | | | | |
| A5 | Contains no "average user" performance claims | | | | |
| A6 | Contains no cherry-picked time periods to exaggerate returns | | | | |
| A7 | Contains no personal P&L screenshots (Brad's or any individual) | | | | |

**If ANY of A1-A7 is "Fail," stop here. Asset must be fixed before further review.**

---

## Section B: Business Model Claims

| # | Check | Pass | Fail | N/A | Notes |
|---|-------|:----:|:----:|:---:|-------|
| B1 | Software/subscription framing is clear (not a fund, not advisory) | | | | |
| B2 | Non-custodial stated where money/funds are discussed | | | | |
| B3 | No custody claims ("deposit with us," "we hold your funds") | | | | |
| B4 | No advisory claims ("let us manage," "we advise") | | | | |
| B5 | No fund language ("pool," "fund," "managed account," "performance fee") | | | | |
| B6 | No exchange confusion ("built-in exchange" — we are software on Coinbase) | | | | |
| B7 | No API key solicitation (OAuth only; no "paste your API key") | | | | |

---

## Section C: Regulatory Compliance

| # | Check | Pass | Fail | N/A | Notes |
|---|-------|:----:|:----:|:---:|-------|
| C1 | Always-On Disclaimer present (footer on pages, checkout, email footer) | | | | |
| C2 | Always-On Disclaimer visible without scrolling (landing pages) | | | | |
| C3 | Always-On Disclaimer immediately above confirm/pay button (checkout) | | | | |
| C4 | Risk language present ("Cryptocurrency trading involves substantial risk of loss") | | | | |
| C5 | Past performance disclaimer present ("Past performance is not indicative of future results") | | | | |
| C6 | "We do not provide investment advice" statement present | | | | |
| C7 | "We do not guarantee profits" statement present | | | | |
| C8 | "Subscription fees are for software and service access only" statement present | | | | |

---

## Section D: Technical Accuracy

| # | Check | Pass | Fail | N/A | Notes |
|---|-------|:----:|:----:|:---:|-------|
| D1 | OAuth described accurately (scopes: view + trade; no transfer scope unless true) | | | | |
| D2 | Tier limits match platform config templates (Starter/Pro/Elite caps) | | | | |
| D3 | Connect process described accurately (OAuth link, not manual key entry) | | | | |
| D4 | Coinbase dependency stated (we are software on Coinbase) | | | | |
| D5 | No implied Coinbase endorsement or partnership | | | | |
| D6 | Pricing matches current published plans | | | | |

---

## Section E: Screenshots and Visuals

| # | Check | Pass | Fail | N/A | Notes |
|---|-------|:----:|:----:|:---:|-------|
| E1 | No Brad personal account screenshots (P&L, balance, trade history) | | | | |
| E2 | Any process/UX screenshots show placeholder/test data, not real account data | | | | |
| E3 | Mockups are clearly marked "Sample interface — not actual trading data" | | | | |
| E4 | If pilot trader case study: written consent obtained, approved metrics only | | | | |
| E5 | Screenshot policy approved by Brad (on file at docs/marketing/CLAIMS_SCREENSHOT_POLICY.md) | | | | |

---

## Section F: Channel-Specific

| # | Check | Pass | Fail | N/A | Notes |
|---|-------|:----:|:----:|:---:|-------|
| F1 | Ad copy: platform policy compliance (Google, Meta, etc.) | | | | |
| F2 | Ad copy: no prohibited keywords ("guaranteed profit," "auto money," scam-adjacent) | | | | |
| F3 | Email/SMS: transactional priority; marketing cadence acceptable | | | | |
| F4 | SMS: reserved for time-sensitive (connect, dunning, red health) only | | | | |
| F5 | Affiliate: contract includes claim whitelist and compliance obligations | | | | |

---

## Section G: Sources and Attribution

| # | Check | Pass | Fail | N/A | Notes |
|---|-------|:----:|:----:|:---:|-------|
| G1 | Any factual claims are traceable to verifiable sources | | | | |
| G2 | Process metrics (uptime %, SLA) are measured and verifiable | | | | |
| G3 | Educational content is neutral, not projecting ROI | | | | |
| G4 | Comparative claims (vs competitors) are fair, accurate, and substantiated | | | | |

---

## Section H: Final Quality

| # | Check | Pass | Fail | N/A | Notes |
|---|-------|:----:|:----:|:---:|-------|
| H1 | All checkboxes above are either "Pass" or "N/A with justification" | | | | |
| H2 | No "Fail" items remain unfixed | | | | |
| H3 | Asset reviewed by Marketing Lead | | | | |
| H4 | Asset approved by Brad (if required per CLAIMS_SCREENSHOT_POLICY table) | | | | |
| H5 | Legal review completed (if required per CLAIMS_SCREENSHOT_POLICY table) | | | | |

---

## Approval Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| **Marketing Review** | | | |
| **Brad Approval** | | | |
| **Legal Review** (if required) | | | |

---

## Document Control

| Version | Date | Author | Notes |
|---------|------|--------|-------|
| 1.0 | 2026-07-16 | Legal Department | Pre-publish checklist per Mkt Plan §9.1 and unified roadmap risk mitigations |

**Canonical path:** `docs/marketing/PRE_PUBLISH_CHECKLIST.md`
**Related:** `docs/marketing/CLAIMS_SCREENSHOT_POLICY.md`, `docs/marketing/LEGAL_ANALYSIS.md`, `docs/marketing/RISK_DISCLOSURES.md`

*Use this checklist for every marketing asset. File completed checklists in the Message Approval Log.*