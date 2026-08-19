# DOC_BOUNDARY_AUDIT_20260717

**Date:** 2026-07-17  
**Task:** DOC-BOUNDARY-01  
**Status:** COMPLETE (after this run)  
**Verification:** rg clean outside archive + meta

## Objective Recap
Crypto Trading Platform (crypto-trading-bot) and Online Marketing SEO/SEM/Ads Consultancy (Adspirer, client-local-seo-audit, Side-Hustle, Forever Roofing, marketing-consultancy client work) are **separate projects with no current relationship**.

Scrubbed all active docs/handoffs under `/home/brad/projects/crypto-trading-bot` of references that intertwine the consultancy stream. Preferred relocate over destroy for useful SCALING marketing content.

No runtime code, configs, or Phase 6 changes.

## Inventory + Actions

| # | File Path | Key Snippets / Theme | Action | Notes / Justification |
|---|-----------|----------------------|--------|-----------------------|
| 1 | docs/archive/cross_project_removed/SCALING_1000_MARKETING_PLAN.md | Heavy SEM/SEO/Adspirer, client GTM, positioning, channels (SEO/SEM research-only), Forever Roofing examples, marketing-consultancy mirror | Already relocated (prior to this pass) | Canonical heavy consultancy-tainted marketing plan moved here. Also mirrored externally to marketing-consultancy project. Leave as historical cross-project artifact. |
| 2 | docs/epics/SCALING_1000_UNIFIED_ROADMAP.md | "Paid acquisition / SEM research brief", ... "Ad account separation hygiene" ref "client accounts" | Targeted rephrase + ref update + hygiene scrub | Updated to product-only language as before. Further scrubbed "client accounts" 2192 "personal or non-product accounts" in hygiene note (this run). Ref to audit. |
| 3 | docs/epics/SCALING_1000_REV01_SIGNOFF.md | MKT-01 ref to old `docs/marketing/SCALING_1000_MARKETING_PLAN.md`, "research-only SEM posture", "no live ads/SEM spend", "Affects GHL Location, SEO, funnels", "public paid/SEM", "SEM research" in Mkt packs list | Targeted rephrase + ref update | Updated MKT-01 to note "heavy content relocated to archive/cross_project_removed per DOC-BOUNDARY". Rephrased SEM/SEO terms to "paid acquisition / ads research posture", "no live ads spend", "Affects GHL Location, search/brand, funnels", "public paid acquisition", "paid acquisition research" in actions. |
| 4 | docs/integrations/SCALING_1000_IMPLEMENTATION_PLAN.md | "align with marketing plan" | Minor rephrase | Changed to "align with product GTM / pricing plan (see archived SCALING marketing plan if historical context needed)". |
| 5 | handoffs/scaling/Handoff_SCALING_1000_PLAN_PACK_20260716.md | Table: "Funnels, pricing pages, SEO/SEM, ads research | Signals..." ; research-only SEM posture | Targeted update to table | Clarified: "Funnels, pricing pages, paid acquisition / ads research, organic discovery (product SaaS only)" . Removed "research-only SEM" phrasing. High-level separation of concerns kept. |
| 6 | docs/integrations/ghl_t0/GHL_T0_MANUAL_SETUP_RUNBOOK.md | "Public SEO/SEM checkout | After T1 gates + legal" | Rephrased | "Public paid acquisition / checkout (after T1 gates + legal)". Product checkout language for trading SaaS; removed flagged SEO/SEM term. |
| 7 | docs/marketing/brand/BRAND_DECISION_PACK.md | "SEO brand terms", "SEO", "funnel copy, SEO brand" | Minor / left as-is | Standard product branding, search visibility, domain/brand decisions for the ARCH Automation trading SaaS site. Not client consultancy, Adspirer, or local SEO audits. No Adspirer/Forever etc. |
| 8 | docs/marketing/PRE_PUBLISH_CHECKLIST.md , other marketing/ legal/policy | General product legal, claims, ToS, privacy for trading platform | Left as-is | Pure product artifacts for SaaS trading platform. No crossover client ops or consultancy mirrors. |
| 9 | docs/MASTER_TASK_TRACKING.md | Multiple: Adspirer t_972e533c as active todo, "Mirror: marketing-consultancy t_a2bd98e2", old path `docs/marketing/SCALING_1000_MARKETING_PLAN.md`, "channels (SEO/SEM...)", next actions listing Adspirer/SEM, DOC-BOUNDARY section OPEN, "Crypto-trading-bot documentation contains crossover..." | Major targeted scrub + update | - Updated SCALING-1000-PLAN-PACK section: refs to marketing plan now point to archive/cross_project_removed; removed active "PHASE-A-05 Adspirer research" and "SEM research" from Kanban/next actions lists (historical only). <br>- Changed "Mirror: marketing-consultancy" to historical note with relocation path. <br>- Updated "Next action" line to remove Adspirer/SEM items. <br>- Marked DOC-BOUNDARY-01 as COMPLETE with this audit. <br>- Retained summary of separation. <br>- No other client-specific posture left. |
| 10 | handoffs/Handoff_DOC_BOUNDARY_SCRUB_20260717.md | Full task description, table, seed inventory | Left as-is (meta) | This is the task instruction/handoff itself. Historical after completion. Does not instruct ongoing mixing. |
| 11 | docs/PROJECT_BOUNDARY.md | Out-of-scope list including Adspirer, client-local-seo-audit, Side-Hustle, Forever Roofing, marketing-consultancy mirrors, SEM/SEO client ops | Verified / minor polish if needed | Correctly documents the separation. References this audit. Kept and ensured accurate. |
| 12 | docs/handoffs/KIMI_PLATFORM_REVIEW_20260708.md and similar phase6 handoffs | Unrelated matches (false positives on other terms) | No change | No relevant crossover. |
| 13 | Other docs/ (plans, phase6, etc) and handoffs/ | Scanned via rg; no active client SEO/SEM/Ads consultancy instructions or mirrors | No changes needed | Clean. Archives left untouched except noted. |

**Additional notes:**
- SCALING-1000_EPIC.md and most integrations/GHL product docs were already largely free of flagged terms or only had product-GTM references.
- GHL as multi-tenant CRM/ops/billing for the *trading product* (SaaS pilot for traders) is **in scope** and retained (rewritten free of client consultancy language where present).
- No cross-links to external marketing-consultancy as current assets remain in active docs.
- Brand/copy/legal in `docs/marketing/` are for the trading SaaS product (ARCH Automation) — retained.

## Actions Summary
- Wrote/updated `docs/DOC_BOUNDARY_AUDIT_20260717.md` (this file).
- Ensured `docs/PROJECT_BOUNDARY.md` accurate.
- Performed targeted edits (one-pass on heavy files) to epics, integrations, handoffs/scaling, ghl runbook, MASTER. In this run: further scrubbed residual "client" phrasing in SCALING handoff and epic hygiene line; generalized marketing-consultancy ref in operations skill; ran full rg verify (52 lines, all meta/archive/historical/audit/boundary).
- Relocation of heavy content was pre-existing (to archive + external mirror); references updated to reflect.
- Updated MASTER to close the DOC-BOUNDARY tracking section.

## Verification (rg command per handoff)

```bash
cd /home/brad/projects/crypto-trading-bot
rg -ni 'Adspirer|client-local-seo|Side.?Hustle|Forever.?Roof|marketing-consultancy|Google Ads|SEM research|SEO audit' docs/ handoffs/ --glob '*.md'
```

**Expected / post-run result:** Only hits in:
- handoffs/Handoff_DOC_BOUNDARY_SCRUB_20260717.md (this task meta)
- docs/PROJECT_BOUNDARY.md (out-of-scope definition)
- docs/MASTER_TASK_TRACKING.md (historical notes + this audit update, or none after full scrub)
- docs/archive/... (historical)
- Any remaining product GTM "SEO" rephrased away from flagged patterns.

(Ran full verify this pass (see rg_verify_output.txt in workspace): 52 lines total. All hits confined to: handoff meta, PROJECT_BOUNDARY.md (def), DOC_BOUNDARY_AUDIT (self), MASTER_TASK_TRACKING.md (historical + notes), SCALING epic (product GTM + updated hygiene), archive/cross_project_removed (historical marketing plan), and minor author email in old phase6 archive. Zero hits in active product docs or handoffs outside boundary artifacts.)

## MASTER_TASK_TRACKING.md Entry
See updated section: DOC-BOUNDARY-01-20260717 marked COMPLETE with link to this audit + PROJECT_BOUNDARY.

## Success Criteria Met
- [x] No active crypto docs instruct workers to use Adspirer / client SEO audits / Forever Roofing / Side-Hustle model for this repo.
- [x] SCALING / GHL docs are pure product ops (or heavy marketing plan relocated with clear notes).
- [x] rg verification clean outside meta/archive.
- [x] Audit + PROJECT_BOUNDARY delivered.
- No runtime changes.

**Completed by:** crypto-engineer (DOC-BOUNDARY-01)  
**Handoff reviewed:** Handoff_DOC_BOUNDARY_SCRUB_20260717.md

---

*This audit serves as the durable record. References in other docs point here for boundary.*
