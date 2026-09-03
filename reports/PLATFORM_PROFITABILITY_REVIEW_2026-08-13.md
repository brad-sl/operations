# Platform review — feature gaps vs getting profitable

**Date:** 2026-08-13  
**Author:** Scotty (Hermes / grok-4.6)  
**Scope:** Phase 6 live book + docs + codebase. Profitability of *this* account first; SaaS/Scaling-1000 second.  
**Not:** a line-by-line audit. Specs↔code matrix already lives in `docs/SPECS_CODE_GAP.md`.  
**Companion:** `docs/SPECS_INDEX.md`, `docs/MASTER_TASK_TRACKING.md` (`P6-SPECS-GAP-BACKLOG-20260807`), `docs/TREND_REPAIR_PLAYBOOK.md`, `docs/EXIT_AUTOMATION.md`.

---

## 0. Plain English

The platform is a **working live trading system** (runner, Coinbase SL, REGIME-CASH, ledger, dashboard KPIs, analyst/OPT loop). It is **not yet a profitable strategy**.

Scoreboard (deposit-adjusted, 2026-08-13):

| Horizon | Number | Read as |
|---------|--------|---------|
| Since go-live (brief) | **−29.3%** | The long scoreboard |
| 30D / health window | **~−8%** | Still declining (slope −0.24%/d) |
| 14D | **+0.13%** | First flatten hint — not recovery |
| 7D / 1D | **−0.7% / −0.1%** | Recent stretch better than window |
| Exit WR | **6/50 = 12%** | Almost all realizing sells are stops |
| Equity | **~$2,439** | ~$1,793 holdings + ~$646 cash; **$460 sticky hold** |
| Util | **74%** vs REGIME-CASH target **65%** | Still over-deployed vs policy |

**North star (Brad / analyst law):** better returns **and** less loss. Platform process > lottery bags. Underwritable bar is **~5%/mo average**, not 20%/mo. 12–15% is a good *month*, not a KPI.

**This review’s thesis:** profitability is blocked by **exit asymmetry + re-entry churn + unvalidated selection**, not by missing SaaS features or another indicator.

---

## 1. What the platform already is (do not rebuild)

These are **shipped and live**. Gaps below assume we keep them.

| Layer | Live truth |
|-------|------------|
| Runner | `phase6.core.phase6_runner` live, 5-min cycles, ARCH-4 rebalance slots |
| Risk | Exchange **3% SL**; `take_profit_pct = null` |
| Regime | Flat = cautious deploy B: cap **$75**, entry RSI≤55 / sent≥0.25, `enforce=true` |
| Capital | Sticky cash hold, 72h SL rebuy block, no force-rebalance on deposit |
| Exits (shadow) | Global shadow TP + regime exit map + hard-exit operator loop — **no live profit-taking** |
| Signals | X 2×/day + free fallback; SignalGenerator BUY/HOLD/SELL (now also dash Status) |
| Observability | Deposit-adj 1D/7D/14D/30D, Exit WR, equity trend, intel brief 2×/day |
| Analyst | Weekly OPT, no auto-promote, Path B + production overlap required |
| Discovery | Funnel + pool cycling + swap CF **shadow only** |

Docs that *are* current SSOT: `SPECS_INDEX`, `REGIME_GATES_AND_ANALYST_LOOP`, `EXIT_AUTOMATION`, `TREND_REPAIR_PLAYBOOK`, `CAPITAL_AND_PORTFOLIO_EVENTS`.  
Docs that are **not** SSOT: `FUNCTIONAL_SPEC.md` (Jun 2026, Reddit 60m, TP as if live), `ARCHITECTURE.md` (Phase 5 paths / old workspace).

---

## 2. Economics of the current book (why it loses)

Evidence: `reports/EXIT_ASYMMETRY_2026-08-12.md`, `/api/performance`, `trend_repair_status.json`, `basket_swap_shadow_counterfactual_latest.json`.

### 2.1 Exit stack is one-sided

30d realizing ledger:

| Reason | n | WR | Sum PnL |
|--------|---|----|---------|
| `stop_loss_exchange` | 39 | 0% | **−$99** |
| `rotation_exchange` | 6 | 100% | +$39 |
| dust / preserve | 10 | ~0 | ~−$1 |
| **All** | 53 | **11%** | **−$61** |

Rotations *do* bank green. Stops dominate count and dollars. There is **no live TP/trail**. Shadow TP has logged thousands of would-fires (`would_fire_count_total` ~9400) — instrumentation, not P&L.

This is the **primary economic gap**. Fees (~tens of dollars / 30d) are secondary.

### 2.2 Re-entry recycles the same losses

After SL: 1 / 5 / 8 rebuys inside 24 / 48 / 72h (30d report). Same-session add-then-SL (RAVE Aug 11, BTC Aug 12) is a **gate miss / race**, not “SL ignored.” Near-stop add-block exists but does not cover rebalance vs open-stop timing.

Sticky **$460 hold** + 72h SL cooldown are correct *less-loss* tools. They do not create winners.

### 2.3 Selection is not a validated edge

Basket swap shadow (as of 2026-08-12):

- Baseline arm 1d mean excess **−4.3%**, 3d **−4.6%**, hit ~25–33%
- Paper sleeve ADD vs stay-on-REMOVE: **−$29** on $100×N
- Decision: **keep_shadow_collecting** (7d N=0). **Do not live-promote.**

OPT weekly winners (e.g. `bear_window_rotation_14d` +1.9% sim) **do not beat production on overlapping real data**. Promotion path = hold.

### 2.4 Book shape vs policy

- Util **74%** vs flat target **65%** — leftover bags, not a broken park switch.
- Open book small green (BTC/LINK/PAXG ~+$36) — path red is **legacy churn + SL bank**, not current MTM.
- Trend-repair diagnosis: `churn_or_legacy_drawdown`. Tier 0 = keep gates. Not thaw.

---

## 3. Feature gaps ranked by profitability (this book)

Gap types match `SPECS_CODE_GAP.md`: **A** spec ahead · **C** gated off · **D** shadow · **ops** behavior hole.

| Pri | Gap | Type | Why it moves P&L | Status / next |
|-----|-----|------|------------------|---------------|
| **P0** | **Live profit-taking is off** | D / C | Banks every −3% and almost never the +6% / trail. Path cannot bend up while only SL realizes. | `P6-EXIT-PROFIT-LIVE-GATES-20260807` **QUEUED**. Regime map ~60d + per-regime episodes + Brad OK. Prefer map over blind global 6%. |
| **P0** | **Same-session / near-stop add** | ops | Rebalance BUY minutes before existing stop = manufactured SL. Highest *new* drag we can still cut without claiming edge. | Isolation exists (`test_isolation_near_stop_add_block`). Need rebalance-path race closed + verify in ledger. |
| **P0** | **Post-SL recycle** | C / ops | 72h hold is on; still 8 rebuys in 72h over 30d (some pre-repair). Confirm code path covers `stop_loss_exchange` *and* add-into-open-stop. | Keep hold-cash true. Do not shorten cooldown to “catch bounce.” |
| **P1** | **Hard-exit still human-loop** | D | RSI-overbought / weak-sent sells stay pending. Brief already flags AVAX SELL. | `P6-HARD-EXIT-AUTO-APPLY-GATES-20260807`. T1 ≥7d/≥5 decisions, then one knob flip. Not a chat desk. |
| **P1** | **Basket / discovery unvalidated** | D | Live promote of ADD/REMOVE would have *lost* vs stay-put on the short tape. | Shadow CF + parallel arms. Broad-brush first: beat `control_no_swap`. No live swaps. |
| **P1** | **Util 74% vs 65% under flat** | ops | Extra beta while policy says cautious. Not a new feature — inventory / no-add until util ≤ target. | Tier 1 glide is **draft only**. SELLs allowed; no lottery trims. |
| **P2** | Mid-cycle allocator | C | Explains “good score, no buy” between slots. Enabling increases churn risk. | `P6-MID-CYCLE-ALLOCATOR-EVAL-20260807` = **study first**. Default stay off until exit stack is less one-sided. |
| **P2** | SignalGenerator vs DynamicRSI 60/40 | docs / UI | Dash Status was the wide 30/70 blend (all HOLD). Brief uses SG. | **Fixed 2026-08-13** — Status = `SignalGenerator`. Still not an order. |
| **P3** | Personalized settings W3+ (banner UI) | A | Product completeness; does not change this book’s expectancy. | W1+W2 shipped (API + `trader_accounts`). W3 banner optional. |
| **P3** | USDC+PAXG park package live | C | W0 shipped, **LIVE OFF**. Capital preservation, not alpha. | Enable only on Brad OK + checklist. Smart Park #3 revisit 2026-08-22. |
| **P4** | Scaling-1000 / GHL / multi-tenant | A | Monetizes *if* the engine is honest and not a −29% showcase. | Do **not** scale a losing book. Runtime slice stays queued. |
| **P4** | SSOT doc hygiene | E | `FUNCTIONAL_SPEC` / `ARCHITECTURE` still read like TP-live + Reddit-on. Agents implement the wrong past. | `P6-SSOT-DOC-HYGIENE-20260807`. |

### Explicit non-goals (do not open as “make us profitable”)

- Another indicator mashup / combo-fish (MACD×RSI×ATR already **dropped** on long WF).
- Live Reddit / Apify.
- OPT promote from Path A or non-overlapping calendars.
- Live TP **this session** without regime-map gates.
- `enforce: false` thaw.
- DeRisk ladder ON.
- 20%/mo average as a design target (fantasy, not a KPI).

---

## 4. Strategic design suggestions (how to get profitable)

Ordered. Each is a **design choice**, not a promise of 5%/mo.

### 4.1 Treat the product as an **exit + capital machine**, not a signal machine

Signals (RSI + X sentiment + SG) already produce BUY/HOLD/SELL. The book loses because **execution only honors the left tail** (SL).

**Design:** one user-facing exit policy per regime (already sketched in `regime_exit_policy_map.json`):

| Regime | Exit idea (research, not live flip) |
|--------|--------------------------------------|
| Bull / flat | TP ~5–6% class + trail/BE; SL stays 3% |
| Bear | Ride / SL; do not scalp TP that cuts survivors |

Promote **one knob** (`take_profit.mode=live` *or* map `live_apply`) after: ≥60d shadow collection **or** enough per-regime episodes, offline path rescue-rate, Brad OK. Weekly mute of would-fire spam stays.

### 4.2 Make “do nothing” the default trade

`control_no_swap` is the right benchmark for basket work. Mid-cycle allocator default **off**. Rebalance cap stays **$75** under flat. Min trade already exists — raise it if small rotates persist.

**Design rule:** a cycle with Executed=0 under park/gates is **success**, not a dead runner.

### 4.3 Close the manufactured-loss loop before hunting alpha

Three concrete code/product slices:

1. **Rebalance must not add to a pair with a live stop inside X%** (and must not buy seconds before that stop can fill).  
2. **SL fill → cash hold + 72h** must be visible on dash and complete (no reason-string miss).  
3. **Same-session BUY+SL** should be a first-class metric on the intel brief (count + pairs), not a screenshot forensics job.

Until (1)–(3) are boring, new entries are just more SL inventory.

### 4.4 Selection: beat stay-put, then refine

Current discovery scores (momentum / pump) **picked worse names** on the short shadow tape (RAVE −18% excess). Parallel arms (`anti_pump`, `risk_adj_mom`, `rel_btc_stable`) exist but have **N≈0** matured.

**Design:** keep shadow 2×/day. Kill an arm if 7d N≥8 and mean excess ≤0 with hit &lt;45%. Only then talk live promote. Quality (fees, SL path) is phase 2.

### 4.5 Analyst stays the creative loop; runner stays dumb gates

Do not merge OPT winners into live because a sim week is green. Path: OPT → board → MASTER → shadow → `live_param_audit` + overlap → **operator apply**. Confidence 0.74 &lt; 0.85 is a **correct** block.

### 4.6 Product (SaaS) after the book is underwritable

Scaling-1000 / GHL / personalized settings are real product gaps. They are **not** the path to this account’s first green 30D. Shipping a multi-tenant wrapper around a −29% go-live path is a GTM liability (claims policy already forbids personal P&L in funnels — keep that).

Sequence: **less loss on Brad-primary → honest 14D/30D flatten → then T0 isolation slice.** Smart Park / USDC stay optional ballast, not a yield story.

### 4.7 Documentation as a risk control

Agents still trip on Jun-era specs (TP live, Reddit cadence, old paths). Banner or archive `FUNCTIONAL_SPEC.md` / `ARCHITECTURE.md` so the next session does not “restore take_profit_pct=5.”

---

## 5. Suggested 90-day path (this book)

| Window | Do | Do not |
|--------|----|--------|
| **Now (T0)** | Keep REGIME-CASH enforce; keep $460 hold until you say Release; fix near-stop/rebalance race; brief metric for same-session SL; continue shadow TP + regime map + basket CF | Live TP, live swaps, mid-cycle on, OPT promote |
| **~2–4 weeks** | Enough shadow TP / hard-exit decisions to score; util glide toward 65% via allowed SELLs only if inventory is the leftover (not lottery) | Thaw cap to $150 because 14D ticked green |
| **~4–8 weeks** | If regime-map episodes + path study still say TP rescues SL-only path → **one** live profit-exit flip (prefer map, not global) | Flip and forget; no auto-promote |
| **~8–12 weeks** | Re-score basket arms at 7d N≥8. Only then consider one shadow-validated swap rule | Batch-promote discovery |
| **After flatten** | Personalized settings W3, park package enable, Scaling T0 — as *product*, not as P&L rescue | Market a 1,000-trader SaaS on an unfixed exit stack |

Success for the next month is **not** +5%. It is: Exit WR up (fewer SL-only realizes), same-session add-SL → 0, 14D not a new bleed, shadow gates still honest.

---

## 6. Doc / code map (where to work)

| Concern | Code / config | Spec / runbook |
|---------|---------------|----------------|
| Live runner / ARCH-4 | `phase6/core/phase6_runner.py`, `evaluation.py`, `signal_generator.py` | `docs/REGIME_GATES_AND_ANALYST_LOOP.md` |
| Exits | `config/exit_automation.json`, `shadow_tp.py`, `regime_exit_shadow.py` | `docs/EXIT_AUTOMATION.md`, `docs/REGIME_EXIT_POLICY_MAP.md` |
| SL / rebuy | `stop_loss_*.py`, `capital_controls.py`, `trading_config_phase6.json` | `docs/CAPITAL_AND_PORTFOLIO_EVENTS.md` |
| Regime cash | `regime_cash_policy.py` + JSON | `docs/epics/REGIME_CASH_EPIC.md` |
| Trend / KPIs | `dashboard_serve_helpers.py`, `trend_repair.py` | `docs/TREND_REPAIR_PLAYBOOK.md` |
| Discovery | `pair_discovery.py`, `basket_swap_shadow_cf.py` | MASTER `PAIR-DISCOVERY-FUNNEL-001`, `POOL-CYCLING-001` |
| Specs vs code | — | `docs/SPECS_CODE_GAP.md`, `docs/SPECS_INDEX.md` |
| SaaS | mostly plans | `docs/epics/SCALING-1000_EPIC.md` |

---

## 7. What this review is not claiming

- That flipping live TP **will** print 5%/mo. It removes a known *negative* expectancy (bank reds only). Rescue rate is the offline test; live is still a gate.
- That SignalGenerator BUY is an edge. It is a **shared language** for brief + dash. Allocator still sits behind regime/cap/hold.
- That the 14D +0.13% is a turn. Slope is still negative. 14d stabilize gate is **≥14d**, not one print.

---

## 8. Recommended next concrete tickets (if Brad OK)

1. **`P6-NEAR-STOP-REBALANCE-RACE-20260813`** — OPEN. Handoff: `handoffs/Handoff_P6_NEAR_STOP_REBALANCE_RACE_20260813.md`.  
2. **`P6-SAME-SESSION-SL-METRIC-20260813`** — OPEN. Handoff: `handoffs/Handoff_P6_SAME_SESSION_SL_METRIC_20260813.md`.  
3. Keep collecting **regime exit map** + **basket CF**; no promote.  
4. Hygiene: banner on `docs/FUNCTIONAL_SPEC.md` / `docs/ARCHITECTURE.md` → LEGACY (child of `P6-SSOT-DOC-HYGIENE`).

Do **not** open “new entry indicator” or “enable mid-cycle to deploy the $460” as profitability work.
