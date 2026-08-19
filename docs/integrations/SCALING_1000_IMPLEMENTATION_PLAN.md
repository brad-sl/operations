# SCALING-1000 Implementation Plan

**Epic:** `docs/epics/SCALING-1000_EPIC.md`  
**Handoff:** `handoffs/scaling/Handoff_SCALING_1000_PLAN_PACK_20260716.md` (IMPL-01)  
**Related:** `docs/integrations/GHL_API_V2_SURFACE_MAP.md` (sibling deliverable), `docs/integrations/GHL_INTEGRATION.md`, `docs/epics/SCALING-1000_EPIC.md`  
**Date:** 2026-07-16  
**Status:** PLAN ONLY — no production multi-tenant code merges in this task. All work packages are for future T0+ waves. Feature flags and isolation required.

**Goal:** Detailed technical plan to support 1,000 traders using GHL as commercial/UX layer + Coinbase OAuth + hardened Phase 6 engine. Preserve Brad's live single-account Phase 6.1 runner.

## 1. Current State (Baseline — Do Not Destabilize)

- **Trading Engine:** Single-tenant `phase6/core/phase6_runner.py` (canonical orchestrator, ~1400 LOC). Runs allocation, hybrid rebalancing, SL coordinator, sentiment. Uses direct Coinbase CDP API key (from env / config). 
- **State:** Mix of JSON files (`data/state/phase6_*.json`, live_state.json), SQLite (`data/phase6.db`), transaction ledger.
- **Config:** One global-ish config via `core/config_loader.py`. Single account (Brad's).
- **Execution:** Service or script (crypto-dashboard.service, run_live.sh, pid files). Cron via Hermes or direct.
- **Alerts:** Telegram (Brad only), structured Phase6Notifier.
- **Exchange:** `coinbase_advanced_client.py` / wrappers (CDP key path).
- **Shared intel:** Global caches for prices, RSI, sentiment (Phase 4 work).
- **Isolation:** None — all state mutable in single process/namespace.
- **GHL:** None (or minimal ramp). Manual setup per `GHL_INTEGRATION.md`. No webhooks, no registry, no multi-tenant.
- **Live:** Phase 6.1 on `phase-6.1` branch. Shadow + paper/live modes. Verified SL, rebal, etc. in prior tasks.
- **Constraints (non-negotiable):**
  - Brad's account + runner must continue uninterrupted (feature flag `MULTI_TENANT_ENABLED=false` until T1+).
  - No API keys pasted into GHL.
  - No full balances/tokens in GHL.
  - Tokens in encrypted vault only.
  - Postgres (alembic present) will be source of truth for multi-account; migrate carefully.

**What must not break:** Existing rebalance logic, SL attachment, ledger, allocation, sentiment fetch, one-off scripts, dashboard (if any), Telegram alerts for primary account.

## 2. Target Architecture (from Epic §2)

High-level (text diagram; see epic for mermaid):

```
GHL (Location) 
  Contacts + Custom Object:TradingAccount + Workflows (W1-W7) + SaaS Products + Conversations
       ↕ webhooks (in) + API upserts (out)  [HMAC / sig verify]
Integration Gateway (new, Flask/FastAPI or similar, public HTTPS)
  - POST /ghl/webhook (verify X-GHL-Signature or legacy, idempotent)
  - GET/POST /connect/coinbase + /callback
  - Internal status APIs
       ↓ (validated events)
Account Registry (Postgres: traders, trader_configs, oauth_tokens, job_runs, ...)
Job Queue / Scheduler (e.g. RQ/Redis, APScheduler, or DB-backed; staggered)
Secrets (KMS / encrypted DB / Vault; never plaintext)
       ↓ AccountContext per job
Worker Fleet (evolved from phase6_runner)
  - One or more workers; inject AccountContext (account_id, auth_mode, portfolio_uuid, tier, config_snapshot, billing_status, flags)
  - Reuse ports: TradingClient (now supports oauth + key), allocation, rebalancer, SL, ledger
  - Shared intel (sentiment/RSI/prices) keyed by (pair, window) — not per account
       ↓
Coinbase Advanced Trade (per-account OAuth + retail_portfolio_id / portfolio_uuid for orders post-May 2025)
```

**Key components to build (T0-T3):**
- Postgres schema + migrations (alembic).
- AccountContext dataclass / injector (wrap existing single-account code paths).
- OAuth adapter for TradingClient (new class or strategy implementing existing interface).
- Integration Gateway (web server for webhooks + OAuth flow).
- Sync worker (platform → GHL upserts for TradingAccount + TradeAlerts).
- Job scheduler with per-account jobs + staggering.
- Secrets management layer.
- Feature flags + dual-run (single vs multi).
- Status read API (JWT or signed for GHL iframe/member area).
- Kill switches / pause APIs.

**Shared vs per-account:**
- Shared: market data, sentiment, global pair selection (with per-account overrides in config).
- Per-account: capital allocation, positions, SL, config, OAuth tokens, ledger entries, runner health.

## 3. GHL API V2 Surface Map

**See sibling deliverable:** `docs/integrations/GHL_API_V2_SURFACE_MAP.md`

Summary for planning:
- **Auth:** Private Integration (T0) → full OAuth Marketplace App (T1+).
- **Contacts + Custom Objects (TradingAccount):** CRUD + upsert records. Use for status mirror.
- **Webhooks (inbound critical):** SaaSPlanCreate, AppPaymentStatus, Contact*, Record*, etc. Verify signatures. Idempotent processing.
- **Conversations/Messaging:** Primarily drive via GHL workflows; platform emits events.
- **SaaS/Products/Subscriptions/Payments:** Webhooks + list/get for mapping tiers.
- **Associations/Relations:** Link Contact ↔ TradingAccount.
- **Rate/pagination/idempotency:** Batch, respect limits, dedup on webhookId, use limit/page.
- **Base:** services.leadconnectorhq.com
- Map explicitly to W1-W7 and sync directions (platform canonical; GHL for UX/billing/comms).

Do **not** invent endpoints; all cited from current marketplace docs + github repo.

## 4. Platform APIs to Build (Gateway + Internal)

Per epic §4.6 (expand in GHL_CONTRACT.md at T1):

- `POST /integrations/ghl/webhook` — main inbound. Verify sig, route by type (subscription, record update, etc.), enqueue jobs. Idempotency key support.
- `GET /connect/coinbase?setup_token=...` — starts OAuth (GHL workflow sends one-time JWT or signed link).
- `GET /connect/coinbase/callback` — Coinbase redirect handler: exchange code, store tokens+portfolio_uuid, update status, notify GHL.
- `GET /api/v1/accounts/{id}/status` — read-only (health, last_rebal, deployed, errors). Secured (short JWT or GHL-signed). For member area iframe or custom code in GHL.
- `POST /internal/accounts/{id}/pause` (or kill) — ops kill switch (from Telegram or dashboard).
- Optional T1+: status push endpoints, alert ingestion.

**OpenAPI skeleton:** Create stub `docs/integrations/GHL_CONTRACT.md` (or openapi.yaml) at start of T1. Include:
- Auth (bearer or query for connect).
- Request/response examples for above.
- Error codes, rate notes.
- Webhook payload contract (subset of GHL events + our extensions).

Also internal:
- Account provisioning on sub webhook.
- Token refresh job.
- Health check for gateway.

## 5. Data Model

**Core tables (Postgres, via alembic):**

- `traders` (or accounts):
  - id (UUID PK)
  - ghl_contact_id (string, unique)
  - ghl_location_id
  - tier (starter|pro|elite)
  - billing_status (active|past_due|canceled|trialing)
  - coinbase_status (disconnected|connected|error|revoked)
  - portfolio_uuid (from OAuth)
  - auth_mode (oauth|api_key) — for Brad migration path
  - created_at, updated_at, last_cycle_at, etc.
  - flags (json or separate)

- `trader_configs`:
  - trader_id FK
  - risk_params, pair_selection, allocation_overrides, rebalance_frequency, etc. (jsonb or normalized)
  - snapshot of tier template at creation + overrides

- `oauth_tokens` (highly sensitive):
  - trader_id FK
  - access_token (encrypted)
  - refresh_token (encrypted)
  - expires_at
  - portfolio_uuid
  - scopes
  - created/updated

- `job_runs` / `cycles`:
  - id, trader_id, started_at, ended_at, status, summary (pairs traded, rebal, sl_events, errors)
  - For audit + metrics.

- `trade_alerts` (optional mirror or event log; GHL may duplicate for comms)
  - event_type, trader_id, occurred_at, payload

**Sync policy:**
- **Canonical in Postgres:** everything trading-related + tokens + full history.
- **Mirror to GHL:** status fields, rounded deployed_pct, health, last_* times, error summaries (via custom object upsert). Rounded P&L if needed for UX.
- **Never in GHL:** raw tokens, full balances, API secrets, detailed positions (unless public summary).
- Use upserts with last_updated to avoid unnecessary writes.
- Soft deletes / status for offboard.

**Additional:** Use existing transaction_ledger pattern extended with trader_id. Feature flag for multi-tenant writes.

## 6. Coinbase OAuth Details

- **Why:** Per-trader auth, revocable by user at Coinbase, aligns with SaaS model. Post May 2025: must pass `retail_portfolio_id` (or portfolio_uuid) on Create Order for spot when using OAuth.
- **Flow (trader-facing):**
  1. GHL (paid) → sends secure link with one-time token.
  2. Platform /connect/coinbase → redirects to Coinbase consent (scopes: view + trade minimum; avoid transfer).
  3. Callback → exchange, store encrypted tokens + discover portfolio_uuid (via /portfolios or permissions), mark connected.
  4. GHL notified (webhook or status poll) → W3 "go live".
- **Adapter:** New `OAuthCoinbaseTradingClient` (or adapter) implementing `TradingClient` port from Phase 6.
  - Handles token refresh on 401.
  - Injects portfolio on order calls.
  - Brad's account: keep `auth_mode: api_key` path (CDP key) until explicitly migrated.
- **Sandbox:** Use Coinbase sandbox for T0-03 spike. Live pilot: optional dedicated small account or Brad's with care.
- **Scopes:** `wallet:accounts:read`, `wallet:transactions:read`, Advanced Trade trade scopes. Confirm exact in Coinbase docs at impl time.
- **Storage:** Only backend. Refresh proactively or on failure.
- **Revoke/Disconnect:** User at Coinbase or platform kill → stop jobs, update status, optional reduce-only exit.

**Pilot account vs Brad:** Use separate test OAuth for dev; Brad remains key-based.

## 7. Phased Work Packages (Expanded T0-T3)

See epic §6 for high-level. Here: engineer-sized, with estimates (S=1-3 dev days, M=4-10, L=11+), deps, isolation/verification notes. **No prod runner changes until isolated tests pass.**

### T0 — Twin account proof (engine + stub GHL; 2 accounts, shadow)
Goal: Isolate 2 accounts (Brad + 1 test) on same host; OAuth roundtrip in sandbox; GHL manual only.

| ID | Package | Est | Deps | Details / Isolation Tests |
|----|---------|-----|------|---------------------------|
| T0-01 | Postgres schema + migrations | S | None (new) | Create tables (traders, configs, oauth_tokens, job_runs). Alembic. ERD review. Test: migrate, insert 2 rows, query. |
| T0-02 | AccountContext + injection | M | T0-01 | Dataclass + context manager or dependency injection. Wrap runner/coordinator/SL/ledger calls. Feature flag `MULTI_TENANT_ENABLED`. Dual path: if false, use legacy single-account globals/JSON. Test: run two contexts side-by-side, assert no shared mutable state leaks. |
| T0-03 | OAuth Coinbase adapter spike | M | T0-01, T0-02 | Implement adapter using sandbox OAuth. Portfolio handling. Token store (temp encrypted). Test: full connect → place/cancel sandbox order → refresh flow. Brad path untouched. |
| T0-04 | Job queue / scheduler | M | T0-02 | Simple queue (RQ + Redis or in-proc + DB polling for start). `schedule_run_cycle(account_id)`. Staggering stub. Test: enqueue 2 accounts, execute independently, no overlap interference. |
| T0-05 | Isolation tests + dual runner | L | T0-01..04 | Hardened tests: cross-account data leak checks (positions, logs, alerts, cache keys). Shadow run 2 accounts (one real Brad via flag, one test). Metrics diff. Kill switch per account. |
| GHL-T0 | GHL sandbox Location + Custom Object | S | None | Manual: create Location/pilot, define TradingAccount schema + fields (per epic), 2 test contacts + records via UI/CSV. Document schemaKey. No automation. Verify fields visible in workflows. |

**T0 Exit (per epic):** Two accounts cycle in shadow; OAuth place/cancel sandbox; no GHL automation yet. Brad live untouched.

### T1 — GHL commercial loop (10-50 traders; end-to-end paid → live)
Goal: Paid in GHL → OAuth → trading + comms. 24h happy path.

| ID | Package | Est | Deps | Details |
|----|---------|-----|------|---------|
| GHL-01 | Private Integration + webhook gateway (staging) | M | T0 | Deploy gateway (dedicated host req). HMAC/sig verify. Route SaaS/ contact events. Idempotency. Test: curl signed payload, process once. |
| GHL-02 | Workflows W1-W3, W5 | M | GHL-01, T0 | In GHL: build W1 (paid → connect link), W2 (reminders), W3 (connected → live), W5 (dunning → pause call). Test end-to-end with staging. |
| GHL-03 | SaaS products ↔ tier mapping | S | GHL-01 | Table/config: product/price → tier caps. Enforce in registry on provision. |
| GHL-04 | Platform → GHL upsert worker | M | T0-02, GHL-01 | Periodic or event-driven: upsert TradingAccount record + tags + alerts. Batch, rate aware. Test: cycle produces visible GHL update. |
| T1-01 | Staggered scheduler | S | T0-04 | Spread jobs (e.g. by account_id hash or time buckets). Avoid herd on shared data. |
| T1-02 | Shared sentiment/RSI cache (multi-tenant) | M | Existing Phase4 | Key by (pair, window). Per-account only selects/allocates. |
| T1-03 | Per-account SL remediation | S | T0-02 | Remove manual `reattach_sl_once`; job per account or on error. |
| T1-04 | Read-only status API | S | GHL-04 | `/api/v1/accounts/{id}/status`. JWT or token for GHL. Read from registry + recent run. |
| T1-GHL extras | W4 stub, basic TradeAlert | S | GHL-04 | Push digest events; create alert records for comms. |

**T1 Exit:** End-to-end test trader: pay (GHL) → email → OAuth → green health in GHL object <24h. Runner cycles the new account.

### T2 — Fleet hardening (50-200)
- T2-01: Autoscaling / sharding (N accounts/pod). K8s or process pool.
- T2-02: Central rate limiter (per OAuth client + per account).
- T2-03: Reconciliation job (Coinbase vs ledger) per account.
- T2-04: W4 daily + W6 escalation (ops tag + task).
- T2-05: Audit export (CSV / signed API).
- GHL-05: TradeAlert object + notification templates.

### T3 — 1,000 traders
- Load/chaos tests (T3-01/02).
- Multi-region/shard plan.
- Key rotation + OAuth refresh failure playbooks.
- GHL-06: White-label Location template (optional).

**Estimates total rough:** T0 ~ S+M+L mix ~3-6 weeks part time; T1 adds GHL work ~4-8 weeks. Depends on hosting + GHL setup ramp.

## 8. Hosting Prereqs (Critical)

From `GHL_INTEGRATION.md`:
- **Dedicated host** for Phase 6 + gateway (not Brad's HP laptop for prod webhooks). Stable public HTTPS URL (domain + cert), uptime SLA, secrets mgmt.
- Local ngrok / tunnel only for dev spikes.
- Webhook target must be reachable 24/7; GHL will retry but design for at-least-once.
- Consider VPS (Hetzner/DO/AWS), Docker, systemd or supervisor for runner + gateway.
- Separate staging/prod if possible.
- Logging/monitoring for gateway (requests, sig fails, latency).

**Before T1 waves:** Complete this + GHL Location + Private Integration creds.

## 9. Security

- **Secrets:** Encrypted at rest (e.g. Fernet + key in env/KMS, or proper vault). oauth_tokens table never plaintext. Never git, never logs, never GHL.
- **Webhooks:** Mandatory signature verification (prefer X-GHL-Signature Ed25519). Reject invalid.
- **OAuth:** Short-lived access + refresh handling. Scope minimal (view+trade). User revocable.
- **Gateway:** HTTPS only, rate limit inbound, validate all inputs, no token exposure.
- **DB:** Row-level if multi-tenant later; least-privilege DB user.
- **Feature flags + isolation:** Guard all multi paths. Canary accounts.
- **Auditing:** job_runs + ledger for all actions per account.
- **Compliance notes:** No guaranteed returns in any surfaced data. Deposit-adjusted honesty in any status.
- **Kill switches:** Per-account pause independent of GHL.

## 10. Exit Criteria (per phase, matching epic §6-9)

- **T0:** 2 accounts (incl. Brad legacy path), shadow cycles, OAuth sandbox success, manual GHL objects, isolation tests green. No breakage to live single runner.
- **T1:** E2E paid → connected → trading + GHL status visible. W1-W3,W5. 10+ accounts possible in staging. Median onboarding <15min target.
- **T2:** Fleet handles 50-200 with sharding/recon/limiters. W4/W6. 95%+ runner healthy.
- **T3:** Load to 1000 simulated, graceful degradation on errors, key mgmt playbooks. 99% healthy, <1min sync lag.
- Cross-cutting: 0 cross-tenant incidents. All docs updated. MASTER links.

## 11. Risks & Mitigations (from epic + plan)

- GHL rate limits / object limits per Location → batch delta syncs only; monitor; fallback to polling.
- Coinbase portfolio rule / token refresh fail → store uuid; pause + alert on refresh fail.
- Hosting/webhook downtime → dedicated host; queue + retry; health dashboards.
- Scope creep → strict T0/T1 gates; no 1000 until T2 green.
- Brad account impact → all changes behind flags + parallel paths + extensive isolation tests.
- Token security → encryption + KMS + audits.
- Regulatory/comms → GHL owns marketing claims; platform surfaces facts only.

## 12. Open Questions / Decisions for SYNTH / Brad (to feed SYNTH-01)

- Exact tier caps / pricing (align with product GTM / pricing plan (heavy marketing plan archived; see DOC_BOUNDARY_AUDIT)).
- Dedicated host provider + domain.
- GHL Location ID / Private token (or full OAuth app timing).
- Queue tech (RQ? Postgres?).
- Encryption lib / KMS choice.
- Exact JWT for status API (or GHL custom code).
- When to migrate Brad to OAuth (post T1?).
- Monitoring stack for fleet (Prom?).
- Backup/restore for tokens + ledger.
- White-label vs single brand.

## 13. Next Steps After This Plan (not for this task)

- SYNTH-01: unified roadmap + RACI + next Kanban wave recs (T0-01 + GHL-T0 + funnel skeleton?).
- REV-01 sign-off.
- Then: actual T0-01 card: schema + ERD.
- Update MASTER with links to these plans.
- Ramp: GHL sub-account + host before heavy impl.

**Success for IMPL-01:** These two docs exist, complete per handoff scope, cite real V2 endpoints, expand phases, cover arch/security/data/hosting/OAuth. No prod multi-tenant runner changes executed.

**References:**
- Epic full phases/metrics/non-goals.
- GHL_INTEGRATION.md (prereqs + delegation).
- GHL_API_V2_SURFACE_MAP.md (detailed endpoints).
- Coinbase OAuth docs (portfolio enforcement May 2025+).
- Phase 6 current runner + state files for baseline.

Plan ready for review & synthesis.
