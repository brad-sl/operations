# PRD — Preserve Mode (Safety sleeve)

**Status:** DRAFT PRD — not live · not coded  
**Date:** 2026-08-01 · **Revised:** 2026-08-02 (P0 review patches + plain English)  
**Owner:** Brad · Crypto-Analyst / platform  
**Evidence:**  
- `reports/USD_HOLD_CONTINGENCY_BACKTEST_2026-08-01.md`  
- `docs/research/USD_HOLD_VALUE_CONTINGENCY_POLICY.md`  
- `data/state/paxg_drawdown_anatomy.json`  
- `reports/PRESERVE_MODE_PRD_FRONTIER_REVIEW.md` (adversarial; patches below close its P0s)  
**Depends on:** REGIME-CASH, layered bull re-entry (shadow), SL + dust paths  
**Doctrine:** Truth-based — no wishful “gold is smooth.” Shadow only after venue probe + this PRD’s freezes.  

**Planned task (blocked on fundamentals):** `PRESERVE-FUNDAMENTALS-GATE-20260802`  
- MASTER: `docs/MASTER_TASK_TRACKING.md`  
- Plan: `.hermes/plans/2026-08-01_222028-preserve-fundamentals-gate.md`  
- Rule: **no live Preserve** until G1 venue probe → G2a Hold economics → G3 Hold-only spec + Brad OK.

---

## 0. Plain English — what we decided and why it matters

Read this section first. Jargon later is only implementing these ideas.

### What Preserve is trying to do

When crypto looks bad, the bot already **parks in USDC** (smart).  
Problem: sitting only in dollars feels useless, and people get tempted to nibble bad alts.  
Preserve lets a **slice of the account** sit in **tokenized gold (PAXG)** so “doing nothing in crypto” isn’t only dead cash — **without** turning gold into another day-trading bot.

### The big fork (this was the #1 review issue)

There are **two different products** hiding under one name:

| Profile | Plain meaning | Default? |
|---------|---------------|----------|
| **Preserve-Hold** | Buy ~20% gold, **mostly leave it alone**. Only a **very deep** emergency stop on the exchange. Bot may **block buying more** after a medium dip. | **YES — default** |
| **Preserve-DeRisk** | Same 20% start, but **automatically sell pieces** of gold as it falls (−12%, then −18%, then flatten). Caps pain earlier; can **sell gold near the bottom** of a big gold crash. | Opt-in only |

**Why this matters:**  
Our own data says gold once fell about **−28%** from peak (2026). The old draft’s “final stop at −26%” would have **sold essentially all the gold in that crash** — locking in the loss and missing any bounce. That’s not “ballast”; that’s “forced exit at max pain.”

**Frozen default:** ship thinking and future code as **Hold** first. DeRisk is a named optional profile, not the silent meaning of Preserve.

### What “exchange stops” means (bot can be dead)

We place **sell-stop orders on Coinbase** when Preserve turns on.  
If our bot crashes, Coinbase can still sell per those orders.  
A Telegram warning alone is **not** safety.

**But:** we must **prove** Coinbase allows the order shape we want (see venue probe). Until proven, we don’t claim “bot-down safe” for multi-step sells.

### What the backtest did *not* prove

The research that said “20% gold is good” assumed you **held** the gold.  
It did **not** simulate selling at −12 / −18 / −26.  
So: **static hold ≠ DeRisk ladder.** We must not use the +8.9% figure as proof DeRisk works.

### Six P0 fixes (plain language)

| # | Problem in plain English | What we freeze |
|---|--------------------------|----------------|
| **1** | Final stop too tight vs worst gold crash | **Hold:** emergency stop only around **−32%** (past the −28% worst). **DeRisk:** if used, S3 at **−32%** not −26%; accept you may still sell deep. |
| **2** | Backtest ≠ ladder product | Success checks must include a **ladder path test** on 2022 and 2026 gold crashes before promoting DeRisk. Hold can lean on static backtest. |
| **3** | Maybe Coinbase won’t allow 3 stops at once | **Venue probe first.** Fallbacks A/B/C below. No “armed” until real orders exist. |
| **4** | Crypto “cancel all stops” might wipe gold stops | Gold stops are a **separate sleeve**. Crypto panic cancel **must not** delete Preserve orders (or must immediately put them back). |
| **5** | “20% of equity” unclear → bot might buy more gold when crypto crashes | Define equity; **never buy more gold** just because crypto MTM fell. After any de-risk or block: **no top-ups** until human re-arm. |
| **6** | Arming gold while still full of alts = double pain | **Default:** only arm Preserve when crypto sleeve is **already parked** (util at park / flat). No “long alts + long gold” by accident. |

### Ugly-path example (honesty)

Account **$10,000**. Preserve-Hold **20%** → about **$2,000** PAXG, **$8,000** USDC.

If gold falls **−28%** and you **hold** (default profile):  
- Gold sleeve ≈ **−$560**  
- Whole account ≈ **−5.6%** from gold alone  
- You still own the gold (can recover if gold recovers)

If you used **old DeRisk ladder** and stages all filled near their triggers into that hole:  
- You **sold** most gold on the way down  
- Losses become **realized**  
- If gold later recovers, you may be stuck in USDC unless someone re-arms  

That contrast is why **Hold is default**.

### What you’re *not* getting

- Not risk-free  
- Not a stablecoin  
- Not guaranteed to beat inflation every year  
- Not proven to beat USDC *with interest* by a wide margin once fees/stops exist  
- Main win may be **behavior**: less urge to buy junk alts while parked  

---

## 1. Problem

Long risk-off is correctly handled today by **USDC park**, but:

- Nominal cash loses ~CPI in real terms.  
- Users feel “the bot is doing nothing” and may override into weak alts.  
- No first-class **capital-preservation mode** separate from the trading sleeve.  
- A bad Preserve design could add a **new** failure: UI says “protected” while stops were cancelled, or gold is **force-sold at the bottom**.

## 2. One-liner

**Preserve Mode** holds a small, static **real-value ballast** (default PAXG) beside USDC while the **crypto opportunity sleeve** stays regime-gated — so park is not only dead dollars, without turning gold into a second day-trading strategy.

## 3. Goals / non-goals

| Goals | Non-goals |
|-------|-----------|
| First-class safety mode in capital architecture | Gold “alpha” / discretionary macro fund |
| Limit *crypto* drawdown behavior; modest real ballast | Guaranteed beat of USDC+APY every window |
| Sleeve-isolated PnL vs trading sleeve | Auto hard-liquidation of whole book into gold |
| Tenant profiles later (SCALING) | Same 3% crypto SL on ballast |
| Shadow → opt-in → conservative default | Live policy edits without gates |
| Design for measured gold path DD (~−15% to −30%) | Pretending PAXG ≈ cash |
| Exchange-backed protection when bot is down | Notify-only “safety” |
| Default profile **holds** ballast through severe gold DD | Silently shipping aggressive stage sells as the only mode |

**North star:** returns **and** less loss · platform reliability > bag lottery.  
**Behavioral north star:** fewer manual overrides into weak alts during park.

## 4. User / tenant value

| Persona | What they get |
|---------|----------------|
| Solo operator (Brad) | Named mode, clear arm/disarm, less alt-nibble temptation |
| Future tenants | `capital_first` / `balanced` / `aggressive` packs |
| Dashboard user | One status line: Preserve % · profile (Hold/DeRisk) · ladder · cash · crypto sleeve |

**Positioning (internal):** differentiator = *regime-native capital modes* + *honest sleeves* + *exchange-backed rules*, not “we hold gold.”

## 5. Mode model (states)

```
PARK (USDC)  →  PRESERVE (USDC + ballast)  →  THAW  →  DEPLOY (crypto sleeve)
```

| Mode | Crypto sleeve | Preserve sleeve | Who arms |
|------|---------------|-----------------|----------|
| **PARK** | Cap $0 / park | 0% ballast | REGIME-CASH bear/transition (existing) |
| **PRESERVE** | **Must already be parked** to arm (default) | Target **B%** ballast (default **20%** PAXG), rest USDC | Operator flag **or** auto-**offer** after bear/transition ≥ **14d** |
| **THAW** | Layered re-entry / flat B path | Hold or **trim** ballast per policy | Existing crypto gates |
| **DEPLOY** | Bull / size-up caps | Default **trim toward 0%** (config hold 10% later) | Existing bull path |

### Hard rules

1. Preserve % is a **ballast ceiling**, never raises crypto rebalance caps.  
2. Ballast buys **do not** consume opportunity / `rebalance_cap_usd`.  
3. Funding: **idle cash only** — never silently sell crypto inventory to buy gold.  
4. Max ballast **30%** product hard ceiling (profiles: 10 / 20 / 30).  
5. Asset allowlist v1: **PAXG only**.  
6. **Arm gate (default):** crypto sleeve util already at park / flat (no large leftover alt book). Exception only with explicit operator override flag `allow_preserve_with_crypto_util=true` (default **false**).  
7. **No naked arm:** protection orders placed+verified (per profile) or arm fails.  
8. **No ghost arm:** if protection is later cancelled by non-Preserve code, state → **fault** + attempt restore or flatten policy (never green “armed” while naked).

## 6. Profiles — Hold vs DeRisk (frozen)

### 6.0 Purpose language (accurate)

| | Crypto sleeve | Preserve ballast |
|--|---------------|------------------|
| Job | Cut losing **trades** fast | Hold **small real ballast**; limit **account** damage from gold via **size**, not via 3% stops |
| 3% exchange SL | Yes | **Never** |
| Default protection | Adaptive ~3% SL | **Hold profile** emergency stop (deep) + no top-ups under stress |

### 6.1 Preserve-Hold (DEFAULT)

**Intent:** Own gold through normal and severe gold drawdowns; account damage limited by **20% size**.

| Control | Setting |
|---------|---------|
| Target | **20%** PAXG / **80%** USDC |
| Buy more after dips | **No** once `adds_blocked` or after any protective fill |
| Exchange resting orders | **One** deep protective sell (**E1**) for ~**98%** of ballast base (`attach_safety_ratio=0.98`) |
| E1 trigger | **−32%** from ref (past measured worst path **−28.1%**) |
| E1 order type | Prefer **stop-market** if venue allows; else stop-limit with **wide** buffer + escalate path |
| Bot-only soft | At **−12%** from ref: set `adds_blocked=true` (persist), notify after — **no forced sell** |
| Dust | Sweep residual after E1 or disarm |
| When bot dead | E1 still on Coinbase |

**Implication:** In a 2026-style −28% gold path, Hold **keeps** gold (unless something worse than −32% hits). Book feels ~−5.6% from the sleeve; gold can still recover inside the position.

### 6.2 Preserve-DeRisk (OPT-IN only)

**Intent:** Automatically reduce gold as it falls hard — **accept realizing losses** to cut a left tail.

| Stage | Trigger from ref | Sell fraction of **original** attachable base | Meaning |
|-------|------------------|-----------------------------------------------|---------|
| S1 | **−12%** | **25%** | First cut; expect this in rough gold years |
| S2 | **−18%** | **35%** | Serious de-risk |
| S3 | **−32%** | **38%** (~98% with dust) | Flatten remaining — **beyond** measured −28% worst so we don’t target “exact max pain” |

**Implication:** You may sell a lot of gold **before** a bounce. Do **not** advertise DeRisk with static-hold backtest returns. Requires venue multi-stop **or** documented fallback B/C.

### 6.3 Ref price

- `arm_vwap` = average buy price when building ballast (always kept).  
- `hwm` = high price since arm (for trailing).  
- **v1 default ref for stops: `arm_vwap` only** (simpler, auditable).  
- **HWM trail up-only = v1.1** (optional later). When used: persist last ref to disk + order metadata; never invent HWM from “current price” on restart alone.

### 6.4 Venue probe (blocking — before claiming bot-down safety)

Probe live/sandbox **before** implementation beyond stubs:

| Result | Product shape |
|--------|----------------|
| **A** — ≥2–3 concurrent stop sells on PAXG | Hold uses E1; DeRisk may use S1–S3 |
| **B** — only one stop | Hold E1 OK; DeRisk = E1/S3 only on exchange + **document** that mid stages need bot (resilience downgrade) or disable DeRisk |
| **C** — stops unreliable on PAXG | **No Preserve live**; USDC park only until solved |

### 6.5 Order / bot rules (both profiles)

1. **Arm transaction:** place all required legs **or** cancel partial + arm **failed**.  
2. **After any Preserve sell fill:** `adds_blocked=true` (persisted); never top up to target until human re-arm + cooldown (**72h** after full flatten).  
3. **After partial fill:** resize remaining open legs so total sells ≤ inventory (no oversell).  
4. **Deploy / disarm order of operations:**  
   a) Cancel Preserve protective orders  
   b) Market/limit sell residual PAXG if policy says trim  
   c) Clear registry + flags  
5. **Sleeve blast radius:** every cancel/suspend protective path is **sleeve-aware**. Crypto suspend **must not** strip `sleeve=preserve` orders (integration test required).  
6. **Notify** only reports what already happened or fault states — never the primary valve.  
7. **Time-under-water (Hold):** optional bot reminder if ≤−12% for 7d; **no second sell** that doubles with exchange. DeRisk: time-under-water must not double-sell S1.  
8. **Min notional:** if ballast **&lt; $500** (config), collapse to **single E1/S3 only** (fractions would be dust/min-size broken).  
9. **Integrity (basis):** if PAXG vs external XAU proxy diverges beyond config for sustained window → fault + block adds; human decision to flatten (multi-tenant: raise priority).

## 6A. PAXG volatility reality (truth box — frozen inputs)

**Source:** Binance Vision `PAXGUSDT` daily → `data/state/paxg_drawdown_anatomy.json`  
**Sample:** 2021-07-05 → 2026-08-02 (~1855 sessions).

| Fact | Measured |
|------|----------|
| Long-horizon return | **~+123% to +126%** |
| Median dip (episodes &lt; −1%) | **~−3.8%** · p90 **~−8.2%** |
| Worst path DD | **−28.1%** (2026-01-28 → 2026-07-16, **still open** at anatomy date) |
| Prior deep episode | **−21.1%** (2022), long recovery |
| ~3m path max DD | **~−16%** |

**Design consequences**

1. No 3% SL on gold.  
2. −12% = common enough in rough years → **block adds** (Hold) or **S1** (DeRisk), not “anomaly only.”  
3. Risk envelope for copy/tests: **−15% to −30%** asset path DD.  
4. **20% size** is the first airbag (~−5.6% book on −28% gold if held).  
5. Emergency flatten stop sits at **−32%** (Hold E1 / DeRisk S3) — **past** measured worst, not aimed at −26%.  
6. Sleeve PnL split mandatory.  
7. UI: ballast / Preserve — never risk-free / stablecoin alternative.

**Non-claims:** past return ≠ future; static backtest ≠ DeRisk; PAXG has venue/issuer risk on top of metal.

## 7. Entry / exit

### Arm

- Operator: `preserve.enabled=true`, `profile=hold|derisk`, `target_pct=0.20`.  
- Auto-**offer** (notify) when bear|transition ≥ 14d **and** crypto already parked — v1 does **not** auto-arm.  
- **Arm date warning:** if gold is already in a deep open drawdown vs recent multi-month peak, UI warns: “You may be buying after a crash; backtest entry was not this path.”

### Build

- Buy PAXG with USDC until ballast_nav / **preserve_equity_base** ≈ target (± `band_pct` 2%).  
- **No** BTC-timed entry required for Hold.

### Equity definition (frozen)

`preserve_equity_base` =  
**USDC cash balances available to the bot + MTM of Preserve PAXG only**  

**Exclude:** crypto opportunity inventory MTM, open crypto orders collateral quirks we can’t free, external wallets.

**Implication:** Crypto crashing does **not** make the bot think “gold % is too low → buy gold.”  
Crypto ripping does **not** force gold trim except via **Deploy/Thaw policy**.

### Rebalance rules

- Top-up toward target only if: armed, **not** `adds_blocked`, under target by &gt; band, cash available, profile allows.  
- Never top-up because crypto MTM moved.  
- Drift from gold MTM alone: allow under/over within band; don’t chase.

### Exit / trim

- **Hold risk-off:** only E1 (−32%) or operator disarm / Deploy trim.  
- **DeRisk risk-off:** S1–S3 as table.  
- **Deploy / bull / size-up:** cancel protection → trim ballast to `on_deploy_target_pct` (default **0**).  
- **Not** on `flat_b` alone (twitchy in backtests).

## 8. Accounting & UI

- Sleeves: `sleeve=crypto` vs `sleeve=preserve`.  
- KPI: profile · target% · actual% · PAXG $ · uPnL · **protection status** (E1 or S1/S2/S3) · ref · `adds_blocked` · armed/fault.  
- Hover truth: “Gold can fall ~15–30%; at 20% that is roughly mid-single-digit account impact if held. Not cash.”  
- Forbidden UI strings: risk-free, stable, can’t dump, guaranteed CPI, FDIC.  
- Trades: `preserve_buy` / `preserve_stage_*` / `preserve_e1` / `preserve_trim`.  
- Alerts: fills after fact; **fault if naked while armed**; leg repair failures.

## 9. Config sketch (future — do not apply live)

```json
"preserve_mode": {
  "enabled": false,
  "armed": false,
  "profile": "hold",
  "target_pct": 0.20,
  "max_pct": 0.30,
  "asset": "PAXG-USD",
  "band_pct": 0.02,
  "preserve_equity_base": "cash_plus_preserve_mtm",
  "allow_preserve_with_crypto_util": false,
  "auto_offer_after_park_days": 14,
  "auto_arm": false,
  "on_deploy_target_pct": 0.0,
  "min_ballast_notional_usd": 500,
  "attach_safety_ratio": 0.98,
  "adds_blocked": false,
  "rearm_cooldown_hours": 72,
  "exchange_sl_crypto_style_3pct": false,
  "rely_on_notify_only": false,
  "consume_rebalance_cap": false,
  "ref_mode": "arm_vwap",
  "trail_hwm": false,
  "hold": {
    "e1_dd_pct": -0.32,
    "e1_order_style": "stop_market_preferred",
    "soft_adds_block_dd_pct": -0.12
  },
  "derisk": {
    "enabled": false,
    "stages": [
      {"id": "S1", "dd_pct": -0.12, "qty_frac_of_original": 0.25},
      {"id": "S2", "dd_pct": -0.18, "qty_frac_of_original": 0.35},
      {"id": "S3", "dd_pct": -0.32, "qty_frac_of_original": 0.38}
    ],
    "limit_buffer_pct": 0.006,
    "s3_order_style": "stop_market_preferred"
  },
  "venue_probe_result": null
}
```

## 10. Success metrics

| Metric | Gate |
|--------|------|
| Ops | No crypto buys from Preserve path; sleeve tags correct |
| Resilience | Kill-bot after successful arm: protection still on exchange |
| Blast radius | Crypto suspend/cancel_all test **leaves** Preserve legs (or restores) |
| Hold economics | Static 20% path tests OK; ugly −28% hold path documented |
| DeRisk economics | **Separate** ladder backtest on 2022 + 2026 paths before enable |
| Honesty | Crypto PnL ≠ gold MTM; no forbidden UI strings |
| Promote | Venue probe A/B/C recorded → shadow ≥ 14d → audit → operator apply |

## 11. MVP scope vs later

| MVP | Later |
|-----|--------|
| **Hold only** + E1 deep stop | DeRisk profile enable |
| Venue probe + kill-bot test | HWM trail |
| Equity base + arm gate + adds_blocked persist | Auto-arm |
| Sleeve-safe cancel paths | USDC yield on cash leg |
| Manual arm, 20%, $500+ min notional | Profiles 10/20/30, multi-tenant packs |
| Ugly-path + static metrics | Timed 20→50 overlay (still discouraged) |

## 12. Open questions (remaining)

1. Coinbase PAXG-USD: liquidity + stop-market availability?  
2. Venue probe outcome A/B/C?  
3. Deploy default trim 0% vs hold 10%? (**PRD default 0%** until changed)  
4. Tax lot messaging for solo vs tenants?  
5. XAU basis feed choice for integrity check?  
6. Exact park util threshold for arm gate (pair-level dust exceptions)?

## 13. Go / no-go

| Call | |
|------|--|
| **Product** | Yes — Preserve as mode beside REGIME-CASH |
| **Default profile** | **Hold** (not DeRisk) |
| **SL** | Not crypto 3%; Hold **E1 −32%** on exchange; DeRisk optional staged |
| **Notify** | Secondary only |
| **Code now** | No — venue probe + shadow design first |
| **Review status** | P0s from `PRESERVE_MODE_PRD_FRONTIER_REVIEW.md` incorporated here |

---

## 14. One-page summary

Preserve = optional **~20% PAXG** beside USDC while crypto is parked.  

**Default = Hold:** size limits pain; **one deep Coinbase stop (~−32%)**; block buying more after medium dips; **do not** stage-sell gold through a normal severe crash.  

**Optional = DeRisk:** staged sells −12 / −18 / −32 — may lock losses; needs its own proof.  

Crypto keeps ~3% SL. Gold never uses 3% SL.  

No arm without live exchange protection. Crypto cancel-all must not strip gold stops.  
Don’t buy gold just because alts crashed. Don’t arm on top of a full alt book by default.  

Static backtest supports Hold; it does **not** automatically support DeRisk.  
Truth in UI. Shadow after venue probe.

---

## 15. Glossary (shorthand → plain English)

| Shorthand | Meaning |
|-----------|---------|
| **Ballast** | Small hold (gold) meant to sit there, not be traded every day |
| **Sleeve** | Separate bucket of money/rules (crypto vs Preserve) so we don’t mix scorecards |
| **Arm** | Turn Preserve on (buy gold + place protection) |
| **Naked arm** | Claiming Protect/Preserve on while **no** exchange stop exists — forbidden |
| **adds_blocked** | Bot is forbidden from buying more gold until a human re-arms |
| **HWM** | Highest price since arm (“high-water mark”) |
| **Ref** | Price the stop % is measured from (v1 = average buy price) |
| **E1** | Hold’s single emergency stop |
| **S1/S2/S3** | DeRisk staged partial sells |
| **Venue probe** | Live test: does Coinbase actually accept our stop orders on PAXG? |
| **Kill-bot test** | Turn our bot off; confirm exchange stops still there |
| **Blast radius** | One “cancel stops” feature accidentally wiping the *other* sleeve’s stops |
| **Util** | How much of the account is still in crypto positions |
| **Realized vs paper loss** | Sold = locked in; still holding = loss may recover if price recovers |
| **P0** | Must fix before building for real |
