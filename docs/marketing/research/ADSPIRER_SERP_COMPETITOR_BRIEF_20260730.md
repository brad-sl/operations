# SCALING-1000 PHASE-A-05 — Adspirer / SERP / Competitor Research Brief

**Task:** `t_972e533c`  
**Date:** 2026-07-30  
**Owner:** Marketing Strategist  
**Posture:** **Research-only** — $0 spend · no campaigns created · no client ad accounts linked  
**Product (working):** ARCH Automation — Coinbase Advanced portfolio automation SaaS (OAuth-first, non-custodial)  
**Sources:** Adspirer `research_keywords` (Google Keyword Planner API, US, 2026-07-30), public competitor pages, DuckDuckGo organic SERP notes, MKT plan §4–§5  

**Related:**
- `docs/marketing/SCALING_1000_MARKETING_PLAN.md` (§4 channels, §5 competitor guide)
- `docs/marketing/CLAIMS_SCREENSHOT_POLICY.md`
- `docs/marketing/brand/BRAND_DECISION_PACK.md` (ARCH Automation / arch-automation.com — not purchased yet)

---

## 0. Executive summary

1. **Category demand is real and brand-heavy.** Planner data shows strong commercial volume on head terms (`crypto trading bot` ~1.9k/mo class, brand queries `3commas` ~3.6k, `crypto hopper` ~2.9k) with **median CPC ~$7.29** and top-of-page ranges often **$3–$16**. Head paid competition is expensive relative to T1 pilot budgets ($500–$2k/mo).  
2. **Coinbase-specific intent is thinner but cleaner.** `coinbase trading bot` returned **~140 searches/mo**, avg CPC ~$6.51, competition LOW — better quality-for-budget than broad “AI trading bot” noise (~6.6k/mo, mixed intent).  
3. **SERP for “Coinbase Advanced trading bot” is owned by multi-exchange bot SaaS + listicles + Coinbase education + DIY GitHub** — not by a Coinbase-depth OAuth portfolio product. Gap for ARCH is **trust + OAuth + portfolio discipline**, not “more grids.”  
4. **Competitors price ~$0–$150/mo SaaS** (or Gunbot lifetime licenses). Claims lean bot ROI / demo PnL / basket %. **We must not mirror that.**  
5. **Account hygiene FAIL until fixed:** Adspirer today is authenticated against **Uncorked Canvas / client Google Ads IDs** — **not** a dedicated ARCH product account. **Never** run product research spend or campaigns on client accounts (including Forever Roofing / any consultancy MCC).  

**Phase B implication:** Win pre-T1 with organic trust pages + waitlist; when paid is unlocked, start **exact/phrase** on brand + Coinbase-high-intent + competitor conquest (negatives heavy), **not** broad AI-bot head terms at Adspirer’s default $400/day fantasy budgets.

---

## 1. Account hygiene (mandatory)

| Check | Status | Detail |
|-------|--------|--------|
| Dedicated **product** Google Ads account for ARCH | **NOT CREATED** | Required before any spend (MKT §4.3) |
| Adspirer connected accounts (2026-07-30) | **Client / other brands only** | Primary: **Uncorked Canvas (3657758680)**; also **2305402140**. No ARCH / arch-automation account. |
| Forever Roofing / client ops accounts | **DO NOT USE** | Explicit ban: never link product ads to client ops accounts |
| Research call this run | **READ-ONLY** | `research_keywords` only via Adspirer MCP. **No** `create_*_campaign`, no budgets, no keywords added to live groups |
| Live campaigns created | **None** | Confirmed by posture + tool choice |

### Hygiene actions for Brad (ops — not done by this task)

1. Create new Google Ads account under **product brand** (ARCH Automation / final legal entity) — separate billing profile.  
2. Optionally place under a **product-only MCC**; never under client consultancy MCC used for Uncorked Canvas / Forever Roofing / roofing clients.  
3. Connect **only** that product account in Adspirer (`adspirer.ai/connections`) and set it primary before any Phase B spend.  
4. Until then: Keyword Planner / Adspirer research may still return Planner metrics (as this run did) but **must not** create or edit campaigns on connected client accounts.  
5. Document account ID in this folder when created: `docs/marketing/research/PRODUCT_GOOGLE_ADS_ACCOUNT.md`.

---

## 2. Keyword research (Adspirer / Keyword Planner)

**Method:** Adspirer MCP `research_keywords` (read-only), location **United States**, English, Search network bid ranges.  
**Exports:**
- `docs/marketing/research/keyword_list_full.csv`
- `docs/marketing/research/adspirer_keyword_research.md`
- `docs/marketing/research/adspirer_keyword_research_raw.json`
- `docs/marketing/research/adspirer_coinbase_pass.md`

**Caveats:**
- Adspirer’s “recommended 20” and **$400+/day** budget tips are **tool defaults for broad campaigns — ignore for our T1 envelope**.  
- CPC = average of low/high top-of-page bid estimates, not our actual CPC.  
- Competition = Planner competition band, not organic KD.  
- Many Coinbase long-tails have low/unreported volume; still map them for LP SEO and exact-match tests.

### 2.1 Planner metrics captured (unique set, US)

| Keyword | Est. mo. searches | Avg CPC ($) | Top-of-page bid range | Competition |
|---------|-------------------|-------------|------------------------|-------------|
| ai trading bots | 6,600 | 7.19 | 2.81–11.58 | MEDIUM |
| 3commas | 3,600 | 10.05 | 3.84–16.26 | LOW |
| crypto hopper | 2,900 | 8.75 | 2.99–14.50 | LOW |
| crypto trading bot (+ near-dupes) | 1,900 | 7.34 | 2.74–11.95 | LOW |
| best ai trading bot | 1,300 | 7.87 | ~2.5–13.2 | MEDIUM |
| ai crypto trading bot | 880 | 8.66 | 3.10–14.21 | MEDIUM |
| artificial intelligence crypto trading (+ variants) | 720 | 10.66 | 3.95–17.37 | MEDIUM |
| automated trading bots | 720 | 6.47 | 2.64–10.29 | MEDIUM |
| pionex trading bot | 590 | 8.15 | 0.05–16.24 | LOW |
| best trading bot | 390 | 6.03 | 2.36–9.71 | MEDIUM |
| best ai crypto trading bot | 320 | 8.58 | 2.96–14.19 | LOW |
| automated crypto trading | 260 | 8.16 | 2.88–13.44 | LOW |
| coinbase trading bot | **140** | **6.51** | (see pass file) | **LOW** |
| best automated crypto trading platform | 110 | 7.32 | — | MEDIUM |

**Aggregate from first Planner pull:** median CPC ~**$7.29**, average ~**$6.71**, high-intent threshold used by tool ≥~$8.02. **Total keywords found in expanded Planner set: 86** (raw export); table above is the structured subset returned with metrics.

### 2.2 Intent tiers (for ARCH — not Adspirer’s AI-hype ranking)

| Tier | Intent | Examples | Paid priority (when allowed) | Notes |
|------|--------|----------|------------------------------|-------|
| **T0 Brand** | Brand defense | `ARCH Automation`, `arch automation bot` (post-launch) | Exact only | $0 until brand exists publicly |
| **T1 High commercial / Coinbase** | Ready to buy automation on Coinbase | `coinbase trading bot`, `coinbase advanced trading bot`, `coinbase advanced automation`, `automate coinbase trading` | **Primary** exact/phrase | Thin volume, high fit |
| **T2 Category commercial** | Bot shoppers | `crypto trading bot`, `automated crypto trading`, `cryptocurrency trading bot` | Secondary, tight match + strong LP | Broad = junk + scam association |
| **T3 Competitor conquest** | Switching / comparing | `3commas`, `crypto hopper`, `bitsgap coinbase`, `coinrule alternative` | Careful exact; **honest contrast LP** | High CPC; policy-safe comparison only |
| **T4 Problem / trust** | Fear of keys / custody | `non custodial crypto bot`, `oauth coinbase bot`, `safer than api key trading bot` | Prefer **organic** first | Low Planner volume; high message fit |
| **T5 Portfolio / rebalance** | Holder discipline | `crypto portfolio rebalancing`, `automatic portfolio rebalance crypto` | Organic cornerstone + later paid tests | Aligns with product truth |
| **T6 AI hype** | Tire-kickers | `ai trading bots`, `ai crypto trading bot` | **Deprioritize / negative-heavy** | Volume high, fit low, claim risk high |

### 2.3 Seed negatives (from MKT §4.3 + this research)

Add before any Search campaign:

```
guaranteed, guarantee profit, risk free, risk-free, free money, double your,
deposit with us, signal group, signals free, copy trading scam, ponzi,
passive income guaranteed, get rich, 10% daily, daily profit, binary options,
forex robot, mlm, cloud mining
```

**Also negative or exclude by match strategy:** pure “AI prints money” creatives; futures/leverage intent if product is spot portfolio only (`futures bot`, `leverage bot`, `short crypto bot` unless Elite explicitly supports).

### 2.4 Adspirer “budget recommendation” — override

| Source | Daily | Monthly-ish | Our plan |
|--------|-------|-------------|----------|
| Adspirer tool default | ~$400–$533/day | ~$12k–$16k/mo | **Reject** |
| MKT plan T1 pilot | — | **$500–$2,000 / mo** total paid | **Authority** |
| Suggested T1 Search share | — | 60–70% of paid (~$300–$1,400/mo) | Brand + T1/T2 only |

---

## 3. Keyword map → landing / pricing / content

| Page / asset | Primary keywords / themes | Secondary | Message pillar |
|--------------|---------------------------|-----------|----------------|
| **Home / hero LP** | Coinbase Advanced automation, Coinbase portfolio automation, OAuth connect | non-custodial, software not a fund | Your Coinbase, your capital |
| **Pricing** | Coinbase trading bot pricing, portfolio automation subscription | Starter/Pro/Elite tier language | Software access tiers — no ROI promise |
| **How it works** | automate Coinbase rebalancing, runner health, pause on billing fail | deposit-adjusted status | Guardrails + honesty UI |
| **Trust / security** | OAuth vs API keys, revoke Coinbase access, non-custodial | what scopes mean | Keyless onboarding story |
| **Compare (fair)** | 3commas alternative Coinbase, bitsgap vs oauth automation | multi-exchange bot marketplace vs Coinbase depth | Narrow depth wins |
| **FAQ** | fees, risk, stop-loss ≠ max portfolio loss | dunning pause | Risk literacy |
| **Blog (90d public)** | See MKT §4.6 themes | — | Education only, no P&L |

**H1 examples (compliance-safe):**
- “Coinbase Advanced portfolio automation — OAuth connect, funds stay on Coinbase”
- “Rules-based rebalancing software for Coinbase holders (not a fund)”
- “No API keys in a random dashboard — connect and revoke at Coinbase”

---

## 4. SERP landscape notes (2026-07-30)

### 4.1 Method limits
- Google Search HTML via automation hit **captcha / sorry page** (IP 75.x) — no reliable Google SERP screenshot this run.  
- **DuckDuckGo HTML** organic results used for “Coinbase Advanced trading bot” proxy + public page extracts for competitor Coinbase landings.  
- **No paid ad creatives scraped** from Google Ads Transparency this run — refresh manually before first spend.

### 4.2 Organic pattern — query: Coinbase (Advanced) trading bot

| Rank-ish type | Example | Role |
|---------------|---------|------|
| Listicle / affiliate | CoinCodeCap “6 Best Coinbase Bots” | SEO capture; often affiliate to multi-exchange bots |
| Exchange education | Coinbase Learn — automated trading platforms; Advanced Trade API | Coinbase **names** 3Commas, Bitsgap, Altrady, Cryptohopper as integrations — **API-key culture reinforced by the exchange itself** |
| Competitor exchange LPs | 3Commas Coinbase bot, Bitsgap Coinbase Advanced, Cryptohopper Coinbase, Gainium, WunderTrading, Gunbot, OctoBot, GoodCrypto | Direct commercial intent pages |
| DIY / GitHub | coinbase-advanced-trade-bot repos | Free alternative; security variance |
| Medium / “I tested AI agents” | Performance storytelling | **High claim risk** — do not emulate |

**Observed commercial angles on competitor Coinbase LPs:**
- Grid / DCA / BTD / Combo bots  
- Demo mode / free trial / paper trading  
- “Automate so you don’t depend on yourself”  
- API key connect (Bitsgap, Gainium guides); **Cryptohopper also pushes Fast Connect OAuth2** for Coinbase — important: OAuth is **not unique forever**, but **OAuth-only + GHL ops shell + deposit-honest status** still differentiates  
- Some sites show **basket %** (OctoBot theme baskets with weekly/monthly %) or testimonial $ gains (Gunbot community quotes) — **forbidden pattern for ARCH marketing**

### 4.3 P&L / prohibited-claim scan (competitors — observational)

| Source | Observation | ARCH response |
|--------|-------------|----------------|
| OctoBot Coinbase LP | Theme baskets show **+X% last week/month** on cards | Never show unverified period returns on marketing |
| Gunbot | User testimonials with portfolio $ increases | No user P&L without legal + consent + methodology |
| Bitsgap | “Profit from slightest moves,” demo risk-free | Avoid “risk-free”; demo OK if labeled simulated |
| Coinrule | “Catch the pump,” AI agents; footer has solid risk disclaimer | Match **disclaimer discipline**, not hype headlines |
| 3Commas | “Automation that pays for itself” | Soft ROI implication — we avoid |
| **This research / our assets** | **No ARCH P&L claims published** | Compliant |

### 4.4 Screenshot archive status

| Item | Status |
|------|--------|
| Full-page Google SERP screenshots | **Blocked** this run — capture manually in browser (logged-out, US) before T1 spend |
| Competitor LP notes | Captured via extract (dated 2026-07-30) in this brief §5 |
| Recommended folder for future screenshots | `docs/marketing/research/serp-screenshots/YYYYMMDD/` |

---

## 5. Competitor analysis (top 10)

Public positioning only. Pricing re-checked 2026-07-30 from public pages (may change; re-verify before external quotes).

### 5.1 Primary set (MKT §5.1)

| # | Competitor | Category | Connect model | Pricing (public, indicative) | Funnel / CTA | Core claims | Gap vs ARCH ICP |
|---|------------|----------|---------------|------------------------------|--------------|-------------|-----------------|
| 1 | **3Commas** | Multi-exchange bot SaaS | API keys (active key limits by plan) | Starter **$20**/mo · Pro **$50** · Expert **$140** (+ custom); demo; free trial | Registration → trial → bots/SmartTrade | DCA/grid/signal bots; “automation that pays for itself”; AI Assistant | Complexity + multi-exchange noise; key culture |
| 2 | **Cryptohopper** | Bot + marketplace | **OAuth Fast Connect** + API keys option | Annual-billed Explorer **~$24**/mo · Adventurer **~$58** · Hero **~$108**; 3-day trial; copy bots extra | Create account → connect exchange → marketplace strategies | 24/7 bots, portfolio bot, AI designer, marketplace | Marketplace quality variance; still multi-exchange zoo |
| 3 | **Bitsgap** | Terminal + bots | API key (“API key is all you need”) | Free demo tier · paid **~$23 / $55 / $119**/mo (annual display) · 7-day PRO trial | Sign-up → connect → GRID/DCA/BTD; **dedicated Coinbase Advanced LP** | Coinbase Advanced bots; demo mode; non-withdrawal API story | Strong Coinbase SEO page; still keys + grid culture |
| 4 | **Coinrule** | No-code rules + AI | Multi-exchange + brokers | Free · Investor **$29.99** · Trader **$59.99** · Pro **~$749**/mo (+ volume fee language on some calculators) | Start free → templates → AI/MCP agents | If-this-then-that; 350+ bots; stocks+crypto; YC social proof | DIY rule burden; hype AI framing |

### 5.2 Extended set (SERP / Coinbase LP presence)

| # | Competitor | Notes | Pricing signal | Threat to ARCH |
|---|------------|-------|----------------|----------------|
| 5 | **Gainium** | Strong Coinbase Advanced SEO page; DCA/grid/combo; free-forever plan; portfolio rebalancing feature | Free + paid higher limits | Direct “rebalancing on Coinbase” overlap — differentiate OAuth-first + ops shell |
| 6 | **Gunbot** | Local execution; Coinbase Advanced LP; lifetime licenses | Standard promo **~$44–$199** lifetime class (sale-dependent) | Power users; not GHL SaaS; different buyer |
| 7 | **OctoBot Cloud** | Baskets + AI strategies; Coinbase page; **shows basket % returns** | Free invest CTAs / freemium cloud | Claim-heavy SERP neighbor — good foil for “honesty” positioning |
| 8 | **WunderTrading** | Coinbase Advanced bot LP; TradingView | SaaS (verify current) | Signal/TV crowd |
| 9 | **Pionex** | Exchange-native free bots | Exchange fees | Custody model different — exclude from head-to-head except education |
| 10 | **GoodCrypto / Altrady** | Terminal + bots; Coinbase mentions | App subscriptions | Secondary |

### 5.3 Snapshot matrix (refresh of MKT §5.2)

| Dimension | 3Commas | Cryptohopper | Bitsgap | Coinrule | Gainium | **ARCH (us)** |
|-----------|---------|--------------|---------|----------|---------|---------------|
| Promise | Multi-exchange bots | Marketplace + cloud bots | Terminal + GRID/DCA | No-code rules / AI agents | No-code DCA/grid/combo | **Coinbase Advanced portfolio automation** |
| Connect | API keys | OAuth + keys | API keys | API keys | API keys | **OAuth-first; keys never in GHL** |
| Custody | User exchange | User exchange | User exchange | User exchange | User exchange | User Coinbase + explicit non-custodial |
| Entry price | ~$20/mo | ~$24/mo | ~$0–$23/mo | Free | Free | Pilot placeholders $29–$49 Starter (MKT) |
| Coinbase SEO | Yes | Yes | **Strong dedicated LP** | Yes (Pro legacy URLs) | **Strong** | Build dedicated pages |
| Ops/billing shell | In-app | In-app | In-app | In-app | In-app | **GHL commercial layer** |
| Status honesty | PnL dashboards | Stats | Bot profit panels | Rules performance | Backtests/paper | **Deposit-adjusted; N/A not 0%** |

### 5.4 Funnel patterns to copy (structure only)

1. **Exchange-specific LP** (Bitsgap/Gainium/Cryptohopper) → trial → connect → first bot.  
2. **Freemium wedge** then paid limits (bots, volume, exchanges).  
3. **Demo / paper** before live.  
4. **Comparison / versus SEO** (Coinrule especially).  

**Copy structure, not claims.** Our funnel remains: waitlist/LP → GHL checkout → OAuth → green runner (MKT §3).

### 5.5 Research log append (MKT §5.8)

| Date | Competitor | Finding | Action for us |
|------|------------|---------|---------------|
| 2026-07-30 | Bitsgap | Coinbase Advanced LP live; API-key story; $23–$119/mo annual | Own “OAuth + no keys in CRM” hero; pricing can sit Starter ~Bitsgap Basic without race-to-zero |
| 2026-07-30 | Cryptohopper | Official Coinbase partner page; **OAuth Fast Connect** documented | Do not claim “only OAuth bot”; claim **OAuth-first product + GHL ops + honesty metrics** |
| 2026-07-30 | 3Commas | $20/$50/$140; AI Assistant; Coinbase bot URL in SERP | Competitor conquest ads only with fair compare LP |
| 2026-07-30 | Coinrule | Free→$30→$60→$749; AI/MCP push; strong disclaimer footer | Mirror disclaimer rigor; avoid “catch the pump” tone |
| 2026-07-30 | Gainium | Portfolio rebalancing called out on Coinbase page; free plan | Content: rebalancing **with guardrails + tier caps + billing pause** |
| 2026-07-30 | OctoBot | Basket % on Coinbase LP | Competitive foil in trust content — “we don’t market period returns that way” |
| 2026-07-30 | Planner | `coinbase trading bot` ~140/mo; head bot terms 1.9k–6.6k | Paid: prioritize Coinbase exact; organic: category + trust |

---

## 6. Positioning implications (feed copy / funnel)

**Primary angle (unchanged, reinforced by research):**  
*Coinbase Advanced automation that treats trust as the product* — OAuth, funds stay on Coinbase, GHL commercial shell, ops digests / kill-switches — **software access, not a fund, not a multi-exchange bot zoo.**

**Competitive one-liners for sales/compare (not ads yet):**
- vs Bitsgap/3Commas: “Less grid casino. More portfolio policy on the exchange you already trust.”  
- vs Cryptohopper: “We don’t sell a strategy marketplace. We sell disciplined Coinbase automation + clear status.”  
- vs Coinrule: “Less DIY rule spaghetti. More opinionated rebalance + risk envelope.”  
- vs Gainium free: “Free bots are fine for tinkering. Paid ops shell when you care about billing-linked pause and support.”  
- vs OctoBot baskets: “We won’t put a weekly % on the homepage to get your click.”

**Messaging pillars to keep in all Phase B assets:** MKT §1.3 + claims policy — no Brad Phase 6 P&L, no guaranteed returns, no custody language.

---

## 7. Recommendations — Phase B (content / SEM)

### 7.1 Before any paid (still Phase A / pre-T1)

1. **Create product Google Ads account** + hygiene doc (see §1).  
2. **Ship foundation pages:** Home, Pricing, How it works, Trust/OAuth, FAQ, fair Compare — keyword map §3.  
3. **Claims review** on every asset (`CLAIMS_SCREENSHOT_POLICY.md` + legal).  
4. **Manual US SERP screenshots** (logged-out) for:  
   - `coinbase trading bot`  
   - `coinbase advanced trading bot`  
   - `crypto trading bot`  
   - `3commas`  
   Save under `serp-screenshots/`.  
5. **Conversion tracking** plan only (GHL + analytics) — no tags firing spend.  
6. Refresh Planner export on **product** account once it exists (volumes can differ slightly by account history).

### 7.2 Content (organic) — first public wave

| Priority | Asset | Target cluster |
|----------|-------|----------------|
| P0 | Trust: “Why OAuth instead of API keys” | T4 trust |
| P0 | Fair compare: “Bot marketplace vs Coinbase-focused automation” | T3/T5 |
| P1 | “What runner health / connected means” | activation |
| P1 | “Stop-loss vs portfolio drawdown” | risk literacy |
| P2 | “How to revoke Coinbase app access” | trust SEO |
| P2 | Exchange LP clone (ours): `/coinbase-advanced-automation` | T1 |

### 7.3 SEM structure (when Brad + legal unlock spend)

| Campaign | Budget share (of Search) | Match | Notes |
|----------|--------------------------|-------|-------|
| Brand | 10–15% | Exact | After public brand |
| Coinbase high-intent | 40–50% | Exact/Phrase | T1 only; single LP |
| Category tight | 20–25% | Phrase | `crypto trading bot` etc. + heavy negatives |
| Competitor | 10–20% | Exact | Only with compare LP; watch trademark policies |
| AI head terms | 0% initially | — | Revisit only with data |

**Ad angles (samples already in MKT §4.3 — keep):** OAuth connect; no API keys in CRM; funds on Coinbase; software not fund; pause on billing fail.

**Success metrics (process, not invented ROAS):** CTR, LP CVR to checkout, paid→OAuth rate, cost per OAuth, compliance flags = 0.

### 7.4 What not to do in Phase B

- No campaigns on Uncorked Canvas / client accounts  
- No Broad match dump of Adspirer’s 20 “AI” keywords without negatives  
- No competitor ROI screenshots  
- No “as seen on” fake social proof  
- No linking Forever Roofing or any local-service account to product MCC  

---

## 8. Deliverables checklist

| Deliverable | Location | Status |
|-------------|----------|--------|
| Keyword list + volume/CPC/competition | `keyword_list_full.csv`, Adspirer MD/JSON | Done |
| Competitor analysis top 5–10 | This brief §5 | Done |
| SERP notes + P&L claim scan | §4 (screenshots blocked — manual follow-up) | Partial / noted |
| Keyword map LP/pricing | §3 | Done |
| Hygiene note separate product account | §1 | Done — **account still missing** |
| Phase B content/SEM recommendations | §7 | Done |
| No live campaigns / no spend | Confirmed | Done |

---

## 9. Dependencies / flags

| Dependency | Owner | Blocks |
|------------|-------|--------|
| Product Google Ads account + billing | Brad | Any paid; cleaner Planner on brand |
| Domain/brand lock (PHASE-A-01) | Brad | Brand SEM, public LP URLs |
| Legal/claims sign-off | Brad + counsel | Public paid + aggressive compare pages |
| GHL funnel + tracking | PHASE-A GHL tasks | SEM conversion optimization |
| Manual SERP screenshots | Marketing / Brad 15 min | Pre-spend creative teardown |

---

## 10. Appendix — Ad copy angles (still $0)

1. **Headline:** Coinbase Advanced Automation — OAuth Connect  
   **Desc:** Keep funds on Coinbase. Rules-based rebalancing + risk controls. Software access, not a fund.  
2. **Headline:** No API Keys in a Random Dashboard  
   **Desc:** Connect via OAuth. Revoke anytime. Status digests and pause-on-billing-fail.  
3. **Headline:** Portfolio Automation for Coinbase Holders  
   **Desc:** Subscribe, connect, run disciplined rules on *your* account.  

Always-on disclaimer: use MKT §1.4 / claims policy footer block.

---

*End of brief. Research-only. Generated for SCALING-1000 Phase A prereq pack.*
