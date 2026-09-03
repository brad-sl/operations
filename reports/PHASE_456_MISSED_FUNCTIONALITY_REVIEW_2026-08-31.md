# Phase 4 / 5 / 6 — Missed functionality review

**Date:** 2026-08-31  
**Scope:** Docs from Phase 4–6 (incl. archive) vs **current platform** under `crypto-trading-bot`.  
**Question:** What was **specified**, **not shipped** (or only partial), and **not superseded** by Phase 6 live design?  
**Not:** line-by-line of every markdown file. Not a “rebuild Phase 5” brief.  
**Companions:** `docs/SPECS_CODE_GAP.md` (2026-08-07, **partially stale**), `docs/SPECS_INDEX.md`, `reports/PLATFORM_PROFITABILITY_REVIEW_2026-08-13.md`, live configs.

---

## 0. Plain English

| Lens | Takeaway |
|------|----------|
| **Single-book trading engine** | Most Phase 4/5 *strategy* specs were **replaced** by Phase 6 (RSI+sent primary, exchange SL, REGIME-CASH, ARCH-4 rebalance, live trail TP as of 2026-08-23). Gaps that still matter for **this book’s P&L** are mostly **exit/capital discipline** and a few **risk knobs loaded but not enforced**. |
| **SaaS / multi-trader product** | Phase 4 end-user UI + OAuth + Phase 5 “scalable multi-process” + SCALING-1000 are still **largely SPEC / stubs**. That is intentional backlog, not a silent regression of a live multi-tenant product. |
| **Do not implement from cold** | `docs/PHASE6.md`, `FUNCTIONAL_SPEC*.md`, `TECHNICAL_DEBT.md` (Apr), most `docs/archive/legacy-phases/*`, and StochRSI-as-primary entry. |

**North star filter (Brad law):** prefer gaps that reduce loss or make the product honest — not another indicator or SaaS wrapper around a weak book.

---

## 1. Method

1. Read living SSOT: `SPECS_INDEX`, `SPECS_CODE_GAP`, feature specs under `docs/features/`, epics, profitability review.  
2. Sample Phase 4/5 archive specs: UI, OAuth, 4b X/digest, Phase 5 functional, 5.1 correlation rebalance, Phase 5 scalable.  
3. Probe **live config + code presence** (not doc status alone).  
4. Classify each item:

| Tag | Meaning |
|-----|---------|
| **MISS** | Spec’d; missing or dead on live path; **not** superseded |
| **PARTIAL** | Code or operator path exists; product incomplete |
| **GATED** | Built; flag/shadow off by design |
| **SUPERSEDED** | Intent replaced by Phase 6 design — do not rebuild |
| **STALE_DOC** | Doc claims wrong current state |

---

## 2. What Phase 6 **did** supersede (ignore for “missed product”)

| Phase 4/5 claim | Phase 6 replacement | Evidence |
|-----------------|---------------------|----------|
| StochRSI %K>%D **primary** entry + 60/40 as sole stack | **RSI primary** + X/free sentiment gates; Stoch = **observe / SL risk scorer** only | Memory + trials `continue_observe_only`; `sl_risk_scorer.py` |
| Fixed **+5% TP** / software **2×ATR SL** as sole exits | Exchange **~3% SL** + adaptive haircut; **live trail TP** (arm 4% / trail 2%, +6% fb) promoted **2026-08-23**; regime map still shadow | `config/exit_automation.json` `take_profit.mode=live`; `regime_exit_policy_map.json` `live_apply=false` |
| Phase 5 multi-process `phase5_multi_pair` + supervisor | Single **`phase6_runner`** live loop | Live PID / ops |
| 4h Telegram digests (Phase 4b) | Dose / intel / trader messaging stack (different cadence & compose rules) | `docs/features/DAILY_DOSE_*`, `TRADER_MESSAGE_COMPOSE_NO_AI` |
| “We use limit → maker fees” | Fills dig + fee tier Intro 2 + **limit-first Phase D pilot** | `FILLS_MARKET_PATH_DIG`, `LIMIT_FIRST_BUY_DESIGN` |
| Reddit/Apify as must-have (TECHNICAL_DEBT Apr) | Product posture **Reddit OFF**; X 2×/day + free fallback | Live sentiment config |
| Static $200×4 pair paper model | Dynamic basket + REGIME-CASH util + seat caps | Live runner |
| May `PHASE6.md` “minimal runner missing rebalance/SL” | **Stale** — dual rebalance + native SL long since live | `SPECS_INDEX` blacklists PHASE6.md as LEGACY |
| AgentKit as production SL | **PoC only** (`agentkit_sl.py`); production = exchange SL path | Code header + compare script |
| UnifiedSignalConsumer ← `reports.db` | Different signal/cache path (rsi_cache, SignalGenerator, dash APIs) | SPECS / dash |

---

## 3. Still open — **MISS / PARTIAL** (not superseded)

### 3.1 Highest relevance to **this book** (trading / risk)

| # | Item | Origin | Status | Evidence | Notes |
|---|------|--------|--------|----------|-------|
| 1 | **`max_daily_loss` circuit on live runner** | P5 risk §5.1 daily loss cap; `risk_management.max_daily_loss_*` in config | **MISS / PARTIAL** | Loaded in `phase6/core/config_loader.py` → `max_daily_loss_usd`; **no** `phase6/core/*` consumer found. Enforcement lives under **legacy** `scripts/order_executor.py` / `scripts/live_portfolio_manager.py` | Config honesty gap: knob may be theater on Phase 6 path |
| 2 | **Correlation circuit / high-corr rebalance** | P5.1 adaptive weekly rebalance; P6 risk module | **PARTIAL / GATED** | `phase6/core/risk/correlation_circuit_breaker.py` + rolling corr + shadow test exist; **not** wired into `phase6_runner` live cycle | P5.1 “reduce high-corr pair 50% weekly” **not** live. P6 has dual clock rebalance + basket **shadow** — different product. Rebuilding 5.1 verbatim = low priority vs exit stack |
| 3 | **Hard-exit auto-apply** | REGIME-CASH / exit automation | **GATED (D)** | `hard_exit.shadow_only=true`, `live_apply=false` | Spec intentional human loop; not “forgotten” |
| 4 | **Regime exit policy map live** | Exit automation | **GATED (D)** | `mode=shadow`, `live_apply=false` | **Global** trail TP is live; **per-regime map** still shadow — SPECS_CODE_GAP outdated on global TP |
| 5 | **`live_attach_on_buy` (exchange TP attach)** | Exit H2 | **GATED (C)** | `live_attach_on_buy=false`; software market exit primary | Wired, not flipped |
| 6 | **Mid-cycle allocator** | Deploy between rebalance slots | **GATED (C)** | `global_settings.mid_cycle_allocator_enabled=false` | Code + tests; default off (churn risk) |
| 7 | **Basket discovery live promote** | IDEALOOP / pair discovery | **GATED (D)** | dual_agree / CF shadow only; `auto_promote=false` | Correctly blocked |
| 8 | **StochRSI as entry driver** | Phase 5 functional | **GATED / research** | Parallel trial observe_only | **Not a miss** if product chose RSI primary — only miss if someone still thinks Phase 5 entry is live |
| 9 | **Limit-first maker buys** | Fee research aspiration | **PARTIAL (pilot)** | Phase D live 2026-08-31 under caps | Was a real path miss until D; still not full promote |

### 3.2 Product / SaaS (Phase 4 UI + SCALING-1000) — real gaps, **low P&L leverage now**

| # | Item | Origin | Status | Evidence |
|---|------|--------|--------|----------|
| 10 | **End-user account UI** (pair picker, leaderboard, bulk exit, slider rebalance, mobile, WebSocket P&L) | `PHASE_4_END_USER_UI_SPEC.md` | **MISS** | Operator dash (`serve_dashboard*.py`, phase6 HTML/API) ≠ trader SaaS UI |
| 11 | **Coinbase OAuth2 multi-account** | `PHASE_4_OAUTH2_PLANNING.md`, SCALING-1000 | **MISS / stub** | `AccountContext.auth_mode` oauth placeholder; `test_t0_registry` oauth_tokens schema tests; **no** production OAuth gateway service in-tree |
| 12 | **GHL runtime** (webhooks, TradingAccount sync, W1–W7 workflows) | SCALING-1000 + `docs/integrations/ghl_t0/*` | **MISS** (docs + manual T0) | Almost no non-doc GHL runtime under `phase6/`; epic **Planned** |
| 13 | **Multi-tenant runner fleet** | PHASE5_SCALABLE + SCALING-1000 | **MISS / stub** | `multi_tenant_enabled=false`; runner short-circuits MT helper to False |
| 14 | **Personalized settings W3** (banner + release on portfolio home) | `TRADER_PERSONALIZED_SETTINGS_SPEC` | **PARTIAL** | W1+W2 shipped (API + per-account state); **W3 UI PLANNED** |
| 15 | **Smart Park package default-on** | Park FEAT | **GATED** | `park_package.json` profile `a_plus_b_micro` / enabled true at package file; **trader_accounts defaults** still `park_package.enabled=false`, `live_usdc_park.enabled=false` | Product off on primary until Brad OK |
| 16 | **Daily Dose full product cycle (editor→pub→TG)** | Dose specs | **PARTIAL** | Disk/scripts; TG product path often off | Not core engine |

### 3.3 SPECS_CODE_GAP (2026-08-07) — **refresh needed**

| Claim in Aug-7 gap doc | Live truth 2026-08-31 |
|------------------------|------------------------|
| Global shadow TP | **`take_profit.mode=live`** since ~2026-08-23 |
| Park package OFF | Package config **enabled** / `a_plus_b_micro`; **account default still off** |
| Preserve “PRD not coded” | Micro preserve **on** (still true that PRD header may be stale) |
| Limit-first not listed | **Phase D pilot ON** (caps 3 / $300) |

---

## 4. Phase-by-phase cheat sheet

### Phase 4

| Theme | Outcome |
|-------|---------|
| Live $1k trading + Dynamic RSI + X sentiment | **Superseded / evolved** into P6 gates |
| 4b digests every 4h | **Superseded** by newer comms |
| End-user multi-trader UI | **Still MISS** → Scaling-1000 |
| OAuth2 business multi-account | **Still MISS** → Scaling-1000 |
| Spend limits / smoke harness | Partial legacy under `scripts/`; P6 has different spend/risk shape |

### Phase 5

| Theme | Outcome |
|-------|---------|
| StochRSI primary entry | **Not live entry** (observe/scorer) — **deliberate**, not accidental omit |
| 2×ATR SL + +5% TP | **Superseded** by exchange SL + live trail |
| Per-pair $50/day loss pause | **Unclear / likely MISS** on P6 path (see max_daily_loss) |
| Dashboard :8501 Streamlit-era | **Superseded** by phase6 dash stack (different UX) |
| Phase 5.1 correlation weekly rebalance | **Not live**; module exists unshackled — **PARTIAL research artifact** |
| Phase 5 Scalable (1 process × N traders) | **Not product**; Scaling-1000 is the real multi-tenant epic |

### Phase 6 (original / living)

| Theme | Outcome |
|-------|---------|
| Full production runner | **LIVE** |
| REGIME-CASH, capital hold, native SL | **LIVE** |
| Exit profit (global trail) | **LIVE** (post–Aug 23) — was D in Aug-7/13 reviews |
| Regime map / hard-exit auto | **Still shadow** |
| IDEALOOP full loops | **Design / shadow** (F/D) |
| Multi-tenant / GHL | **A — planned** |
| Maker path | **Pilot only** |
| Fee tier honesty | **Shipped** (snapshot + dig) |

---

## 5. Ranked recommendations (what to do with this)

### Do **not** treat as “missed alpha”

- Rebuild StochRSI-as-primary from Phase 5 functional.  
- Rebuild Phase 5.1 weekly corr cut as specified.  
- Ship full Phase 4 UI before book is underwritable.  
- Enable DeRisk ladder, Reddit live, auto basket promote, mid-cycle allocator “to print.”

### Worth a **focused** engineering pass (single book)

1. **`max_daily_loss` + corr breaker — PARKED (Brad 2026-08-31).** CF: complexity ≫ return (`reports/MAX_DAILY_LOSS_CORR_BREAKER_CF.md`). No wire / no promote. Optional later honesty-only for the theater knob; not critical path.  
2. ~~Decide fate of `correlation_circuit_breaker`~~ → **PARKED** with max_daily_loss (same CF). Dark/LEGACY.  
3. Keep **regime map / hard-exit** gated until gates in exit docs are met (already product law).  
4. **Refresh `SPECS_CODE_GAP.md`** (TP live, park package, limit-first D, parked daily-loss/corr).  
5. Limit-first D: observe fill rate → Phase E or kill — already in design.

### Product backlog (after book quality)

1. Personalized settings **W3** banner.  
2. SCALING-1000 T0 isolation (registry already sketched) → OAuth → GHL-01.  
3. Trader UI subset of Phase 4 (hold release, status, exits) — not the full 3Commas clone.

---

## 6. Honest limits of this review

- Did not re-read every file under `docs/archive/**`.  
- Did not instrument runtime to prove max_daily_loss never fires (static path search only).  
- Dashboard UX completeness vs Phase 4 wireframes not pixel-audited.  
- Parallel digests (3 subagents, 2026-08-31) cross-checked; deltas folded in §8.

---

## 7. Bottom line

**Almost nothing critical from Phase 4/5 strategy docs is “silently missing” from Phase 6** — it was **replaced**.  

What **is** still missing and **not** superseded:

1. **SaaS surface** (OAuth, GHL runtime, end-user UI, multi-tenant fleet) — documented since Phase 4 / SCALING-1000, still planned.  
2. **A few risk modules** that look complete in tree/config but are **not on the live control plane** (`max_daily_loss` enforcement; correlation breaker).  
3. **Gated product layers** (hard-exit auto, regime map live_apply, mid-cycle, discovery promote, park defaults) — intentional, not omissions.  
4. **Doc debt** — agents still risk implementing LEGACY specs; SSOT hygiene remains a real ops risk.

**Profitability of this book is not blocked by unfinished Phase 4 UI.** It is blocked by expectancy / exits / churn economics (see profitability review) — with the important update that **live trail TP is now on**, so the Aug-13 “TP fully off” P0 is partially closed; **regime-map promote and hard-exit auto** remain the open exit-stack items.

---

## 8. Subagent cross-check delta (2026-08-31)

Three parallel digests (Phase 4 features · Phase 5 features · SPECS Type-A) agreed with §2–§5. Extra items worth recording:

| Item | Origin | Verdict | Note |
|------|--------|---------|------|
| Parallel exit throttle strategies (FIXED / FEE_AWARE / PAIR_SPECIFIC) | GITHUB_PHASE4_TASKS | **SUPERSEDED** | Only in legacy phase4 runners; P6 uses regime map + live trail + exchange SL |
| Compound engine (“profits → top pair”) | PHASE5_BRD | **MISS / low value** | No active compound matcher; capital events + allocator are different design |
| P5 async single-process + `manage_traders` / `trader_registry` | PHASE5_SCALABLE | **MISS (arch not adopted)** | Scaling path is SCALING-1000 epic, not revive phase5_scalable.py |
| `indicators/stochrsi_strategy.py` | P5 | **Orphan module** | Not imported by phase6 runner; Stoch %K may still appear in rsi_cache / SL scorer — not P5 crossover entry |
| OAuth tokens schema (Postgres T0) | P4 OAuth + SCALING | **PARTIAL scaffold** | `db/models` + `test_t0_registry`; no Coinbase OAuth flow in live client |
| WebSocket dash + in-app alert UI | P4 UI | **MISS** | Dash = HTTP poll + TG/Hermes alerts |
| Prometheus Phase 5 metrics | P5 ops | **SUPERSEDED / gone** | No phase6 prometheus path |
| `ReportingAgent` / `UnifiedSignalConsumer` / old MultiPairAnalyzer | old PHASE6.md | **SUPERSEDED** | SignalGenerator + evaluation + allocation |
| Bear profit-take (no short) | FEAT 2026-08-20 | **Shadow only (F/D)** | Post–Aug-7; not a forgotten P4/P5 ship |
| Stand-down filter C | 2026-08-31 research | **Shadow only** | Not a live gate yet |
| Near-stop rebalance race + same-session SL metric | profitability P0 | **DONE** (Aug-13 MASTER/GH#22) | Closed since profitability review |

**No new Type-A bombs** beyond SaaS stack + risk-knob honesty + gated exit promote.
