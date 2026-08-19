# SCALING-1000 Unified Roadmap (SYNTH-01)

**Epic:** `docs/epics/SCALING-1000_EPIC.md`  
**Synthesized from:**  
|- MKT-01: heavy product-GTM draft relocated to `docs/archive/cross_project_removed/SCALING_1000_MARKETING_PLAN.md`; see DOC_BOUNDARY_AUDIT_20260717.md and PROJECT_BOUNDARY.md (product GTM only retained in active docs; separate consultancy workstreams are out of scope)
- IMPL-01: `docs/integrations/SCALING_1000_IMPLEMENTATION_PLAN.md` + `docs/integrations/GHL_API_V2_SURFACE_MAP.md`  
- Supporting: `docs/epics/SCALING-1000_EPIC.md`, `docs/integrations/GHL_INTEGRATION.md`, `docs/MASTER_TASK_TRACKING.md` (plan-pack section)  
**Date:** 2026-07-16  
**Status:** Plans synthesized. Ready for REV-01 sign-off then executable T0 wave. **Plans only** — no multi-tenant runner or live GHL prod changes executed here.  
**Working product name (placeholder):** ARCH Automation (brand decision pack ready — `docs/marketing/brand/BRAND_DECISION_PACK.md`; awaiting Brad sign-off; no purchase yet).  

**North Star (from Epic):** Support 1,000 independent traders on their own Coinbase Advanced accounts via OAuth. GHL = commercial/UX/billing/CRM/comms layer. Trading engine = execution, risk, vault, registry, workers. Never custody funds, never paste API keys into GHL, no guaranteed returns in any marketing.

---

## Executive Summary

This roadmap unifies the GTM (marketing) 90-day pilot plan with the technical T0–T3 implementation plan. 

**Core separation of concerns (non-negotiable):**
- GHL owns: funnels, SaaS subscriptions, workflows (W1–W7), CRM (Contacts + TradingAccount custom object), comms, member status presentation.
- Engine owns: Coinbase OAuth (per-trader, revocable), AccountContext-injected Phase 6 logic (allocation, rebalance, SL, ledger), Postgres registry as canonical state, secrets vault, job scheduling, shared intel (sentiment/RSI/prices), kill switches.
- Never: tokens/balances/full precision in GHL; API keys in CRM; Brad's live single-account Phase 6 destabilized (feature flags + parallel paths + isolation tests mandatory).

**Pilot guardrails:**
- Invite-only / closed cohort until T1 exit criteria proven: end-to-end pay (GHL) → OAuth connect → green runner_health in GHL <24h, median human time pay→connected <15min.
- Dedicated host + public HTTPS webhook URL required before T1 automation (GHL_INTEGRATION.md prereq; not Brad's HP laptop).
- Research-only paid acquisition (dedicated product account only, post T1 + legal/brand readiness); no live spend until gates met.
- Compliance: deposit-adjusted honesty, strong disclaimers, no P&L screenshots from personal account in funnels.

**High-level sequencing:**
- **Pre-T0 / Phase A (Mkt 0-30d):** Brand/GHL foundation + manual GHL objects + T0 engine spikes (schema, context, OAuth sandbox adapter, isolation, manual GHL-T0). Brad live untouched.
- **T1 / Phase B (Mkt 31-60d):** GHL commercial loop (webhooks, W1-W3/W5, SaaS mapping, sync worker) + E2E pilot cohort (5-15 traders). Pay→OAuth→green activation.
- **T2+ / Phase C:** Fleet hardening, W4/W6, scale to 50-200 then load to 1k. Controlled expansion post-gates.

**Key success gates (Epic + Mkt metrics):**
- T0: 2 accounts (incl. legacy Brad path) shadow cycling; OAuth sandbox success; no GHL automation yet.
- T1: 95% connected→green within 24h; median pay→connected <15min human time; 0 cross-tenant incidents.
- Marketing: waitlist→paid, checkout ≥70%, pay→OAuth ≥80% within 72h, activation ≥75% in 7d.

---

## 1. Critical Path Alignment: GTM Phases vs T0–T3 Impl

### 1.1 Mapping Table (GTM drives commercial loop; T-phases drive engine readiness)

| GTM Phase (Mkt Plan §8) | Days (relative to pilot start) | Required Eng Readiness | Key Mkt Deliverables | Key Impl Packages | Exit / Gate |
|-------------------------|--------------------------------|------------------------|----------------------|-------------------|-------------|
| **Phase A: Foundation** | 0–30 | T0 complete (or near) + prereqs (host, GHL Location, Private Integration) | Brand decision; GHL Location + SaaS products (even if only Starter); W1–W3/W5 copy; unlisted funnel + pricing + disclaimers; waitlist/invite list (10–25); claims/screenshot policy; UTM/KPI sheet; paid acquisition / keyword research (no spend pre-T1, dedicated product acct); TradingAccount field dict aligned. | T0-01 Postgres schema/migrations (traders, configs, oauth_tokens, job_runs); T0-02 AccountContext + feature flag MULTI_TENANT_ENABLED + dual legacy path; T0-03 OAuth Coinbase adapter spike (sandbox + portfolio_uuid); T0-04 Job queue/scheduler stub + staggering; T0-05 Isolation tests (2 accounts, no leaks); GHL-T0 (manual Custom Object schema + 2 test contacts/records via UI/CSV). | Unlisted funnel reviewable; copy approved; invite list ready; 2 accounts shadow in T0; OAuth sandbox place/cancel; Brad live untouched. No prod webhooks pointed yet. |
| **Phase B: Closed Pilot** | 31–60 | T1 commercial loop | Onboard 5–15 invite-only paid (or comp Elite); instrument timestamps (pay→OAuth→green); friction log + FAQ from real use; weekly QA; optional 2 educational posts (no perf claims). | GHL-01 Private Integration + webhook gateway (staging, sig verify, idempotency); GHL-02 Workflows W1–W3/W5 in GHL; GHL-03 SaaS products ↔ tier mapping + enforce in registry; GHL-04 Platform→GHL upsert/sync worker (TradingAccount + tags + alerts, batched); T1-01 Staggered scheduler; T1-02 Shared sentiment/RSI cache (multi-tenant); T1-03 Per-account SL remediation; T1-04 Read-only status API (JWT/GHL-signed for iframe); T1-GHL extras (W4 stub, TradeAlert). | ≥80% of paid cohort connected; median connect time trending <15min; 95% connected→green <24h in GHL object; 0 compliance incidents; runner cycles new accounts. E2E happy path test trader proven. |
| **Phase C: Harden + Controlled Expansion** | 61–90 | T1 exit + T2 prep | Fix top 3 frictions; turn on W4 digests; document referral; prepare paid acquisition brief (still no spend until OK); pricing reality check; readiness for public waitlist vs checkout. | T2 items (autoscaling/sharding, rate limiter, recon job, W4/W6, audit); GHL-05 TradeAlert + templates. Post-T1 only. | T1 exit criteria met before any public paid acquisition / checkout. |
| **T2 Fleet (50–200)** | Post-pilot | T2 hardening | Scale content / discovery & case studies (opt-in pilots only); W6 escalation polish; possible referral program. | T2-01..05 as above; full W4 daily + W6. | 50–200 accounts with 95%+ healthy; sharding/recon in place. |
| **T3 Scale (1,000)** | Later | T3 load/chaos | Public paid acquisition (dedicated account); white-label messaging (GHL-06 optional); partner expansion. | T3-01..04 load/chaos, multi-region, key mgmt; GHL-06 white-label template. | Load tests to 1k simulated; graceful degradation; <1min sync lag; 99% healthy. |

**Dependencies flagged early (Mkt cares):**
- Dedicated host + public webhook URL (no reliable W1 without it).
- GHL Private Integration + SaaS products.
- Connect URL + JWT + status API.
- Legal ToS/privacy/disclosures.
- Brand name + domain.
- MULTI_TENANT flag + Brad isolation (trust signal).
- GHL Location / creds ramp (see GHL_INTEGRATION.md).

**Hosting note (critical, from GHL_INTEGRATION + IMPL):** Complete dedicated VPS (Hetzner/DO/AWS recommended), Docker/systemd, public HTTPS, before T1 waves. Local ngrok only for dev spikes. Webhook target 24/7 reachable.

### 1.2 Overall Timeline Estimate (rough, part-time)
- T0 + GHL-T0 + Mkt Phase A prep: 3–6 weeks (schema, context, OAuth spike, isolation, manual GHL setup, copy/funnel).
- T1 + Phase B pilot: +4–8 weeks (gateway, workflows, sync, E2E cohort).
- Depends on: host provisioning, GHL sub-account ramp, legal review, brand lock.
- Total to T1 exit: ~2–4 months calendar from kickoff, assuming parallel Mkt/Eng + prereqs met.

---

## 2. Consolidated RACI

Extended from Mkt RACI (§11) with Eng/Ops from IMPL + Epic + GHL_INTEGRATION.

| Activity | Marketing | Engineering | Ops | Brad | GHL Admin / Notes |
|----------|-----------|-------------|-----|------|-------------------|
| Positioning, claims policy, disclaimers | R | C | C | A | Compliance review mandatory |
| GHL funnel / landing / pricing pages | R | C (events/API) | C | A | Unlisted until gates |
| W1–W7 copy / sequences | R | C (event payloads) | C | A | GHL native; engine emits events only |
| SaaS product setup + tier mapping in GHL | R/C | C | R | A | Map to platform caps (Starter 6 pairs/low cap etc.) |
| OAuth / connect UX copy + screens | R | R (flow + adapter) | C | A | Platform controls redirect/callback |
| Paid acquisition research (dedicated product account) | R | I | I | A | Research-only (dedicated product acct); no live until post T1 |
| Live paid acquisition / ads spend | R | I | I | A | Only post-T1 exit + legal + dedicated acct |
| KPI / funnel reporting | R | C | C | A | Weekly pilot; align with epic gates (pay→OAuth, green health) |
| Legal disclosures / ToS / privacy | C | I | I | A (with counsel) | Pre-public paid |
| Postgres schema + migrations (T0-01) | I | R | C | A | Alembic; update DATA_FLOW_AND_LOCATIONS.md |
| AccountContext + injection + flags (T0-02) | I | R | C | A | Dual path; Brad legacy untouched |
| OAuth adapter + portfolio_uuid (T0-03) | I | R | C | A | Sandbox first; Brad CDP key path preserved |
| Job queue / staggered scheduler | I | R | C | A | Avoid herd on shared intel |
| Isolation tests (T0-05) | I | R | C | A | Cross-account leak checks mandatory |
| GHL-T0 manual (Location, Custom Object, test records) | R (field dict + CSV) | C (schema align) | R (setup) | A | Manual UI/CSV; no automation yet |
| Integration Gateway (webhook + /connect + status API) (GHL-01, T1-04) | C | R | C | A | HMAC/sig verify (X-GHL-Signature); HTTPS; staging first |
| Workflows W1–W3/W5 in GHL | R | C (payloads) | C | A | Trigger on sub active / connected status |
| Platform → GHL upsert / sync worker (GHL-04) | C | R | C | A | Batched, rate-aware; rounded fields only |
| Shared intel (sentiment/RSI) multi-tenant | I | R | C | A | Keyed by (pair, window) not account |
| Per-account SL / rebal / ledger | I | R | C | A | Feature-flagged; no manual reattach long-term |
| Dedicated host provisioning + uptime | I | C | R | A | Prereq before T1; separate staging/prod ideal |
| Secrets / encryption / vault (oauth_tokens) | I | R | C | A | Never plaintext, never GHL, KMS or equiv |
| Kill switches / pause per account | I | R | R | A | Independent of GHL billing |
| Brand name / domain / logo / support identity | R | C | C | A | Critical early decision |
| Pricing + deploy caps finalization (Starter/Pro/Elite) | R (Mkt) | R (enforce) | C | A | Align placeholders ($29-49 / $79-129 / $199-349 or custom) with unit econ |
| Pilot invite list + onboarding | R | C | C | A | Closed cohort |
| Monitoring / fleet health (T2+) | I | R | R | A | Prom? + GHL W6 + ops Telegram aggregate |
| White-label / partner (T3 GHL-06) | R | C | C | A | Optional later |

**R = Responsible (does the work); A = Accountable (final decision); C = Consulted; I = Informed.**

**GHL admin ramp note:** Manual Location + Private Integration + Custom Object for T0/GHL-T0 by Ops/Mkt/Brad. Full OAuth Marketplace App for T1+ scaling (per-location tokens, public webhooks).

---

## 3. Consolidated Open Questions / Decisions for Brad (and owners)

From MKT §10 + IMPL §12 + Epic + GHL_INTEGRATION. Prioritize pre-T0 / Phase A.

1. **Public brand name and domain** (Mkt lead, Brad A) — Lock "ARCH Automation" or new? Separate from personal bot brand. Affects search visibility / brand, support@, GHL Location identity.
2. **Final Starter/Pro/Elite USD prices and platform deploy caps** (Mkt + Eng align, Brad A) — Pilot placeholders vs real unit economics + Coinbase fees. Enforce in registry on provision. Map to GHL SaaS products.
3. **Invite-only duration after T1 exit** (Mkt, Brad) — How many weeks closed beta before public waitlist/checkout?
4. **Comp / feedback seats** (Mkt) — How many Elite comps for pilot feedback? Criteria?
5. **Legal counsel contact / timeline** (Brad) — Review before public paid checkout (broker/dealer, CTA/CPO, money transmitter, state rules, ToS/privacy, risk disclosures by channel). **DRAFT DOCS COMPLETE** — see `docs/marketing/LEGAL_DOCS_INDEX.md` for full legal pack (7 docs).** Needs counsel engagement + review before public paid checkout.**
6. **Founder-led content comfort** (Mkt + Brad) — Process blogging / thought leadership (risk, architecture, ops) vs silent pilot? No personal P&L.
7. **Geographic restriction** (Mkt + legal) — US-only at launch? (ICP is US-oriented Coinbase holders).
8. **Support hours / channel** (Mkt + Ops) — GHL chat vs email vs Telegram business? SLA once defined.
9. **Dedicated host provider + domain + cert** (Ops lead, Eng C, Brad A) — Hetzner/DO/AWS? Public HTTPS URL for webhooks. Staging vs prod. Before T1.
10. **GHL Location ID / Private Integration token timing** (or full OAuth Marketplace App) (Mkt/Ops) — Sandbox Location first for GHL-T0. When to switch to full App for public webhooks/scaling.
11. **Queue / scheduler tech** (Eng) — RQ + Redis, APScheduler, DB-backed, or Postgres LISTEN/NOTIFY? Staggering strategy.
12. **Encryption lib / KMS / secrets mgmt** (Eng) — Fernet + env? Vault? For oauth_tokens table (encrypted at rest).
13. **Exact JWT / auth for status API + member area** (Eng + GHL) — Short-lived signed token or GHL custom code / iframe? For `/api/v1/accounts/{id}/status`.
14. **When (if ever) to migrate Brad's live account to OAuth path** (Eng + Brad) — Post T1? Keep api_key path behind flag forever for founder account?
15. **Monitoring / observability stack for fleet** (Eng + Ops) — Prometheus? GHL tasks + aggregate Telegram? Health dashboards.
16. **Backup / restore / disaster recovery for tokens + ledger + registry** (Eng + Ops).
17. **White-label vs single brand** (Mkt + Brad) — GHL-06 optional in T3.
18. **Tier limits enforcement details** (Eng) — Exact $ caps, pair counts per tier; upgrade path (never auto without payment event).
19. **Ad account separation hygiene** (Mkt) — Use dedicated product Google Ads account only (never mix with personal or non-product accounts).
20. **GHL sub-account vs multi-Location strategy** (Mkt + Ops) — One Location for pilot; Agency token minting for later white-label.

**Decision owners:** Brad final A on brand/pricing/legal/geo/host. Mkt drives ICP/positioning/funnel/copy. Eng drives arch/data/OAuth/queue/security. Ops drives host/GHL admin/monitoring.

**Recommendation:** Lock 1-8 + 9-10 (host + GHL creds) in Phase A before heavy T0-01 or copy work. Use Kanban comments or new decision cards.

---

## 4. Risks & Mitigations (Cross-Cut Summary)

From Mkt §9, IMPL §11, Epic §8. Full lists in source docs.

**High-impact:**
- **Regulatory/comms (broker-dealer, CTA, money transmitter):** Counsel review pre-public paid. "Software access" framing only. Strong disclaimers everywhere. Mitigation: no advisory language; GHL owns billing claims.
- **Scam-category association / chargebacks:** OAuth-only + non-custodial story. Ban guaranteed % copy. Red-flag checklist in every asset publish.
- **Over-promising (live P&L, invented numbers):** Screenshot policy; deposit-adjusted honesty; process metrics only in marketing. Never use Brad personal wallet as hero.
- **Brand = Brad personal account bleed:** Separate domain/logo/support. Case studies only opt-in pilots. Ops Telegram internal.
- **GHL confusion ( "the exchange"):** Explicit copy: GHL = billing/CRM/comms; funds + execution at Coinbase.
- **Hosting / webhook downtime:** Dedicated host (prereq). Queue + retry. Health checks. At-least-once design.
- **GHL rate/object limits:** Batch delta only; monitor; fallback polling.
- **Coinbase OAuth / portfolio / refresh failures:** Store uuid; pause + W6 alert; proactive refresh.
- **Scope creep / selling before ready:** Strict T0/T1 gates. Invite-only until E2E proven. No public ads pre-T1.
- **Token / data leakage:** Encrypt at rest only in backend. Never GHL. HMAC verify on webhooks. Least-privilege DB.
- **Cross-tenant leaks or Brad impact:** Feature flags + parallel legacy path + exhaustive isolation tests before any prod path. Canary accounts.
- **SMS spam / fatigue:** Transactional priority; marketing SMS rare.
- **Affiliate / partner exaggeration:** Contracts + claim whitelist only.

**Always-on:** Pre-publish claim checklist (Mkt plan §9.1). Zero tolerance for prohibited language.

---

## 5. Recommended Next Executable Kanban Wave (post SYNTH + REV-01)

**Do not execute T0 engine/GHL prod changes until plans + REV approved and prereqs met.**

**Suggested wave (create cards under SCALING-1000 parent; link to this roadmap):**

**Prereqs / Parallel (immediate, low-code):**
- Dedicated host provisioning + public HTTPS + basic monitoring (Ops/Eng). Update GHL_INTEGRATION.md if needed.
- GHL pilot Location + Private Integration creds + SaaS product drafts (even Starter only) (Mkt/Ops). Manual.
- Brand mini-decision (name, domain, logo, support@) (Mkt + Brad).
- Claims & screenshot policy one-pager (Brad-approved) (Mkt).
- Paid acquisition / ads research brief (Coinbase automation SERP/competitor landscape; research-only until dedicated acct + legal) (product GTM).
- Copy pack: W1–W3 + W5 final strings in GHL + MD backup `docs/marketing/copy/` (Mkt).
- GHL-T0 marketing pack: pipelines, tags (`coinbase_connected`, `runner_healthy`, `needs_attention`), TradingAccount field dict, unlisted funnel skeleton + pricing + risk pages (Mkt + align Eng).

**T0 Engine (plan-only spikes; no prod runner merge):**
- SCALING-1000-T0-01: Postgres schema + alembic migrations (traders, trader_configs, oauth_tokens, job_runs, etc.) + ERD review. Test migrate/insert/query. Update DATA_FLOW_AND_LOCATIONS.md.
- SCALING-1000-T0-02: AccountContext dataclass + injection (feature flag). Dual path tests. Wrap existing coordinator/SL/ledger/allocation.
- SCALING-1000-T0-03: OAuth CoinbaseTradingClient adapter (sandbox spike). Full connect → place/cancel sandbox order → refresh. Portfolio handling. Brad api_key path untouched.
- SCALING-1000-T0-04: Job queue/scheduler stub (`schedule_run_cycle(account_id)`). Simple RQ/Redis or DB poll + staggering stub. Enqueue/execute 2 accounts independently.
- SCALING-1000-T0-05: Isolation tests + dual-runner shadow (2 accounts, leak checks on state/logs/alerts/caches/positions). Metrics diff. Kill switch per account. Hardened tests green.
- SCALING-1000-GHL-T0: GHL sandbox Location + TradingAccount custom object (manual via UI/CSV; 2 test contacts/records). Document schemaKey + fields (align epic + Mkt dict). Verify in workflows. No automation.

**GHL / Commercial Prep (T1 path):**
- GHL-01 spike (staging gateway skeleton): POST /ghl/webhook (sig verify, idempotent), /connect/coinbase + callback, status API stub.
- OpenAPI skeleton `docs/integrations/GHL_CONTRACT.md` (or openapi.yaml).
- Hermes delegation config note (if starting GHL waves): set provider/model per GHL_INTEGRATION.md.

**Other:**
- Update MASTER (this task).
- Create REV-01 card for sign-off vs epic + real API surfaces.
- After REV: promote T0-01 etc to ready; handoff docs per epic §10.

**Order suggestion:** Prereqs + brand + policy + GHL-T0 manual + T0-01 schema (foundation) in parallel where possible. Then T0-02/03/04/05 + gateway spike. Then Mkt Phase A close + T1 start only after gates.

**Do not:** Point prod webhooks at local machine; run live ads; merge multi-tenant to Brad's live branch; invent metrics.

**Next after this wave:** T1 commercial loop packages (GHL-01–04, T1-01–04) once T0 + Phase A exit green. Then pilot cohort onboarding.

---

## 6. Success Criteria for SYNTH-01 + Pack

- [x] Unified roadmap exists with critical path sequencing, RACI, open Qs, next wave recs.
- [x] MASTER updated with artifact links (see below).
- [ ] REV-01 sign-off (next child).
- Plans cite real V2 surfaces, align with Epic non-goals/metrics.
- No production multi-tenant code executed.

**References for follow-up:**
- Full phases/metrics in Epic §6,9.
- Detailed packages in IMPL §7.
- 90-day GTM + assets in Mkt §6,8.
- Prereqs in GHL_INTEGRATION.md.
- API surfaces in GHL_API_V2_SURFACE_MAP.md.

---

## 7. Document Control

| Version | Date | Author | Notes |
|---------|------|--------|-------|
| 1.0 | 2026-07-16 | crypto-orchestrator (SYNTH-01 t_cb94942c) | Unified from MKT-01 + IMPL-01 handoffs. Critical path, RACI, open Qs consolidated, next wave recommended. |

**Canonical:** `docs/epics/SCALING_1000_UNIFIED_ROADMAP.md`  
**Related:** See sources above + `docs/DATA_FLOW_AND_LOCATIONS.md` (update on migrations), `handoffs/scaling/...`

*End of SYNTH-01 deliverable. Ready for REV-01 and executable wave.*

---

**Artifact links for MASTER:**
- Unified roadmap: `docs/epics/SCALING_1000_UNIFIED_ROADMAP.md`
- (SCALING marketing plan heavy content relocated to docs/archive/cross_project_removed/SCALING_1000_MARKETING_PLAN.md per boundary separation; no active mirrors to external consultancy)
