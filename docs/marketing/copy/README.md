# ARCH Automation — Copy Pack (PHASE-A-06)

**Version:** 2.0  
**Date:** 2026-07-30  
**Kanban:** t_5e21287a  
**Brand (pending lock):** ARCH Automation · arch-automation.com · support@arch-automation.com  
**Status:** Draft for Mkt + Brad review. **Unlisted / invite-only only.** No public publish. No live ads.  
**Legal:** Aligns with Claims & Screenshot Policy + draft ToS / Privacy / Risk. Counsel review still required before public paid checkout.

---

## What’s in this pack

| Path | Purpose |
|------|---------|
| `COMPLIANT_COPY_PACK.md` | Master compliant templates (v2 — supersedes legal v1 body with brand lock + full W1–W7) |
| `sequences/` | Paste-ready Email + SMS strings for GHL workflows W1–W7 |
| `pages/` | Landing, pricing, checkout, risk, ToS/privacy sections, member placeholder, FAQ |
| `funnel/UNLISTED_FUNNEL_SKELETON.md` | Funnel map + GHL page list + build order (no public URL) |
| `funnel/ghl_workflows_skeleton.json` | Workflow trigger/tag/step skeleton for GHL builder |
| `funnel/tags_pipelines.md` | Tags + onboarding pipeline stages (from GHL T0 field dict) |
| `metrics/UTM_KPI_TEMPLATE.md` | UTM conventions + KPI sheet (pay→connect instrumentation) |
| `PRE_PUBLISH_APPLIED.md` | Checklist run against this pack |

**Upstream sources:** brand pack, MKT plan §2–4/§6/§8–9, legal docs, GHL T0 field dict, COMPLIANT_COPY_PACK v1.

---

## Merge tokens (GHL / platform)

| Token | Source |
|-------|--------|
| `{{contact.first_name}}` / `{{first_name}}` | Contact |
| `{{tier_name}}` | Contact custom / product (Starter · Pro · Elite) |
| `{{trader_tier}}` | `starter` \| `pro` \| `elite` |
| `{{connect_link}}` | Platform one-time setup JWT URL |
| `{{member_status_link}}` | Member area / status surface |
| `{{payment_update_link}}` | GHL billing portal |
| `{{cancel_link}}` | GHL cancel / manage |
| `{{support_email}}` | support@arch-automation.com |
| `{{config_summary}}` | Pairs / windows (no balances) |
| `{{deploy_cap_label}}` | Tier cap label (not live P&L) |
| `{{next_rebalance_window}}` | Schedule label |
| `{{runner_health}}` | green / yellow / red / unknown |
| `{{coinbase_status}}` | disconnected / connected / error |

**Never** put API keys, OAuth tokens, or portfolio balances in email/SMS.

---

## Pilot prices (placeholders — finalize before public checkout)

| Tier | SKU | Monthly |
|------|-----|---------|
| ARCH Starter | `arch_starter_mo` | **$39** |
| ARCH Pro | `arch_pro_mo` | **$99** (draft) |
| ARCH Elite | `arch_elite_mo` | **$249** (draft) |

---

## Always-on disclaimer (every page footer + email footer + above checkout confirm)

> ARCH Automation provides software that can place trades on your Coinbase Advanced account after you authorize access. Cryptocurrency trading involves substantial risk of loss. Past performance is not indicative of future results. We do not provide investment advice, do not custody your assets, and do not guarantee profits. Subscription fees are for software and service access only.

Short ad form: *Trading involves risk. Software access only. Not investment advice.*

---

## Build / deploy rules (Phase A)

1. **Unlisted only** — password, invite link, or noindex + not in main nav.  
2. Do **not** run ads or public SEO until legal counsel + Brad claims-policy checkbox.  
3. GHL Location name: **ARCH Automation — Pilot**.  
4. Live GHL page build is ops/human (agent has no GHL UI creds); this pack is the source of truth for strings.  
5. After Brad + Mkt approval: paste into GHL workflows; keep MD as backup.

---

## Approval

| Role | Sign-off | Date |
|------|----------|------|
| Marketing (self-check) | Pack v2 complete; claims policy applied | 2026-07-30 |
| Brad | [ ] | |
| Legal counsel | [ ] (before public paid) | |

Canonical root: `docs/marketing/copy/`
