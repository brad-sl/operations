# USD hold-value contingency policy (sketch)

**Status:** CONTINGENCY / NOT LIVE — research sketch only  
**Frozen draft:** 2026-08-01  
**Owner:** Brad + Crypto-Analyst  
**Evidence:** `data/state/usd_hold_value_consistency_2026-08.json`  
**Related:** `config/regime_cash_policy.json`, `docs/research/BULL_REENTRY_LAYERED_SPEC.md`, REGIME-CASH epic  

---

## Problem

Over the last ~12–18 months (buy-and-hold vs USDT≈USD, Binance daily closes through ~2026-08-01):

| Asset class | 12m | 18m | Notes |
|-------------|-----|-----|--------|
| **PAXG** (tokenized gold) | **+20%** | **+44%** | Only clear inflation-beater; shallow path DD |
| **TRX** | **~+2%** | **+29%** | Only major crypto that roughly held / beat CPI on 18m |
| **USDC/USDT** | ~0% | ~0% | Holds **nominal** USD; loses ~3%/yr real |
| **BNB** | **−22%** | **−15%** | Least-bad large non-stable crypto |
| **BTC** | **−44%** | **−39%** | Still “least bad beta” vs most alts |
| **ETH / SOL / most alts** | **−45% to −90%** | worse | Failed as USD stores this window |

**North star:** better returns **and** less loss.  
Current REGIME-CASH already parks in bear/transition (`usdc_park`, cap $0). It does **not** yet answer:

> When risk-on is wrong for a long stretch, what *else* (if anything) may we hold besides pure USD stable — and what must we never do?

This doc is that contingency sketch. **No live policy edits. No coding required to adopt as operator doctrine.**

---

## Goals

1. **Preserve USD purchasing power** when crypto beta is in a multi-quarter drawdown.  
2. Stay **simple** — few assets, few rules, no new strategy engine.  
3. Plug into existing **REGIME-CASH** + **layered bull re-entry** without replacing them.  
4. Keep **hard sells / Tier-1 exits** on explicit operator OK only (unchanged).  
5. Prefer **platform reliability** over lottery alt bags.

## Non-goals

- Replacing BTC as the **regime timing** asset.  
- Live-adding PAXG/TRX to the rebalance basket without a separate gated trial.  
- Claiming gold/TRX “always” win (this is a **bear/flat multi-quarter** contingency, not a forever allocation).  
- Auto hard-exit of entire book into gold.  
- Yield farming, leverage, or basis trades.

---

## Policy sketch (three sleeves)

Think of book as three sleeves. Only **Sleeve A** is live today. B/C are contingency.

### Sleeve A — Operating cash + gated crypto (LIVE today)

Unchanged REGIME-CASH:

| Regime | Cash posture | New risk |
|--------|--------------|----------|
| **Bear** | Park (`usdc_park`), cap **$0** | No new buys |
| **Transition** | Prefer cash | Cap **$0** effective while knob_map says hold (or policy $50 park — fingerprint live status) |
| **Flat B** | Cautious | Cap **$75**, pair RSI≤55, sent≥0.25 |
| **Bull** | Deploy | Cap **$200**; size-up only with 30d/+15% (not sole timer — see layered re-entry) |

**Dust:** post-SL residual sweep stays on (clean book; no “orphans as positions”).

**Layered bull re-entry** (shadow until promoted): bear veto → breakout+RSI[50–70]@$75 → 30d/+15% size-up@$200 only.

### Sleeve B — Nominal USD hold (default contingency)

**Instrument:** USDC/USD cash (already).  

**When:** Default whenever Sleeve C is off and regime ≠ bull deploy.  

**Why:** Zero path volatility vs gold/crypto; loses only CPI (~3%/yr).  
**Rule:** Do **not** force idle cash into alts to “do something.” Idle USD is a feature in bear/transition.

### Sleeve C — Real-value hedge (CONTINGENCY — not live)

**Purpose:** Optional inflation / deep-risk-off ballast when we expect **many months** of weak crypto beta.

| Rank | Asset | Role | Max sleeve (sketch) | Why |
|------|--------|------|---------------------|-----|
| 1 | **PAXG** (or cash-settled gold proxy if simpler later) | Real USD purchasing-power hedge | **10–20%** of total equity | Only asset in study that clearly beat CPI on both 12m and 18m with milder DD |
| 2 | **TRX** | Optional “least-bad crypto hold” | **0–5%** | Only major crypto that held/beat on 18m; still crypto beta — **secondary** |
| 3 | **BNB** | Watchlist only | **0%** until proven | Best large-cap loser; not a hedge |

**Hard exclusions for Sleeve C:** SOL, most mid/small alts, “narrative” bags, anything without liquid Coinbase (or current venue) spot + working SL path.

**Funding Sleeve C:** Only from **idle cash** (Sleeve B), never by selling core positions without explicit OK. Never by raising crypto rebalance caps.

---

## When Sleeve C may turn ON (contingency triggers)

All of the following (AND) — sketch thresholds, tunable later:

1. **Regime:** detector `bear` **or** `transition` for **≥ 14 consecutive days** (aligns with trend Tier-2 patience; not a one-day flicker).  
2. **BTC damage:** BTC **30d ≤ −10%** (bear veto already) **and** BTC **~12m return ≤ −25%** (deep, not a dip).  
3. **Book state:** crypto sleeve util already low (e.g. holdings &lt; 30% equity) — we are not mid-bag-average-down.  
4. **Operator flag:** `contingency_real_hedge: armed | off` (default **off**). No silent ON.  
5. **Venue ready:** PAXG (or chosen gold proxy) tradeable live, min notional OK, **SL attach + dust sweep** path validated in shadow once before first live fill.

**Size ramp (if ever armed):**

| Step | Action | Cap |
|------|--------|-----|
| C0 | Off | 0% |
| C1 | Shadow log only (“would buy PAXG $X”) | 0% live |
| C2 | First live buy | **$50–100** total PAXG |
| C3 | Only if C2 held ≥14d and regime still bear/transition | up to **10%** equity |
| C4 | Hard ceiling | **20%** equity PAXG; TRX ≤ **5%** if ever allowed |

**TRX:** default **off** even if C armed. Enable only as a separate sub-flag after PAXG path is boring and reliable. TRX is “least bad crypto,” not gold.

---

## When Sleeve C turns OFF (exit contingency)

Any one (OR):

1. Layered **re-entry** fires (breakout + RSI band) **or** detector **bull** / 30d ≥ +15% size-up path.  
2. BTC **30d ≥ +10%** (early thaw probe — reduce hedge, don’t dump crypto rules).  
3. PAXG sleeve **−12% from local peak** (optional soft risk cap — gold can correct).  
4. Operator **disarm**.  
5. Venue/SL failure on PAXG → disarm and stay USDC.

**Exit style:** Prefer **reduce hedge into USDC** over rotating hedge proceeds straight into alt beta. Crypto re-entry stays on **existing** gates only.

---

## What we do **not** change while this is “sketch only”

| Keep as-is | Why |
|------------|-----|
| REGIME-CASH detector + park | Already correct first defense |
| Flat B $75 / bull $200 envelopes | Proven ops surface |
| Layered bull re-entry shadow path | Opportunity timer ≠ gold policy |
| Hard exit `operator_approve` | No auto liquidation surprises |
| No fake prices / no placeholder fills | Trading integrity |
| Dust sweep after SL | Book hygiene |

**Operator doctrine today (no code):**

1. **Bear/transition → cash is success**, not failure.  
2. Do not “get productive” by nibling weak alts.  
3. If multi-month park persists and CPI bite matters, **consider gold (PAXG) contingency** — not SOL “catch-up.”  
4. BTC remains the **weather vane**; gold is optional **ballast**, never the timer.

---

## Easy implementation path (later — not now)

When/if we code, keep it dumb:

1. **Config only** under `regime_cash_policy.json` → `contingency_real_hedge: { enabled, armed, max_pct_paxg, max_pct_trx, arm_rules, disarm_rules }`.  
2. **Status JSON** field: `contingency: { state, would_size_usd, blockers[] }` for dashboard hover.  
3. **Rebalance filter:** if armed and triggers pass, allow a **single** pair `PAXG-USD` buy up to step cap; still blocked if `allow_new_buys` false unless we add explicit `allow_contingency_hedge_buys`.  
4. **SL + dust** on PAXG same as any pair.  
5. **Shadow ≥ 1–2 weeks** before C2.  
6. **Trial type:** `Type:test` on MASTER; promote only if: no ops incidents + does not worsen drawdown vs pure USDC park on the same window.

**Effort guess:** small (config + gate + one pair allowlist) after PAXG is in venue product list and price/SL paths work — not a new strategy rewrite.

---

## Decision table (operator cheat sheet)

| Situation | Do |
|-----------|-----|
| Short bear blip (&lt;14d) | Sleeve A park only (USDC). No gold. |
| Long bear/transition + deep 12m BTC hole + armed | Sleeve B full; Sleeve C1→C2 PAXG only |
| Flat B with gates green | Small crypto rebalance only; **C off** |
| Bull / layered re-entry ON | Disarm C; crypto rules own risk-on |
| Bored of cash | **Still don’t** buy weak alts; arm C only with eyes open |
| Want yield on cash | Out of scope (CeFi/DeFi yield ≠ this policy) |

---

## Open questions (resolve before any code)

1. Is **PAXG-USD** available and liquid enough on the live venue for $50–$500 clips?  
2. Is gold hedge worth ops surface, or is “USDC park + patience” enough given account size?  
3. Tax/lot handling for PAXG vs USDC — any reason to avoid?  
4. Should contingency ever use **BTC** as partial hold (halved beta) instead of gold? (Study says BTC still lost ~40% — gold won; default answer **no**.)  
5. TRX: cultural/venue preference — keep **permanently optional**.

---

## Bottom line

- **Default contingency = USDC park** (already built). That *is* the plan for most of this tape.  
- **Optional upgrade** if park lasts and real value matters: small, gated **PAXG** sleeve; never a junk-alt rotation.  
- **TRX** is a footnote, not a second strategy.  
- **Do not code** until Brad arms the doctrine and venue checks pass.  
- North star check: this policy exists to **lose less purchasing power** in long risk-off — not to chase the next bag.

---

## Evidence fingerprint

- Study as_of: `2026-08-01` (see JSON `as_of`)  
- Source: Binance Vision 1d USDT closes; USDT≈USD  
- Top consistency: PAXG ≫ stables ≫ TRX ≫ BNB ≫ BTC ≫ ETH/alts

## PRD

- **Preserve Mode (product):** `docs/research/PRESERVE_MODE_PRD.md`  
  - Option A formalized as Park → Preserve → Thaw → Deploy  
  - **SL:** crypto sleeve keeps ~3%; ballast does **not** use the same 3% stop  

## Backtest pointer

- Report: `reports/USD_HOLD_CONTINGENCY_BACKTEST_2026-08-01.md`
- JSON: `data/state/usd_hold_contingency_backtest_latest.json`
- Runner: `phase6/research/run_usd_hold_contingency_backtest.py` + refined pass script
- As-of plain English: 18m (2025-01-30→2026-08-01): USDC0 0.0%, USDC4% 6.065%, PAXG BH 44.768% (DD -28.067%), BTC BH -40.065%, static 20% PAXG 8.947% (DD -9.297%), static 25% 11.184% (DD -11.164%), static 50% 22.373% (DD -18.653%). Best doc timed: doc_s7_no12m_w50_bullOnly ret 8.746% hedged 48.09% days. Go/no-go: shadow_static_ballast_first.

## Park regime (live operator policy)

- **Canonical simple park doc:** `docs/research/PARK_REGIME_POLICY.md`
- Micro live sleeve + full Hold product live under `preserve_mode` (see MASTER `PARK-MICRO-PRESERVE-20260802`).

## Canonical matrix

- **Operator decision matrix:** `docs/research/PARK_BALLAST_DECISION_MATRIX.md`
