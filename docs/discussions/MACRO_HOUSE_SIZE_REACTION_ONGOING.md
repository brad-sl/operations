# Macro game: house, size, reactionary retail — ongoing discussion

**Status:** living note (append, don’t overwrite history)  
**Started:** 2026-08-30 (PDT)  
**Owner:** Brad + Scotty  
**Triggers:** game-theory / fee realism / whale flow / “who is the product?” product design  
**Related:** `docs/COINBASE_FEE_RESEARCH.md`, Phase 6 membership gates, dual_agree / preferred arm, discovery quiet-TG (2026-08-30), Denning game-theory article discussion  

---

## 0. How to use this note

- **Not a promote ticket.** No live knobs change from this file alone.
- Append dated sections when the discussion moves.
- Prefer: structure → implications → testable questions → explicit GO/NO-GO for any experiment.
- Pair with offline-strategy honesty: shadow first, frozen params, no fake edge claims.

---

## 1. Seed premises (Brad, 2026-08-30)

1. On Coinbase, **win or lose, the house takes a cut** (fees on flow).
2. **Large traders / whales** can swing thin names (pump-dump, inventory, forced flow).
3. **Small reactionary traders** absorb the hit — they are often the exit liquidity.

### Working model (three payoff layers)

| Layer | Optimizes | Paid by |
|-------|-----------|---------|
| Exchange (house) | Volume × fee, spread, listing economics | Every round-trip; indifferent to your thesis |
| Size / informed / forced flow | Inventory, liquidations, narrative, known retail patterns | Moves price *through* thin books |
| Small reactionary trader | “Be right after the move is visible” | Spread + fee + slippage + stops |

**One-liner:** Effort inside a *reaction* game gets absorbed by fees and size. Change the payoff matrix or stay a well-informed bidder in a dollar auction.

### Link to Denning / game-theory framing (same day)

- Dollar auction / rent-seeking ↔ overtrading + chasing heat  
- Traffic jam ↔ everyone “sensibly” FOMO-ing the same tape  
- Congestion pricing ↔ **decision structure** (live swaps OFF, dual_agree, revisit dates, quiet scout TG)  
- Walking away ↔ park dead research (e.g. return-entropy), refuse same-day flip pile-on  

---

## 2. Lane A — Personal book (non-reactionary process)

### Goal

Survive and compound **without needing to out-react size** on every name.

### What “non-reactionary” means here

| Do | Don’t |
|----|--------|
| Pre-commit risk budgets / seat caps | Size up because the candle is green |
| Prefer low turnover when edge is thin | Pay the house twice to “be active” |
| Sit cash / ballast when structure is hostile | Force deployment to feel productive |
| Treat pump-shaped tape as **hostile structure** | Treat every rip as opportunity |
| Exits: protect dump path, bank “good enough” | Hold for perfect top after FOMO entry |
| Majors / liquid names as default battlefield | Long-tail reaction scalps as core PnL |

### Concrete rule families (map to existing Phase 6 culture)

1. **Turnover budget (fee realism)**  
   - Every round-trip pays maker (hopefully) or taker (pain).  
   - Personal bar: if expected edge << 2× round-trip cost + slippage, **no trade** is the edge.  
   - See fee tiers in `docs/COINBASE_FEE_RESEARCH.md` (maker vs taker; volume tiers).

2. **Participation filter (when the game is playable)**  
   - Play: liquid books, clear regime, process signal not heat.  
   - Don’t play: vertical 24h alts, thin weekend books, unlock/list theater unless *explicit* experimental sleeve with tiny size.

3. **Reaction lag acceptance**  
   - You will often **not** be early.  
   - Late-chase after public heat = buying someone else’s exit.  
   - “Missed ZORA” can be a **win** if dual_agree never fired.

4. **Capital structure > call quality**  
   - Seat ~15–20% eq, max seats discipline, pair cap ~30%.  
   - Preserve / park / ballast modes already encode “different road,” not harder driving.

5. **Horizon honesty**  
   - ~5%/mo process bar is a *regime for expectations*, not a promise.  
   - High-frequency reaction on alts fights both house and size.

### Testable questions (personal book)

- [ ] What is **max round-trips / week** before fee drag dominates our realized edge?  
- [ ] What % of historical losers were “reaction to heat” vs “process signal that failed fairly”?  
- [ ] Does **cash/ballast time** improve path DD more than it costs upside on this book size?

### Anti-goals

- Becoming a mini-whale via leverage fantasy.  
- Automating faster reaction to the same public tape (“smarter rat, same race”).

---

## 3. Lane B — Product (multi-trader platform)

### Goal

**Trust / reliability product** that does not industrialize users becoming exit liquidity — while remaining honest that the house and size still exist.

### Product truth (say out loud)

- We cannot abolish Coinbase fees or whales.  
- We *can* refuse to ship **alpha theater** that trains reactionary behavior.  
- Users who churn from FOMO fills are not a growth win; they’re a trust debt.

### Design implications

| Surface | Better default | Avoid |
|---------|----------------|--------|
| Signals | BUY/HOLD/SELL + **·gated / ·blocked** reasons | Naked “hot” without gate language |
| Discovery / rotation | Scout ≠ recommend; rare “seriously consider” only on dual_agree / preferred arm | Big Δ push notifications as dopamine |
| KPIs | Funnel: seat → signal → fill → win; deposit-adjusted | Fake guarantees, vibes scoreboards |
| Copy / compose | Template, no-AI hype | “You can outsmart whales daily” |
| Risk product | Adjustable factors / regime budgets | Round-number fear caps that fight design |
| Education | Fee drag, adverse selection, when *not* to trade | Only green PnL screenshots |

### Platform-scale (100s traders / 1000s trades/day)

- **Aggregate user flow** can *itself* become detectable / exploitable if everyone gets the same chase signal at once → **congestion you create**.  
- Implication: diversity of risk budgets, staggered gates, not one global FOMO siren.  
- Reliability (fills, SL honesty, no fake prices) compounds more than a slightly cleverer RSI.

### Testable questions (product)

- [ ] After a blocked/gated signal, do users understand *why* (trust) or feel robbed (churn)?  
- [ ] Does showing **fee-to-date** / turnover drag reduce harmful overtrading?  
- [ ] Can we measure “reactionary entry rate” (entry after +X% 24h without process pass)?

### Anti-goals

- Dark-pattern engagement via heat alerts.  
- Promising “whale-beating AI” as brand.

---

## 4. Lane C — Venue (Coinbase-specific)

### What the venue actually is

- **Toll booth + matching engine + custody UX**, not a partner in your PnL.  
- Advanced Trade: tiered **maker/taker** by 30d volume (see fee research doc).  
- Your stack prefers **limits / maker** path; emergency exits may pay taker — model that.

### Coinbase frictions that matter more than “evil exchange”

1. **Fee tier vs strategy** — high turnover at low tier is a self-tax; size and style interact with tier.  
2. **Book depth by pair** — BTC/ETH ≠ long-tail USD pairs; “whale” is often “anyone larger than the top of book.”  
3. **What you can see** — public trades / candles ≠ full institutional intent; don’t pretend L3 god-view.  
4. **What you can’t see** — OTC, other venues, derivatives hedges that print spot later.  
5. **Operational risk** — API, outages, maintenance windows as *structure*, not bad luck only.  
6. **Listing / narrative gravity** — venue attention concentrates retail; that’s a flow magnet, not free alpha.

### Venue strategy implications

- **Default battlefield:** liquid USD pairs where adverse selection is survivable.  
- **Long-tail:** tryout size only, or research sleeve — not core identity.  
- **Maker discipline** as product + personal rule.  
- **Don’t confuse Coinbase “Advanced” branding with professional information parity.**

### Testable questions (venue)

- [ ] Realized maker % vs assumed; taker bleed on exits?  
- [ ] Slippage by pair tier (majors vs discovery contenders)?  
- [ ] After fee + slippage, does basket rotation paper edge survive L2 realism?

---

## 5. Lane D — Externalities: can whale trades be leveraged to “outsmart the system”?

### Short answer

**Partially usable as risk/context. Rarely as a clean “outsmart” edge. Easy to become a fancier reactionary.**

Following whales *is still a reaction game* unless you have **(a)** faster/cleaner data than the crowd, **(b)** a structural reason their print predicts *your* horizon, and **(c)** costs that don’t eat the move.

### What “whale” actually means (disambiguate)

| Label | Reality | Usable? |
|-------|---------|---------|
| Large print on Coinbase tape | Someone lifted/hit size *here* | Sometimes — often already in the candle |
| Exchange whale wallet alert (on-chain) | Often wrong venue, delayed, spoofable narratives | Weak for spot CB book timing |
| “Smart money” influencer lists | Marketing + lag | Usually reverse-indicator after amplification |
| Forced flow (liqs, unlocks, options expiry) | Calendar/structure | Better — **event structure**, not hero worship |
| Inventory distribution after a run | Size needs exit liquidity | Fade/exhaustion *research*, not default buy |

### Ways externalities *can* help (honest ladder)

**Tier 0 — Don’t fight size (highest ROI, least sexy)**  
- If tape is one-sided and vertical, **stand down** (anti-pump, block-max, run-phase gates).  
- This *is* leveraging the externality: size’s presence changes *your* action set to **no trade**.  
- Already closest to current culture.

**Tier 1 — Structure & calendar externalities**  
- Known unlocks, listings, expiry windows, extreme funding (if you ever touch perps), weekend thinness.  
- Use as **participation filters**, not entry signals.

**Tier 2 — Exhaustion / distribution shadows (research only)**  
- After parabolic + high volume, probability of *mean path pain* for late buyers rises.  
- Shadow: “no new seats into +X% 24h” already rhymes with this.  
- **Not** the same as “fade every pump” (catching knives).

**Tier 3 — Tape / large-print features (expensive, easy to fool)**  
- Features like: unusual notional rate, trade-count skew, multi-minute absorption.  
- Problems:  
  - Public, so crowded if it works briefly  
  - Spoofing / one-shot dumps  
  - Horizon mismatch (1m print vs your hold days)  
  - Data/engineering cost vs Phase 6 north star (process reliability)  
- **Gate:** only shadow with frozen defs + fee-aware CF; no live until Brad go.

**Tier 4 — Co-move with size (usually a trap for small accounts)**  
- “Buy when whales buy” on public alerts → you are late retail on a marketing feed.  
- Exceptions require proprietary or truly early data most retail stacks don’t have.

### “Outsmart the system” reframe

Wrong target: **beat the house + beat whales at short-horizon prediction.**  
Right target: **build a payoff matrix where house cut is minimized and size is treated as weather.**

| Strategy | Vs house | Vs size | Notes |
|----------|----------|---------|-------|
| High-turnover reaction | Lose | Lose | Classic exit liquidity |
| Low-turnover process + stand-down | Contain | Respect | Default |
| Maker + liquid pairs | Contain | Survive | Venue-aligned |
| Whale-alert chase | Lose | Lose | Reaction with branding |
| Forced-flow calendar filters | Neutral | Respect | Structure |
| Shadow tape features | ? | ? | Research tax; prove or park |

### If we ever test whale/tape leverage (preflight checklist)

1. **Definition frozen** (what counts as whale print: notional, vs ADV, window).  
2. **Horizon match** (signal horizon ≈ hold horizon).  
3. **Cost model** (maker/taker + slippage) in CF.  
4. **Inverse control** (does doing the opposite or random beat it?).  
5. **Congestion check** (if productized, do all users fire together?).  
6. **Shadow only** until Brad go; no discovery-TG style hype.  
7. Success metrics: path DD, excess vs no-trade, fee drag — **not** win rate alone.

### Current codebase note (2026-08-30)

- No serious whale-tape module in Phase 6 core; “whale” mostly sentiment keyword weight.  
- Do **not** confuse keyword hits with order-flow edge.

---

## 6. Cross-lane synthesis

```
House always gets paid
        ↓
Minimize unnecessary round-trips (personal + product)
        ↓
Size is weather on thin names
        ↓
Default = don’t be exit liquidity (gates, anti-pump, quiet heat)
        ↓
Optional research = structure/calendar filters → only then tape features
        ↓
Never market “outsmart whales” as brand
```

**Product north star alignment:** excitement after **boring correct cycles**, not after catching a rip that dual_agree never blessed.

---

## 7. Open threads / next discussion prompts

1. Quantify **fee drag** on live book last 30–90d (realized maker/taker mix).  
2. Label historical entries as process vs reaction-heat (sample audit).  
3. Product copy pass: one paragraph “who gets paid in crypto trading” for Scale FAQ.  
4. GO/NO-GO: any whale-print shadow dig at all, or **park** in favor of fee + participation work?  
5. How discovery contenders list should be framed in UI forever (scout optics only).

---

## 8. Decision log

| Date | Decision | Note |
|------|----------|------|
| 2026-08-30 | Save as ongoing discussion | This file created |
| 2026-08-30 | Discovery cron TG off | Scout on disk; serious-consider only via dual_agree/preferred/hard CF |
| 2026-08-30 | Explore A/B/C + whale leverage | Sections 2–5; **no live implement** from this note alone |

---

## 9. Append log

### 2026-08-30 — Initial capture

- Macro premise from Brad (house / whales / reactionary small).  
- Full pass on personal book, product, venue, whale externalities.  
- Stance: leverage externalities mainly as **stand-down and structure**, not chase-the-whale heroics.

*(Append below this line.)*

### 2026-08-31 — Audits 1/2/3 completed (Brad GO overnight)

Brad: run fee drag, entry labels, Scale FAQ; no live changes.

#### Artifacts

| # | Deliverable | Path |
|---|-------------|------|
| 1 | Fee drag audit | `reports/FEE_DRAG_AND_ENTRY_LABEL_AUDIT.md` + `reports/FEE_DRAG_AUDIT_LATEST.json` |
| 2 | Entry process vs heat | `reports/ENTRY_PROCESS_VS_HEAT_LABELS_90D.json` |
| 3 | FAQ “who gets paid” | `docs/faq/External_Client_FAQ.md` + staff section in `docs/faq/Internal_Trading_Platform_FAQ.md` |
| — | Re-run scripts | `scripts/phase6/audit_fee_drag_and_entry_labels.py`, `_finalize_fee_entry_audit.py` |

#### Fee drag (verified fills, portfolio ~$2.3k NAV)

- **30d:** fees **~$139**, notional ~$16.8k → **~0.83% of notional**, **~6.1% of NAV**
- **90d:** fees **~$218** → **~9.5% of NAV**
- Fill types in set: **MARKET + STOP_LIMIT only** (no LIMIT/maker observed)
- Median fee rate ~**0.8%** → **taker-like**, not maker 0.05–0.25% schedule
- August fee/notional step-up vs June–July

**Implication for thesis:** house cut is not theoretical on this book; turnover style is already paying the toll booth hard. Maker aspiration ≠ realized path on verified ledger.

#### Entry labels (90d, n=198 buys)

| Label | n | Crude exit WR | Sum next-sell PnL (imperfect lots) |
|-------|---|---------------|-------------------------------------|
| process | 121 | 0.378 | −$25 |
| ambiguous | 70 | 0.404 | +$81 |
| process_in_elevated_tape | 5 | 0.000 | −$108 |
| heat_reaction | 2 | 0.000 | −$25 |

- Pure heat-chase rare under frozen thresholds (good).
- **Elevated-tape process** and **heat** look toxic on tiny N — do not overclaim; lot match crude.
- Many “process” rows = fresh_start / arch4_rebalance / reconcile — machinery, still can be late without tripping heat.

#### FAQ

External § *Who gets paid when you trade* — house / size / you; no whale-hero marketing; BUY ≠ promise.

#### Still open

1. Why MARKET-heavy entries vs limit/maker intent  
2. Live account fee tier vs 0.8% realized  
3. Better lot-matched round-trip after fees  
4. GO/NO-GO whale-print shadow still **not** requested — default remains stand-down/structure

### 2026-08-31 — Brad clarify: lag FOMO after size, not chase whales

**Brad (post overnight fee/entry audit):**
- Confirms leak framing: mostly **not** FOMO-by-label; leak is **late process on already-hot tape** + **taker on every turn**.
- **Not interested** in chasing whales / whale-hero product.
- Open question: whales (size) drive **post-move sentiment**, then market **reacts with lag (FOMO)** — is that lag **exploitable**?

**Working split (do not collapse):**
1. Chase the print (buy with size) → reaction game; declined.
2. Use size→sentiment→retail lag as **structure signal** — three different trades:
   - **A. Join second wave** (buy the FOMO leg) — often *becomes* exit liquidity; high adverse selection + fees.
   - **B. Fade / exhaustion** after public heat (short or avoid longs) — research-only; needs definition of heat + horizon + costs.
   - **C. Stand-down / participation filter** (don’t process-enter elevated tape) — aligns with overnight labels + product honesty; default high-EV use of the externality without needing to out-predict size.

**Exploitability bar (unknown until measured):** edge after **round-trip taker (~1.6%+ on this book style)** + slippage, on **our horizon** (rebalance/seat, not HFT), out-of-sample, frozen rules. Academic order-flow papers ≠ free edge for retail CB spot process book.

**Default until GO:** treat size/heat lag as **why gates exist** (C), not a promote path for A. B only if explicit shadow dig requested.

### 2026-08-31 — Stand-down filter C exploitability dig

**Ask:** Is C (stand-down / don’t process-enter elevated tape) exploitable on this book?

**Artifacts:** `reports/STANDDOWN_FILTER_C_DIG.md` + `.json` · `scripts/phase6/dig_standdown_filter_c.py`  
**Mode:** read-only CF · frozen defs · no live gate.

#### Method (frozen)
- Window: 90d buys · first same-pair SELL ≤21d · fees after (impute 0.8% if blank)
- **C primary:** block process-hint buys when `r24≥5` (`elev_r24_5`)
- Also tested: heat_strict / elev_r24_8 / elev_soft; arm “block all elevated”
- Sanity: drop |return|>200% tape features; tighten process_hint (no bare reconcile/signal)

#### Headline results (NAV ~$2,295)
| Slice | n exits | WR | sum PnL aft fees | avg |
|-------|---------|----|------------------|-----|
| All matched buys | 161 | 13.7% | −$761 | −$4.73 |
| Calm process | 90 | 15.6% | −$427 | −$4.75 |
| Elevated process (r24≥5) | 8 | **0%** | **−$88.51** | **−$11.06** |

**Primary C CF (process + r24≥5):** block 9 / exit 8 · avoided net **+$88.51 (~3.9% NAV)** · blocked WR **0%** · H1 n=3 avg −$4.46 · H2 n=5 avg −$15.02 (both red).  
**All-elevated arm same def:** avoided ~**$149 (~6.5% NAV)**, still 0% WR on blocked.  
**Strict heat:** N too small (inconclusive). **Soft elev:** larger N, milder Δ — weaker discrimination.

#### Verdict
- **Class:** `ATTENTION_ONLY_less_loss_path` — **not** HIT_10/20 abs.
- **GO/NO-GO live gate:** **NO**
- **Shadow-only candidate:** YES (optional log would-block at rebalance; no fill change) — Brad GO required to wire.
- **Honest limit:** Calm process was **also red**. C is “hurt less on hot tape,” not “process works when calm.” Overall book still fee/turnover taxed.
- **Not done:** capital-reuse path CF; maker entry path; longer OOS; cleaner signal_source on ledger.

**Default product stance unchanged:** C as doctrine/bias; whale chase still off.

### 2026-08-31 — C shadow logger shipped

**Shipped (no live gate):**
- `phase6/core/standdown_filter_c_shadow.py`
- `scripts/phase6/run_standdown_filter_c_shadow.py` (`--quiet-ok` / `--telegram`)
- Isolation: `phase6/core/test_isolation_standdown_filter_c_shadow.py` PASS
- State: `data/state/standdown_filter_c_shadow_latest.json` + events jsonl
- Report: `reports/STANDDOWN_FILTER_C_SHADOW_LATEST.md`

**Behavior:** scans basket tape; logs `would_block_process` when `r24≥5`. Never orders, never config, never `evaluate_buy_entry`.

**Money-print honesty:** dig + board = **less-loss stand-down**, not a printer. Calm process was also red on sample. Fees/churn still dominate. No method currently prints money on this book after fees.

### 2026-08-31 — Fills / MARKET path dig

**Ask:** Why MARKET-only fills? Live fee tier vs ~0.8% realized?

**Artifacts:** `reports/FILLS_MARKET_PATH_DIG.md` + `.json` · `scripts/phase6/dig_fills_market_path.py`

#### Code
- BUY: `OrderExecutor.execute_buy` → `place_market_buy` → `market_market_ioc`
- SELL: `protected_market_exit` → `place_market_sell` → market IOC
- `config_loader` hardcodes `order_type="market"`; fee constants 0.25/0.40 **stale**
- Live `CoinbaseExchangeClient.place_*`: market buy, market sell, stop_limit sell, bracket buy — **no `place_limit_buy`**
- Legacy `place_limit_buy` exists on old wrapper only — not on Phase6 entry path
- 90d verified: **MARKET 95 + STOP_LIMIT 80 + LIMIT 0**

#### Live fee tier (transaction_summary)
- **Intro 2** · taker **0.8%** · maker **0.4%** · vol ~$20.3k (band $10k–$25k)
- Next **Advanced 1** @ $25k → taker 0.5% / maker 0.25%
- Realized median **0.8% = tier taker** (matches)

#### Verdict
- MARKET-only = **by design**, not labeling bug
- Live maker path: **NO** without design+shadow+Brad GO
- Maker is cost reduction on buy leg only; not a printer
- Do not churn to unlock Adv1
- Still correct: no method currently prints money after fees

### 2026-08-31 — Limit-first buy design (no implement)

**Shock context:** MARKET-only was not a new regression — executor never had limit-first. March `COINBASE_FEE_RESEARCH.md` stated “we use limit orders → maker” as fact; that was aspiration. config fee constants looked like Advanced 1; live tier is **Intro 2** (0.8% taker / 0.4% maker).

**Design SSOT:** `docs/design/LIMIT_FIRST_BUY_DESIGN.md`  
**Fee research:** superseded banner → points at fills dig + design.

#### Design summary
- v1: post_only limit at bid, wait ~45s, **no** market fallback by default, no requotes
- SL only on verified filled size; cancel/fill race handled
- C elevated tape → abort (don’t maker-chase rips)
- Phases A honesty → B client/tests → C shadow → D Brad GO pilot → E promote-or-not
- EV class: cost reduction only (~0.4% buy leg ceiling); not alpha; RT still ~1.2% if exits taker

**No live code / no flag on.** Open questions in design §13 for Brad.

### 2026-08-31 — Limit-first Phase A/B shipped (flag OFF)

Brad answers locked: unfilled=**skip**, universe=**full basket**, wait=**45s**, start **A/B**.

**Shipped (no live limit fills):**
- Fee tier snapshot → `data/state/fee_tier_snapshot_latest.json` (Intro 2 confirmed 0.8/0.4)
- `place_limit_buy` + `get_order` + `get_best_bid_ask` on CoinbaseExchangeClient
- `OrderExecutor` limit branch behind `entry_execution.limit_first.enabled` (config default **false**, mode **market_ioc**)
- Isolation PASS: `phase6/core/test_isolation_limit_first_buy.py`
- Design SSOT updated: `docs/design/LIMIT_FIRST_BUY_DESIGN.md`

**Not done:** Phase C shadow board · Phase D live pilot · wiring elevated_tape into all buy callers.

**EV class:** cost-cut engineering only — not alpha / not money printer.

### 2026-08-31 — Limit-first Phase C shadow (no orders)

Board + post-market-buy CF log shipped.
- 72h first tick: N=2 market buys · notional ~$821 · fee Δ upper bound ~$3.28 (if all maker — **fill rate unknown**)
- live_gate=OFF · place_orders=False · edge=ATTENTION_ONLY_cost_cut
- Artifacts: `reports/LIMIT_FIRST_BUY_SHADOW_LATEST.md`, `data/state/limit_first_buy_shadow_*`
- Cron: phase6-limit-first-buy-shadow (local, quiet-ok)
- **Not** Phase D. Do not read Δ as saved money.

### 2026-08-31 — Limit-first Phase D pilot LIVE (Brad GO)

- Config: `mode=limit_first_v1` · `enabled=true` · post_only bid · 45s · **skip** unfilled · no market fallback
- Caps: **3 buys/day** · **$300/day** (over-cap → market IOC legacy)
- Kill: `data/state/limit_first_buy_KILL` or env `LIMIT_FIRST_BUY_KILL=1`
- Live path fix: platform `TradeExecutor` now delegates to `OrderExecutor` when limit-first ON (was market-only hole)
- Park/USDC convert: `force_market=True`
- Elevated tape: abort via C shadow best-effort
- Runner restarted PID with wire log `[P4-04] ... limit-first D`
- Board: `reports/LIMIT_FIRST_BUY_PILOT_LATEST.md`
- **Not alpha.** Cost-cut pilot. Phase E after ≥30 attempts or 14d + fill-rate/fee review.
- Edge class remains `ATTENTION_ONLY_cost_cut` / `process_cost_reduction_candidate_not_alpha`

### 2026-08-31 — Coinbase volume mix (institutional ~80%) — Brad clarification

**Source class:** Coinbase-reported Consumer vs Institutional volume (not a third "whale" bucket).

| Period | Consumer | Institutional | Inst share |
|--------|----------|---------------|------------|
| FY2025 | $239B | $982B | ~80.4% |
| Q4 2025 | $59B | $237B | ~80% |
| Q1 2026 | $36B | $166B | ~82% |
| FY2023–FY2025 avg | — | — | ~81.9% (peak ~84% FY2023) |

**Long arc:** Inst ~20% (Q1 2018) → ~56% (FY2019) → ~80%+ now. Stable split since ~2022–2023.

**Whales:** Not broken out. Large organized flow mostly sits in **Institutional** (Prime / custody / block). Some HNW still in Consumer.

**Revenue vs volume (critical for our stack):**
- Consumer effective take rate ~**1.4%** (2025 figures) vs Institutional ~**5 bps**
- Smaller retail slice → **most transaction revenue**
- Our live path = Intro 2 **0.8% taker / 0.4% maker** = firmly in the *paying-for-the-party* cohort

**Implications for Phase 6 (honest, not alpha claims):**
1. **Whale/FOMO lag as long signal** — even weaker. Public "size move" lag is often *after* institutional flow already printed; retail FOMO is the residue. Confirms prior: C as **stand-down filter**, not chase.
2. **Fee drag is structural** — we are on the high take-rate side of the venue. Cutting RT volume + maker-preferring entry (limit-first D pilot) is *house-tax mitigation*, not edge discovery.
3. **Tier climb** — only real path toward inst-like bps is volume/Prime economics; not a bot feature. Don't pretend limit-first gets us to 5 bps.
4. **No "print money" revision** — 80% inst volume does not create a retail printer; it explains why tape can look "smart" while our 0.8% legs still lose.

**Does not change:** leave book as-is; C shadow only; limit-first D caps (3/$300); no whale-follow product.

### 2026-08-31 — max_daily_loss + corr breaker contribution CF

**Question:** Do we have data that these two missed/partial rails would have moved the needle?

**Data:** `trades/phase6_trades.jsonl` realized SELL days (47d, May–Aug 2026) + rolling OHLCV corrs. Artifacts: `reports/MAX_DAILY_LOSS_CORR_BREAKER_CF.md` + `.json`. Script: `scripts/phase6/dig_max_daily_loss_corr_breaker_cf.py`.

**max_daily_loss (cfg 2% of $1k = $20; live 2% ≈ $46):**
- EOD fires: 4 days at $20, **1 day** at live-2% (2026-06-05 −$70). Never hit 5% NAV.
- CF buy-block after breach: **3 buys / ~$30 notional** blocked; fantasy buy fee ~$0.24.
- Pre-breach sell PnL on fire days **−$141** vs post **−$32** → damage mostly already locked (SL). Buy-block is pile-on brake, not loss eraser.
- Class: `ATTENTION_ONLY_less_loss_path_weak`. Honesty wire-or-delete; not a P&L unlock.

**Corr breaker (0.85 → 30% reduce):**
- Market pairs fire **~100% of sample days** (BTC–ETH etc. routinely ≥0.85) → threshold hair-trigger if applied blindly.
- Multi-pair co-loss days (2+ pairs each <−$2): **5**; fantasy 30% cut save only when loser-pair corr≥0.85: **~$21** (one day, XRP–SOL 0.853 on 2026-06-05).
- Single-name worst days (LINK −36/−30, ICP −14) untouched by corr cut.
- Class: `ATTENTION_ONLY_less_loss_path_sparse`. Keep shadow/LEGACY; do not promote.

**Rank vs known levers:** fee drag ~$139/30d ≫ C stand-down ~$89/90d ≫ corr fantasy ~$21 ≫ daily-loss buy-block residual.

**No live changes.**

### 2026-08-31 — PARK max_daily_loss + corr breaker

**Brad GO:** Park. Additional complexity for few returns (CF dig confirmed).

- **Correlation circuit breaker:** dark / LEGACY. Do **not** wire to live runner. No promote path.
- **max_daily_loss:** not a strategy project. Optional later honesty-only (wire buy-block on % live equity **or** delete theater knob). No promote / no flatten.
- **Not** on critical path next to limit-first pilot evidence, C stand-down observe, fewer RTs, exit gates.
- CF evidence: `reports/MAX_DAILY_LOSS_CORR_BREAKER_CF.md`

