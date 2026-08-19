# Smart Park — idle cash that still works for you

**Product name (trader-facing):** **Smart Park**  
**Internal FEAT:** `FEAT-PARK-USDC-PAXG-PACKAGE-2026-08`  
**Audience:** New and non-technical crypto traders  
**Status:** Product path built · live options you choose (defaults stay simple and safe)  
**Deep tech:** `PARK_USDC_PAXG_PACKAGE_SPEC.md` · checklist for operators  

---

## The problem most bots ignore

Most trading apps do one of two things when markets get messy:

1. **Keep gambling** — still hunting entries while you’re stressed, or  
2. **Go blank** — dump everything to cash and leave your money **sitting idle** with no plan.

Neither feels like a real money product. You either take more risk than you wanted, or your cash does nothing while you wait.

---

## What Smart Park is (one sentence)

**When it’s not a good time to buy more crypto, Smart Park parks most of your money in calm cash (with optional yield) and, only if you want, a small gold sleeve — then brings crypto risk back only when the platform’s rules say it’s okay.**

That’s the differentiator: **defense with a job**, not “bot always on” and not “cash in a drawer with no story.”

---

## Feature → benefit (plain English)

| What you get | Why it matters to you |
|--------------|------------------------|
| **A clear “pause crypto” mode** | You’re not forced to stay fully invested just because a bot needs something to do. |
| **Cash as the default safe lane** | Most parked money stays as **stable cash** (dollars or USDC — a dollar-like stablecoin on the exchange), ready when opportunities return. |
| **Optional yield on parked cash** | On supported venues, USDC can **earn a small yield at the exchange’s current rate**. We show real rates when we can — we **never invent a fixed “guaranteed %.”** |
| **Optional gold sleeve (PAXG)** | A **small**, optional slice of **tokenized gold** as ballast while you wait — not a second day-trading system. **It moves with gold**, not with meme coins (see below). |
| **You stay in control** | Gold is **opt-in**. Scaling up is **your** choice. Nothing sneaks to a huge gold position overnight. |
| **An emergency brake on gold** | If gold is on, a **deep safety stop** lives on the exchange so a crash path is bounded even if software hiccups. |
| **A plan to come back** | When conditions improve, the platform has an orderly path: calm the gold sleeve if needed, free cash, then allow crypto buys under the usual risk limits. |
| **Honest labeling** | Gold is **not** “safe.” Cash park is **not** a get-rich product. We say that up front. |

---

## How it feels day to day (story)

**Bad week for crypto.**  
The platform stops chasing new risky buys. Your book shifts toward **cash**.

**You prefer cash that can earn a little.**  
You turn on **USDC park** so idle money can sit in USDC and pick up the exchange’s yield (if offered). No need to become a DeFi expert.

**You want a touch of real-world ballast.**  
You optionally add a **tiny gold position** (we start micro-sized on purpose). It’s there to diversify the wait — not to “call the bottom” on Bitcoin.

**Markets look better.**  
Rules open the door for crypto again. Default path: don’t throw gold proceeds straight into random alts; free up cash first, then deploy under caps. You can always override with eyes open.

---

## Three simple buckets (no jargon required)

Think of your account in three jars:

| Jar | Everyday name | What’s in it | Job |
|-----|----------------|--------------|-----|
| **1 · Calm cash** | “Parking lot” | USD or USDC | Safety + dry powder (+ optional yield on USDC) |
| **2 · Gold sleeve** | “Optional ballast” | PAXG (gold on-chain) | Small diversifier while parked — **optional** |
| **3 · Crypto book** | “Active trades” | BTC, ETH, alts | Only when the platform allows new risk |

**Remember this line:**  
**Cash parks. Gold is optional. Crypto waits its turn.**

---

## Does the gold sleeve actually follow real gold?

**Short answer: yes.** One PAXG is built to represent about **one ounce of vaulted gold**. In normal markets it behaves like **gold on the exchange**, not like a random crypto token.

**What we measured (platform study, ~2 years of daily prices + recent hourly):**

| Check | Result (plain English) |
|-------|------------------------|
| Do the **price charts** line up? | Almost perfectly (level correlation ≈ **0.999**) |
| Do they **move together day to day**? | Strongly (daily move correlation ≈ **0.85**) |
| **Hour by hour** (when both markets are open)? | Very tightly (hourly move correlation ≈ **0.97**) |
| Is there a **multi-day lag** (“gold moves, PAXG catches up later”)? | **No.** Best match is **same day / same hour** |
| Typical gap vs gold futures | Often well under **1%**; many days under **0.5%** |

**What that means for you:**  
If gold has a rough day, expect the gold sleeve to feel rough **the same day** — not next week. That’s good for honesty (“this is gold risk”). It’s **not** a free timing toy.

**When a small gap can still appear:** weekends (crypto rails can trade while classic gold is quiet), thin exchange liquidity, or panic demand for “on-chain gold.” Those gaps usually **shrink again**; they are not a reliable multi-day delay.

Full numbers: `reports/PAXG_GOLD_CORRELATION.md`.

---

## “Can I arb gold moves vs PAXG?” (honest answer)

**The idea people hope for:** gold jumps first → wait → buy/sell PAXG before it “catches up” → free money.

**What the data says:** on the timescales we can measure cleanly (**hours and days**), there is **no dependable lag**. Peak correlation is at **lag zero**. So the simple “gold moved, I’ll front-run PAXG’s delayed move” story is **not** a Smart Park edge and is **not** something this platform is built to harvest.

| Approach | Reality check |
|----------|----------------|
| Retail “see GC, scalp PAXG on Coinbase” | Spreads, fees, and slippage often **eat** the tiny leftover gap. Our study shows gaps are usually **small**. |
| Weekend / off-hours PAXG wiggle | Can drift while London/COMEX is closed — then **snap** when gold reopens. Direction is **not** a free gift; you can easily be wrong-footed. |
| True institutional arb (mint/redeem vs vault gold) | Needs **Paxos access**, size, banking, and ops — not a button in a novice trading app. When it works, it **removes** the gap (good for holders), it doesn’t leave a permanent ATM. |
| “Correlation trade” as yield | Holding PAXG **is** the gold exposure. You’re not owed extra return for the token wrapper beyond gold ± a small premium/discount. |

**Platform stance:**  
Smart Park’s gold sleeve is **ballast and honesty**, not an arb desk. We do **not** auto-trade gold/PAXG basis. Trying to turn a micro learning sleeve into a high-frequency arb bot fights the product goal (calm park, small size, deep safety stop).

**If a gap ever looks huge:** treat it as a **warning** (liquidity, venue stress, or data glitch) — not as “easy mode.” Size stays the airbag.

---

## When we turn on option 3 (Cash + yield + tiny gold)

**Intention:** option **3** is the target profile.  
**Not yet:** live **USDC yield park** stays off until the **base trading bot** is no longer the main bleed story.

**Revisit:** scheduled **2026-08-22** (cron: Smart Park #3 revisit) — or sooner if Brad asks.

**Health gates before enable (deposit-adjusted KPIs):**
1. **14D ≥ 0** held for a **solid** stretch (not a single green print after a bad month).  
2. **30D improving** (deep hole shrinking).  
3. **Exit WR** not stuck near pure-loss lottery.  
4. Trend repair not only **Declining** with a steep negative slope.  
5. Gates stay on — no fantasy OPT thaw.

Until then: **USD park + MICRO gold + flat discipline** is the honest live product.

---

## What makes this different from “the other half-dozen bots”

| Typical bot | Smart Park on this platform |
|-------------|-----------------------------|
| Always looking for the next trade | Knows how to **stand down** with a real parked structure |
| Cash = dead weight | Cash can be **productive** (venue yield on USDC when you opt in) |
| Gold ignored or treated like another meme coin | Gold is a **separate, slow sleeve** with hold-first rules and a deep stop |
| Settings buried in YAML / Discord commands | Aimed at **human choices**: park style, gold on/off, release cash hold |
| Hype APY screenshots | **No fake fixed APY** — rate is whatever the venue actually pays |
| “Set and forget until liquidation” | **Micro first**, then scale only if you choose |

Competitors optimize for **activity**. We optimize for **surviving dull and dangerous markets without abandoning the account to pure inertia.**

---

## Choices you’ll see (friendly names)

| Trader choice | Meaning |
|---------------|---------|
| **Simple pause** | Crypto risk off / capped; money mostly in ordinary cash (USD). Easiest default. |
| **Cash + yield** | Same pause, but parked money prefers **USDC** so it can earn the exchange rate when available. |
| **Cash + yield + tiny gold** | Above, plus a **small** gold sleeve you explicitly turn on. |
| **Larger gold (advanced)** | Only after you’re comfortable with the tiny sleeve — **you** scale up; we don’t surprise you. |

Internal profile codes (`off`, `a_only`, `a_plus_b_micro`, …) map to these choices for engineers — traders shouldn’t need those names.

---

## Honest limits (builds trust)

- **Crypto can still fall** on what you already hold. Smart Park mainly governs **new risk** and **how idle capital is structured**.  
- **USDC yield is not guaranteed** and can change or be zero.  
- **Gold can drop a lot** on the way (double-digit path risk is real). Size is your airbag.  
- **PAXG ≈ gold**, same day — not a delayed clone you can easily front-run (see sections above).  
- **Not financial advice.** This is product behavior, not a promise of profit.  
- **Live switches** are opt-in; the platform can ship the feature while your account stays on the simple path until you choose.

---

## Where to go next

| You are… | Read |
|----------|------|
| A trader deciding if this matters | **This page** |
| “Does PAXG really track gold?” / arb myths | This page § gold track + arb · `reports/PAXG_GOLD_CORRELATION.md` |
| Turning it on for real | `PARK_USDC_PAXG_OPERATOR_CHECKLIST.md` |
| Building UI / settings copy | This page § feature-benefit + honest limits |
| Implementing systems | `PARK_USDC_PAXG_PACKAGE_SPEC.md` |
| Doctrine / edge cases | `docs/research/PARK_BALLAST_DECISION_MATRIX.md` |

---

*Product voice v1.1 — 2026-08-07/08. Prefer this language in dashboards, onboarding, and marketing over internal bucket codes. Gold-track study: `reports/PAXG_GOLD_CORRELATION.md`.*
