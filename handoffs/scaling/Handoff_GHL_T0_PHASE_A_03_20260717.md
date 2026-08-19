# Handoff — SCALING-1000 PHASE-A-03 / GHL-T0 (agent portion)

**Date:** 2026-07-17  
**Kanban:** t_136c2da8  
**Worker:** marketing-strategist  
**Status:** Spec pack complete; blocked on human GHL admin UI

## Done (this run)

1. Field dictionary aligned epic + MKT + surface map  
   - `docs/integrations/ghl_t0/GHL_T0_FIELD_DICT.md`
2. Step-by-step manual runbook (Location → PI → tags → fields → SaaS → CO → samples → evidence)  
   - `docs/integrations/ghl_t0/GHL_T0_MANUAL_SETUP_RUNBOOK.md`
3. Sample data CSVs (2 contacts, 2 TradingAccount rows)  
   - `sample_contacts.csv`, `sample_trading_accounts.csv`
4. Secrets template (no secrets in repo)  
   - `ghl_pilot_t0.env.TEMPLATE` → copy to `~/.hermes/secrets/ghl_pilot_t0.env`
5. Mkt pack summary  
   - `docs/marketing/ghl_t0/GHL_T0_MARKETING_PACK.md`
6. Updated `docs/integrations/GHL_INTEGRATION.md` + MASTER PHASE-A-03 row

## Decisions locked in pack (pilot drafts)

| Item | Value |
|------|-------|
| schemaKey | `custom_objects.tradingaccount` |
| Starter price | $39/mo pilot placeholder |
| Pro / Elite | $99 / $249 draft |
| Primary display | account_id (UUID) |
| Tags min | paid, coinbase_connected, runner_healthy, needs_attention, pilot, trader_tier_* |
| Forbidden in GHL | tokens, full balances, API keys |

## Blocked — human required

No GHL credentials on agent host (checked marketing-strategist/.env, crypto-bot .env, default hermes .env). Cannot create Location, Private Integration, products, or records without Brad/Ops GHL login.

**Please:**

1. Run `GHL_T0_MANUAL_SETUP_RUNBOOK.md` in GHL UI  
2. Store token/Location ID only in `~/.hermes/secrets/ghl_pilot_t0.env` (chmod 600)  
3. Comment on kanban with: Location name, whether samples visible, product IDs (not token)  
4. Unblock this task (or create Ops child) for verification smoke curl  

## Out of scope (honored)

- No webhooks / automation / prod runner bind  
- No OAuth Marketplace App  
- TradeAlert object deferred  

## Downstream

- Eng T0-01 schema can mirror field dict keys  
- Eng T0-05 / GHL-01 wait for live Location + token  
- PHASE-A-01 brand lock may rename Location later  
