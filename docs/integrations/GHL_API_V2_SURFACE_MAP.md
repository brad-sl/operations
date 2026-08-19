# GHL API V2 Surface Map for SCALING-1000

**Date:** 2026-07-16  
**Epic:** `docs/epics/SCALING-1000_EPIC.md`  
**Sources:** 
- GitHub: https://github.com/GoHighLevel/highlevel-api-docs
- Marketplace Docs: https://marketplace.gohighlevel.com/docs
- Official API base (most endpoints): `https://services.leadconnectorhq.com`

**Scope for this integration (server-side, not client-side):**
- Use **Private Integration Token** for initial T0/T1 pilot (simpler, sub-account scoped, good for 1 Location).
- Migrate to **OAuth 2.0 Marketplace App** (Authorization Code + Refresh) for production SaaS scaling (per-Location tokens, webhooks, scopes, AppInstall events). 
- **Never** embed tokens in browser or GHL custom fields.

## 1. Authentication

### Private Integration Token
- Generate in GHL sub-account (Location) settings under Integrations > Private Integrations.
- Header: `Authorization: Bearer <token>`
- `Version: 2021-07-28` or `v3` header in some calls.
- Good for: internal sync, webhooks (with signing), single Location.

### OAuth 2.0 (Marketplace App)
- Register app in https://marketplace.gohighlevel.com (Private for dev, Public later).
- Target User: Sub-account (recommended).
- Scopes: select minimal (see Scopes section).
- Redirect URI for callback.
- Install URL provided by GHL.
- Exchange `code` for `access_token` + `refresh_token` via `POST /oauth/token`.
- Refresh: use refresh_token (valid ~1 year or until used; access ~24h).
- Also: Agency token can mint Location token via `/oauth/locationToken`.
- Webhook setup in app Advanced Settings (after draft/live).
- Key endpoints:
  - `POST https://services.leadconnectorhq.com/oauth/token` (auth code grant or refresh)
  - `GET /oauth/installed-locations` (list where app installed)
- Sample install payload on webhook: includes `locationId`, `companyId`, `userId`, `appId`.

**Recommendation for SCALING-1000:** Start Private Integration for T0 GHL sandbox + manual. Switch to full OAuth App for T1+ (required for public webhooks + multi-location if white-label).

## 2. Core CRM Objects

### Contacts (standard)
- Base: `/contacts/`
- Key endpoints (from docs):
  - `POST /contacts/` — Create Contact (requires `locationId`, email/phone/name etc.)
  - `GET /contacts/{contactId}`
  - `PUT /contacts/{contactId}` — Update
  - `POST /contacts/upsert` — Upsert (respects dup settings)
  - `GET /contacts/` or search variants, by businessId
  - Tags, customFields, dnd settings, assignedTo, source.
- Example create body includes firstName, email, phone, tags: ["coinbase_connected"], customFields.
- Scope examples: `contacts.write`, `contacts.readonly`
- Map: Trader human = Contact. Add tags like `trader_tier:starter`, `subscription_status:active`, `coinbase_connected`.

### Custom Objects
- Powerful for `TradingAccount` per trader.
- Schema key format: `custom_objects.YourObjectKey` (e.g. `custom_objects.tradingaccount`)
- Create schema first in GHL UI or via API (objects/schema).
- Record endpoints:
  - `POST /objects/:schemaKey/records` — Create Record
  - `GET /objects/:schemaKey/records/{id}`
  - `PUT /objects/:schemaKey/records/{id}` — Update
  - `DELETE ...`
  - Search/list with pagination.
- Body: `properties: { ...your fields... }`, `owner: ["userId"]`, `followers`
- Associations: link Contact <-> TradingAccount record via Relation/Association APIs or in workflows.
- Webhook events: `RecordCreate`, `RecordUpdate`, `RecordDelete`, `RelationCreate` etc.
- Scope: `objects/record.write`, `objects/record.readonly`, `objects/schema.*`
- **TradingAccount custom object fields** (per epic):
  - account_id (platform UUID)
  - coinbase_status (disconnected/connected/error)
  - portfolio_uuid
  - last_cycle_at, last_rebalance_at
  - runner_health (green/yellow/red)
  - deployed_pct
  - last_error_summary
  - subscription_tier or link via association

**Do not** put full balances, OAuth tokens, or raw private keys in properties.

## 3. Webhooks (Inbound — GHL → Platform)

Critical for real-time: subscription paid, OAuth done (via platform callback but status sync), billing events.

**Setup:** In Marketplace App (OAuth) or Private Integration advanced settings → Webhooks section. Toggle events + set HTTPS URL (your Integration Gateway `/ghl/webhook`).

**Verification (mandatory):**
- Headers: `X-GHL-Signature` (Ed25519, preferred; legacy `X-WH-Signature` RSA-SHA256 deprecated after ~Sep 2026)
- Public keys documented in Webhook Integration Guide.
- Always verify + respond 200 quickly; process async. Idempotent via `webhookId`.

**Key events for SCALING-1000 (relevant to W1-W7):**
- `ContactCreate`, `ContactUpdate`, `ContactTagUpdate`
- `SaaSPlanCreate` (or PlanChange, AppPaymentStatus for billing)
- `RecordCreate` / `RecordUpdate` (when platform upserts TradingAccount, or GHL side)
- `AppInstall`, `AppUninstall`, `AppPaymentStatus` (for marketplace billing)
- `InvoicePaid`, `InvoicePartiallyPaid` (if using GHL invoices)
- `Opportunity*` if using pipeline for support/escalation
- `TaskCreate` etc for ops.

**SaaSPlanCreate example payload** (from docs): planId, title, description, saasProducts[], prices[] (with amount in cents, billingInterval), productId, trialPeriod, isSaaSV2, etc.

**AppPaymentStatus:** for dunning, recurring fail/success.

Use `webhookId` + local store for dedup.

Inbound webhooks map to:
- New sub → create registry row + Contact link + default config (W1)
- Payment fail → pause runner
- etc.

Full list in https://marketplace.gohighlevel.com/docs/category/webhook

## 4. Conversations / Messaging (Outbound comms triggers)

- Use for W4 daily digest, W3 go-live, reminders, alerts (W6).
- Endpoints under `/conversations/` : create, search, get, update, send message?
- Send SMS/Email via Conversations or dedicated email/SMS actions in workflows, but platform can push via API for events.
- Also `OutboundMessage`, `InboundMessage` webhooks.
- Scope: `conversations.write` etc.
- **Preferred:** Trigger GHL Workflows from platform events (push `TradeAlert` custom object or specific webhook payload); GHL owns template rendering + delivery. Platform only emits events.

## 5. SaaS / Subscriptions / Products / Payments

- **Products & Prices:** for defining tiers (Starter/Pro/Elite).
  - `GET /products/`
  - Prices tied to products for recurring.
- **Subscriptions / Payments:**
  - `GET /payments/subscriptions/`, `/payments/subscriptions/:id`
  - List transactions, etc.
- **SaaS specific:** SaaSPlanCreate webhook, PlanChange, AppPaymentStatus, charges in marketplace billing.
- GHL handles checkout / Stripe under the hood for SaaS mode.
- Platform receives webhook → maps to tier caps in registry (never store card details).

Inbound: New subscription active → provision account (do not start trading until Coinbase OAuth complete).

## 6. Other Relevant

- Associations / Relations: for linking objects (Contact to TradingAccount).
- Opportunities / Pipelines: optional for support funnel (W6).
- Calendar / Appointments: not primary.
- Rate limits & pagination:
  - Standard REST pagination: `limit` (often max 100 or 20-50), `page`, `skip`, or cursor in some.
  - Rate limiting: documented in glossary as general mechanism; exact per-endpoint/plan limits in GHL dashboard or response headers (X-RateLimit-*). Batch upserts, respect 429s with backoff + jitter. Avoid thundering herd in scheduler.
  - Idempotency: rely on unique ids (webhookId, event_id in custom payloads), client-generated keys where supported.
- Locations / Companies: `GET /locations/:id` , sub-account vs agency tokens.

## 7. Mapping to Workflows W1–W7 & Trading Sync (per epic)

| Workflow | GHL Trigger / Endpoint | Platform Action / Sync |
|----------|------------------------|------------------------|
| W1 Onboarding — paid | SaaSPlanCreate / AppPaymentStatus / ContactCreate + subscription webhook | Create trader row + TradingAccount record (stub), send connect link |
| W2 Coinbase connect reminder | Time-based in GHL workflow (or poll status) | Platform exposes status; GHL triggers |
| W3 Go live | Platform callback sets coinbase_status=connected → upsert Record or custom webhook | GHL workflow on status change or RecordUpdate |
| W4 Daily digest | Platform pushes summary (via Record or dedicated event) | GHL workflow on digest event |
| W5 Billing dunning | GHL native + AppPaymentStatus | Platform pauses on failed |
| W6 Support runner red | Tag `needs_attention` or Task/Opportunity | Platform upserts health/error → triggers |
| W7 Offboarding | Cancel sub | Platform disconnects + final ledger |

**Platform → GHL sync (outbound, batched):**
- Upsert TradingAccount custom object record on cycle/rebalance/health (use PUT/POST records)
- Create TradeAlert records for events (rebalance, SL, error) → GHL workflow fires SMS/email
- Update Contact tags
- Never full precision P&L or secrets.

## 8. Security, Rate, Best Practices Notes

- Always verify webhook signatures (Ed25519 primary).
- HMAC for any custom platform endpoints if needed.
- Rate: implement client-side throttling + retry with exponential backoff. Shared intel (sentiment) is 1 fetch for all.
- Pagination: implement cursor or page loopers; don't assume all data in one call.
- Idempotency keys on critical upserts if API supports.
- Tokens: only in backend vault (encrypted at rest). GHL gets only public status + rounded metrics.
- Versioning: pin `Version` header where required.
- Error handling: 429 → backoff; 401 → refresh token flow; log traceId from responses.

## References & Next
- Full webhook payloads & more endpoints: marketplace docs + github repo (apps/, models/, docs/ folders contain specs).
- Scopes full table: https://marketplace.gohighlevel.com/docs/Authorization/Scopes (objects.*, contacts.*, conversations.*, payments/subscriptions.*, etc.)
- Custom objects details & record schema: https://marketplace.gohighlevel.com/docs/ghl/objects/...
- For GHL_CONTRACT.md (T1): formal OpenAPI + exact payload examples for /ghl/webhook and status API.

**This map cites live V2 surfaces as of 2026-07.** Re-validate before T1 implementation waves. Use as input for OpenAPI skeleton and gateway implementation.

**Citations for key pages:**
- Main docs & categories [from extracts].
- OAuth flows, custom objects create, SaaSPlanCreate schema, webhook guide, contacts, scopes, conversations.
