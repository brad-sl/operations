# Handoff — SCALING-1000-PHASE-A-06 Copy Pack

**Date:** 2026-07-30  
**Kanban:** t_5e21287a  
**Owner (agent):** marketing-strategist  
**Status:** Agent deliverables complete — Brad/Mkt approval + live GHL paste remaining

---

## 1. Objective

Produce final compliant copy strings for GHL workflows W1–W3/W5 (plus full W4/W6/W7), unlisted funnel skeleton, pricing, risk/legal page shells, UTM/KPI template — aligned to brand + legal. No live publish / no ads.

---

## 2. Current state

- Brand recommendation: **ARCH Automation** / arch-automation.com / support@arch-automation.com (Brad formal domain purchase still out-of-band).
- Legal draft pack exists (ToS, Privacy, Risk, Claims policy) — counsel engagement still required before public paid.
- GHL live Location/UI requires Brad admin (PHASE-A-03).
- Prior ad-copywriter attempts on this card failed protocol; rebuilt as full pack under `docs/marketing/copy/`.

---

## 3. Success criteria vs delivery

| Criterion | Status |
|-----------|--------|
| Copy under docs/marketing/copy/ | **Done** |
| W1–W3/W5 (+ W4/W6/W7) strings | **Done** |
| Unlisted funnel skeleton MD + workflow JSON | **Done** (not live GHL UI) |
| Pricing page copy with placeholders | **Done** ($39/$99/$249) |
| Risk/ToS/Privacy page shells | **Done** (full legal remains canonical docs) |
| UTM/KPI template incl. pay→connect | **Done** |
| Pre-publish checklist applied | **Done** (`PRE_PUBLISH_APPLIED.md`) |
| No public publish / no ads | **Honored** |
| Copy approved by Mkt + Brad | **Pending Brad** |
| Funnel reviewable unlisted in GHL | **Pending human GHL build** |

---

## 4. Scope

**In**
- All MD/TXT/JSON copy artifacts in repo
- Compliance self-check
- Workflow skeleton for builder

**Out**
- Live GHL page creation without credentials
- Domain purchase, public DNS, ads
- Counsel legal opinion
- Platform JWT connect_link implementation

---

## 5. Deliverables (canonical paths)

| Artifact | Path |
|----------|------|
| Index | `docs/marketing/copy/README.md` |
| Master pack | `docs/marketing/copy/COMPLIANT_COPY_PACK.md` |
| Sequences | `docs/marketing/copy/sequences/W*.txt` |
| Pages | `docs/marketing/copy/pages/*.md` |
| Funnel | `docs/marketing/copy/funnel/*` |
| Metrics | `docs/marketing/copy/metrics/UTM_KPI_TEMPLATE.md` |
| Checklist applied | `docs/marketing/copy/PRE_PUBLISH_APPLIED.md` |
| This handoff | `handoffs/scaling/Handoff_SCALING_1000_PHASE_A_06_COPY_20260730.md` |

---

## 6. Next actions (human / other profiles)

1. **Brad:** Skim pack; approve messaging + placeholder prices; Claims Policy §9 checkbox.  
2. **Brad/ops:** Build unlisted GHL funnel pages from `funnel/UNLISTED_FUNNEL_SKELETON.md`; paste sequences into workflows from JSON skeleton.  
3. **Legal:** Counsel before public checkout.  
4. **Platform:** Real connect links + paid_at/connected_at fields for KPI sheet.  
5. **Do not:** Public index, ads, or open checkout until gates clear.

---

## 7. Risks

- Brand domain not purchased — emails show support@arch-automation.com as intended end-state.  
- Refund window language must match final ToS.  
- Elite/Pro prices draft — label as pilot in UI until lock.
