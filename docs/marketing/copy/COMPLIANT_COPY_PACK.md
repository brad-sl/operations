# COPY PACK — ARCH Automation (Master Index)

**Version:** 2.0  
**Date:** 2026-07-30  
**Status:** Phase A unlisted / invite-ready strings. Subject to Brad + counsel before public paid.  
**Kanban:** t_5e21287a (PHASE-A-06)

This file is the **master map**. Paste-ready bodies live in sibling folders. v1 (2026-07-16 legal) content is superseded by the sequence/page files below; compliance rules unchanged.

---

## Always-On Disclaimer

> ARCH Automation provides software that can place trades on your Coinbase Advanced account after you authorize access. Cryptocurrency trading involves substantial risk of loss. Past performance is not indicative of future results. We do not provide investment advice, do not custody your assets, and do not guarantee profits. Subscription fees are for software and service access only.

---

## Lifecycle sequences (W1–W7)

| ID | File | Channel |
|----|------|---------|
| W1 Welcome | `sequences/W1_welcome_onboard.txt` | Email + optional SMS |
| W2a Connect 24h | `sequences/W2_connect_24h.txt` | Email + SMS |
| W2b Connect 72h | `sequences/W2_connect_72h.txt` | Email + SMS |
| W3 Go live | `sequences/W3_go_live.txt` | Email + optional SMS |
| W4 Daily digest | `sequences/W4_daily_digest.txt` | Email (stub until platform event) |
| W4 Weekly | `sequences/W4_weekly_digest.txt` | Email optional |
| W5a Dunning 1 | `sequences/W5_dunning_1.txt` | Email + SMS |
| W5b Dunning 2 | `sequences/W5_dunning_2.txt` | Email + SMS |
| W6 Needs attention | `sequences/W6_support_red.txt` | Email + SMS |
| W7 Offboard | `sequences/W7_offboard.txt` | Email + optional SMS |

Workflow wiring: `funnel/ghl_workflows_skeleton.json`

---

## Pages / funnel

| Surface | File |
|---------|------|
| Landing | `pages/landing.md` |
| Pricing | `pages/pricing.md` |
| Checkout | `pages/checkout.md` |
| Risk page shell | `pages/risk_disclosure_page.md` |
| ToS shell | `pages/tos_page_sections.md` |
| Privacy shell | `pages/privacy_page_sections.md` |
| Member placeholder | `pages/member_area_placeholder.md` |
| FAQ | `pages/faq.md` |
| Funnel skeleton | `funnel/UNLISTED_FUNNEL_SKELETON.md` |
| Tags/pipelines | `funnel/tags_pipelines.md` |

Canonical full legal bodies remain in:
- `docs/marketing/TERMS_OF_SERVICE.md`
- `docs/marketing/PRIVACY_POLICY.md`
- `docs/marketing/RISK_DISCLOSURES.md`

---

## Pricing placeholders (pilot)

| Tier | SKU | /mo |
|------|-----|-----|
| Starter | arch_starter_mo | $39 |
| Pro | arch_pro_mo | $99 |
| Elite | arch_elite_mo | $249 |

---

## Metrics

`metrics/UTM_KPI_TEMPLATE.md` — UTM rules, pay→connect instrumentation, cohort + weekly sheets.

---

## Compliance

- Policy: `docs/marketing/CLAIMS_SCREENSHOT_POLICY.md`
- Applied check: `PRE_PUBLISH_APPLIED.md`
- Brand: `docs/marketing/brand/`

**Forbidden:** guaranteed returns, personal P&L in marketing, API-key paste, custody/advisory/fund language, fabricated backtests.

---

## Document control

| Version | Date | Author | Notes |
|---------|------|--------|-------|
| 1.0 | 2026-07-16 | Legal Department | W1–W3, W5, landing, checkout seed |
| 2.0 | 2026-07-30 | Marketing Strategist | Full W1–W7, pages, funnel skeleton, GHL JSON, UTM/KPI, brand lock-in |

*Subject to legal review before public use. Unlisted invite testing OK after Brad skim.*
