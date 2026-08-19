# Handoff: DOC-BOUNDARY-01 — Scrub Online Marketing SEO/SEM/Ads from crypto-trading-bot docs

**ID:** DOC-BOUNDARY-01-20260717  
**Date:** 2026-07-17  
**Board:** `crypto-bot-project`  
**Assignee (implement):** `crypto-engineer`  
**Reviewer:** `crypto-orchestrator` / Scotty  
**Priority:** High (doc integrity / project boundary)

---

## Objective

**Crypto Trading Platform** and **Online Marketing SEO/SEM/Ads** are **two completely separate projects with no current relationship.**

Review **all documentation under** `/home/brad/projects/crypto-trading-bot` and **remove (or relocate out of this repo)** every reference that imports or intertwines the online marketing SEO/SEM/Ads consultancy stream into crypto-trading docs.

---

## Project boundary (non-negotiable)

| In scope for **crypto-trading-bot** docs | **Out of scope** — belongs to marketing consultancy / separate project |
|------------------------------------------|------------------------------------------------------------------------|
| Phase 6 runner, ledger, dashboard, capital, REGIME-CASH, Coinbase | Client SEO / SEM / Google Ads delivery |
| Trading platform product engineering | `client-local-seo-audit`, Side-Hustle audit model |
| Optional: **product** multi-tenant / GHL **as CRM for the trading product** only if purely product ops (see below) | Adspirer as **client** research tool; Forever Roofing; Uncorked Canvas; marketing-consultancy reports |
| | Cross-links to `/home/brad/projects/marketing-consultancy` or `/home/brad/reports` Side_Hustle packs as if they were crypto project assets |

**Rule of thumb:** If a sentence would not make sense to a pure trading-bot engineer, it should not live in this repo’s docs.

### SCALING-1000 / GHL nuance

- **Remove** from crypto docs: Adspirer, research-only SEM, SEO clusters, local SEO audits, Forever Roofing / client Google account hygiene, marketing-consultancy mirror paths, `seo-agent` / `client-local-seo-audit` skill callouts.
- **Decide explicitly in the audit table (do not silently delete product architecture):**
  - GHL as **multi-tenant CRM/ops for the trading SaaS product** may stay in `docs/integrations/*` **only** if rewritten free of SEO/SEM/Ads consultancy language.
  - If GHL + “marketing plan” packs are actually GTM for a separate commercial stream, **move** those files under marketing-consultancy (or archive under `docs/archive/cross_project_removed/`) and leave a one-line pointer **or** delete with MASTER note — **prefer relocate over destroy** when content is still useful elsewhere.

---

## Must Do

1. **Inventory** (write `docs/DOC_BOUNDARY_AUDIT_20260717.md`):
   - File path
   - Snippet / theme (SEO, SEM, Adspirer, client audit, marketing-consultancy, Forever Roofing, Side Hustle, Google Ads client ops)
   - Action: **scrub in place** | **relocate to marketing-consultancy** | **archive** | **keep (justify)**
2. **Apply** actions across:
   - `docs/**` (including `docs/marketing/**`, `docs/epics/**`, `docs/integrations/**`)
   - `handoffs/**` that encode the crossover as current truth (not historical incident notes buried in archive — still strip if they instruct workers to mix projects)
   - Do **not** rewrite git history; do **not** mass-edit `logs/` or large binary assets
3. **MASTER_TASK_TRACKING.md**: add completion note; if SCALING pack is relocated, mark doc paths updated
4. **Isolation / verification:**
   ```bash
   cd /home/brad/projects/crypto-trading-bot
   rg -ni 'Adspirer|client-local-seo|Side.?Hustle|Forever.?Roof|marketing-consultancy|Google Ads|SEM research|SEO audit' docs/ handoffs/ --glob '*.md'
   ```
   Expected: **zero hits** outside `docs/archive/` (if any residual historical archive is explicitly labeled “historical cross-project — not active”) **or** zero hits entirely if archive also scrubbed.
5. Leave a short **`docs/PROJECT_BOUNDARY.md`** (half page): crypto-trading-bot vs marketing SEO/SEM/Ads — no shared deliverables.

## Must Not Do

- Do not change trading runtime code, configs, or Phase 6 behavior for this task
- Do not delete marketing-consultancy files outside this repo without placing relocated content there first
- Do not merge the two projects “for convenience”
- Do not invent new GTM strategy; only boundary cleanup

## Expected deliverables

1. `docs/DOC_BOUNDARY_AUDIT_20260717.md` — full inventory + actions taken  
2. Cleaned / relocated docs under crypto-trading-bot  
3. `docs/PROJECT_BOUNDARY.md`  
4. MASTER entry DONE with verification command output  
5. Kanban implement + review complete  

## Success criteria

- [ ] No active crypto docs instruct workers to use Adspirer / client SEO audits / Forever Roofing / Side-Hustle model for this repo  
- [ ] SCALING / GHL docs either pure product ops **or** moved out with clear MASTER note  
- [ ] `rg` verification clean (per policy above)  
- [ ] Reviewer sign-off on Kanban  

## Seed inventory (non-exhaustive — expand)

High-signal paths already matching SEO/SEM/Ads/GHL-marketing crossover:

- `docs/marketing/SCALING_1000_MARKETING_PLAN.md` (heavy SEM/SEO/Adspirer)
- `docs/epics/SCALING_1000_UNIFIED_ROADMAP.md`, `SCALING_1000_REV01_SIGNOFF.md`, `SCALING-1000_EPIC.md`
- `docs/integrations/SCALING_1000_IMPLEMENTATION_PLAN.md`, `GHL_*`
- `docs/marketing/**` brand/GHL packs that cite SEO/Adspirer
- `handoffs/scaling/*`, `handoffs/ideas/Marketing_Business_Development_Ideas.md`
- Scattered: `docs/MASTER_TASK_TRACKING.md` (edit narrative only where it asserts active crossover as current coupling)

---

## Validation method

1. Audit table complete  
2. Edits applied  
3. `rg` verification  
4. Reviewer reads PROJECT_BOUNDARY + sample of scrubbed SCALING files  
