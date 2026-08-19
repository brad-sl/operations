# SCALING-1000 Marketing / GTM Plan

**Epic:** `docs/epics/SCALING-1000_EPIC.md`  
**Handoff:** `handoffs/scaling/Handoff_SCALING_1000_PLAN_PACK_20260716.md`  
**Date:** 2026-07-16  
**Owner:** Marketing Strategist (MKT-01)  
**Status:** Plan only — no live ad spend, no invented performance claims  
**Working product name:** *ARCH Automation* (placeholder until Brad sign-off)  
**Brand decision pack:** `docs/marketing/brand/BRAND_DECISION_PACK.md` (PHASE-A-01 / t_cff262a8) — recommended lock: ARCH Automation + arch-automation.com + support@; **not purchased / not public yet**

---

## 0. Executive summary

ARCH Automation is a **multi-trader SaaS shell + automation access** product: GoHighLevel owns funnels, billing, CRM, and lifecycle comms; the trading engine owns Coinbase Advanced execution, risk, and OAuth tokens. Customers pay for **software and managed automation access** on **their own Coinbase accounts**. We never custody crypto, never ask traders to paste API keys into the CRM, and never market guaranteed returns.

**90-day pilot north star:** prove a clean commercial loop for a **small closed cohort** (invite-only → paid → OAuth → green runner status) while Brad’s single-account Phase 6 live stack stays untouched. Paid acquisition and broad organic content scale only after T1 exit criteria (end-to-end pay → OAuth → health in GHL within 24h).

**What this plan is:** positioning, ICP/tiers, funnel, **product** online marketing channels (with phase budgets/time), competitor research guide, offer narrative, asset list, metrics, 90-day GTM sequence, and risk controls.  
**What this plan is not:** multi-tenant runner implementation; invented ad ROAS/P&L; client SEO/SEM consultancy work for third-party businesses (separate project — see `docs/PROJECT_BOUNDARY.md`).

---

## 1. Positioning

### 1.1 Category and one-liner

| Layer | Statement |
|-------|-----------|
| **Category** | Coinbase Advanced portfolio automation software (SaaS subscription) |
| **One-liner** | Subscribe, connect Coinbase with OAuth, let disciplined rebalancing and risk rules run on *your* account — funds stay at Coinbase. |
| **For** | US-oriented retail / prosumer crypto holders who want rules-based automation without building bots or wiring API keys into random dashboards. |
| **Unlike** | Multi-exchange “bot marketplaces” (3Commas, Cryptohopper, Bitsgap, Coinrule, etc.) that compete on bot templates, grids, and copy-trading. |
| **We win by** | Coinbase Advanced focus, **OAuth-first** connect (no keys in CRM), **GHL-native** onboarding/billing/status, deposit-aware honesty in status UI, and ops discipline from a live Phase 6 stack — sold as *software access*, not as a managed fund. |

### 1.2 Competitive frame (research-backed, not a feature war)

Public market context (2026): Coinbase Advanced is commonly automated via third-party bots that still largely push **API key** setup. Multi-exchange bot SaaS (Cryptohopper, 3Commas, Bitsgap, and peers) typically prices roughly **~$20–$50/mo** at entry paid tiers and **~$90–$150+/mo** at top self-serve tiers (example: Cryptohopper annual-billed Explorer ~$24/mo through Hero ~$108/mo on public pricing pages; third-party 2026 roundups put similar products roughly in the same band). Freemium and demo modes are common. We do not invent our own performance numbers to “beat” these competitors on ROI claims.

| Competitor pattern | Their default story | Our counter |
|--------------------|---------------------|-------------|
| Multi-exchange bot SaaS | “100+ strategies, any CEX” | Depth on **Coinbase Advanced** + portfolio-scoped OAuth |
| API-key connect UX | “Paste key + secret” | **OAuth connect URL**; revoke at Coinbase; keys never in GHL |
| Custodial / “deposit with us” scams | “Guaranteed %” | **Non-custodial**; funds on Coinbase; no return guarantees |
| DIY scripts | Free but brittle | Paid support path, status digests, kill switches, dunning-linked pause |
| Brad personal bot brand | Single-account vibe | **Product brand** separate from personal live account; no mixing screenshots |

### 1.3 Messaging pillars (use everywhere)

1. **Your Coinbase, your capital** — OAuth grant; revoke anytime; platform never holds balances.  
2. **Automation with guardrails** — rebalance windows, deploy caps, stop-loss attach, pause on billing failure.  
3. **Status you can trust** — deposit-adjusted honesty; no fake “0%” when data is N/A; marketing never invents P&L.  
4. **Software, not a fund** — subscription = access to automation + ops shell, not investment advice or pooled capital.  
5. **Boring reliability over hype** — green runner health, digests, support escalation — not “AI prints money.”

### 1.4 Compliance-safe claims (mandatory)

**Allowed (with product truth):**

- “Connect Coinbase Advanced via OAuth; capital stays in your Coinbase account.”  
- “Automated rebalancing and risk rules subject to your tier limits and market conditions.”  
- “Pause trading if billing lapses or connection errors; you can revoke access at Coinbase.”  
- Process claims: onboarding time targets, uptime/health %, support response SLAs (once defined).  
- Educational content on how rebalancing / SL mechanics work (neutral, no projected ROI).

**Forbidden in ads, landing pages, emails, SMS, social, affiliate:**

- Guaranteed returns, “risk-free,” fixed monthly %, “AI never loses.”  
- Live or historical P&L screenshots from Brad’s personal Phase 6 account as product proof.  
- Invented backtest or “average user return” numbers.  
- Implying we custody, insure, or guarantee fills.  
- Implying GHL/CRM is the exchange or holds balances.  
- Asking users to paste API keys into GHL forms.

**Always-on disclaimer block (footer + checkout):**

> ARCH Automation provides software that can place trades on your Coinbase Advanced account after you authorize access. Cryptocurrency trading involves substantial risk of loss. Past performance (if ever shown after legal review) is not indicative of future results. We do not provide investment advice, do not custody your assets, and do not guarantee profits. Subscription fees are for software and service access only.

**Legal note:** Before public paid acquisition, confirm with counsel: (a) whether marketing + OAuth trading software triggers any broker/dealer, CTA/CPO, or state money-transmitter analysis for the *specific* operating model; (b) required risk disclosures by channel; (c) terms of service + privacy for GHL + platform. This plan does not replace legal review.

### 1.5 Brand vs Brad personal account

| Do | Don’t |
|----|-------|
| Separate product domain, logo, support@, GHL Location | Use personal Telegram P&L screenshots in funnels |
| Case studies only with **opt-in pilot traders** + approved metrics | “Our live bot is up X% this month” from Brad’s wallet |
| Thought leadership as builder/operator (process, risk, architecture) | Monetize Brad’s account as the product demo without disclaimers |
| Ops Telegram for fleet health stays internal | Route customer support into Brad’s personal trading chat |

---

## 2. ICP and tiers

### 2.1 Primary ICP (pilot)

**Persona: “Coinbase holder who wants discipline, not day trading.”**

| Attribute | Detail |
|-----------|--------|
| **Who** | US adults with an existing Coinbase Advanced account (or willing to open one) |
| **Portfolio** | Roughly $1k–$50k liquid crypto/cash they already keep on Coinbase |
| **Pain** | Manual rebalancing is inconsistent; they distrust “deposit with us” bots; API-key UX feels unsafe |
| **Job to be done** | Keep a rules-based allocation running with stops and clear status without babysitting charts |
| **Triggers** | Tired of FOMO/FUD entries; wants “set policy, check digest”; hears about OAuth-only connect |
| **Disqualifiers** | Wants leverage/futures grids; wants multi-exchange arbitrage; wants guaranteed yield; refuses Coinbase; wants us to hold funds |

**Secondary ICP (post-T1):** crypto-curious professionals referred by pilots; small RIAs/family-office *explorers* (white-label only in T3 GHL-06 — not pilot focus).

### 2.2 Product tiers (map to epic SaaS table)

Platform enforces trading limits; GHL sells the plan. **Dollar prices below are pilot placeholders** — finalize against unit economics and Coinbase fee reality before public checkout.

| Tier | Who it’s for | Trading limits (platform) | Messaging angle | Placeholder price (pilot) |
|------|--------------|---------------------------|------------------|---------------------------|
| **Starter** | First automation, smaller deploy | Max deployable $X (pilot: align ~$1k–$3k class), **6 pairs**, 1× daily rebalance bias (or single window) | “Start simple. OAuth connect. Clear caps.” | $29–$49 / mo |
| **Pro** | Active holders wanting fuller universe | Higher cap, **11 pairs**, hybrid / dual rebalance windows (e.g. 09:00 + 21:00 PT class) | “More pairs, more cadence, fuller status.” | $79–$129 / mo |
| **Elite** | Power users / priority | Custom pairs window, priority support tag, earliest feature flags | “Priority ops + flexible config.” | $199–$349 / mo or custom |

**Tier → GHL fields:** `trader_tier`, SaaS product ID, platform registry caps (epic §4.3).  
**Upgrade path:** Starter → Pro when deploy needs or pair count exceeds Starter; never auto-upgrade without payment event.

### 2.3 Messaging matrix by tier

| Moment | Starter | Pro | Elite |
|--------|---------|-----|-------|
| Headline | Automate a focused Coinbase portfolio without API-key anxiety | Full pair set + dual-window discipline | Priority automation with operator attention |
| Proof style | Process + safety (OAuth, pause, digests) | Process + richer status / digests | Process + SLA / named support path |
| Objection | “Is this another scam bot?” | “Will it thrash my fees?” | “Can you support custom risk?” |
| Answer | Non-custodial + OAuth + no return promises | Deploy caps, rebalance policy, fee awareness education | Config templates + priority tag + human ops |

---

## 3. Funnel architecture

End-to-end commercial path (GHL + platform):

```
Awareness
   → Landing / content (GHL funnel or site)
   → Lead capture (optional magnet) OR direct Pricing
   → Checkout (GHL SaaS / payments)
   → W1 Onboarding — paid (subscription active)
   → Connect Coinbase (platform URL + one-time setup JWT)
   → OAuth consent → callback → TradingAccount.coinbase_status=connected
   → W3 Go live sequence
   → Activation (first healthy cycle / green runner_health)
   → Retention (W4 digests, in-app status, education)
   → Expansion (tier upgrade) / Win-back (W5 dunning) / Exit (W7)
```

### 3.1 Stage detail

| Stage | Owner | Experience | Success signal |
|-------|-------|------------|----------------|
| **Awareness** | Marketing | Product content, waitlist, referrals, then paid acquisition after T1 | Qualified visit / waitlist join |
| **Landing** | GHL | Value prop, how it works, pricing, compliance footer | Pricing CTA click |
| **Checkout** | GHL SaaS | Plan select, payment, ToS/risk acceptance checkbox | `subscription_status=active` |
| **Connect** | Platform + W2 | Email/SMS with connect link; 24h/72h reminders | OAuth complete |
| **Activation** | Platform + W3 | “You’re live” + status member link | `runner_health=green` within T1 gate |
| **Retention** | GHL W4 + product | Daily/weekly digest from platform events | Open rate + 30d retention |
| **Support** | GHL W6 | `needs_attention` → ops task | Time-to-ack |
| **Offboard** | GHL W7 | Cancel → disconnect guidance + final statement email | Clean revoke + no orphan jobs |

### 3.2 Critical conversion: pay → OAuth

Epic success metric: **median human time pay → connected < 15 min (T1), < 5 min (T3).**  
Marketing owns friction removal: single primary CTA after pay, mobile-friendly connect, plain-language OAuth screen copy, no dead ends if Coinbase tab closes (W2 recovers).

### 3.3 Surfaces

| Surface | Role |
|---------|------|
| Funnel / website | Value, pricing, checkout |
| Member area / custom menu | Connect Coinbase + Status (iframe or JWT status API) |
| Email / SMS | All lifecycle; engine emits **events**, not raw SMTP |
| Support pipeline | Billing, connect failures, red runner |

---

## 4. Online marketing plan (product only — ARCH Automation)

> **Scope:** channels used to **promote this crypto trading SaaS product**.  
> **Out of scope:** third-party client SEO/SEM/ads, local service SEO packs, shared Google Ads with other businesses.  
> **Account rule:** all paid media uses a **dedicated product ads account** (new MCC/ad account under product brand). No client account linkage.

### 4.1 Channel mix by phase

| Channel | Pre-T1 (pilot build) | T1 (10–50 traders) | T2+ (scale) |
|---------|----------------------|--------------------|-------------|
| **Owned content / organic search** | Foundation pages + FAQ + waitlist | 4–8 cornerstone articles | Ongoing topic expansion |
| **Paid search (Google Ads)** | Keyword/ad research only; **$0 spend** until legal + tracking + product ad account | Limited pilots (brand + high-intent) | Scale winners; kill losers weekly |
| **Paid social** | Creative drafts; $0 spend | Small tests (LinkedIn / X / Meta — pick 1–2) | Double down on CAC winners |
| **Email / SMS (lifecycle)** | Build W1–W3, W5 copy | Live lifecycle | W4, W6, W7 polish |
| **Community / social organic** | Soft founder updates (process, not P&L) | Pilot testimonials (approved) | Selective partnerships |
| **Referral / affiliate** | Manual invite codes | Structured referral after ~20 happy pilots | Tiered rewards (credit preferred) |
| **Partnerships / influencers** | None public | 1–2 process-focused creators (no ROI claims) | Formal affiliate terms |

### 4.2 Phase budgets, time, and owners (planning ranges — not committed spend)

Ranges are **planning envelopes** for Brad to approve; not forecasts of CAC or ROAS. Revisit after T1 exit gates.

| Phase | Duration (indicative) | Paid media budget | Organic / content labor | Lifecycle (GHL) labor | Primary owner | Gate before next phase |
|-------|----------------------|-------------------|-------------------------|------------------------|---------------|------------------------|
| **Pre-T1** | 4–8 weeks | **$0** paid | 6–10 hrs/wk (pages, FAQ, waitlist) | 4–6 hrs/wk (workflows W1–W3, W5) | Marketing + product | Funnel live; legal one-pager; claims policy; product Google Ads account created |
| **T1 paid pilot** | 4–8 weeks | **$500–$2,000 / mo** total paid (search + one social) | 4–6 hrs/wk | 2–4 hrs/wk (ops digests) | Marketing (Brad approves spend) | ≥10 paid → OAuth green; CAC proxy logged; no compliance flags |
| **T2 scale** | Ongoing | **$2k–$10k / mo** only if unit economics OK | 6–10 hrs/wk | 2–4 hrs/wk + support | Marketing + ops | Documented CAC vs LTV proxy; support SLAs hold |

**Suggested split inside T1 paid pilot ($500–$2k/mo):**

| Channel | Share of paid | Notes |
|---------|---------------|--------|
| Google Ads Search | 60–70% | Brand + high-intent commercial queries only |
| Paid social (one platform) | 20–30% | Creative testing; hard stop if CTR/quality poor |
| Tools (tracking, creative) | 5–10% | Analytics, landing A/B, stock/creative |

**Time split (steady state T1, ~12–16 hrs/wk marketing):**

| Workstream | Hrs/wk | Output |
|------------|--------|--------|
| Paid search ops | 3–4 | Keywords, negatives, LP alignment, weekly kill/keep |
| Paid social creative | 2–3 | 2–4 variants/week; compliance check |
| Organic content | 3–4 | 1 cornerstone or 2 short posts / week |
| Lifecycle / CRM copy | 2 | Email/SMS polish from platform events |
| Competitor / messaging | 1–2 | Ad samples, gap notes (see §5) |
| Metrics review | 1 | CAC proxy, funnel conversion, incident log |

### 4.3 Paid search (product Google Ads) — when spend is allowed

| Rule | Detail |
|------|--------|
| **Now (pre-T1)** | Keyword research, competitor ad copy review, LP wireframes — **$0 spend** |
| **Account** | Dedicated **product** ads account only |
| **When live** | Brand terms + high-intent non-brand; exclude “guaranteed profit,” “auto money,” scam-adjacent queries |
| **Creative** | Lead with OAuth + non-custodial + software access; compliance footer on every LP |
| **Conversion** | Primary: paid subscription; secondary: waitlist |
| **Negatives (seed)** | free money, guaranteed, risk free, deposit with us, double your, signal group, copy trading scam |
| **Landing** | Single product LP (or pricing) with ToS/risk checkbox path into GHL checkout |

**Example ad angles (copy samples — not live):**

1. *Headline:* Coinbase Advanced Automation — OAuth Connect  
   *Desc:* Keep funds on Coinbase. Rules-based rebalancing + risk controls. Software access, not a fund.  
2. *Headline:* No API Keys in a Random Dashboard  
   *Desc:* Connect via OAuth. Revoke anytime. Status digests and pause-on-billing-fail.  
3. *Headline:* Portfolio Automation for Coinbase Holders  
   *Desc:* Subscribe, connect, run disciplined rules on *your* account.

### 4.4 Paid social (product)

| Platform | Fit | Message bias | Avoid |
|----------|-----|--------------|--------|
| **LinkedIn** | Prosumer / operator ICP | Process, OAuth trust, software framing | “Passive income” clichés |
| **X** | Crypto-native discovery | Builder transparency, architecture | Live P&L flex from personal account |
| **Meta** | Broader reach (later) | Simple non-custodial story | ROI screenshots, urgency scams |
| **YouTube** (later) | Education | How OAuth/risk works | Fake backtest montages |

Start with **one** platform in T1. Creative must pass claims policy (§1.4) before spend.

### 4.5 Organic content / search (when public site exists)

**Primary intent clusters (validate volumes at build time — no invented keyword numbers):**

1. **Commercial:** Coinbase Advanced trading bot, Coinbase portfolio rebalancing software, Coinbase OAuth trading automation  
2. **Problem:** automate Coinbase rebalancing, safer than API keys crypto bot, non-custodial crypto automation  
3. **Educational:** how portfolio rebalancing works, stop-loss vs portfolio drawdown, deposit-adjusted performance honesty  
4. **Trust:** how to revoke Coinbase app access, what OAuth scopes mean  

**On-page minimum:** unique H1s, FAQ schema on trust/FAQ pages, clear pricing page, no doorway spam.  
**Local SEO:** **off** for national SaaS product (not a local service business).

### 4.6 Content calendar themes (first 90 days of *public* content)

| Theme | Example titles (draft) | Goal |
|-------|------------------------|------|
| Trust | “Why we use OAuth instead of API keys” | Reduce scam association |
| Product education | “What ‘connected’ and ‘runner health’ mean” | Activation |
| Risk literacy | “Stop-loss is per position, not max portfolio loss” | Align expectations (see `docs/Trading_Bot_FAQ.md`) |
| Ops transparency | “What happens when billing fails” | Retention / dunning fairness |
| Comparison (fair) | “Bot marketplace vs Coinbase-focused automation” | Organic + sales |

No performance numbers in these posts until a **reviewed** methodology exists.

### 4.7 Email / SMS lifecycle (W1–W7)

| ID | Workflow | Marketing ownership |
|----|----------|---------------------|
| **W1** | Onboarding — paid | Welcome, what you bought, connect CTA, risk reminder |
| **W2** | Connect reminder 24h/72h | Urgency without fear-mongering; support link |
| **W3** | Go live | Celebrate process completion, not returns; status link |
| **W4** | Daily digest | Template design; payload from platform (`daily_summary_ready`) |
| **W5** | Billing dunning | GHL native + clear “trading may pause” language |
| **W6** | Support — runner red | Ops tone; set expectations on response time |
| **W7** | Offboarding | Disconnect Coinbase steps, final statement, exit survey |

**SMS:** reserve for time-sensitive connect + dunning + red health; avoid marketing spam cadence.

### 4.8 Partnerships / referral (pilot)

- Invite-only cohort of 10–25 from founder network.  
- Offer: extended onboarding help, not “profit share.”  
- Capture qualitative feedback for messaging, not public case studies until approved.

---

## 5. Competitor market research guide

Use this section as a **living research pack** for product GTM. Update quarterly or before each paid-media phase. Public sources only; **do not invent competitor ROIs**.

### 5.1 Competitor set (primary 4)

| # | Competitor | Category | Why they matter for us |
|---|------------|----------|------------------------|
| 1 | **3Commas** | Multi-exchange bot SaaS | Brand recognition; template/DCA/grid; API-key connect culture |
| 2 | **Cryptohopper** | Multi-exchange bot SaaS + marketplace | Strategy marketplace, freemium entry, broad exchange list |
| 3 | **Bitsgap** | Terminal + bots multi-exchange | Explicit Coinbase Advanced bot marketing; demo mode; grid/DCA |
| 4 | **Coinrule** | Rule-based / no-code automation | “If-this-then-that” simplicity; freemium; TradingView-adjacent story |

**Watch list (secondary):** Pionex (exchange-native free bots — different custody model), Haasbot / pro quant tools, copy-trading networks (usually wrong category for our compliance posture).

### 5.2 Snapshot matrix (public positioning — verify before campaigns)

| Dimension | 3Commas | Cryptohopper | Bitsgap | Coinrule | **ARCH Automation (us)** |
|-----------|---------|--------------|---------|----------|--------------------------|
| **Core promise** | Multi-exchange bots, smart trade, templates | Cloud bots + strategy marketplace | Unified terminal + bots across CEXes | No-code rules / automation | Coinbase Advanced **portfolio automation** via OAuth |
| **Exchange breadth** | Many CEXes | Many CEXes | 15–20+ CEXes | Many CEXes + some on-chain | **Coinbase Advanced focus** (depth over breadth) |
| **Connect model** | API keys (typical) | API keys | API keys | API keys | **OAuth-first**; keys never in CRM |
| **Custody** | Non-custodial (user exchange) | Non-custodial | Non-custodial | Non-custodial | Non-custodial + explicit “funds stay on Coinbase” |
| **Pricing band (public, indicative)** | ~$12–$140+/mo tiers (roundups vary) | Free → ~$100+/mo | Free / Basic ~$20–$30 → Pro ~$100+/mo | Free → mid-tier ~$30–$50 band; upper tiers higher | TBD — software access tiers (see §6); avoid race-to-bottom freemium |
| **Marketing platforms** | SEO, YouTube, affiliates, paid search | SEO, marketplace SEO, YouTube | SEO, comparison pages, Coinbase-landing pages | SEO, “vs” pages, product-led free tier | GHL funnel + product content; paid search/social after T1 |
| **Typical ad / landing angle** | Win-rate bots, smart trade, multi-exchange | Marketplace strategies, AI helpers | “Coinbase trading bot”, demo mode | Easy rules, free start | OAuth trust, non-custodial, software not fund, status honesty |
| **Weak spot (gap we exploit)** | Key-management fear; complexity; multi-exchange noise | Same + marketplace quality variance | Still keys; multi-exchange UI weight | Rule DIY burden; less “ops shell” | Single-exchange depth; GHL commercial shell; deposit-aware status |

*Pricing cells are approximate from public pages/roundups (2025–2026) and must be re-checked before citing externally.*

### 5.3 Strengths / weaknesses (research checklist)

For each competitor, fill (or refresh) this template:

```
Competitor:
Last reviewed (date):
Sources (URLs):

Strengths:
- Product:
- Marketing:
- Trust / social proof:

Weaknesses:
- Product:
- Connect / security story:
- Claims risk (ROI screenshots, etc.):

Gaps vs our ICP (Coinbase holder wanting discipline, not day trading):
-

What they target (ICP guess from ads/landing):
-

Where they advertise (observed):
- Search terms / LP themes:
- Social / YouTube:
- Affiliates:
```

### 5.4 Ad / creative samples to collect (competitor teardowns)

| Collect | How | Use |
|---------|-----|-----|
| Search ads (headlines/descriptions) | Manual SERP for “Coinbase trading bot”, “crypto trading bot”, brand terms | Differentiate copy; build negative keyword list |
| Landing page hero + CTAs | Screenshots + notes (date-stamped) | LP wireframes; claims comparison |
| Pricing page structure | Feature gates, freemium | Our tier packaging narrative |
| Social creatives | Public ads library where available | What to avoid (hype) vs test (trust) |
| Email (if subscribed as prospect) | Optional research inbox | Lifecycle ideas — never copy ROI claims |

**Our creative must never mirror** competitor ROI/PnL hero numbers as if they were ours.

### 5.5 Target marketing contrast

| | Typical bot marketplace | **Our target** |
|--|-------------------------|----------------|
| Buyer job | “Run many strategies / exchanges” | “Automate Coinbase portfolio with guardrails” |
| Fear | Missing alpha | Keys stolen / scam bots / opaque P&L |
| Success metric they sell | Strategy ROI | Connected + healthy runner + clear status (process) |
| Channel bias | YouTube signals, affiliate bots | Founder network → waitlist → high-intent search → GHL lifecycle |
| Message | “Start free, 100 strategies” | “OAuth, your account, software access, pause on billing fail” |

### 5.6 Proposed competitive angle (use in all GTM)

**Primary angle:** *Coinbase Advanced automation that treats trust as the product* — OAuth connect, capital never leaves Coinbase, commercial shell in GHL, ops digests and kill-switches — sold as **software access**, not a fund and not a multi-exchange bot zoo.

**Supporting angles:**
1. **Keyless onboarding story** — no paste-keys into random SaaS.  
2. **Honesty UI** — deposit-adjusted metrics; N/A when unknown; no fake perfection.  
3. **Ops discipline** — pause on dunning, status member area, support on red health.  
4. **Narrow depth** — Coinbase Advanced done well vs 20 exchanges done shallow.

**Do not compete on:** invented win rates, free-bot wars, copy-trading social proof, or “AI that never loses.”

### 5.7 Competitive review cadence

| When | Action |
|------|--------|
| Pre-T1 | Complete §5.3 for all 4 primaries; archive dated LP screenshots |
| Before first paid spend | Refresh ad samples + pricing; update negative keywords |
| Monthly (T1+) | 1-hr SERP/social scan; note new claims or features |
| Quarterly | Full matrix refresh; decide if watch-list competitor graduates to primary |

### 5.8 Research log (append rows)

| Date | Competitor | Finding | Action for us |
|------|------------|---------|---------------|
| 2026-07-17 | Bitsgap | Public Coinbase Advanced bot landing; demo mode emphasized | Our LP should stress OAuth + non-demo live status honesty |
| 2026-07-17 | 3Commas / Cryptohopper / Coinrule | Multi-exchange + API-key default in market education content | Double-down messaging on Coinbase-only depth + OAuth |
| | | | |

---

## 6. Offer and pricing narrative

### 5.1 What is sold

| Sold | Not sold |
|------|----------|
| Software access to ARCH automation workers | Investment management / advisory |
| Tier-limited pair sets and rebalance policy | Custody of USDC/crypto |
| Lifecycle status, digests, support shell (GHL) | Guaranteed yield or insurance |
| OAuth-based connection UX | “We trade a pool with your deposit” |

**Checkout copy skeleton:**

> You’re subscribing to ARCH Automation software. After payment you’ll connect **your** Coinbase Advanced account via OAuth. We never ask for API keys in our CRM. Trading involves risk; you can revoke access anytime at Coinbase.

### 5.2 Packaging levers

- **Monthly default** for pilot (lower commitment, higher learning).  
- Annual discount only after churn data exists.  
- **No “performance fee”** in pilot packaging (avoids looking like a fund).  
- Optional one-time **setup / white-glove onboarding** for Elite only.

### 5.3 Price justification story (honest)

Price pays for: continuous job scheduling, risk tooling, OAuth token lifecycle ops, status sync, support, and product development — **not** for market outperformance. If a competitor charges $19 for multi-exchange toys, we do not race to free; we charge for Coinbase-native reliability and ops.

### 5.4 Trial / guarantee policy (recommend)

| Option | Pilot recommendation |
|--------|----------------------|
| Free trial with live trading | **Avoid** (support + risk complexity) |
| Money-back on software fee (7 days, unused connect) | Optional, legal-reviewed |
| Paper / shadow mode | Product decision; market as “observe before go-live” only if eng ships it |

---

## 7. Asset list

Create under GHL + `docs/marketing/` as needed. Owners: **Mkt** = marketing strategist / ops; **GHL** = location admin; **Eng** = platform; **Legal** = external review.

### 6.1 Pages and funnels

| Asset | Tool | Owner | Phase |
|-------|------|-------|-------|
| Homepage / value prop | GHL funnel | Mkt + GHL | Pre-T1 |
| How it works (OAuth diagram) | GHL | Mkt | Pre-T1 |
| Pricing + tier comparison | GHL SaaS products | Mkt + Eng caps | Pre-T1 |
| Risk & disclosures | GHL + PDF | Legal + Mkt | Pre-T1 |
| FAQ (product + performance literacy) | GHL | Mkt (seed from `Trading_Bot_FAQ.md`) | Pre-T1 |
| Checkout + ToS acceptance | GHL | GHL + Legal | Pre-T1 |
| Member: Connect Coinbase | Platform URL | Eng | T1 |
| Member: Status (iframe/API) | Platform status API | Eng | T1 |
| Blog / resources index | GHL or site | Mkt | T1 |

### 6.2 Lead magnets (optional pre-checkout)

| Asset | Format | Note |
|-------|--------|------|
| “OAuth vs API keys checklist” | PDF / email gate | Trust magnet; no P&L |
| “Rebalancing policy one-pager” | PDF | Education |
| Waitlist for invite-only pilot | GHL form | Pre-public |

### 6.3 Sequences and templates

| Asset | Channel | Maps to |
|-------|---------|---------|
| Welcome / W1 series | Email + optional SMS | W1 |
| Connect nudges | Email + SMS | W2 |
| Go-live | Email | W3 |
| Digest templates | Email (SMS optional) | W4 |
| Dunning | Email + SMS | W5 |
| Ops attention | Email + internal task | W6 |
| Cancel / disconnect | Email | W7 |
| Upgrade Starter→Pro | Email | Lifecycle |

### 6.4 Creative / brand

| Asset | Owner | Phase |
|-------|-------|-------|
| Working logo + color (product, not personal) | Mkt / design | **Draft kit** `docs/marketing/brand/` — Pre-T1 |
| OAuth explain illustration | Mkt | Pre-T1 |
| Social avatars + banner | Mkt | T1 |
| Ad copy doc (research) | Marketing (product angles only) | Pre-T1 |
| Screenshot policy doc | Mkt + Ops | Pre-T1 |

### 6.5 Ops / measurement assets

| Asset | Tool | Owner |
|-------|------|-------|
| UTM dictionary | Sheet | Mkt |
| Funnel KPI dashboard | GHL + later BI | Mkt |
| Message approval log | Notion/Airtable or MD | Mkt |
| Ad account runbook (when live) | MD | Mkt |

### 6.6 Tooling map

| Need | Tool |
|------|------|
| Funnels, CRM, SaaS billing, SMS/email | **GoHighLevel** |
| Paid search research | Product Google Ads account + manual SERP notes ($0 until T1 gate) |
| Organic content audit (if public domain) | Product site only — no local-service SEO packs |
| Platform connect + status | Integration gateway + status API |
| Content drafts | Marketing profile + humanizer pass before publish |

---

## 8. Metrics

Align commercial metrics with epic engineering gates; do not replace them.

### 7.1 Funnel KPIs

| Metric | Definition | Pilot target (directional) |
|--------|------------|----------------------------|
| **Waitlist → paid** | Invited or waitlisted who convert to paid | Track; no fake target until cohort size known |
| **Checkout completion** | Started checkout → active sub | ≥ 70% after form polish |
| **Pay → OAuth (connected)** | Active sub → `coinbase_status=connected` | ≥ 80% within 72h; median human time **&lt; 15 min** (epic T1) |
| **Connected → green** | Connected → `runner_health=green` | ≥ 95% of connected within 24h (epic T1 accounts green) |
| **Time-to-connected** | Timestamp pay → OAuth callback | Epic: &lt; 15 min median human time T1 |
| **Activation rate** | Paid who complete first healthy cycle | ≥ 75% of paid in 7d |

### 7.2 Economics proxies (until full attribution)

| Metric | Definition | Notes |
|--------|------------|-------|
| **CAC proxy** | (Ad spend + tools + paid creative + onboarding labor) / new paid | Pre-paid: CAC ≈ labor-heavy invite cost |
| **Software ARPU** | MRR / active paid | By tier |
| **Payback proxy** | CAC / ARPU (months) | Target &lt; 3–6 mo once ads run |
| **Gross margin proxy** | 1 − (support + infra + Coinbase-related ops cost)/revenue | Eng inputs required |

### 7.3 Retention and billing

| Metric | Definition | Watch |
|--------|------------|-------|
| **Logo churn** | Canceled / starting active | Monthly |
| **Churn after dunning** | Canceled within 14d of first payment_failed | W5 quality |
| **Involuntary churn** | Failed payment ultimate cancel | Payment UX |
| **Reactivation** | Past_due → active | Dunning efficacy |
| **Upgrade rate** | Starter → Pro/Elite | Messaging + limits |

### 7.4 Trust / quality (marketing-relevant)

| Metric | Why |
|--------|-----|
| Support tickets per account (connect vs strategy vs billing) | Content and UX fixes |
| Unsubscribe / SMS opt-out | Cadence hygiene |
| Compliance incidents (prohibited claims published) | **Zero target** |
| Cross-tenant / privacy incidents | Zero (engineering; marketing never requests cross-tenant screenshots) |

### 7.5 Reporting cadence

| Cadence | Content | Audience |
|---------|---------|----------|
| Weekly (pilot) | Pay, connect, green, tickets | Brad + ops |
| Monthly | Funnel, churn, CAC proxy, content shipped | Strategy review |
| Phase gate | Epic exit criteria + commercial readiness | SYNTH / REV |

---

## 9. 90-day pilot GTM

Assumes eng progresses T0 → T1 in parallel; **do not** open public paid ads before T1 exit. Days are relative to “pilot GTM start,” not calendar absolute.

### Phase A — Days 0–30: Foundation (before 50 traders; can start before T1 code complete)

**Build (marketing / GHL):**

1. Brand decision pack delivered (`docs/marketing/brand/`) — **awaiting Brad sign-off** on ARCH Automation + arch-automation.com.  
2. GHL Location pilot: pipelines, tags (`coinbase_connected`, `runner_healthy`, `needs_attention`), SaaS products Starter/Pro/Elite (even if only Starter sold).  
3. Draft `TradingAccount` field dictionary aligned with epic (for GHL-T0).  
4. Write W1–W3 + W5 email/SMS copy (English, compliance-safe).  
5. Landing + pricing + risk pages (can be unlisted).  
6. Screenshot / claims policy signed off by Brad.  
7. Waitlist + invite list (10–25 targets).  
8. UTM + KPI sheet.  
9. Keyword + competitor SERP notes (product account research; $0 spend).

**Do not:**

- Point production webhooks at Brad’s HP laptop (see `GHL_INTEGRATION.md`).  
- Run live search ads.  
- Publish Brad personal P&L.

**Exit A:** Unlisted funnel reviewable; W1–W3/W5 copy approved; invite list ready; claims policy live.

### Phase B — Days 31–60: Closed pilot (requires T1 commercial loop path)

**Depends on eng:** webhook → registry account; connect URL; OAuth; status sync; W3 trigger.

**Actions:**

1. Onboard **5–15** invite-only paid (or comped Elite-for-feedback) traders.  
2. Instrument pay → OAuth → green timestamps.  
3. Weekly message QA (did any email over-claim?).  
4. Collect friction log (Coinbase UX, mobile, email deliverability).  
5. Ship FAQ updates from real questions.  
6. Optional: 2 educational posts (no performance claims).

**Exit B:** ≥ 80% of paid cohort connected; median connect time trending to epic target; zero compliance incidents; churn reasons classified.

### Phase C — Days 61–90: Harden for T1 exit → controlled expansion

**Actions:**

1. Fix top 3 funnel frictions.  
2. Turn on W4 digest templates when platform emits events.  
3. Document referral offer for next cohort.  
4. Prepare paid-search brief for **product** Google Ads account (still no spend until Brad + legal OK).  
5. Pricing reality check (Starter price vs support cost).  
6. Marketing readiness checklist for “public waitlist” vs “public checkout.”

**After T1 exit criteria (epic):**

- End-to-end test trader: pay → email → OAuth → green health in GHL object within 24h.  
- Only then consider: public checkout, broader content SEO, limited SEM.

**After T2 (50–200):** scale content, W6 polish, case studies with permission, possible partner/white-label messaging (GHL-06 later).

### 8.1 What to build *before* 50 traders vs after

| Before ~50 (through T1) | After T1 exit / toward T2 |
|-------------------------|---------------------------|
| Core funnel + pricing | SEO cluster expansion |
| W1–W3, W5 | W4 at quality, W6/W7 mature |
| Invite GTM | Referral program |
| Claims policy + disclaimers | Public SEM (dedicated account) |
| Manual onboarding help | Self-serve polish |
| KPI sheet | Automated dashboard |
| Research-only ads intel | Paid acquisition experiments |

### 8.2 Dependencies to flag early

| Dependency | Why marketing cares |
|------------|---------------------|
| Dedicated host + public webhook URL | No reliable W1 automation without it |
| GHL Private Integration + SaaS products | Checkout and webhooks |
| Connect URL + JWT | Activation |
| Status API / iframe | Member area promise |
| Legal ToS / privacy / disclosures | Checkout blocker |
| Brand name + domain | SEO and ads |
| MULTI_TENANT and Brad isolation | Trust: don’t break the founder’s live account while selling reliability |

---

## 10. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Regulatory / communications** | Enforcement, forced rewrite of all assets | Counsel review before public paid; keep “software access” framing; no advisory language; strong risk disclosures |
| **Scam-category association** | Low conversion, chargebacks, app store/ad bans | OAuth-only story, non-custodial clarity, ban guaranteed-return copy, CFTC/FINRA-style red-flag awareness in review checklist |
| **Over-promising with live P&L screenshots** | Misleading ads, broken trust when markets drop | Screenshot policy; deposit-adjusted honesty; prefer process metrics in marketing |
| **Brand = Brad personal account** | Privacy, bias, single point of failure narrative | Separate brand identity; no personal wallet as hero image |
| **GHL as “the exchange” confusion** | Support load, bad reviews | Explicit copy: GHL = billing/comms; Coinbase = funds |
| **Paid media on wrong Google account** | Cross-business pollution, policy risk | Dedicated **product** ads account only; $0 until ready |
| **Selling before T1 works** | Refunds, reputation damage | Invite-only until pay→OAuth→green proven |
| **Invented performance numbers** | Legal + credibility | Plan forbids; only post-legal methodologies |
| **SMS fatigue / spam** | Carrier filtering | Transactional priority; marketing SMS rare |
| **Affiliate exaggerations** | Brand damage | No affiliate until contract + claim whitelist |
| **Data in GHL** | Token/PII leakage | Never store OAuth tokens or full-precision balances in GHL (epic) |

### 9.1 Pre-publish claim checklist (every asset)

- [ ] No guaranteed / risk-free / fixed-% language  
- [ ] Non-custodial + Coinbase funds stated where money is discussed  
- [ ] Software/subscription framing clear  
- [ ] Disclaimer present on LP and checkout  
- [ ] No Brad personal P&L  
- [ ] No fabricated backtests  
- [ ] OAuth described accurately (scopes high-level; no “we can withdraw” unless true — default: no transfer scope)  
- [ ] Tier limits match platform config templates  

---

## 11. Open questions for Brad (handoff to SYNTH-01)

1. **Public brand name and domain** — decision pack ready: recommend **ARCH Automation** + **arch-automation.com** + **support@** (`docs/marketing/brand/BRAND_DECISION_PACK.md`). Awaiting Brad sign-off; no purchase yet.  
2. **Final Starter/Pro/Elite USD prices and deploy caps** for pilot?  
3. **Invite-only duration** after T1 exit — weeks of closed beta?  
4. **Comp seats** for feedback (how many Elite comps)?  
5. **Legal counsel** contact / timeline before public checkout? **Draft docs complete** — see `docs/marketing/LEGAL_DOCS_INDEX.md`. Needs counsel engagement + review.  
6. **Founder-led content** comfort (process blogging vs silent pilot)?  
7. **Geographic restriction** (US-only checkout at launch)?  
8. **Support hours / channel** (GHL chat vs email vs Telegram business)?  

---

## 12. RACI (marketing-facing)

| Activity | Marketing | Eng | Ops | Brad |
|----------|-----------|-----|-----|------|
| Positioning & claims policy | R | C | C | A |
| GHL funnel/pages | R | C | C | A |
| W1–W7 copy | R | C (events) | C | A |
| SaaS product setup in GHL | R/C | C | R | A |
| OAuth/connect UX copy | R | R | C | A |
| Paid search research | R | I | I | A |
| Live paid media spend | R | I | I | A |
| KPI reporting | R | C | C | A |
| Legal disclosures | C | I | I | A (with counsel) |

R = responsible, A = accountable, C = consulted, I = informed

---

## 13. Suggested next executable marketing tasks (post-approval)

For SYNTH-01 / next Kanban wave (do **not** auto-create here without orchestrator):

1. **GHL-T0 marketing pack** — pipeline stages, tags, SaaS product draft, unlisted funnel skeleton.  
2. **Copy pack W1–W3/W5** — final strings in GHL + MD backup under `docs/marketing/copy/`.  
3. **Claims & screenshot policy** — one-page Brad-approved.  
4. **Competitor + SERP research pack** — fill §5 checklist for primary 4; SERP landscape notes (no live ads).  
5. **Brand mini-decision** — **pack ready** (PHASE-A-01); Brad sign-off then domain purchase when host/legal ready.  

Engineering parallel (owned by IMPL-01, not marketing): T0 registry/OAuth, dedicated host, webhook endpoint.

---

## 14. Document control

| Version | Date | Author | Notes |
|---------|------|--------|-------|
| 1.0 | 2026-07-16 | marketing-strategist (MKT-01) | Initial full GTM plan per plan pack |

**Canonical path:** `docs/marketing/SCALING_1000_MARKETING_PLAN.md`  
**Related:** `docs/epics/SCALING-1000_EPIC.md`, `docs/integrations/GHL_INTEGRATION.md`, `docs/Trading_Bot_FAQ.md`

---

*End of MKT-01 deliverable.*
