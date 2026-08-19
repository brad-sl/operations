# GoHighLevel (GHL) integration — ramp-up & agent setup

**Status:** GHL-T0 **spec pack complete** (2026-07-17); live Location / Private Integration / sample records **pending human admin UI**  
**Epic:** `docs/epics/SCALING-1000_EPIC.md`  
**Kickoff:** `handoffs/scaling/Handoff_SCALING-1000_EPIC_Kickoff.md`  
**Field dict + runbook:** `docs/integrations/ghl_t0/`

---

## Prerequisites (before GHL front-end / integration dev)

Complete these **before** starting multi-module GHL + platform integration work (workflows, webhooks, connect UX, sync worker):

| # | Prerequisite | Notes | Status |
|---|----------------|-------|--------|
| 1 | **GHL sub-account / Location setup** | Pilot Location, Private Integration credentials, `TradingAccount` custom object (`SCALING-1000-GHL-T0`). | **Spec ready** — field dict, runbook, sample CSVs in `docs/integrations/ghl_t0/`. Live UI setup requires Brad/Ops admin (no token on agent hosts). Token → `~/.hermes/secrets/ghl_pilot_t0.env` only. |
| 2 | **Trading bot on dedicated host** | Phase 6 runner + integration gateway **not** on Brad’s local HP machine — stable webhook URL, uptime, secrets, fleet path to T1+. | Open (PHASE-A-02) |
| 3 | **Hermes delegation model (see below)** | Apply when ramp-up is done and GHL implementation waves begin — not required during manual GHL admin setup. | Config note only |

Until 1–2 are done, limit work to epic T0 schema/OAuth spikes and **manual** GHL configuration; do not treat local-only runner as the webhook target for production workflows.

### GHL-T0 package (PHASE-A-03)

| Artifact | Path |
|----------|------|
| Field dictionary (Contact + TradingAccount + SaaS + tags + pipelines) | `docs/integrations/ghl_t0/GHL_T0_FIELD_DICT.md` |
| Manual UI runbook | `docs/integrations/ghl_t0/GHL_T0_MANUAL_SETUP_RUNBOOK.md` |
| Sample contacts / TradingAccount CSVs | `docs/integrations/ghl_t0/sample_*.csv` |
| Secrets template (empty) | `docs/integrations/ghl_t0/ghl_pilot_t0.env.TEMPLATE` |
| Mkt pack summary | `docs/marketing/ghl_t0/GHL_T0_MARKETING_PACK.md` |

**schemaKey:** `custom_objects.tradingaccount`  
**Pilot products:** ARCH Starter $39 / Pro $99 draft / Elite $249 draft (Brad A before public checkout)  
**Do not:** enable webhooks/automation or bind prod runner yet. T0 shadow only.

---

## Hermes agent configuration (when implementation starts)

GHL integration is multi-module (GHL API, workflows, platform registry, OAuth connect, status sync). Use a **Composer primary + delegated implementer** pattern:

**When kicking off GHL implementation waves**, set in `~/.hermes/config.yaml`:

```yaml
delegation:
  provider: xai-oauth
  model: grok-4.5
```

- **Primary session** (`model.default: grok-composer-2.5-fast`): handoffs, scope, MASTER updates, ops triage.
- **`delegate_task` children** inherit `delegation.*` → heavier integration slices (gateway routes, sync worker, front-end modules).
- **Deploy / capital-risk gate:** unchanged — `code-reviewer` profile + `scripts/hermes/run_analyst_deploy_evaluator.sh` (do **not** point global `delegation.model` at the reviewer).

**Context compression** (long GHL sessions): `auxiliary.compression` should use `xai-oauth` + `grok-4.5` (configured 2026-07-08; replaces dead `openrouter/owl-alpha`).

**Policy:** Delegate slices with formal Handoff Documents (`agent-delegation` skill); keep trivial checks on the primary model.

---

## Related docs (later)

| Doc | When |
|-----|------|
| `GHL_CONTRACT.md` | T1 — webhook payloads, field mapping, idempotency |
| `docs/integrations/COINBASE_OAUTH.md` | T0-03 |
| `docs/DATA_FLOW_AND_LOCATIONS.md` | After first DB migration |
| `docs/integrations/GHL_API_V2_SURFACE_MAP.md` | API surface reference |

---

## MASTER

Tracked under **SCALING-1000** / PHASE-A-03 in `docs/MASTER_TASK_TRACKING.md`.
