# Handoff: SCALING-1000 Epic Kickoff

**Date:** 2026-07-06  
**Epic doc:** `docs/epics/SCALING-1000_EPIC.md`  
**Status:** Planned — execution not started

## User directive

- Scale toward **1,000 trading accounts**
- **GoHighLevel** = front end, onboarding, comms, subscriptions
- **Coinbase OAuth** = per-trader auth (not API keys in CRM)

## Constraints

- Do **not** break Brad’s single-account Phase 6 runner during T0
- GHL is system of record for **commercial** relationship; Postgres is system of record for **trading + tokens**
- Reuse Phase 6 ports (`TradingClient`, coordinator, SL stack) via `AccountContext`

## First sprint (T0) — suggested order

1. `SCALING-1000-T0-01` — ERD + migrations (`traders`, `oauth_tokens`, `trader_configs`)
2. `SCALING-1000-T0-03` — OAuth adapter spike (sandbox)
3. `SCALING-1000-GHL-T0` — GHL Location: `TradingAccount` custom object + 2 test contacts (manual)
4. `SCALING-1000-T0-02` — Wire `AccountContext` in runner behind feature flag `MULTI_TENANT_ENABLED=false`

## Verification gates

- T0: two accounts, isolation test pass, OAuth sandbox order round-trip
- T1: GHL paid webhook creates registry row; W3 fires after OAuth callback

## Delegation note

Implementation waves should use `agentic-architecture` + `code-isolation-testing`; GHL workflow work can be parallelized with integration gateway once webhook URL is stable.

**Ramp-up (not started):** GHL sub-account/Location setup + deploy trading bot to a **dedicated host** (not local HP). See `docs/integrations/GHL_INTEGRATION.md`.

**When GHL implementation waves begin:** set Hermes `delegation.provider: xai-oauth` and `delegation.model: grok-4.5` per that doc (primary stays `grok-composer-2.5-fast`).