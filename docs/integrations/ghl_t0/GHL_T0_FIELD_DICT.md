# GHL-T0 Field Dictionary — TradingAccount + Contact + SaaS

**Task:** SCALING-1000-PHASE-A-03 / GHL-T0 (manual)  
**Date:** 2026-07-17  
**Status:** Spec ready for manual GHL UI setup — live Location/token/records pending human admin  
**Canonical sources:** `SCALING-1000_EPIC.md` §4.2–4.3, `SCALING_1000_MARKETING_PLAN.md` §2.2, `GHL_API_V2_SURFACE_MAP.md`, `SCALING_1000_UNIFIED_ROADMAP.md`  
**Product brand (placeholder):** ARCH Automation (until PHASE-A-01 brand lock)

---

## 0. Principles (non-negotiable)

| Rule | Detail |
|------|--------|
| Platform is canonical | Registry/Postgres owns truth for trading state, OAuth, balances, orders |
| GHL is commercial mirror | CRM, SaaS billing, workflows, rounded status for UX/comms |
| Never in GHL | OAuth tokens, refresh tokens, API keys, full-precision balances, private keys |
| Sync direction | Almost all TradingAccount fields: **Platform → GHL** (upsert worker GHL-04) |
| Object budget | ≤10 custom object types per Location (use 1 now; TradeAlert optional later) |
| schemaKey | `custom_objects.tradingaccount` (API prefix `custom_objects.` is automatic if key = `tradingaccount`) |

---

## 1. Location (sub-account)

| Item | Pilot value | Notes |
|------|-------------|-------|
| Name | `ARCH Automation — Pilot` (or `ARCH-Pilot-Sandbox`) | Rename after brand lock |
| Mode | Sandbox / pilot first | Not production runner target |
| Timezone | `America/Los_Angeles` | Align with Phase 6 ops |
| Currency | USD | SaaS prices in USD |
| Location ID | _FILL after create_ | Store only in secure note (see runbook) |

---

## 2. Contact (standard) — human trader

### 2.1 Custom fields (Contact)

| Internal key (suggested) | UI label | Type | Allowed values | Source of truth | Sync | Notes |
|--------------------------|----------|------|----------------|-----------------|------|-------|
| `trader_tier` | Trader Tier | Single-select / dropdown | `starter`, `pro`, `elite` | GHL SaaS plan + platform registry | Bidirectional via payment events | Maps to platform caps |
| `subscription_status` | Subscription Status | Single-select | `active`, `past_due`, `canceled`, `trialing`, `none` | GHL billing | GHL → Platform (webhook) | Platform pauses on past_due/canceled |
| `platform_account_id` | Platform Account ID | Text (UUID) | UUID v4 | Platform registry | Platform → GHL | Not Coinbase user id |
| `pilot_cohort` | Pilot Cohort | Text / dropdown | e.g. `closed-2026q3` | Mkt | Manual | Invite-only tracking |
| `connect_link_sent_at` | Connect Link Sent At | DateTime | ISO | GHL workflow W1 | GHL | Optional T1 |

### 2.2 Tags (Contact)

| Tag | Purpose | Set by |
|-----|---------|--------|
| `paid` | Subscription active / paid cohort | GHL SaaS / W1 |
| `coinbase_connected` | OAuth complete | Platform → tag update |
| `runner_healthy` | runner_health = green | Platform sync |
| `needs_attention` | Health red/yellow or ops flag | Platform / W6 |
| `trader_tier_starter` | Segmentation | On provision |
| `trader_tier_pro` | Segmentation | On provision |
| `trader_tier_elite` | Segmentation | On provision |
| `priority_support` | Elite ops path | On Elite plan |
| `pilot` | Closed cohort | Manual / invite |
| `do_not_market_perf` | Claims policy: no P&L marketing | Manual if needed |

### 2.3 Contact custom field → GHL UI create checklist

Create under **Settings → Custom Fields → Contact** (or equivalent). Use exact labels above for workflow readability; map internal keys in platform config later (`GHL_CONTRACT.md` at T1).

---

## 3. Custom Object: TradingAccount

### 3.1 Object identity

| Property | Value |
|----------|-------|
| Singular label | Trading Account |
| Plural label | Trading Accounts |
| Key | `tradingaccount` → full schemaKey **`custom_objects.tradingaccount`** |
| Description | Per-trader automation status mirror (platform canonical). No secrets. |
| Primary display property | `account_id` (TEXT) — shows platform UUID in list views |
| Association | Contact ↔ TradingAccount (one Contact : one TradingAccount for pilot) |

### 3.2 Fields

| Field key | UI label | GHL field type | Allowed / format | Source of truth | Sync direction | Trader-visible? | Notes |
|-----------|----------|----------------|------------------|-----------------|----------------|------------------|-------|
| `account_id` | Account ID | Text | UUID | Platform registry | Platform → GHL | Ops / member status (opaque id OK) | Primary display; unique |
| `display_name` | Display Name | Text | free text | Platform / Contact name | Platform → GHL | Yes (optional) | e.g. "Pilot A — Starter" |
| `coinbase_status` | Coinbase Status | Single-select | `disconnected`, `connected`, `error` | Platform OAuth | Platform → GHL | Yes (status only) | W2/W3 triggers |
| `portfolio_uuid` | Portfolio UUID | Text | Coinbase portfolio id | OAuth connect | Platform → GHL | **No** (internal) | Needed for Advanced Trade orders; hide from client menus if possible |
| `subscription_tier` | Subscription Tier | Single-select | `starter`, `pro`, `elite` | GHL plan / registry | Prefer GHL plan event → Platform → mirror | Ops | Align with Contact `trader_tier` |
| `billing_status` | Billing Status | Single-select | `active`, `past_due`, `canceled`, `none` | GHL billing | GHL → Platform; mirror optional | Ops | Platform enforces pause |
| `runner_health` | Runner Health | Single-select | `green`, `yellow`, `red`, `unknown` | Platform telemetry | Platform → GHL | Yes (high level) | W6 on red |
| `deployed_pct` | Deployed % | Number | 0–100, **1 decimal max** | Telemetry | Platform → GHL | Yes (rounded) | Never full wallet precision |
| `last_cycle_at` | Last Cycle At | DateTime | ISO-8601 | Worker | Platform → GHL | Ops / member | |
| `last_rebalance_at` | Last Rebalance At | DateTime | ISO-8601 | Worker | Platform → GHL | Ops / member | |
| `last_sync_at` | Last Sync At | DateTime | ISO-8601 | Sync worker | Platform → GHL | Ops | When GHL was last upserted |
| `last_error_summary` | Last Error Summary | Multi-line text | ≤280 chars, sanitized | Ops | Platform → GHL | Ops (careful in client view) | No stack traces, no secrets |
| `alerts_open_count` | Alerts Open Count | Number | integer ≥0 | Platform | Platform → GHL | Ops | Optional rollup |
| `pair_count_cap` | Pair Count Cap | Number | 6 / 11 / custom | Tier template | Platform → GHL (mirror) | Ops | Starter=6, Pro=11 |
| `max_deploy_usd` | Max Deploy USD | Number | integer dollars | Tier template | Platform → GHL (mirror) | Ops | Pilot placeholders — finalize with Eng/Brad |
| `notes_internal` | Notes (Internal) | Multi-line text | free | Ops | Manual | No | Pilot friction log |

### 3.3 Explicitly forbidden on this object

- `access_token`, `refresh_token`, `api_key`, `api_secret`
- Full balances, positions JSON, order books
- Card numbers / Stripe customer secrets
- Brad personal Phase 6 account identifiers used as product demo proof

### 3.4 Optional later object: TradeAlert (do **not** create in T0 unless spare object budget)

| Field | Type | Notes |
|-------|------|-------|
| `event_type` | Single-select | rebalance, sl_attach, error, digest, pause |
| `pair` | Text | e.g. BTC-USD |
| `message` | Text | Short, compliance-safe |
| `occurred_at` | DateTime | Event time |
| Association | TradingAccount → TradeAlert | Append-only; W4/W6 |

---

## 4. SaaS products (pilot draft prices)

**Status:** Pilot placeholders from MKT plan §2.2. Brad A final before public checkout.  
**Currency:** USD monthly. Trial: optional 0 days for closed cohort (comps allowed).

| Product name (UI) | Internal SKU | Pilot monthly price | Platform caps (enforced in registry, not GHL) | Messaging angle |
|-------------------|--------------|---------------------|-----------------------------------------------|-----------------|
| ARCH Starter | `arch_starter_mo` | **$39** | Max deploy pilot class ~$1k–$3k (finalize), **6 pairs**, 1× daily rebalance window | Start simple. OAuth. Clear caps. |
| ARCH Pro | `arch_pro_mo` | **$99** (draft) | Higher deploy cap, **11 pairs**, dual rebalance windows | More pairs, more cadence. |
| ARCH Elite | `arch_elite_mo` | **$249** (draft) or custom | Custom pairs window, priority support tag | Priority ops + flexible config. |

**Pilot recommendation:** Create all three products; sell/invite **Starter first**. Pro/Elite can remain unlisted/inactive in checkout until pricing lock.

**GHL product fields to set:**

| Product | Description (short, compliance-safe) |
|---------|--------------------------------------|
| Starter | Automated rebalancing access for Coinbase Advanced. Capital stays in your Coinbase account. Connect via OAuth. No return guarantees. |
| Pro | Expanded pair set and rebalance cadence. Same non-custodial OAuth model. |
| Elite | Priority support path and flexible config window. Same non-custodial OAuth model. |

**Never claim** returns, “risk-free,” or use Brad personal P&L in product copy.

### 4.1 Tier mapping table (platform config draft)

```yaml
# For GHL-03 later — do not hardcode secrets
tier_map:
  arch_starter_mo:
    trader_tier: starter
    pair_count_cap: 6
    max_deploy_usd: null   # set after Eng unit-econ (pilot class 1000-3000)
    rebalance_windows: 1
  arch_pro_mo:
    trader_tier: pro
    pair_count_cap: 11
    max_deploy_usd: null
    rebalance_windows: 2
  arch_elite_mo:
    trader_tier: elite
    pair_count_cap: null   # custom
    max_deploy_usd: null
    rebalance_windows: null
    tags: [priority_support]
```

After create, record GHL `productId` / price IDs in secure note + this file’s appendix (IDs only, no tokens).

---

## 5. Pipelines & stages

### 5.1 Pipeline: Trader Onboarding (pilot)

| Stage | Meaning | Typical tags |
|-------|---------|--------------|
| Invite / Waitlist | Not paid | `pilot` |
| Paid — Awaiting Connect | Sub active, no OAuth | `paid` |
| Connecting | Connect link sent | `paid` |
| Live — Healthy | coinbase connected + green | `paid`, `coinbase_connected`, `runner_healthy` |
| Needs Attention | yellow/red or ops | `needs_attention` |
| Paused / Billing | past_due or admin pause | `paid` or remove |
| Offboarded | canceled + disconnected | — |

### 5.2 Pipeline: Support Escalation (optional pilot)

| Stage | Meaning |
|-------|---------|
| New | needs_attention opened |
| Investigating | Ops working |
| Waiting on trader | Need Coinbase re-auth / action |
| Resolved | Tag cleared |

Opportunities are optional for T0; tags alone are enough for shadow testing.

---

## 6. Private Integration scopes (minimal for T0 shadow + T1 prep)

Create under Location → **Settings → Integrations → Private Integrations**.  
Name: `arch-platform-t0-shadow`.  
**Do not enable webhooks URL to production runner yet.**

Recommended scopes (enable only what UI offers; names may vary slightly):

| Scope family | Purpose |
|--------------|---------|
| `contacts.readonly` / `contacts.write` | Test contacts + tags |
| `objects/schema.readonly` | Inspect schema |
| `objects/record.readonly` / `objects/record.write` | TradingAccount records |
| `products.readonly` / `products/prices.readonly` | Tier mapping |
| `payments/subscriptions.readonly` | Future billing map |
| `opportunities.readonly` / `opportunities.write` | Pipelines if used |
| `locations.readonly` | Confirm Location ID |
| `associations.readonly` / `associations.write` + relation write | Contact ↔ TradingAccount |
| `workflows.readonly` | Verify fields appear (no automation enable) |

**Note:** Creating object *schemas* via API often requires Agency-level token (`objects/schema.write`). Prefer **UI for schema** at T0; Private Integration for record CRUD + later gateway.

Token storage: **secure note only** — never git, never Hermes memory, never Contact fields. Path template: `~/.hermes/secrets/ghl_pilot_t0.env` (mode 600) or password manager.

---

## 7. Sample data contract (2 contacts + 2 TradingAccount rows)

See CSV files in this folder:

- `sample_contacts.csv`
- `sample_trading_accounts.csv`

| Contact | Email (test) | Tier | Tags | TradingAccount |
|---------|--------------|------|------|----------------|
| Pilot Alpha | pilot.alpha+arch@example.com | starter | pilot, paid | disconnected, unknown health |
| Pilot Beta | pilot.beta+arch@example.com | starter | pilot, paid, coinbase_connected, runner_healthy | connected, green |

Use `@example.com` so no real messages send until domains/SMTP configured. Associate each TradingAccount record to its Contact after import.

---

## 8. Platform ↔ GHL property map (for Eng T0-01 / GHL-04)

| Platform (registry) | GHL TradingAccount property | Notes |
|---------------------|----------------------------|-------|
| `traders.id` / `account_id` | `account_id` | UUID string |
| `oauth.coinbase_status` | `coinbase_status` | enum |
| `oauth.portfolio_uuid` | `portfolio_uuid` | internal |
| `job_runs.last_cycle_at` | `last_cycle_at` | |
| `rebalances.last_at` | `last_rebalance_at` | |
| `health.level` | `runner_health` | green/yellow/red |
| `telemetry.deployed_pct` | `deployed_pct` | round to 1 decimal |
| `errors.last_summary` | `last_error_summary` | sanitize |
| `config.tier` | `subscription_tier` | |
| `billing.status` | `billing_status` | from GHL webhooks later |

---

## 9. Acceptance checklist (this dictionary)

- [x] Contact fields + tags defined
- [x] TradingAccount schemaKey + fields + sync directions
- [x] SaaS products + pilot prices + platform caps notes
- [x] Pipelines/stages
- [x] Forbidden data list
- [x] Sample CSV contract
- [ ] Live GHL schema created (human)
- [ ] Live product IDs filled (human)
- [ ] Live Location ID + Private token in secure note (human)

---

## 10. Doc control

| Doc | Role |
|-----|------|
| This file | Field dict + product draft (Mkt R) |
| `GHL_T0_MANUAL_SETUP_RUNBOOK.md` | Step-by-step UI |
| `GHL_API_V2_SURFACE_MAP.md` | API surfaces |
| `GHL_INTEGRATION.md` | Prereqs status |
| `GHL_CONTRACT.md` | T1 formal payloads (not yet) |
