# GHL-T0 Manual Setup Runbook

**Task:** `t_136c2da8` SCALING-1000-PHASE-A-03  
**Phase:** A / GHL-T0 — **manual only**  
**Do not:** enable production webhooks, point runner at this Location, or store tokens in git.  
**Companion:** `GHL_T0_FIELD_DICT.md` (fields, products, tags)

---

## Outcome

When this runbook is finished you will have:

1. Pilot Location ID  
2. Private Integration token (secure note)  
3. SaaS products: Starter (+ draft Pro/Elite)  
4. Custom object `custom_objects.tradingaccount` with fields  
5. Tags + optional onboarding pipeline  
6. 2 test contacts + 2 TradingAccount records (viewable/editable in UI)  
7. Screenshot or export for audit  

---

## Pre-flight

- [ ] GHL agency or sub-account admin access (Brad / Ops)  
- [ ] Brand placeholder OK for Location name (`ARCH Automation — Pilot`) or temporary name  
- [ ] Read field dict end-to-end  
- [ ] Password manager or path ready: `~/.hermes/secrets/ghl_pilot_t0.env` (chmod 600)  
- [ ] Confirm Custom Objects available (all plans: up to 10 objects / Location as of Oct 2025 GHL release)

---

## Step 1 — Create / configure Location (sandbox first)

1. Agency → **Sub-Accounts** → **Create Sub-Account** (or use existing pilot sandbox).  
2. Name: `ARCH Automation — Pilot`  
3. Timezone: `America/Los_Angeles`  
4. Currency: USD  
5. Complete business profile with placeholder support email if required (real support@ after brand lock).  
6. Copy **Location ID** from Settings → Business Profile / Company (or URL / API).  

**Secure note (do not commit):**

```bash
# ~/.hermes/secrets/ghl_pilot_t0.env
GHL_LOCATION_ID=
GHL_LOCATION_NAME="ARCH Automation — Pilot"
GHL_ENV=pilot_sandbox
# paste Location ID after create; never commit this file
```

---

## Step 2 — Private Integration token

1. Inside the pilot Location: **Settings → Integrations → Private Integrations**  
2. **Create** → Name: `arch-platform-t0-shadow`  
3. Description: `T0 shadow read/write for contacts + TradingAccount records. No prod webhooks.`  
4. Enable scopes from field dict §6 (contacts, objects record, products readonly, associations, locations.readonly, workflows.readonly).  
5. **Do not** configure live webhook endpoint to the trading host yet (T1 / GHL-01).  
6. Generate token → copy once → paste into secure note:

```bash
GHL_PRIVATE_INTEGRATION_TOKEN=
GHL_PI_NAME=arch-platform-t0-shadow
GHL_PI_CREATED=
# paste token once after generate; never commit this file
```

7. `chmod 600 ~/.hermes/secrets/ghl_pilot_t0.env`  
8. Optional smoke test (from a machine that has the secret file; never log full token):

```bash
set -a; source ~/.hermes/secrets/ghl_pilot_t0.env; set +a
curl -sS -o /tmp/ghl_loc.json -w "%{http_code}" \
  -H "Authorization: Bearer ${GHL_PRIVATE_INTEGRATION_TOKEN}" \
  -H "Version: 2021-07-28" \
  "https://services.leadconnectorhq.com/locations/${GHL_LOCATION_ID}"
# Expect 200. Inspect /tmp/ghl_loc.json without committing it.
```

---

## Step 3 — Tags

**Settings → Tags** (or Contacts → Tags) — create:

- `paid`  
- `coinbase_connected`  
- `runner_healthy`  
- `needs_attention`  
- `trader_tier_starter`  
- `trader_tier_pro`  
- `trader_tier_elite`  
- `priority_support`  
- `pilot`  

---

## Step 4 — Contact custom fields

**Settings → Custom Fields → Contact** — create:

| Label | Type | Options |
|-------|------|---------|
| Trader Tier | Dropdown | starter, pro, elite |
| Subscription Status | Dropdown | active, past_due, canceled, trialing, none |
| Platform Account ID | Text | — |
| Pilot Cohort | Text | — |

---

## Step 5 — SaaS products

**Payments / SaaS / Products** (exact menu depends on GHL version):

1. Create product **ARCH Starter**  
   - Recurring monthly **$39**  
   - SKU note: `arch_starter_mo`  
   - Description from field dict §4 (compliance-safe)  
2. Create **ARCH Pro** — monthly **$99** draft — `arch_pro_mo` (can leave unlisted)  
3. Create **ARCH Elite** — monthly **$249** draft — `arch_elite_mo`  
4. Record product IDs / price IDs into secure note:

```bash
GHL_PRODUCT_STARTER_ID=
GHL_PRICE_STARTER_ID=
GHL_PRODUCT_PRO_ID=
GHL_PRICE_PRO_ID=
GHL_PRODUCT_ELITE_ID=
GHL_PRICE_ELITE_ID=
```

5. Do **not** open public checkout until legal + T1 gates.

---

## Step 6 — Custom Object: TradingAccount

1. **Settings → Custom Objects → Create** (or Objects builder).  
2. Singular: `Trading Account` / Plural: `Trading Accounts`  
3. Key: `tradingaccount` → confirm schemaKey becomes `custom_objects.tradingaccount`  
4. Primary display: **Account ID** (text)  
5. Add fields exactly as field dict §3.2 (dropdowns for enums).  
6. Create **Association**: Contact ↔ Trading Account (label e.g. `has_trading_account` / `owned_by`).  
7. Confirm records list view shows Account ID + Coinbase Status + Runner Health columns.

**Schema creation tip:** UI is preferred. API `POST /objects/` for schema often requires **Agency** token + `objects/schema.write`.

---

## Step 7 — Pipeline (optional but recommended)

**Opportunities → Pipelines → Create** `Trader Onboarding`:

1. Invite / Waitlist  
2. Paid — Awaiting Connect  
3. Connecting  
4. Live — Healthy  
5. Needs Attention  
6. Paused / Billing  
7. Offboarded  

---

## Step 8 — Sample data (2 contacts + 2 records)

### 8.1 Contacts

Import or create manually using `sample_contacts.csv`:

| firstName | lastName | email | tags | trader_tier | subscription_status | platform_account_id | pilot_cohort |
|-----------|----------|-------|------|-------------|---------------------|---------------------|--------------|
| Pilot | Alpha | pilot.alpha+arch@example.com | pilot,paid,trader_tier_starter | starter | active | 11111111-1111-4111-8111-111111111111 | closed-2026q3 |
| Pilot | Beta | pilot.beta+arch@example.com | pilot,paid,trader_tier_starter,coinbase_connected,runner_healthy | starter | active | 22222222-2222-4222-8222-222222222222 | closed-2026q3 |

### 8.2 TradingAccount records

Create two records (UI) using `sample_trading_accounts.csv`, then associate:

**Alpha (not connected yet):**

- account_id: `11111111-1111-4111-8111-111111111111`  
- display_name: `Pilot Alpha — Starter`  
- coinbase_status: `disconnected`  
- runner_health: `unknown`  
- subscription_tier: `starter`  
- billing_status: `active`  
- deployed_pct: `0`  
- pair_count_cap: `6`  
- max_deploy_usd: `3000` (placeholder)  
- last_error_summary: _(empty)_  

**Beta (shadow healthy):**

- account_id: `22222222-2222-4222-8222-222222222222`  
- display_name: `Pilot Beta — Starter`  
- coinbase_status: `connected`  
- portfolio_uuid: `portfolio-shadow-beta-not-real`  
- runner_health: `green`  
- subscription_tier: `starter`  
- billing_status: `active`  
- deployed_pct: `42.5`  
- last_cycle_at / last_rebalance_at / last_sync_at: now (UTC)  
- pair_count_cap: `6`  
- max_deploy_usd: `3000`  

### 8.3 Manual verification

- [ ] Open each TradingAccount in GHL UI; edit `runner_health` Alpha → `yellow` → save → re-open confirms  
- [ ] Association visible on Contact record  
- [ ] Tags visible on contacts  
- [ ] (Future) Fields selectable in Workflow builder — do not activate workflows yet  

---

## Step 9 — Evidence pack

Capture:

1. Screenshot: Custom Object field list  
2. Screenshot: Products list (Starter highlighted)  
3. Screenshot: Contact Beta with tags + associated TradingAccount  
4. Optional: CSV export of Trading Accounts  

Store screenshots under:

`docs/integrations/ghl_t0/evidence/`  
(or Ops private folder if screenshots show Location IDs you prefer not to commit — then link path in MASTER only)

Update appendix in field dict with product IDs (not tokens).

---

## Step 10 — Doc updates after live setup

- [ ] `GHL_INTEGRATION.md` — mark prereq #1 complete; note Location name only  
- [ ] `MASTER_TASK_TRACKING.md` — PHASE-A-03 → DONE  
- [ ] Unblock kanban `t_136c2da8` with comment: “UI complete; token in secrets file”  
- [ ] Notify Eng (T0-05 isolation + GHL-T0 verification, GHL-01 later)

---

## Out of scope (explicit)

| Item | When |
|------|------|
| Webhooks to platform | GHL-01 / dedicated host |
| W1–W7 live workflows | GHL-02 + copy pack |
| OAuth Marketplace App | T1+ |
| Prod runner binding | After T0 exit + isolation |
| Public paid acquisition / checkout | After T1 gates + legal |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| No Custom Objects menu | Confirm plan/location feature; GHL all plans have CO since Oct 2025 — check admin role |
| schema API 401/403 | Use UI; or Agency token with `objects/schema.write` |
| Token works for contacts but not objects | Add `objects/record.*` scopes; recreate token if scopes immutable |
| Import drops custom fields | Create fields before import; map columns carefully |
| Accidental real email send | Use `+arch@example.com` only until domains ready |

---

## RACI (from unified roadmap)

| Role | This runbook |
|------|----------------|
| Mkt | Field dict, product copy, CSV, this checklist (done in agent pack) |
| Ops / Brad | Execute UI steps, secure token |
| Eng | Schema align consult; later sync worker uses schemaKey |
| Brad A | Pricing final, Location go-ahead |
