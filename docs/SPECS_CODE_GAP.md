# Specs ↔ Code Gap Analysis (Phase 6 platform)

**ID:** `P6-SPECS-CODE-GAP-20260807`  
**Date:** 2026-08-07  
**Status:** LIVING SNAPSHOT (not exhaustive line-by-line audit)  
**Companion:** [`docs/SPECS_INDEX.md`](SPECS_INDEX.md)  
**Not the same as:** [`docs/research/BACKTEST_LIVE_GAP_MATRIX.md`](research/BACKTEST_LIVE_GAP_MATRIX.md) (sim path A/B vs live knobs for ANALYST-OPT)

---

## 0. Short answers

| Question | Answer |
|----------|--------|
| Do we already have a full specs-vs-coded gap analysis? | **No.** Pieces exist; no single living matrix until this doc. |
| Closest prior artifacts | ANALYST-OPT R1 **backtest↔live knob** matrix; SPECS_INDEX status tags; MASTER narrative; April 2026 codebase audit (stale) |
| Can we deprecate things? | **Yes** — docs and some code paths. See §4. Prefer mark LEGACY + stop linking as SSOT before hard-delete. |

### Gap types used below

| Type | Meaning |
|------|---------|
| **A — Spec ahead of code** | Documented product; missing or incomplete implementation |
| **B — Code ahead of / vs stale spec** | Behavior live or shipped; doc status wrong or missing |
| **C — Gated off** | Code exists; config/flag keeps it non-live (intentional) |
| **D — Shadow only** | Instrumented would-fire; no live orders from that path |
| **E — Doc noise / deprecate** | Safe to demote from SSOT or archive |
| **F — Research only** | Frozen design; not a ship commitment |

---

## 1. Prior gap work (what we already had)

| Artifact | Covers | Does **not** cover |
|----------|--------|---------------------|
| `docs/research/BACKTEST_LIVE_GAP_MATRIX.md` | Scenario knobs Path A/B/C for OPT promotion | Product FEATs, UI, park package, Scaling-1000 |
| `docs/SPECS_INDEX.md` §5 | Doc SSOT vs legacy | Runtime verification |
| MASTER task blocks | Session-level done/partial | Systematic FEAT matrix |
| `docs/CODEBASE_AUDIT_2026_04_19.md` | Orphan code Apr 2026 | Post–REGIME-CASH / ARCH-4 world |
| `phase6/archive/README.md` | Deprecated phase6 files moved | Specs inventory |

---

## 2. Feature / domain gap matrix (2026-08-07)

Evidence: live configs (`trading_config_phase6`, `regime_cash_policy`, `exit_automation`, `trader_accounts`, `regime_exit_policy_map`) + module presence under `phase6/core/`.

### 2.1 Capital, regime, deploy

| Spec / surface | Coded? | Live? | Gap type | Notes |
|----------------|--------|-------|----------|-------|
| REGIME-CASH epic foundation | Yes | **Yes** (`regime_cash_policy.enabled=true`, not shadow-only) | — | Operating model live |
| Manual cash hold + clear flags | Yes (`capital_controls.py`) | **Yes** | B | Ops path solid; **SaaS settings UI** still A |
| FEAT personalized settings (multi-tenant UI/API) | Partial (state + flags + JSON read model) | Operator-only | **A** | Spec filed 2026-08-07; no trader Settings UI |
| Mid-cycle allocator | Yes (wired) | **Off** (`mid_cycle_allocator_enabled: false`) | **C** | Explains “score later, no buy” |
| Multi-tenant runner | Largely no / stub | **Off** (`multi_tenant_enabled: false`) | **A** / C | Scaling-1000 |

### 2.2 Park / Preserve / USDC

| Spec / surface | Coded? | Live? | Gap type | Notes |
|----------------|--------|-------|----------|-------|
| Preserve Hold MVP (micro + E1) | Yes | **Micro path on** (`preserve_mode.enabled=true`, `micro_live=true`) | B vs PRD header | **PRD still says “not coded”** — stale |
| DeRisk ladder | Code paths exist | **Off** (`derisk.enabled=false`) | **C** / doctrine OFF | Do **not** promote |
| Full 20% PAXG Hold | Arm path | Not default | **C** | Manual scale only |
| Live USDC park executor | Yes | **Off** on primary account | **C** | Toggle ready; not product-on |
| **USDC carry + PAXG as one package** | **W0 yes** (`park_package.py` + config) | Package **OFF** (`profile=off`) | **C** (live) | Spec/checklist/status shipped; enable = W5 + Brad OK |
| Park ballast decision matrix | Doctrine doc | Ops law | — | Not executable code by itself |

### 2.3 Exits / risk

| Spec / surface | Coded? | Live? | Gap type | Notes |
|----------------|--------|-------|----------|-------|
| Global shadow TP + trail | Yes | **Shadow** (`take_profit.mode=shadow`); TG would-fire muted | **D** | Legacy instrumentation |
| Regime exit policy map | Yes | **Shadow** (`mode=shadow`, `live_apply=false`); 60d gate | **D** | Prefer this over global TP for future promote |
| Hard exit | Yes | Shadow + operator_approve; `live_apply=false` | **D** | Human loop intentional |
| Live trail market exit | Config knob | **false** | **C** | Until quality bar |
| Native SL (exchange) | Yes (production path) | Live | — | Dust/sweep companion skills |

### 2.4 Signals / scanner / IDEALOOP

| Spec / surface | Coded? | Live? | Gap type | Notes |
|----------------|--------|-------|----------|-------|
| X sentiment 2×/day + cost control | Yes | Live policy | — | Reddit OFF per book posture |
| Free sentiment fallback | Yes | Live when X empty | — | |
| Opportunity scanner / IDEALOOP-002 | Partial/shadow designs | Shadow proposals | **D** / F | Not auto-expand live basket from IDEALOOP alone |
| IDEALOOP-001/005 designs | Specs | Not full product loops | **F** | Design-phase docs |
| Stoch RSI parallel | Instrumentation | observe_only (CLOSED trial posture) | **D** | Not allocator driver |

### 2.5 Comms / dashboard

| Spec / surface | Coded? | Live? | Gap type | Notes |
|----------------|--------|-------|----------|-------|
| Daily Dose Phase A | Yes | Disk publish; TG product path separate | **C** / partial | Spec PHASE_A_RUNNABLE |
| Daily Dose publication cycle (editor→pub) | Scripts | Disk; TG off in cycle doc | **C** | |
| Dashboard KPI data spec | Mapping doc | Live dash exists | B risk | Spec vs current React/serve path can drift — treat KPIs as product bugs when wrong |
| Capital hold on dash banner | Read model in `capital_user_controls.json` | Partial | **A** | UI action flags often `enabled: false` |

### 2.6 Analyst OPT / backtest

| Spec / surface | Coded? | Live? | Gap type | Notes |
|----------------|--------|-------|----------|-------|
| Scenario packs + knobs | Yes | Research/OPT | — | |
| Path A simple backtest | Yes | Ranking smoke only | Known gap | Stub sentiment — **do not promote from A** |
| Path B ARCH-4 harness | Yes | Authoritative for strategy claims | Partial parity gaps | See BACKTEST_LIVE_GAP_MATRIX |
| Live clock rebalance vs day-stride knobs | Documented gap | Live = clock slots | Known | |

### 2.7 Scaling-1000 / GHL / SaaS

| Spec / surface | Coded? | Live? | Gap type | Notes |
|----------------|--------|-------|----------|-------|
| SCALING-1000 epic + roadmap | Plans | **Not multi-tenant prod** | **A** | Spec-heavy, code-light |
| GHL-T0 field dict / integration docs | Spec pack | Admin/credentials pending | **A** | Almost no `phase6` GHL runtime |
| Brand/legal packs | Draft docs | Not public ship | F / counsel | |

---

## 3. Highest-value open gaps (product) → MASTER tasks

Ordered by “spec implies product, book doesn’t fully deliver.”  
**Program:** `P6-SPECS-GAP-BACKLOG-20260807` in `docs/MASTER_TASK_TRACKING.md` (2026-08-07).

| # | Gap | MASTER task | Status |
|---|-----|-------------|--------|
| 1 | Personalized settings UI/API (multi-tenant) | `FEAT-PERSONALIZED-SETTINGS-IMPL-20260807` | **W1+W2 SHIPPED** · W3+ QUEUED |
| 2 | USDC + PAXG park package | `FEAT-PARK-USDC-PAXG-PACKAGE-20260807` | W0 SHIPPED · LIVE OFF |
| 3 | Exit profit automation (live) | `P6-EXIT-PROFIT-LIVE-GATES-20260807` | QUEUED / GATED |
| 4 | Hard-exit auto-apply | `P6-HARD-EXIT-AUTO-APPLY-GATES-20260807` | QUEUED / GATED |
| 5 | Mid-cycle deploy | `P6-MID-CYCLE-ALLOCATOR-EVAL-20260807` | QUEUED |
| 6 | Scaling-1000 runtime | `SCALING-1000-RUNTIME-SLICE-20260807` | QUEUED |
| 7 | Stale SSOT docs | `P6-SSOT-DOC-HYGIENE-20260807` | QUEUED |
|| 8 | Rebalance add-into-stop race | `P6-NEAR-STOP-REBALANCE-RACE-20260813` | **DONE** (kanban t_f1d02d37, GH#22 closed) |
| 9 | Same-session SL metric (brief) | `P6-SAME-SESSION-SL-METRIC-20260813` | **DONE** |

Update this table when a child task leaves QUEUED.

---

## 4. Deprecation candidates

### 4.1 Docs — deprecate as SSOT (keep as history or archive)

| Path | Action | Why |
|------|--------|-----|
| `docs/SPEC.md` | **LEGACY SSOT** — already indexed | May 2026 unified spec |
| `docs/PHASE6.md` | **LEGACY** | Wrong runner paths/status |
| `docs/PHASE6_CURRENT_STATUS.md`, `PHASE6_README.md`, old deploy schedules | Archive or banner | Point-in-time |
| `docs/FUNCTIONAL_SPEC.md`, `FUNCTIONAL_SPEC_v1.md` | LEGACY | Pre–REGIME-CASH law |
| `docs/SENTIMENT_STRATEGY_SPEC.md` | LEGACY v1 | Prefer FREE_SENTIMENT + cost control ops docs |
| `phase6/specs/*` (except README warning) | **Mirror only** | Prefer `docs/` |
| `docs/research/PRESERVE_MODE_PRD.md` **header status** | **Fix status line** (not delete) | Says not coded; micro is live |
| IDEALOOP design skeletons if abandoned | Mark F or archive when Brad confirms | Avoid fake roadmap weight |
| April `CODEBASE_AUDIT_2026_04_19` orphan lists | Historical only | Tree changed massively |

**Safe process:** SPECS_INDEX §5 already blacklists. Next step optional: move to `docs/archive/ssot-legacy/` + stub “moved” file. Low urgency if index is used.

### 4.2 Code / config — deprecate or keep-gated

| Item | Recommendation |
|------|----------------|
| `use_new_allocator=False` / `[LEGACY FALLBACK]` deploy path | **Keep as emergency only**; do not build features on it. Candidate to delete after N months clean ARCH-4. |
| Global shadow TP as *policy* | **Superseded for policy** by regime exit map; keep logging until map trusted, then `mode: off` |
| Path A leaderboard for promotion | **Deprecate for promote**; smoke-only (matrix already says this) |
| DeRisk ladder enable | **Do not enable** — doctrine OFF (economics fail) |
| Reddit sentiment live | **Keep OFF** unless product reverses |
| `phase6/archive/*` | Already deprecated tree — leave |
| Dual dash implementations / stale `:8080` orphans | Ops issue (post-hermes-update) — kill stale processes, not a spec |
| Coinbase Pro API wrappers | Long deprecated — ensure no remaining callers (historical fix) |

### 4.3 What **not** to deprecate

| Item | Why |
|------|-----|
| REGIME-CASH policy + epic | Live control plane |
| Capital hold controls | Just proven load-bearing |
| Preserve micro + E1 path | Live learning sleeve |
| Shadow exit map + hard-exit operator loop | Active proof stack |
| ANALYST test cycle docs | Process SSOT for Type:test |
| SPECS_INDEX + this gap doc | Navigation |

---

## 5. Suggested maintenance cadence

| Cadence | Action |
|---------|--------|
| When shipping a FEAT | Update SPECS_INDEX status **and** a row in §2 here |
| Monthly | Re-read live config flags vs §2.2–2.3 |
| Before any “promote to live” exit/TP | Require shadow gates + this matrix C/D column |
| Quarterly | Archive another batch of §4.1 docs |

---

## 6. Honest limitations of this snapshot

- Not a full static analysis of every `docs/**/*.md` claim vs every function.  
- Does not replace isolation tests or MASTER trial decisions.  
- Dashboard UI drift and Hermes skill drift not fully walked.  
- Scaling-1000 assessed at “plans vs runtime” level only.

**Upgrade path:** turn §2 into a generated check (config flag probe + `Path.exists` for modules) in `scripts/docs/specs_code_gap_probe.py` if we want CI-ish drift alerts.

---

*Created 2026-08-07 with SPECS inventory consolidation.*
