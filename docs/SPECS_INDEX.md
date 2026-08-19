# Phase 6 / Platform — Specs & Product Docs Index

**Canonical home for “where is the spec?”**  
**Audience:** Brad, operators, Hermes/coding agents  
**Updated:** 2026-08-16  
**Repo root:** `projects/crypto-trading-bot` (paths below are from repo root)

---

## 0. Start here (30 seconds)

| Need | Go to |
|------|--------|
| **This index (you are here)** | `docs/SPECS_INDEX.md` |
| **Specs ↔ code gaps + deprecations** | `docs/SPECS_CODE_GAP.md` |
| **Profitability / P&L-ranked gaps (2026-08-13)** | `reports/PLATFORM_PROFITABILITY_REVIEW_2026-08-13.md` |
| **Cron SSOT (Hermes only)** | `docs/HERMES_CRON_SSOT.md` |
| **Gap backlog (MASTER program)** | `P6-SPECS-GAP-BACKLOG-20260807` in `docs/MASTER_TASK_TRACKING.md` |
| **What is in/out of this repo** | `docs/PROJECT_BOUNDARY.md` |
| **Execution status / tickets** | `docs/MASTER_TASK_TRACKING.md` (not a product spec) |
| **Live config truth** | `config/trading_config_phase6.json`, `config/regime_cash_policy.json`, `config/exit_automation.json`, `config/trader_accounts.json` |
| **New product feature specs** | `docs/features/` + register row in **§3** of this file |
| **Park / gold / cash doctrine** | §2.2 Park & Preserve |
| **Exits / SL / TP** | §2.3 Risk & exits |
| **Regime & deploy gates** | §2.1 Regime & capital |
| **Multi-tenant / GHL / SaaS** | §2.7 Scaling-1000 |
| **Analyst OPT / tests** | §2.6 Research & analyst |
| **Scale test lanes + gaps** | [`docs/testing/SCALE_TEST_LANES.md`](testing/SCALE_TEST_LANES.md) · MASTER `P6-SCALE-TEST-LANE-MAP-20260816` |
| **Post-liquidation redeploy** | [`docs/features/LIQUIDATION_ROTATION_REDEPLOY_POLICY.md`](features/LIQUIDATION_ROTATION_REDEPLOY_POLICY.md) · study `reports/LIQUIDATION_REDEPLOY_STUDY_LATEST.md` |
| **Stale May-era “unified SPEC”** | Treat as **historical** — see §5 |

### Agent rules

1. Prefer **this index** over `docs/SPEC.md`, `docs/PHASE6.md`, or `phase6/specs/*` for current product truth.  
2. Prefer **doctrine + feature specs + live config** over MASTER narrative alone.  
3. MASTER = *what we did / what’s queued*; specs = *what the product should be*.  
4. `docs/archive/**` and dated reports are **not** live specs unless linked from here as evidence.  
5. When you create a new feature spec: put it under `docs/features/`, add a row to §3 and the domain table in §2, bump **Updated** date.

---

## 1. Document classes (how to read status)

| Class | Meaning | Typical location |
|-------|---------|------------------|
| **FEAT** | Feature / product spec (ship criteria, UI, non-goals) | `docs/features/` |
| **PRD** | Product requirements (broader than one MVP slice) | `docs/research/` |
| **DOCTRINE** | Operator decision rules (how to run live) | `docs/research/*POLICY*`, `*MATRIX*` |
| **EPIC** | Multi-wave program (not day-to-day ops) | `docs/epics/` |
| **OPS** | Operator runbook / loop (how to push buttons) | `docs/*.md`, `docs/features/*COMMANDS*` |
| **ARCH** | Architecture / data-flow (how code is shaped) | `docs/*ARCHITECTURE*`, `DATA_FLOW*` |
| **RESEARCH** | Evidence, sketches, frozen research (may not be live) | `docs/research/` |
| **PROCESS** | How we build/test/ops-the-platform (agents) | `docs/testing/`, `OPS_*`, `TREND_*` |
| **GTM/LEGAL** | SaaS brand/legal (trading product only) | `docs/marketing/` |
| **LEGACY** | Superseded or frozen snapshot — do not implement from cold | `docs/archive/`, `phase6/specs/`, old `SPEC.md` |

### Status vocabulary (use in new specs)

| Tag | Meaning |
|-----|---------|
| `LIVE` | Behavior on in production path |
| `LIVE_SHADOW` | Instrumented / would-fire; **no** live orders from that path |
| `PARTIAL_LIVE` | Code + some path live; product incomplete |
| `CODE_SHIPPED` | Merged; may still be gated `enabled=false` |
| `IMPL_READY` | Spec + code ready; surface may be off |
| `SPEC_ONLY` / `PLANNED` | Spec exists; not built or not enabled |
| `RESEARCH` | Evidence / frozen design; not a ship commit |
| `LEGACY` | Historical; superseded by rows in this index |
| `DRAFT` | Unfrozen; do not treat as operator law |

---

## 2. Domain map (logical navigation)

### 2.1 Regime, cash park, deploy gates

| Doc | Class | Status (summary) | Notes |
|-----|-------|------------------|-------|
| [`docs/epics/REGIME_CASH_EPIC.md`](epics/REGIME_CASH_EPIC.md) | EPIC | Foundation complete (RC-01..06) | Program spine |
| [`docs/REGIME_GATES_AND_ANALYST_LOOP.md`](REGIME_GATES_AND_ANALYST_LOOP.md) | OPS | LIVE (flat = cautious deploy B) | Day-to-day operating model |
| [`docs/plans/2026-07-17-regime-cash.md`](plans/2026-07-17-regime-cash.md) | PLAN | Historical impl plan | Prefer epic + live config |
| [`docs/research/REGIME_ADAPTIVE_KNOBS.md`](research/REGIME_ADAPTIVE_KNOBS.md) | RESEARCH | Reference | Knob taxonomy |
| [`docs/research/REGIME_USDC_OPTIMIZATION.md`](research/REGIME_USDC_OPTIMIZATION.md) | RESEARCH | Research | USDC park economics |
| [`docs/LIVE_USDC_PARK.md`](LIVE_USDC_PARK.md) | OPS | Code live; **primary account off** | Per-account toggle · package coords |
| [`docs/CAPITAL_AND_PORTFOLIO_EVENTS.md`](CAPITAL_AND_PORTFOLIO_EVENTS.md) | OPS | LIVE | Deposits, manual sells, **cash hold** |
| [`docs/features/TRADER_PERSONALIZED_SETTINGS_SPEC.md`](features/TRADER_PERSONALIZED_SETTINGS_SPEC.md) | FEAT | PARTIAL_LIVE · MT planned | Cash hold + prefs |
| [`docs/features/PARK_USDC_PAXG_PACKAGE_SPEC.md`](features/PARK_USDC_PAXG_PACKAGE_SPEC.md) | FEAT | **W0 SHIPPED · LIVE OFF** | Coordinated A+B package |
| [`docs/features/PARK_SMART_IDLE_CASH.md`](features/PARK_SMART_IDLE_CASH.md) | **PRODUCT VOICE** | Canonical for traders/UI | **Smart Park** differentiator |
| [`docs/features/PARK_USDC_PAXG_OPERATOR_CHECKLIST.md`](features/PARK_USDC_PAXG_OPERATOR_CHECKLIST.md) | OPS | Companion | Go-live checklist |
| Config | — | LIVE | `config/regime_cash_policy.json`, `config/park_package.json` |

### 2.2 Park stack, Preserve / PAXG ballast

| Doc | Class | Status | Notes |
|-----|-------|--------|-------|
| [`docs/research/PARK_BALLAST_DECISION_MATRIX.md`](research/PARK_BALLAST_DECISION_MATRIX.md) | **DOCTRINE** | Canonical cheat sheet | **Start here for A/B/C** |
| [`docs/research/PARK_REGIME_POLICY.md`](research/PARK_REGIME_POLICY.md) | DOCTRINE | LIVE policy (micro) | Onboarding plain English |
| [`docs/features/PARK_SMART_IDLE_CASH.md`](features/PARK_SMART_IDLE_CASH.md) | FEAT | W0 coord · live off | **Smart Park** product home (trader voice) |
| [`docs/features/PARK_USDC_PAXG_PACKAGE_SPEC.md`](features/PARK_USDC_PAXG_PACKAGE_SPEC.md) | FEAT | W0 technical | Internal profiles / coordinator |
| [`docs/research/PRESERVE_MODE_PRD.md`](research/PRESERVE_MODE_PRD.md) | PRD | DRAFT label stale — code shipped later | Product freezes; check MVP spec for live |
| [`docs/research/PRESERVE_HOLD_MVP_SPEC.md`](research/PRESERVE_HOLD_MVP_SPEC.md) | FEAT/MVP | CODE_SHIPPED · LIVE MICRO | Hold-only; DeRisk off |
| [`docs/research/PRESERVE_VENUE_PROBE_PLAN.md`](research/PRESERVE_VENUE_PROBE_PLAN.md) | PLAN | Done (G1 A) | Evidence gate |
| [`docs/research/USD_HOLD_VALUE_CONTINGENCY_POLICY.md`](research/USD_HOLD_VALUE_CONTINGENCY_POLICY.md) | RESEARCH | NOT LIVE sketch | Pre-Preserve contingency |
| Code | — | Status each cycle | `phase6/core/park_package.py` → `park_package_status.json` |

### 2.3 Risk, stops, exits, dust

| Doc | Class | Status | Notes |
|-----|-------|--------|-------|
| [`docs/EXIT_AUTOMATION.md`](EXIT_AUTOMATION.md) | OPS | LIVE_SHADOW layers | Big picture exit stack |
| [`docs/REGIME_EXIT_POLICY_MAP.md`](REGIME_EXIT_POLICY_MAP.md) | FEAT/OPS | LIVE_SHADOW | Regime TP/trail/RSI map |
| [`docs/HARD_EXIT_OPERATOR_LOOP.md`](HARD_EXIT_OPERATOR_LOOP.md) | OPS | LIVE shadow + notify; no auto-sell | Human hard-exit |
| Config | — | LIVE | `config/exit_automation.json`, SL in `trading_config_phase6.json` |
| Skills (Hermes) | PROCESS | LIVE ops knowledge | `phase6-sl-exits-and-dust`, `phase6-exit-automation`, `phase6-exit-profit-shadow` |

### 2.4 Bull re-entry & pair universe

| Doc | Class | Status | Notes |
|-----|-------|--------|-------|
| [`docs/research/BULL_REENTRY_LAYERED_SPEC.md`](research/BULL_REENTRY_LAYERED_SPEC.md) | FEAT | RESEARCH / SHADOW-CANDIDATE | Layered re-entry frozen design |
| [`docs/PAIR_SELECTION_MATRIX.md`](PAIR_SELECTION_MATRIX.md) | RESEARCH | Proposed | Pair inclusion matrix |
| [`docs/Predictive_Filter_Opportunity_Scanner.md`](Predictive_Filter_Opportunity_Scanner.md) | FEAT | Shadow-only | IDEALOOP-002 scanner |

### 2.5 Signals: RSI, sentiment, IDEALOOP

| Doc | Class | Status | Notes |
|-----|-------|--------|-------|
| [`docs/FREE_SENTIMENT_SHADOW.md`](FREE_SENTIMENT_SHADOW.md) | OPS | LIVE path (fallback) | Free hybrid when X empty |
| [`docs/X_SENTIMENT_COST_CONTROL.md`](X_SENTIMENT_COST_CONTROL.md) | OPS | LIVE policy | 2×/day X cost guard |
| [`docs/RSI_SENTIMENT_DATA_FLOW_DEPENDENCIES.md`](RSI_SENTIMENT_DATA_FLOW_DEPENDENCIES.md) | ARCH | Reference | Pipeline deps |
| [`docs/RSI_SENTIMENT_RELIABILITY_PLAN.md`](RSI_SENTIMENT_RELIABILITY_PLAN.md) | PLAN | Reference | Reliability program |
| [`docs/SENTIMENT_STRATEGY_SPEC.md`](SENTIMENT_STRATEGY_SPEC.md) | LEGACY | Archived v1 | Prefer live ops docs |
| [`docs/IDEALOOP-001_Performance_Feedback_Loop_Design.md`](IDEALOOP-001_Performance_Feedback_Loop_Design.md) | RESEARCH | Design | Opt feedback loop |
| [`docs/IDEALOOP-002_Opportunity_Scanner_Loop_Design.md`](IDEALOOP-002_Opportunity_Scanner_Loop_Design.md) | RESEARCH | Design | Scanner loop |
| [`docs/IDEALOOP-005_Shadow_AB_Experimentation_Loop_Design.md`](IDEALOOP-005_Shadow_AB_Experimentation_Loop_Design.md) | RESEARCH | Design | Shadow A/B |
| [`docs/IDEALOOP_LIVE_ENABLEMENT_ROADMAP.md`](IDEALOOP_LIVE_ENABLEMENT_ROADMAP.md) | ROADMAP | Historical | Live enablement notes |
| [`docs/DYNAMIC_RSI_STRATEGY.md`](DYNAMIC_RSI_STRATEGY.md) | RESEARCH | Reference | RSI strategy write-up |

### 2.6 Analyst OPT, scenarios, testing

| Doc | Class | Status | Notes |
|-----|-------|--------|-------|
| [`docs/epics/ANALYST-OPT_EPIC.md`](epics/ANALYST-OPT_EPIC.md) | EPIC | In progress | Scenario optimization program |
| [`docs/research/scenario_schema.md`](research/scenario_schema.md) | ARCH | LIVE schema | Scenario packs |
| [`docs/research/REGIME_SCENARIO_PROCEDURE.md`](research/REGIME_SCENARIO_PROCEDURE.md) | PROCESS | LIVE procedure | How to run packs |
| [`docs/research/BACKTEST_LIVE_GAP_MATRIX.md`](research/BACKTEST_LIVE_GAP_MATRIX.md) | RESEARCH | R1 matrix | Sim vs live honesty |
| [`docs/research/CRYPTO_ANALYST_PERSONALITY.md`](research/CRYPTO_ANALYST_PERSONALITY.md) | PROCESS | LIVE persona | Analyst voice/rules |
| [`docs/research/MEMORY_AND_LEARNING.md`](research/MEMORY_AND_LEARNING.md) | PROCESS | Reference | Analyst memory |
| [`docs/testing/ANALYST_TEST_STRATEGY.md`](testing/ANALYST_TEST_STRATEGY.md) | PROCESS | Canonical v1 | Portfolio of tests |
| [`docs/testing/ANALYST_TEST_CYCLE.md`](testing/ANALYST_TEST_CYCLE.md) | PROCESS | Canonical v2 | Pickup → trial → decide |
| [`docs/testing/SCALE_TEST_LANES.md`](testing/SCALE_TEST_LANES.md) | PROCESS | Canonical v1 (2026-08-16) | Scale lanes inventory + **Decision** column + ranked gaps → MASTER `P6-SCALE-TEST-LANE-MAP-20260816` |
| [`docs/testing/inbox/`](testing/inbox/) | PROCESS | Ephemeral | Trial review queue |
| [`docs/testing/trials/`](testing/trials/) | PROCESS | Ephemeral | Trial protocols |

### 2.7 Product surfaces: dashboard, Daily Dose, capital UI

| Doc | Class | Status | Notes |
|-----|-------|--------|-------|
| [`docs/PHASE6_DASHBOARD_DATA_SPEC.md`](PHASE6_DASHBOARD_DATA_SPEC.md) | FEAT/ARCH | Reference | KPI source mapping |
| [`docs/DASHBOARD_README.md`](DASHBOARD_README.md) | OPS | Setup | Streamlit/legacy notes — verify against live `:8080` serve |
| [`docs/features/DAILY_DOSE_NEWS_FEED_PHASE_A_SPEC.md`](features/DAILY_DOSE_NEWS_FEED_PHASE_A_SPEC.md) | FEAT | PHASE_A_RUNNABLE | News feed Phase A |
| [`docs/features/DAILY_DOSE_PUBLICATION_CYCLE.md`](features/DAILY_DOSE_PUBLICATION_CYCLE.md) | FEAT | IMPL_READY (TG off) | Editorial publish loop |
| [`docs/features/DAILY_DOSE_OPERATOR_COMMANDS.md`](features/DAILY_DOSE_OPERATOR_COMMANDS.md) | OPS | LIVE commands | Quick ops |
| [`docs/features/TRADER_PERSONALIZED_SETTINGS_SPEC.md`](features/TRADER_PERSONALIZED_SETTINGS_SPEC.md) | FEAT | PARTIAL_LIVE | Settings / cash hold |

### 2.8 Platform ops, Hermes, reliability

| Doc | Class | Status | Notes |
|-----|-------|--------|-------|
| [`docs/OPS_TRIAGE_TASK_WORKFLOW.md`](OPS_TRIAGE_TASK_WORKFLOW.md) | PROCESS | LIVE | Triage → registry → GH |
| [`docs/OPS_ISSUE_LOOP.md`](OPS_ISSUE_LOOP.md) | PROCESS | LIVE | Close-the-loop |
| [`docs/TREND_REPAIR_PLAYBOOK.md`](TREND_REPAIR_PLAYBOOK.md) | PROCESS | LIVE | Trend repair process |
| [`docs/CRON_SCHEDULE.md`](CRON_SCHEDULE.md) | OPS | Reference | Crons (verify vs live) |
| [`docs/HERMES_TELEGRAM_KANBAN_GATEWAY_POLICY.md`](HERMES_TELEGRAM_KANBAN_GATEWAY_POLICY.md) | PROCESS | LIVE policy | Gateway / Kanban |
| [`docs/GIT_REPO_DAILY_MANAGEMENT.md`](GIT_REPO_DAILY_MANAGEMENT.md) | PROCESS | LIVE | Git hygiene |
| [`docs/DATA_FLOW_AND_LOCATIONS.md`](DATA_FLOW_AND_LOCATIONS.md) | ARCH | Reference | Where data lives |
| [`docs/LOGGING_PATHS.md`](LOGGING_PATHS.md) | OPS | Reference | Log locations |
| [`docs/P6_PARAM_AUDIT_AND_TRADING_LOG.md`](P6_PARAM_AUDIT_AND_TRADING_LOG.md) | ARCH | Reference | Param audit / ledger |

### 2.9 Multi-tenant Scaling-1000, GHL, GTM (trading SaaS only)

| Doc | Class | Status | Notes |
|-----|-------|--------|-------|
| [`docs/epics/SCALING-1000_EPIC.md`](epics/SCALING-1000_EPIC.md) | EPIC | Planned | Multi-trader platform |
| [`docs/epics/SCALING_1000_UNIFIED_ROADMAP.md`](epics/SCALING_1000_UNIFIED_ROADMAP.md) | ROADMAP | Plans only | Synthesized roadmap |
| [`docs/epics/SCALING_1000_REV01_SIGNOFF.md`](epics/SCALING_1000_REV01_SIGNOFF.md) | PROCESS | Approved w/ opens | Review sign-off |
| [`docs/integrations/SCALING_1000_IMPLEMENTATION_PLAN.md`](integrations/SCALING_1000_IMPLEMENTATION_PLAN.md) | PLAN | PLAN ONLY | Engineering waves |
| [`docs/integrations/GHL_INTEGRATION.md`](integrations/GHL_INTEGRATION.md) | FEAT | GHL-T0 pack | CRM/ops for **trading** SaaS |
| [`docs/integrations/GHL_API_V2_SURFACE_MAP.md`](integrations/GHL_API_V2_SURFACE_MAP.md) | ARCH | Reference | API map |
| [`docs/integrations/ghl_t0/GHL_T0_FIELD_DICT.md`](integrations/ghl_t0/GHL_T0_FIELD_DICT.md) | FEAT | Spec ready | Field dictionary |
| [`docs/marketing/LEGAL_DOCS_INDEX.md`](marketing/LEGAL_DOCS_INDEX.md) | GTM | Drafts | Legal pack index |
| [`docs/marketing/CLAIMS_SCREENSHOT_POLICY.md`](marketing/CLAIMS_SCREENSHOT_POLICY.md) | GTM | Policy | Claims discipline |
| Boundary | — | — | **No client SEO/SEM** — `PROJECT_BOUNDARY.md` |

### 2.10 Architecture & functional (platform core)

| Doc | Class | Status | Notes |
|-----|-------|--------|-------|
| [`docs/CRYPTO_BOT_ARCHITECTURE.md`](CRYPTO_BOT_ARCHITECTURE.md) | ARCH | Prefer over PHASE6.md | Canonical architecture intent |
| [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) | ARCH | Reference | Config/architecture notes |
| [`docs/phase6/ARCHITECTURE_ISOLATED_COMPONENTS.md`](phase6/ARCHITECTURE_ISOLATED_COMPONENTS.md) | ARCH | Reference | Isolated components |
| [`docs/FUNCTIONAL_SPEC_v1.md`](FUNCTIONAL_SPEC_v1.md) | LEGACY | Phase 5 approved | Superseded in parts by live + feature specs |
| [`docs/FUNCTIONAL_SPEC.md`](FUNCTIONAL_SPEC.md) | LEGACY | Draft | Prefer domain docs |
| [`docs/SPEC.md`](SPEC.md) | LEGACY | May 2026 snapshot | **Not** current SSOT |
| [`docs/PHASE6.md`](PHASE6.md) | LEGACY | May 2026 codex | Paths/status stale — use this index |
| [`docs/TRADING_BOT_DOCS.md`](TRADING_BOT_DOCS.md) | LEGACY | Older umbrella | Prefer this index |
| [`docs/faq/Internal_Trading_Platform_FAQ.md`](faq/Internal_Trading_Platform_FAQ.md) | OPS | FAQ | Operator FAQ |
| [`docs/faq/External_Client_FAQ.md`](faq/External_Client_FAQ.md) | GTM | FAQ | External wording |

---

## 3. Feature registry (`docs/features/`)

| ID | Spec | Status | Domain |
|----|------|--------|--------|
| `FEAT-DAILY-DOSE-NEWS-2026-08` | [DAILY_DOSE_NEWS_FEED_PHASE_A_SPEC.md](features/DAILY_DOSE_NEWS_FEED_PHASE_A_SPEC.md) | PHASE_A_RUNNABLE | Comms |
| `FEAT-DAILY-DOSE-PUB-CYCLE-2026-08` | [DAILY_DOSE_PUBLICATION_CYCLE.md](features/DAILY_DOSE_PUBLICATION_CYCLE.md) | IMPL_READY (disk; TG off) | Comms |
| — | [DAILY_DOSE_OPERATOR_COMMANDS.md](features/DAILY_DOSE_OPERATOR_COMMANDS.md) | OPS companion | Comms |
| `FEAT-TRADER-PERSONALIZED-SETTINGS-2026-08` | [TRADER_PERSONALIZED_SETTINGS_SPEC.md](features/TRADER_PERSONALIZED_SETTINGS_SPEC.md) | PARTIAL_LIVE · MT planned | Capital / settings |

**Rule:** New shippable product work gets a `FEAT-…` id, a file under `docs/features/`, a row here, and a MASTER block only if execution is tracked.

Also treat these as **feature-class** even if not yet moved under `features/`:

| ID (informal) | Path | Status |
|---------------|------|--------|
| Preserve Hold MVP | `docs/research/PRESERVE_HOLD_MVP_SPEC.md` | LIVE MICRO |
| Regime exit map | `docs/REGIME_EXIT_POLICY_MAP.md` | LIVE_SHADOW |
| Bull re-entry layered | `docs/research/BULL_REENTRY_LAYERED_SPEC.md` | RESEARCH/SHADOW |
| Live USDC park | `docs/LIVE_USDC_PARK.md` | CODE; account off |
| Capital events / hold | `docs/CAPITAL_AND_PORTFOLIO_EVENTS.md` | LIVE |

*(Optional future cleanup: move preserve/exit/usdc into `docs/features/` with redirects — not required for index usefulness.)*

---

## 4. Epics registry (`docs/epics/`)

| Epic | Path | Status |
|------|------|--------|
| REGIME-CASH | [REGIME_CASH_EPIC.md](epics/REGIME_CASH_EPIC.md) | Foundation complete |
| ANALYST-OPT | [ANALYST-OPT_EPIC.md](epics/ANALYST-OPT_EPIC.md) | In progress |
| SCALING-1000 | [SCALING-1000_EPIC.md](epics/SCALING-1000_EPIC.md) | Planned (+ roadmap/sign-off) |

---

## 5. Do-not-use-as-SSOT (legacy / mirrors / noise)

| Path | Why |
|------|-----|
| `docs/SPEC.md` | Unified May-15 snapshot; architecture and runner paths outdated |
| `docs/PHASE6.md` | “Project Codex” May-13; wrong runner paths, basket, status |
| `docs/PHASE6_CURRENT_STATUS.md`, `PHASE6_README.md` | Point-in-time status dumps |
| `docs/FUNCTIONAL_SPEC.md` / `FUNCTIONAL_SPEC_v1.md` | Pre–REGIME-CASH / pre-ARCH-4 product law |
| `phase6/specs/*` | **Mirrors / legacy copies** — may lag `docs/`; verify date before citing |
| `docs/archive/**` | Explicit archive (legacy phases, old phase6, cross-project scrub) |
| `docs/testing/inbox/*`, `trials/*` | Trial artifacts, not product specs |
| `reports/**` | Evidence and reviews, not requirements (except when a FEAT links them) |
| `docs/MASTER_TASK_TRACKING.md` | Execution ledger — huge; use for tickets, not product definition |
| Client SEO/SEM docs | **Out of project** — `PROJECT_BOUNDARY.md` |

### Known stale status labels (still linked as content)

| Doc | Issue |
|-----|--------|
| `PRESERVE_MODE_PRD.md` header | Still says “not live · not coded” — **code + micro live** exist; PRD freezes still useful |
| `docs/README.md` | Old Phase 5.1 test commands — not docs hub (see §7) |

---

## 6. Inventory summary (2026-08-07)

Rough scan of `docs/**/*.md` (~300+ files):

| Bucket | Approx role | Count class |
|--------|-------------|-------------|
| **Canonical product/ops/research in this index** | Use these | ~70 listed |
| **Feature specs directory** | Active FEAT home | 4 (+ README) |
| **Epics** | Programs | 5 |
| **Testing process + trial junk** | Process + ephemeral | strategy/cycle + inbox/trials |
| **Marketing/legal for trading SaaS** | GTM only | `docs/marketing/` |
| **Archive + legacy phases** | Do not implement cold | `docs/archive/`, old SPEC/PHASE6 |
| **Point-in-time reports, changelogs, audits** | Evidence | `docs/*REPORT*`, dated files |

**Consolidation choice (this pass):**  
**Logical consolidation via this index** — not mass file moves (would break handoffs, MASTER, skills, and git history noise). Physical home for *new* specs = `docs/features/` (product) + `docs/research/` (doctrine/PRD) + `docs/epics/` (programs).

---

## 7. Where to put new docs

| Kind | Directory | Register in |
|------|-----------|-------------|
| New product feature | `docs/features/<NAME>_SPEC.md` | §3 + domain §2 |
| Operator doctrine / matrix | `docs/research/` | §2 domain |
| Multi-wave program | `docs/epics/` | §4 |
| GHL / SaaS engineering | `docs/integrations/` | §2.9 |
| Trading SaaS legal/brand | `docs/marketing/` (not consultancy SEO) | §2.9 |
| Analyst trial | MASTER Type:test + `docs/testing/` | Not feature registry |
| One-off evidence | `reports/` | Link from FEAT if needed |

### Required header for new FEAT files

```markdown
# Feature Spec — <Name>

**ID:** `FEAT-<SLUG>-YYYY-MM`
**Status:** <STATUS_TAG>
**Date:** YYYY-MM-DD
**Domain:** <regime|park|exits|signals|dashboard|comms|settings|scaling|…>
**Related:** <paths>
```

Then add a row to §3 of **this** file in the same PR/session.

---

## 8. Quick “topic → primary doc” cheat sheet

| Topic | Primary | Secondary |
|-------|---------|-----------|
| Why the book loses / P&L-ranked gaps | reports/PLATFORM_PROFITABILITY_REVIEW_2026-08-13 | SPECS_CODE_GAP + TREND_REPAIR |
| Idle cash / manual hold | CAPITAL_AND_PORTFOLIO_EVENTS + PERSONALIZED_SETTINGS | capital_controls.py |
| Flat deploy / RSI entry gates | REGIME_GATES_AND_ANALYST_LOOP | regime_cash_policy.json |
| USDC park toggle | LIVE_USDC_PARK | trader_accounts.json |
| PAXG / Preserve / E1 | PARK_BALLAST_DECISION_MATRIX | PRESERVE_HOLD_MVP_SPEC |
| Shadow TP / regime exits | EXIT_AUTOMATION + REGIME_EXIT_POLICY_MAP | exit_automation.json |
| Hard exit human loop | HARD_EXIT_OPERATOR_LOOP | — |
| Daily Dose | features/DAILY_DOSE_* | phase6-product-comms skill |
| Multi-tenant | SCALING-1000 epic + roadmap | GHL_INTEGRATION |
| Analyst OPT weekly | ANALYST-OPT epic | scenario_schema + test cycle |
| Stoch / indicator trials | testing strategy + MASTER Type:test | not product FEAT |
| Dashboard KPI truth | PHASE6_DASHBOARD_DATA_SPEC | phase6-capital-and-dashboard-kpis skill |
| Ops broken overnight | OPS_TRIAGE_TASK_WORKFLOW | phase6-ops-triage skill |

---

## 9. Maintenance

| When | Action |
|------|--------|
| Ship or freeze a FEAT | Update §3 status + domain table |
| Supersede a doc | Mark LEGACY in §5; point primary to new path |
| Quarterly | Re-scan `docs/features`, `research`, `epics`; fix stale Status headers (e.g. Preserve PRD) |
| Agent session | If you cannot find a topic in §2/§8, search then **patch this index** |

**Companion mini-index:** [`docs/features/README.md`](features/README.md) (features only).  
**Execution ledger:** [`docs/MASTER_TASK_TRACKING.md`](MASTER_TASK_TRACKING.md).  
**Boundary:** [`docs/PROJECT_BOUNDARY.md`](PROJECT_BOUNDARY.md).

---

*Inventory pass: 2026-08-07. Logical consolidation; no mass moves.*
