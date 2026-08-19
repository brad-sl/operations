# Epic: SCALING-1000 — Multi-Trader Platform (GHL + Coinbase OAuth)

**Status:** Planned  
**Created:** 2026-07-06  
**Owner:** Platform / Ops  
**Supersedes / extends:** `docs/archive/phase6-old/PHASE6_GAP_ANALYSIS_AND_BACKLOG.md`  
**Single-account baseline:** Phase 6 live runner on `phase-6.1` (stable); do **not** destabilize Brad’s account while building alongside.

---

## 1. North Star

Support **1,000 independent traders**, each with:

- Own Coinbase connection (**OAuth2**, not shared API keys)
- Own capital limits, risk tier, and trading config
- Own audit trail (orders, fills, SL events)
- **No cross-tenant data leaks** (state, logs, alerts, credentials)

**GoHighLevel (GHL)** is the **commercial & experience layer**:

| GHL owns | Trading engine owns |
|----------|---------------------|
| Marketing sites / funnels | Signals, allocation, execution, CR-03 |
| Trader onboarding UX (forms, e-sign if needed) | Coinbase OAuth token lifecycle |
| Subscriptions & SaaS billing (plans, dunning) | Per-account runner jobs |
| Email / SMS / in-app comms templates | Ledger, reconciliation, kill switches |
| CRM (contacts, pipelines, support) | Secrets vault, rate limits, fleet health |
| Client-facing status summaries (fed by API) | Raw exchange API calls |

**Principle:** Traders never paste API keys into GHL. They connect Coinbase via **OAuth** on a **platform-controlled** connect URL; tokens live only in the backend vault.

---

## 2. Architecture (target)

```
                    ┌─────────────────────────────────────┐
                    │     GoHighLevel (per Location)      │
                    │  Contacts · Pipelines · Workflows   │
                    │  SaaS Plans · Subscriptions · Comms │
                    │  Custom Object: TradingAccount        │
                    └──────────────┬──────────────────────┘
                                   │ webhooks in / API out
                    ┌──────────────▼──────────────────────┐
                    │   Integration Gateway (new service)   │
                    │  POST /ghl/webhooks/*  (provision)    │
                    │  POST /coinbase/oauth/callback        │
                    │  HMAC verify · idempotency keys       │
                    └──────────────┬──────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
         ▼                         ▼                         ▼
┌─────────────────┐    ┌──────────────────────┐   ┌─────────────────┐
│ Account Registry │    │  Job Queue / Scheduler│   │  Secrets (KMS)  │
│ (PostgreSQL)     │    │  run_cycle(account)   │   │  OAuth tokens   │
└────────┬─────────┘    └──────────┬───────────┘   └─────────────────┘
         │                         │
         └────────────┬────────────┘
                      ▼
         ┌────────────────────────────┐
         │  Worker Fleet (Phase 6)    │
         │  AccountContext injected   │
         │  TradingClient = OAuth     │
         │  adapter per account       │
         └────────────────────────────┘
                      │
                      ▼
              Coinbase Advanced Trade
              (per-user OAuth + portfolio_id)
```

**Shared intel layer** (one fetch → many accounts): sentiment, RSI, pair prices — keyed by `(pair, window)`, not by `account_id`. Accounts only differ in **which pairs they trade** and **how much capital** they deploy.

---

## 3. Coinbase OAuth (authN / authZ)

### 3.1 Why OAuth (not API keys in CRM)

- Coinbase documents **OAuth2 for third-party access** to user accounts; API keys are for **your own** account only.
- Traders revoke access at [Coinbase connections](https://accounts.coinbase.com/security/connections) without rotating platform keys.
- Aligns with SaaS: each trader = distinct authorization grant.

### 3.2 Platform obligations (2025+)

- **Portfolio-scoped trading:** After May 2025, OAuth apps must specify **`portfolio_id`** on Advanced Trade **Create Order** when users restrict portfolio access. Registry must store `portfolio_uuid` per account (discovered at connect or from permissions API).
- **Token storage:** Access + refresh tokens encrypted at rest (KMS/Vault); never in GHL custom fields, never in git, never in Hermes memory.
- **Scopes (minimum viable):** `view` + trade scopes required for rebalance/SL; avoid `transfer` unless product explicitly needs withdrawals.
- **Adapter:** New `OAuthCoinbaseTradingClient` implementing existing `TradingClient` port; Brad’s account may remain on CDP API key path until migrated (`auth_mode: api_key | oauth`).

### 3.3 Connect flow (trader-facing)

1. GHL workflow: subscription active → send link `https://app.<brand>/connect/coinbase?token=<one-time-setup-jwt>`
2. Platform OAuth redirect → Coinbase consent → callback stores tokens → marks `TradingAccount.coinbase_status = connected`
3. GHL workflow branch: connected → “you’re live” sequence; failed → support pipeline
4. Disconnect: trader revokes at Coinbase **or** admin kill switch → worker stops scheduling cycles; GHL status `paused`

---

## 4. GoHighLevel buildout

### 4.1 GHL account model

- **One GHL Location** (or sub-accounts per white-label partner later).
- **Private Integration** (API key + webhook signing) for server-to-server — not embedded in client browsers.
- Plan features: **Custom Objects** (available on current tiers with per-location limits — design ≤10 object types; use associations heavily).

### 4.2 CRM objects & fields

**Contact** (standard) — the human trader.

| Field / tag | Purpose |
|-------------|---------|
| `trader_tier` | Maps to risk/capital template |
| `subscription_status` | active / past_due / canceled |
| `platform_account_id` | UUID in our registry (not Coinbase id) |
| Tags | `coinbase_connected`, `runner_healthy`, `needs_attention` |

**Custom Object: `TradingAccount`** (one per trader, associated to Contact)

| Field | Source of truth | Sync direction |
|-------|-----------------|----------------|
| `account_id` | Platform registry | Platform → GHL |
| `coinbase_status` | disconnected / connected / error | Platform → GHL |
| `portfolio_uuid` | OAuth connect | Platform → GHL (internal, not shown to trader) |
| `last_cycle_at` | Worker | Platform → GHL |
| `last_rebalance_at` | Worker | Platform → GHL |
| `runner_health` | green / yellow / red | Platform → GHL |
| `deployed_pct` | Telemetry | Platform → GHL |
| `last_error_summary` | Ops | Platform → GHL |

**Optional Custom Object: `TradeAlert`** (append-only rows for comms)

- Association: TradingAccount → TradeAlert  
- Fields: `event_type`, `pair`, `message`, `occurred_at`  
- GHL workflow: new record → SMS/email template

Do **not** store OAuth tokens or balances with full precision in GHL if avoidable; use rounded metrics for marketing, detailed numbers in platform DB only.

### 4.3 SaaS & subscriptions (GHL engine)

Use GHL **SaaS mode** / subscription products:

| Product tier (example) | Trading limits (platform enforces) |
|----------------------|-------------------------------------|
| Starter | Max deployable $X, 6 pairs, 1× daily rebalance |
| Pro | Higher cap, 11 pairs, hybrid triggers |
| Elite | Custom pairs window, priority support tag |

**Inbound webhooks (GHL → Platform):**

| Event | Platform action |
|-------|-----------------|
| New subscription / plan created | Create `account_id`, Contact link, default config, **do not** start trading until OAuth |
| Subscription updated | Adjust tier caps in registry |
| Payment failed / canceled | `billing_status=canceled` → stop worker, optional reduce-only exit policy |
| Contact created (funnel) | Staging record; no runner |

**Outbound (Platform → GHL API):**

- Upsert `TradingAccount` custom object fields on cycle/rebalance/health change (batched, rate-aware).
- Create `TradeAlert` rows for trader-visible events (rebalance executed, SL attached, actionable error).
- Update Contact tags for segmentation (campaigns).

### 4.4 GHL workflows (minimum set)

| # | Workflow | Trigger |
|---|----------|---------|
| W1 | **Onboarding — paid** | Subscription active |
| W2 | **Coinbase connect reminder** | 24h/72h without `coinbase_connected` |
| W3 | **Go live** | Webhook: `coinbase_status=connected` |
| W4 | **Daily digest** | Webhook: `daily_summary_ready` (platform pushes payload) |
| W5 | **Billing dunning** | GHL native + platform pause on 2nd failure |
| W6 | **Support — runner red** | Tag `needs_attention` → task for ops |
| W7 | **Offboarding** | Cancel → confirm disconnect Coinbase + final statement email |

### 4.5 Trader-facing surfaces in GHL

- **Funnel / website:** value prop, pricing, checkout (GHL payments / Stripe via GHL).
- **Member area / custom menu link:** “Connect Coinbase” + “Status” (iframe or link to platform read-only dashboard).
- **Comms:** all lifecycle email/SMS in GHL; trading engine sends **events**, not raw SMTP.

### 4.6 Integration Gateway API (platform exposes)

| Endpoint | Caller | Notes |
|----------|--------|-------|
| `POST /integrations/ghl/webhook` | GHL | Verify signature; idempotent by `event_id` |
| `GET /connect/coinbase` | Browser | Starts OAuth |
| `GET /connect/coinbase/callback` | Coinbase | Token exchange |
| `GET /api/v1/accounts/{id}/status` | GHL custom code / iframe | Read-only JWT |
| `POST /internal/accounts/{id}/pause` | Ops | Kill switch |

Document OpenAPI + shared secret rotation in `docs/integrations/GHL_CONTRACT.md` (T1 deliverable).

---

## 5. Trading engine changes (summary)

| Component | Today | Target |
|-----------|-------|--------|
| State | `data/state/*.json` | `accounts/{id}/*` or DB rows |
| Runner | Singleton `phase6_runner` | Worker consumes `account_id` jobs |
| Config | One JSON file | Per-account row + tier template |
| Exchange | CDP API key from `.env` | OAuth adapter + `portfolio_id` |
| Crons | Hermes single-tenant | Fleet scheduler + per-shard Hermes/ k8s |
| Alerts | Telegram Brad | GHL events + ops Telegram aggregate |
| Sentiment | Global cache files | Shared cache service (multi-tenant Phase 4) |

**AccountContext** (mandatory fields): `account_id`, `auth_mode`, `portfolio_uuid`, `tier`, `config_snapshot`, `billing_status`, `feature_flags`.

---

## 6. Phased delivery

### Phase T0 — Twin account proof (engine only, GHL stub)

**Goal:** Two isolated accounts on one host; Brad unchanged.

| ID | Work |
|----|------|
| SCALING-1000-T0-01 | PostgreSQL schema: `traders`, `trader_configs`, `oauth_tokens`, `job_runs` |
| SCALING-1000-T0-02 | `AccountContext` + inject through runner/coordinator/SL |
| SCALING-1000-T0-03 | OAuth Coinbase adapter (sandbox + one live pilot account) |
| SCALING-1000-T0-04 | Queue: Redis/RQ job `run_cycle(account_id)` |
| SCALING-1000-T0-05 | Isolation tests: two accounts, no shared mutable state |
| SCALING-1000-GHL-T0 | GHL sandbox Location + Custom Object schema drafted; manual CSV import of 2 test contacts |

**Exit:** Two accounts cycle in shadow; OAuth place/cancel in sandbox; no GHL automation required yet.

---

### Phase T1 — GHL commercial loop (10–50 traders)

**Goal:** Paid signup → OAuth → live trading with GHL comms.

| ID | Work |
|----|------|
| SCALING-1000-GHL-01 | Private Integration + webhook endpoint deployed (staging) |
| SCALING-1000-GHL-02 | Workflows W1–W3, W5 live |
| SCALING-1000-GHL-03 | SaaS products ↔ tier caps mapping table |
| SCALING-1000-GHL-04 | Platform → GHL upsert worker (TradingAccount sync) |
| SCALING-1000-T1-01 | Staggered scheduler (avoid thundering herd) |
| SCALING-1000-T1-02 | Shared sentiment/RSI cache (RSI multi-tenant Phase 4) |
| SCALING-1000-T1-03 | Per-account SL remediation job (no manual `reattach_sl_once`) |
| SCALING-1000-T1-04 | Read-only status API for GHL iframe |

**Exit:** End-to-end test trader: pay in GHL → email → OAuth → green health in GHL object within 24h.

---

### Phase T2 — Fleet hardening (50–200 traders)

| ID | Work |
|----|------|
| SCALING-1000-T2-01 | Worker autoscaling / sharding (N accounts per pod) |
| SCALING-1000-T2-02 | Central rate limiter per OAuth client_id + per account |
| SCALING-1000-T2-03 | Reconciliation job (Coinbase vs ledger) per account |
| SCALING-1000-T2-04 | W4 daily digest + W6 ops escalation |
| SCALING-1000-T2-05 | Audit export (CSV/API) for compliance questions |
| SCALING-1000-GHL-05 | TradeAlert object + trader notification templates |

---

### Phase T3 — 1,000 traders

| ID | Work |
|----|------|
| SCALING-1000-T3-01 | Load test 100 → 500 → 1000 simulated accounts |
| SCALING-1000-T3-02 | Chaos: 401/429 on subset; verify fleet degrades gracefully |
| SCALING-1000-T3-03 | Multi-region or multi-shard deployment plan |
| SCALING-1000-T3-04 | Key rotation, OAuth refresh failure playbook |
| SCALING-1000-GHL-06 | Partner/white-label Location template (optional) |

---

## 7. Non-goals (this epic)

- Building a custom trader CRM (GHL is it).
- Storing payment cards on the trading server (GHL/Stripe owns PCI scope).
- 1,000 concurrent Hermes chat sessions.
- Migrating Brad’s live account to OAuth on day one (optional later).

---

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| GHL API rate limits / object limits | Batch sync; only delta fields; keep canonical state in Postgres |
| Coinbase OAuth portfolio rule | Store `portfolio_uuid` at connect; integration test create-order |
| Token refresh failures | Pause account; GHL W6; alert ops |
| Trader expects GHL to “be” the exchange | Copy/docs: GHL = billing/comms; Coinbase = funds |
| Epic scope creep | T0/T1 gates; no 1000 load until T2 reconciliation green |

---

## 9. Success metrics

| Metric | T1 | T3 |
|--------|----|----|
| Median onboarding (pay → connected) | < 15 min human time | < 5 min |
| Accounts with runner green | 95% | 99% |
| Cross-tenant incident count | 0 | 0 |
| GHL sync lag | < 5 min | < 1 min |
| Shared intel API calls / pair / hour | 1 | 1 |

---

## 10. Documentation map

| Doc | When |
|-----|------|
| `docs/integrations/GHL_INTEGRATION.md` | **Now** — ramp-up prerequisites + Hermes `delegation.provider` note before GHL dev waves |
| `docs/integrations/GHL_CONTRACT.md` | T1 start |
| `docs/integrations/COINBASE_OAUTH.md` | T0-03 |
| `handoffs/scaling/Handoff_SCALING-1000_T0.md` | T0 kickoff |
| `docs/DATA_FLOW_AND_LOCATIONS.md` | Update on first DB migration |

---

## 11. MASTER linkage

All child tasks logged under **SCALING-1000** in `docs/MASTER_TASK_TRACKING.md`. Kanban epic: `SCALING-1000` (create when T0-01 starts).

**Next concrete action:** `SCALING-1000-T0-01` — trader registry schema + ERD review (no production runner changes).