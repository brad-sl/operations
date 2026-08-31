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

