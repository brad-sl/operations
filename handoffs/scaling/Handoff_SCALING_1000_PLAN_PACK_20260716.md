# Handoff: SCALING-1000 Planning Pack — Marketing + Implementation Plans

**Date:** 2026-07-16  
**Epic:** `docs/epics/SCALING-1000_EPIC.md`  
**GHL API reference:** https://github.com/GoHighLevel/highlevel-api-docs  
**Official docs site:** https://marketplace.gohighlevel.com/docs  
**Integration ramp:** `docs/integrations/GHL_INTEGRATION.md`  
**Kickoff:** `handoffs/scaling/Handoff_SCALING-1000_EPIC_Kickoff.md`

## Objective

Produce two **full planning documents** (marketing GTM + technical implementation), then a **unified phased roadmap** that sequences GHL commercial work with platform T0–T3 — without destabilizing Brad’s single-account live Phase 6.

## Boundary principles (non-negotiable)

| GHL / marketing owns | Trading engine owns |
|----------------------|---------------------|
| Funnels, pricing pages, paid acquisition / ads research (product only), organic discovery | Signals, allocation, execution, SL |
| Onboarding UX, e-sign, SaaS billing, dunning | Coinbase OAuth token vault, runners |
| Email/SMS/workflows, CRM pipeline | Ledger, recon, kill switches, fleet health |
| Client-facing status *presentation* | Canonical state, raw exchange APIs |

**Never:** store OAuth tokens / full balances in GHL · traders paste API keys into CRM · fake portfolio numbers in marketing claims.

## Task graph

| ID | Deliverable | Assignee | Depends |
|----|-------------|----------|---------|
| **MKT-01** | Full marketing / GTM plan | `marketing-strategist` | — |
| **IMPL-01** | Full implementation plan + GHL API V2 surface map | `crypto-engineer` | — |
| **SYNTH-01** | Unified roadmap (phases, deps, metrics, open questions) | `crypto-orchestrator` | MKT + IMPL |
| **REV-01** | Reviewer sign-off vs epic + API docs | `crypto-orchestrator` | SYNTH |

MKT and IMPL run **in parallel**.

## MKT-01 scope — marketing plan

**Path:** `docs/marketing/SCALING_1000_MARKETING_PLAN.md` (NOTE: heavy content relocated to `docs/archive/cross_project_removed/SCALING_1000_MARKETING_PLAN.md` per DOC-BOUNDARY-01 for project separation; this handoff retained for historical sequencing reference only)

Must include:

1. **Positioning** — multi-trader automated crypto (Coinbase Advanced), GHL as commercial shell; compliance-safe claims (no guaranteed returns; deposit-adjusted honesty).
2. **ICP & tiers** — Starter / Pro / Elite mapped to epic product table; messaging per tier.
3. **Funnel architecture** — awareness → landing → checkout (GHL SaaS) → connect Coinbase → activation → retention/digest.
4. **Channel plan** — content, email/SMS lifecycle (W1–W7 from epic), paid acquisition research (dedicated product account only, research posture; no client tools or live spend pre-gates).
5. **Offer & pricing narrative** — what is sold (software + automation access), not “we hold your crypto.”
6. **Asset list** — pages, lead magnets, sequences, status member area; owners and tools (GHL, paid acquisition research if applicable).
7. **Metrics** — CAC proxy, pay→OAuth conversion, time-to-connected, churn after dunning.
8. **90-day pilot GTM** — what to build *before* 50 traders vs after T1 exit criteria.
9. **Risks** — regulatory/comms, over-promising live P&amp;L screenshots, brand vs Brad personal account.

**Must not:** launch live ads on wrong Google account (mixing with personal or unrelated accounts); invent backtest/marketing performance numbers.

## IMPL-01 scope — implementation plan

**Path:** `docs/integrations/SCALING_1000_IMPLEMENTATION_PLAN.md`  
**API map path:** `docs/integrations/GHL_API_V2_SURFACE_MAP.md`

Must include:

1. **Current state** — single-tenant Phase 6 live; what must not break.
2. **Target architecture** — diagram from epic §2; Integration Gateway, registry, queue, workers, secrets.
3. **GHL API V2 surface map** — from [highlevel-api-docs](https://github.com/GoHighLevel/highlevel-api-docs) / marketplace docs:
   - Auth (Private Integration / OAuth marketplace app if needed)
   - Contacts, Custom Objects, Associations
   - Workflows / webhooks inbound
   - SaaS / subscriptions / products
   - Conversations / SMS / email triggers
   - Rate limits, pagination, idempotency
   - **Which endpoints** map to W1–W7 and TradingAccount sync
4. **Platform APIs to build** — epic §4.6 endpoints; OpenAPI skeleton outline for `GHL_CONTRACT.md`.
5. **Phased work packages** — expand T0–T3 into engineer-sized packages with deps, estimate (S/M/L), isolation tests.
6. **Data model** — traders, configs, oauth_tokens, job_runs; what syncs to GHL vs stays Postgres-only.
7. **Coinbase OAuth** — scopes, portfolio_uuid, adapter port; pilot account vs Brad CDP key.
8. **Hosting prereqs** — dedicated host for webhooks (from `GHL_INTEGRATION.md`); not HP laptop as prod webhook target.
9. **Security** — secrets, HMAC, never put tokens in GHL fields.
10. **Exit criteria** per phase matching epic §6–9.

**Must not:** implement production runner multi-tenant changes in this task — **plan only**. Optional: stub OpenAPI file if tiny.

## SYNTH-01 scope — unified roadmap

**Path:** `docs/epics/SCALING_1000_UNIFIED_ROADMAP.md`

- Sequence: GTM assets vs T0 engine vs T1 GHL loop (critical path).
- RACI (marketing vs eng vs ops).
- Decision log / open questions for Brad.
- Suggested next **executable** Kanban wave after plans approved (likely T0-01 + GHL-T0 + funnel skeleton).
- Update MASTER table with plan artifact links.

## REV-01

- Check plans against epic non-goals and success metrics.
- Confirm GHL API map cites real V2 surfaces (not invented endpoints).
- Approve or block with concrete gaps.

## Success criteria (pack)

- [ ] Marketing plan MD exists, complete sections 1–9.
- [ ] Implementation plan + API surface map exist, T0–T3 packages listed.
- [ ] Unified roadmap merges both; next wave recommended.
- [ ] MASTER updated; Kanban complete with artifact paths in summaries.
- [ ] No production runner multi-tenant merge required for this pack.

## References

- Epic: `docs/epics/SCALING-1000_EPIC.md`
- GHL ramp: `docs/integrations/GHL_INTEGRATION.md`
- API docs repo: https://github.com/GoHighLevel/highlevel-api-docs
- Marketplace: https://marketplace.gohighlevel.com/docs
- Paid acquisition / ads research posture (product GTM only): dedicated product Google account only (no mixing with non-product accounts)
