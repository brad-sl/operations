# Trajectory gap score — 2026-07-29

**Trigger:** Still ~−3.2% 7D after course corrections (~2 weeks). Reexamine SL / exit / rebalance triggers vs prior proposals.  
**North star:** better returns **and** less loss; reliable platform path > lottery bag picks.  
**Live config writes from this note:** none.

## Live snapshot (as_of refresh)

| Metric | Value |
|--------|-------|
| 1D / 7D / 30D (dep-adj) | −0.42% / **−3.15%** / −28.8% |
| Equity path window / recent7 / slope | −8.44% / −3.05% / **−0.42%/d** |
| Health | **Declining** |
| Exit WR (ledger nonzero) | **5/53 (9.4%)** |
| Book | ~$2507 · cash ~$1302 · **LINK only** ~$1205 (+~0.4%) · util **48%** vs park target 45% |
| Regime | **transition / usdc_park** · buys blocked · cap $0 · enforce true |
| Trend-repair layer | `churn_or_legacy_drawdown` |
| Manual cash hold still on books | ~$519 |

## What course corrections actually did (~Jul 17–27)

| Change | Status | Effect on path |
|--------|--------|----------------|
| REGIME-CASH enforce + transition PARK | Live | Stops *new* buy churn **now**; did not erase prior inventory damage |
| `capital_event_force_rebalance: false` (Jul 24 Tier0) | Live | Stops deposit same-cycle redeploy |
| TREND_REPAIR measure + playbook | Live | Diagnosis OK; no auto capital moves |
| Tier1 SOL park-soft glide (Jul 25) | **Executed once** (~$232 SOL) | Reduced SOL book; residual SOL later SL’d Jul 27 (−$18) |
| Transition deploy / faster-flip test | **drop** (Jul 27) | Offline: park/USDC beats higher util on transition |
| Kelly sizing | **drop** (Jul 21) | Recent edge non-positive — do not lean-in size |
| SL attach / settlement / fill recon | Shipped earlier Jul | SL **fires**; problem is **what** we realize, not “SL never works” |

## 21d ledger shape (unique rows; real data)

- **stop_loss_exchange:** n≈49, **sum pnl ≈ −$90** (ADA/ARB/AVAX/DOGE/OP/SOL/XRP)
- **rotation_exchange:** n≈5, **sum pnl ≈ +$38** (BTC/ETH/UNI/XRP/OP — clustered ~Jul 21)
- Realized WR ~**9%** — system **banks losses via SL** far more often than it **banks winners**
- Late re-entries still happened under rebalance: **OP Jul 20, SOL Jul 23, LINK Jul 19/23** — SOL Jul 23 → SL Jul 27 at ~−6% is the clean micro-case of “buy then stop”

**Interpretation:** 7D red is **not** “3% SL broken on LINK.” LINK is flat-green and util is already near target. Path red is **legacy + SL-as-primary-exit asymmetry + residual bag MTM**, with park correctly blocking new risk.

## Prior proposals — what landed vs what’s still missing

| Proposal / surface | Landed? | Gap |
|--------------------|---------|-----|
| Park / buy gates (REGIME-CASH) | **Yes** | Entry side largely fixed under transition |
| Force rebalance off | **Yes** | Tier0 done |
| SL preflight / attach / ledger truth | **Mostly yes** | Coverage KPI ~1.0 on open book; dust SL noise remains |
| `prefer_exit` + exit knobs in `regime_cash_policy.json` | **JSON only** | Soft helper; **not** wired into live TradePlan SELLs |
| Tier1 glide automation | Draft + one manual OK | No recurring rules-based util glide in runner |
| Take-profit | **`take_profit_pct: null`** | Code path exists (`attach_take_profit`) but **disabled** live |
| SL → cash hold | **`capital_event_stop_loss_exchange_hold_cash: false`** | Only **24h** rebuy block — weak vs re-entry churn when park not binding |
| Trailing / breakeven ratchet | Partial allocator research language | Not a hard live exit product |
| Catch gainers under transition | Offline **reject** | Higher util loses on DD; idle cash not the dominant bug |
| Analyst learnings → allocator loop | Accepted backlog, not closed loop | Learnings still observational |
| OHLCV freshness | Live BTC merge works | Base OHLCV still lag ~18d — hygiene, not main PnL |

## Probability score — missing drivers of continued down trajectory

Scores = P(this gap is a **material** driver of the last ~14d path **and** fixing it would bend slope), conditioned on current evidence. Sum >1 because factors interact.

| Rank | Gap | P | Why |
|------|-----|---|-----|
| 1 | **Exit asymmetry: SL realizes losses; no systematic profit-taking** | **0.38** | TP null; wins almost only via rare rotation; Exit WR 9%; 21d SL −$90 vs rotation +$38 |
| 2 | **`prefer_exit` / hard exit knobs not live-wired** | **0.22** | Policy documents overbought RSI / weak sentiment exits; runner only **filters BUYs**; Tier1 is offline draft |
| 3 | **Re-entry after SL / rebalance while park incomplete (Jul 19–23 pattern)** | **0.18** | Documented SOL/LINK/OP buys then stops; SL hold-cash false; 24h block insufficient historically |
| 4 | **Single-name residual beta (LINK ~48% util) with no multi-leg upside under PARK** | **0.12** | Path still moves with one bag; “catch gainers” structurally off — by design after transition drop |
| 5 | **No trailing lock / breakeven after green** | **0.10** | Adaptive SL range 1.5–5% exists; no evidence of profit-protect ratchet on winners before giveback |
| 6 | **3% SL “too tight” as root cause** | **0.06** | SL is doing its job; tightness without TP creates negative expectancy when edge p is low — secondary to missing wins |
| 7 | **Need Tier2 transition micro-deploy to stop bleed** | **0.04** | Jul 27 offline: deploy util raises DD ≫ return; **do not** thaw on hope |
| 8 | **Regime mislabel from OHLCV lag** | **0.03** | Live merge keeps transition; BTC ~+11% still below bull 15% |

### What is **not** the main story

- “SL coverage failed on the open book” — open LINK has estimated stop; SL OK metric 1.0  
- “7D −3% proves every leg lost >3%” — wallet path ≠ per-leg stop (playbook)  
- “Park is the bug because we miss gainers” — tested; deploy costs more DD than idle under transition  

## Trajectory reading (plain)

1. **Controls reduced whip** (fewer multi-bag death spirals) but **did not create a positive expectancy exit stack**.  
2. **Smoothing ≠ winning** — still true; last7 (−3%) is actually **worse** than older segments in the current path split (legacy narrative of “recent better than window” is weak today: recent −3% vs window −8% only because deep July damage sits in the longer window).  
3. Under PARK with util≈target and one flat bag, **further inventory glide is low leverage**. The missing product is **how winners exit and how losers stop recycling**, not another buy gate.  
4. **Catching gainers** requires either (a) regime leave transition/bull with evidence, or (b) a **separate**, tiny, gated optionality sleeve — not loosening SL blindly.

## Recommended trajectory (ranked actions)

### P0 — instrument + decide (no hope-thaw)

1. **Exit-asymmetry trial (Type:test instrumentation)**  
   - Label every realizing sell: `stop_loss_exchange` | `rotation` | `tier1_glide` | `tp` | `manual`  
   - Track: win rate by reason, avg win/loss, time-to-exit, re-entry within 24–72h  
   - Success: clear attribution that TP/trailing or hard_exit would have changed path (counterfactual on real marks)

2. **Wire `prefer_exit` hard reasons → optional SELL legs in coordinator** (shadow first)  
   - Hard only: RSI ≥ overbought **or** sentiment ≤ max_sentiment_hold  
   - **Do not** auto-fire `park_prefer_reduce` without Brad (lottery risk)  
   - Isolation test + shadow log 7d before live

3. **Under repair: `capital_event_stop_loss_exchange_hold_cash: true`** (or extend rebuy block 72h) while transition PARK  
   - Closes the Jul 20–23 class of bleed if park ever softens or flat option B returns

### P1 — profit side (the actual hole)

4. **Shadow / tiny-live take-profit or trailing lock**  
   - Start research: fixed TP 6–8% **or** trail after +4% to breakeven+fees  
   - Live `take_profit_pct` stays null until offline + shadow gates  
   - Score with north star: WR up **and** path DD not worse

5. **Fresh Tier1 draft only if util ≫ target or hard_exit fires**  
   - Today util~48% / LINK green → **no mandatory glide**

### P2 — do not do without new evidence

6. Transition micro-deploy / enforce:false / raise cap — **rejected** Jul 27  
7. Kelly lean-in deploy_pct — **rejected** Jul 21  
8. Widen SL alone to “let winners run” without TP/trail — likely **worse** given p≈0.19 recent Kelly window

## Evidence clocks (from playbook)

- Claim stabilizing: ≥14d recent_path ≥0 or slope improving  
- Tier2 design: ≥14d slope >0 and window not collapsing  
- Current: **not met** (declining, recent −3%)

## Operator one-liner

**Bleed source shifted from “buy the dip forever” to “only the stop exit prints, and it prints red.”** Park was necessary; **exit stack + anti-rebuy** are what’s missing to bend the path. Catching gainers is a **later regime/optionality** problem, not today’s first lever.
