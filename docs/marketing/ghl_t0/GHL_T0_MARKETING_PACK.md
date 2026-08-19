# GHL-T0 Marketing Pack (summary)

**Date:** 2026-07-17  
**Kanban:** t_136c2da8 PHASE-A-03  
**Status:** Spec + samples + runbook delivered; live GHL admin UI pending (no credentials on agent host)

## Delivered (repo)

| Artifact | Path |
|----------|------|
| Field dictionary | `docs/integrations/ghl_t0/GHL_T0_FIELD_DICT.md` |
| Manual runbook | `docs/integrations/ghl_t0/GHL_T0_MANUAL_SETUP_RUNBOOK.md` |
| Sample contacts CSV | `docs/integrations/ghl_t0/sample_contacts.csv` |
| Sample TradingAccount CSV | `docs/integrations/ghl_t0/sample_trading_accounts.csv` |
| Secrets template | `docs/integrations/ghl_t0/ghl_pilot_t0.env.TEMPLATE` |

## Pilot SaaS SKUs (draft)

| SKU | Price/mo | Caps (platform) |
|-----|----------|-----------------|
| ARCH Starter `arch_starter_mo` | $39 | 6 pairs; deploy class ~$1k–$3k TBD |
| ARCH Pro `arch_pro_mo` | $99 draft | 11 pairs; dual windows |
| ARCH Elite `arch_elite_mo` | $249 draft | custom + priority_support |

## Tags (minimum)

`paid`, `coinbase_connected`, `runner_healthy`, `needs_attention`, `trader_tier_*`, `pilot`, `priority_support`

## schemaKey

`custom_objects.tradingaccount`

## Human remaining

1. Execute runbook in GHL UI  
2. Store Location ID + Private Integration token in `~/.hermes/secrets/ghl_pilot_t0.env` (chmod 600)  
3. Drop evidence screenshots under `docs/integrations/ghl_t0/evidence/` (optional)  
4. Mark PHASE-A-03 complete on MASTER  

## Out of scope

Webhooks, W1–W7 automation, prod runner, OAuth Marketplace App.
