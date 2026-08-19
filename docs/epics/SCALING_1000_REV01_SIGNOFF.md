# SCALING-1000 REV-01: Reviewer Sign-off Report

**Task:** t_5e0243c7 SCALING-1000-REV-01  
**Reviewer:** crypto-orchestrator  
**Date:** 2026-07-16  
**Epic:** docs/epics/SCALING-1000_EPIC.md  
**Parent:** SYNTH-01 (t_cb94942c) — Unified Roadmap delivered  
**Status:** Plans reviewed vs epic non-goals + HighLevel (GHL) API docs. **APPROVED with tracked open items.**

## Documents Reviewed
- **Epic (source of truth):** `docs/epics/SCALING-1000_EPIC.md` (North Star, arch, OAuth, GHL buildout, phases T0-T3, non-goals §7, metrics §9, risks)
- **MKT-01:** heavy content relocated to `docs/archive/cross_project_removed/SCALING_1000_MARKETING_PLAN.md` (see DOC_BOUNDARY_AUDIT_20260717.md); product GTM retained in unified roadmap and brand/copy packs only
- **IMPL-01:** `docs/integrations/SCALING_1000_IMPLEMENTATION_PLAN.md` (current state, target arch, GHL surface summary, platform APIs, data model, OAuth details, phased packages T0-T3 with est/ deps/ tests, hosting, security, risks, open Qs)
- **GHL API V2 Surface Map (HighLevel docs):** `docs/integrations/GHL_API_V2_SURFACE_MAP.md` (auth private/OAuth, contacts, custom objects/records, webhooks, SaaS/products/subscriptions, conversations, associations, rates, mapping to W1-W7)
- **Unified (SYNTH-01):** `docs/epics/SCALING_1000_UNIFIED_ROADMAP.md` (exec summary, critical path mapping table GTM vs T0-T3, consolidated RACI, 20 open Qs, risks, recommended next Kanban wave, success criteria)
- **Supporting:** `docs/integrations/GHL_INTEGRATION.md` (prereqs: dedicated host + GHL Location + Private Integration before waves; delegation note), MASTER plan-pack section, handoffs/scaling/Handoff_SCALING_1000_PLAN_PACK_20260716.md, epic kickoff

**Artifact locations (canonical):**
- Unified: `/home/brad/projects/crypto-trading-bot/docs/epics/SCALING_1000_UNIFIED_ROADMAP.md`
- Mirrors as noted in MASTER.

## HighLevel (GHL) API Docs Alignment
- Surface map **cites real V2 surfaces** (no inventions):
  - Auth: Private Integration token (T0 pilot) → OAuth 2.0 Marketplace App (T1+ scaling). Headers, scopes (minimal: contacts/objects/etc.), token exchange/refresh.
  - Contacts: POST/GET/PUT/upsert /contacts/ ; tags, customFields.
  - Custom Objects (TradingAccount): schema via UI/API (`custom_objects.tradingaccount`), POST/GET/PUT /objects/:schemaKey/records ; properties for account_id, coinbase_status, runner_health, etc. Associations to Contact.
  - Webhooks (inbound critical): SaaSPlanCreate / AppPaymentStatus / PlanChange / Contact* / RecordCreate/Update / AppInstall etc. Verification: X-GHL-Signature (Ed25519 preferred; legacy RSA). Idempotency via webhookId. Setup in app settings.
  - SaaS / Products / Subscriptions / Payments: GET /products/, /payments/subscriptions/, SaaS-specific webhooks, prices for tiers.
  - Conversations/Messaging: For W4/W3 etc. (preferred: platform emits events → GHL workflows/templates; or /conversations/).
  - Other: Associations/Relations, Locations, rate limits (batch + backoff), pagination (limit/page/cursor), idempotency keys.
- Base: services.leadconnectorhq.com ; references GitHub highlevel-api-docs + marketplace.gohighlevel.com/docs (as of 2026-07).
- Mapping table in surface map + unified aligns to epic W1–W7 and TradingAccount sync directions (platform canonical; GHL for UX/billing/comms).
- **Gaps noted (deferred):** Full OpenAPI contract `GHL_CONTRACT.md` (or openapi.yaml) recommended for T1 start. Exact payload examples / error codes to flesh in gateway spike. Re-validate surfaces before T1 waves.
- **No issues:** All cited endpoints real per sources. Never embed tokens in GHL/browser. HMAC/sig verify mandatory. Good hygiene.

## Alignment vs Epic Non-Goals (§7)
All plans explicitly respect and reinforce:
- **GHL is the CRM/comms/billing/UX layer** (funnels, SaaS products, workflows W1-W7, Contacts + TradingAccount custom object, member status). No custom trader CRM built by platform.
- **No payment cards / PCI on trading server** (GHL + Stripe own checkout/billing; platform receives webhooks only for tier mapping; never store cards).
- **No 1,000 concurrent Hermes chat sessions** (focus on server-to-server webhooks/events, status API for iframe/member area, GHL-native comms. No chat concurrency modeled).
- **Brad’s live account not migrated to OAuth on day one** (optional later; explicit: feature flag MULTI_TENANT_ENABLED=false by default; dual legacy + new paths; isolation tests; "do not destabilize Brad’s account"; api_key path preserved for founder).
- Additional principles repeated: Never custody funds; never paste API keys into GHL; tokens encrypted vault only (never GHL fields); no cross-tenant leaks; plans-only in this pack (no prod runner/GHL automation changes executed).

**Strong alignment across MKT/IMPL/UNIFIED.**

## Overall Assessment
- **Plans comprehensive and high-quality.** MKT covers full scope per handoff (positioning with compliance-safe claims, ICP/tiers mapped to epic, full funnel, channel plan with paid acquisition / ads research (product only), offer narrative "software access", detailed assets, metrics aligned to epic gates, 90-day GTM with Phase A/B/C gates, risks + pre-publish checklist, RACI, open Qs).
- **IMPL solid:** Baseline (preserve Phase 6.1), target arch (gateway, registry, queue, fleet with AccountContext), expanded T0-T3 packages with est/ deps/ isolation tests, data model (Postgres canonical vs GHL mirror), OAuth adapter details (portfolio_uuid, sandbox first), hosting prereqs, security (encrypt at rest, sig verify, least-privilege), exit criteria matching epic.
- **UNIFIED excellent synthesis:** Critical path mapping table (GTM drives commercial; T drives engine), consolidated RACI (Mkt/Eng/Ops/Brad), 20 open Qs with owners/phases, cross-cut risks, recommended executable Kanban wave (prereqs first, then T0-01..05 + GHL-T0 + Mkt packs), success gates, doc control.
- **Discipline honored:** "Plans only" repeated; isolation/feature flags/Brad untouched mandatory; dedicated host + GHL Location prereqs before T1 webhooks/automation; invite-only closed cohort until T1 exit (pay→OAuth→green <24h, median <15min); no live ads spend pre-gates; no fake P&L/claims; update docs (DATA_FLOW post-migration).
- **Metrics/Risks/Exit:** Aligned to epic §6/9. Cross-tenant 0 incidents; GHL sync lag targets; shared intel (not per-account).
- **Success criteria for plan-pack (per handoff):** 
  - [x] MKT/IMPL/UNIFIED + API map exist and complete required sections.
  - [x] Cite real V2 surfaces, align epic non-goals/metrics.
  - [x] No production multi-tenant code.
  - [x] MASTER updated (by SYNTH); REV sign-off.
  - [x] Next wave recs provided.

## Gaps / Open Items / Recommendations (Tracked — Not Blocking Plan Sign-off)
Prioritize in Phase A / pre-T0 heavy work (per UNIFIED recs). Many already listed as open Qs in sources; consolidated here for actionability.

1. **Brand / domain / identity / support@ / logo** (UNIFIED Q1, Mkt Phase A, Brad A) — Lock "ARCH Automation" or new? Affects GHL Location, search/brand visibility, funnels. Mini-decision pack.
2. **Final tier pricing + platform deploy caps** (UNIFIED Q2, Mkt/IMPL placeholders e.g. Starter $29-49 / 6 pairs / $1-3k cap; Pro/Elite) — Align unit econ + Coinbase fees. Map to GHL SaaS products. Enforce in registry.
3. **Dedicated host + public HTTPS + domain/cert + monitoring** (GHL_INTEGRATION critical prereq, IMPL §8, UNIFIED) — Hetzner/DO/AWS rec. Not Brad HP laptop for prod webhooks. Staging/prod ideal. Complete **before T1**. Update GHL_INTEGRATION if needed.
4. **GHL pilot Location + Private Integration creds + SaaS products (Starter first) + pipelines/tags + TradingAccount field dict** (GHL-T0 manual, Mkt Phase A) — Manual UI/CSV for 2 test contacts/records. Align epic fields + Mkt dict. No automation yet.
5. **Legal counsel / timeline / ToS / privacy / risk disclosures / broker analysis** (UNIFIED Q5, Mkt §1.4/9, pre-public paid) — US-only? CTA/CPO/money transmitter? Strong disclaimers everywhere. Pre-checkout. **DRAFT DELIVERABLES COMPLETE** — see `docs/marketing/LEGAL_DOCS_INDEX.md` (7 docs). **Needs counsel engagement + review before public paid checkout.**
6. **Exact queue/scheduler tech + staggering** (UNIFIED Q11, IMPL T0-04) — RQ/Redis, APScheduler, DB-backed? Decide + spike in T0.
7. **Encryption / KMS / secrets mgmt for oauth_tokens** (UNIFIED Q12) — Fernet/env vs proper Vault. At-rest only.
8. **JWT / auth details for status API + member iframe** (UNIFIED Q13, IMPL T1-04) — Short-lived signed or GHL custom code?
9. **GHL_CONTRACT.md / OpenAPI skeleton** (IMPL §4, surface map) — At T1 start: full payloads for /ghl/webhook, /connect/*, status API, errors, webhook contract.
10. **Claims & screenshot policy one-pager** (Mkt Phase A, pre-publish checklist) — Brad-approved. Zero tolerance.
11. **Paid acquisition research brief** (Mkt, research-only sandbox; dedicated product Google acct hygiene) — SERP/competitor landscape for Coinbase automation. No live spend pre-T1 + legal.
12. **Invite-only duration, comp seats, geo, support SLA** (UNIFIED Q3,4,7,8) — Closed beta weeks? # Elite comps? US-only checkout?
13. **When (if) migrate Brad live to OAuth** (UNIFIED Q14) — Post T1? Keep api_key path forever behind flag?
14. **Monitoring / observability / backup-DR for fleet** (UNIFIED Q15,16) — Prom? GHL tasks + aggregate Telegram? Token/ledger backups.
15. **Tier limits enforcement details + upgrade path** (UNIFIED Q18) — Exact $ caps, pair counts; never auto-upgrade w/o payment.
16. **White-label / sub-account vs multi-Location strategy** (UNIFIED Q17,20) — Pilot one Location; later optional.
17. **DATA_FLOW_AND_LOCATIONS.md + schema docs update** (Epic §10, post T0-01 migration).
18. **Coinbase OAuth exact scopes / portfolio discovery / sandbox pilot acct** (IMPL §6) — Confirm at spike; separate test acct.
19. **MASTER / Kanban / handoff updates post-REV** (this task).
20. **Other minor:** Screenshot policy doc, UTM/KPI sheet, copy pack under docs/marketing/copy/.

**Recommendation:** Address prereqs (brand, host, GHL setup, legal timeline, policy, copy) + T0-01 schema spike in parallel where safe. Strict gates: T0 exit before T1 code; T1 E2E before public paid acquisition / checkout.

## Decision
**APPROVED.** Plans meet pack success criteria, align with epic, use real API surfaces, respect non-goals and "do not destabilize" constraints. Comprehensive foundation for executable T0 wave.

**MASTER status update:** Change plan-pack from **OPEN** to **PLANS READY (REV-01 approved; open Qs tracked above; next: T0 wave cards per unified §5)**.

**Next actions (post this sign-off):**
- Update MASTER (plan-pack section + SCALING-1000 epic linkage).
- Create/promote Kanban cards for prereqs + T0-01 (Postgres schema) + GHL-T0 (manual) + Mkt foundation (brand decision, policy, copy, paid acquisition research, GHL-T0 pack) + host provisioning.
- Handoff docs per epic §10.
- Lock decisions 1-8 + 9-10 (host/GHL) before heavy T0-01 or copy finalization.
- After T0 + Phase A: T1 commercial loop.

**References for follow-up:** See unified roadmap §5 (recommended wave), epic §6/10, GHL_INTEGRATION.md prereqs, this sign-off + source plans.

*Sign-off complete. Ready for executable implementation waves.* 

**Artifact:** This file (`docs/epics/SCALING_1000_REV01_SIGNOFF.md`) + MASTER update. Kanban t_5e0243c7 complete.