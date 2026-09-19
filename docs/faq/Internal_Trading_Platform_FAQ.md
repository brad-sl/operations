# Internal FAQ — Trading Platform Staff

**Audience:** ops, engineers, analysts, on-call. **Not** for client portals or public help centers.  
**External counterpart:** [`External_Client_FAQ.md`](External_Client_FAQ.md)

---

## Sentiment & data sources

### Do we need Reddit in live sentiment if it’s off? What compensates?

**Short answer:** On normal days we do **not** need Reddit. Live sentiment is **X-primary**. Reddit was optional fill, not the main driver. Free RSS + funding run in **shadow** and only promote to live if X fails or is empty.

#### What actually drives rebalance decisions

| Layer | Role (current) |
|--------|----------------|
| **X (Twitter API)** | **Primary live** — refreshed ~08:50 / 20:50 PT; canonical cache typically `source: "x"` |
| **Reddit / Apify** | **Off** on cron (`SENTIMENT_REDDIT_APIFY_ENABLED=0`). Not in live scores |
| **Free hybrid (RSS + funding + F&G)** | **Shadow** ~08:40 / 20:40 PT; **live fallback only** if X empty / spend-cap / hard fail |
| **Rebalance** ~09:05 / 21:05 PT | Reads live cache (usually X warmed 10 min earlier) |

Sentiment is a **pre-rebalance input**, not a continuous mid-cycle Reddit loop.

#### When Reddit used to matter

In `refresh_sentiment` merge:

1. Fill a pair only if X was missing/zero  
2. If both existed → keep **X** score, may tag `x+reddit`

Turning Reddit off removes a **backup text channel**, not the core signal.

#### What compensates for missing Reddit

- **Normal ops:** nothing extra — X alone is enough when healthy  
- **X unhealthy:** config `sentiment.primary = x_with_free_fallback` promotes free hybrid (expanded RSS text + contrarian funding + F&G fill) into `sentiment_cache.json`  
- **Research:** expanded RSS (9 feeds, 72h half-life) correlated well vs a one-shot Reddit pull (sign agree high; single-day — not a multi-day proof). See `reports/RSS_VS_REDDIT_PROBE_2026-07-29.md`

We are **not** blending RSS into every live rebalance yet. That would be an explicit policy change.

#### Ops pointers

- Free shadow: `docs/FREE_SENTIMENT_SHADOW.md`  
- Exit automation knobs (separate topic): `docs/EXIT_AUTOMATION.md`  
- Do **not** re-enable Apify Reddit cron without budget + multi-day free gates  

---

## Dashboard KPIs (staff detail)

### Why can 7D be −15% if stops are ~3%?

**3% stop-loss is per position from that bag’s entry, not a portfolio max-drawdown.**

Deposit-adjusted **7D %** = whole-wallet NAV over a week (cash + open MTM + realized). It can be much worse than −3% because:

1. Multiple stop-outs and re-entries stack losses across cycles  
2. Open positions MTM under the stop on large bags  
3. Stop-limit fills can overshoot ~3% (gaps, fees)  
4. Missing attach on some rebalance BUYs leaves legs unprotected until recovery  

**Real SL failure** = open size with price through stop and no protective order/fill — audit exchange stops, not “7D > 3%.”

Client-safe wording: see External FAQ (no attach/recovery internals).

### What does Exit WR mean?

Share of **recent realizing exits** (nonzero PnL in the last 100 ledger rows) that won. Count-based; not 1D/7D wallet return.

### What does Util mean?

**Holdings ÷ total NAV** (non-cash share). Not ARCH-4 target exposure and not “fully invested.”

### Why is 30D N/A?

Not enough portfolio snapshot history for a 30-day baseline. Prefer **N/A** over a fake **0.00%**.

### What is SL OK?

Fraction of **open trading positions** with a protective stop estimate / attach flag — not portfolio max loss.

---

## Rotation after liquidation / free capital

### After we sell a bag (rotation or liquidation), do we immediately buy the Signals “BUY”?

**No — not by default.** Signals BUY/HOLD/SELL is **allocator context**, not an order. After a large free-capital event the disposition path is usually **hold cash** (plus pair rebuy cooldown). Deploy still needs entry gates (RSI/sentiment/cooldowns). Internal soft cash budgets exist on some paths, but they are **not** a hard per-cycle dollar ceiling (recovery/rotation can exceed them) — the dashboard does **not** promise a “cap $N.” Mid-cycle `ROTATE_IN` logs are proposals, not fills.

**2026-08-16 example:** BTC `rotation_exchange` ~$2k → cash hold / BTC cooldown → **no** follow BUY into LINK/RAVE despite tile BUY.

### Is there a defined “partial redeploy after liquidation” path?

**Yes — as product policy, default OFF.** Canonical:

`docs/features/LIQUIDATION_ROTATION_REDEPLOY_POLICY.md`

| Mode | Meaning |
|------|---------|
| `off` | **Live default** — hold / normal flat lab only |
| `shadow` | Would-fire candidate + size; log only |
| `live_partial` | At most one hop ≤ min(portion×proceeds, max_usd, cap) — **Brad + evidence only** |

Start allow-list: **rotation_exchange** proceeds only. **stop_loss_exchange** funded hops stay denied until a separate less-loss proof.

### Is immediate rotation redeploy reliable?

**On current evidence: unreliable as a default.** Ledger study (cut ≥ 2026-07-01):

- Free-cap sells ≥$50 with other-pair BUY in 24h → follow legs often hit SL; sum follow SL PnL **≈ −$242**
- BUY→SL within 72h still common (sum SL ≈ −$163 on that set)
- Early 2026-06 catch-the-wave sim was fee-sensitive at high turnover
- Immediate 6h hop is rare **by design** under hold disposition

**Verdict:** `unreliable_as_default` · **Live partial: NO-GO** until shadow gates pass.

Regenerate: `PYTHONPATH=. python -m phase6.research.run_liquidation_redeploy_study`  
Report: `reports/LIQUIDATION_REDEPLOY_STUDY_LATEST.md`

### Why not always rotate weak → strong (the June intent)?

Intent stands: cash as a **bridge**, not a sink — **if fees and second stops don’t erase the edge**. Live tape + exit asymmetry say full or aggressive hop fails that test. Product answer is **gated portion + shadow**, not silent full redeploy.

---

## Marketplace / competitor stats (staff)

### Why do some bots show 90%+ ROI and 100% win rates?

Usually **marketing showcases**, not forecasts. Tiny N, short windows, unclear capital, highlight bias. Full decoder:

`docs/marketing/copy/HOW_TO_READ_BOT_MARKETPLACE_STATS.md`

Use External FAQ / education copy for client-facing explanations.

---

## Macro structure — house, size, reaction (staff)

### Who gets paid on Coinbase flow?

| Layer | Gets paid how |
|-------|----------------|
| **Exchange** | Maker/taker fees on notional — **PnL-agnostic** |
| **Size / forced flow** | Moves thin books; retail reaction is often inventory sink |
| **Small reactionary account** | Pays fees + spread + late prices |

Client-safe copy: `docs/faq/External_Client_FAQ.md` § *Who gets paid when you trade*.  
Living discussion: `docs/discussions/MACRO_HOUSE_SIZE_REACTION_ONGOING.md`.

### Fee drag audit (operator book)

Re-run: `python scripts/phase6/audit_fee_drag_and_entry_labels.py` then `python scripts/phase6/_finalize_fee_entry_audit.py`.

Latest brief: `reports/FEE_DRAG_AND_ENTRY_LABEL_AUDIT.md`.

**2026-08-30 snapshot (live portfolio ~$2.3k NAV):** ~**$139 fees / 30d** (~**6% of NAV**), ~**0.83% of notional**; verified fills were **MARKET + STOP_LIMIT only** (no LIMIT/maker path in that set). Median fee% ~**0.8%** → taker-like, not maker schedule.

### Process vs heat entry labels

Same audit labels 90d buys: heat rules are strict (few pure heat-chases). **process_in_elevated_tape** and **heat_reaction** showed worse crude exit PnL than plain process/ambiguous in the first cut — treat as directional (lot match imperfect). JSON: `reports/ENTRY_PROCESS_VS_HEAT_LABELS_90D.json`.

### Product rules

- Do **not** brand “outsmart whales.”  
- Scout heat ≠ recommend (discovery TG local-only).  
- Gate visibility: `docs/PRODUCT_EXPECTATION_HONESTY.md`.

---

## Tryout happy path & plain-English glossary (staff)

**Context:** Phase 6 recovery / quality_tryout / luck-ladder work (2026-09).  
**Plans:** `docs/plans/2026-09-15-luck-ladder-platform-refine.md`, `docs/plans/2026-09-15-rsi-event-x-tryout-shadow.md`, `reports/LUCK_LADDER_STATUS_LATEST.md`  
**Full lifecycle (Fresh vs Takeover, Manage stages, coverage tags):** `docs/features/CRYPTO_PROCESS_LIFECYCLE.md`  
**Trader voice one-pager:** `docs/features/CRYPTO_PROCESS_TRADER_VOICE.md`  
**Takeover normalize playbook:** `docs/features/TAKEOVER_NORMALIZE_PLAYBOOK.md`  
**Mode default:** measure/shadow first; **no** live knobs, auto-buy, or promote without Brad GO.

### What is the “happy path” for a trading pair?

**Happy path** = a name travels the full money path with **gates doing their job**, not with five coin flips lining up. Designed strip:

```text
eligible door
  → RSI wash (event path, not only 09:00/21:00 clock)
  → knife OK (reclaim / no new low / not elev stand-down C)
  → sent is real (≥ tryout floor when we decide)
  → top 1–2 rank wins the $75 seat (when several flip)
  → $75 limit-first tryout + SL attached (naked-bag fail-closed)
  → episode/lot id true (buy → protective → exit attributable)
  → exit nets > fee + SL process tax (or controlled loss + cooloff)
  → size up only on graduation packet
  → regime still allows (tryout overlay; membership swaps stay OFF)
  → promote only on evidence + Brad GO
```

| Stage | What “good” looks like | What it is *not* |
|-------|------------------------|------------------|
| **Seat / door** | Tryout- or thaw-eligible; not hard-block / missfire-locked | “In the basket” ≠ bought |
| **Wash** | RSI/structure washed enough to *consider* entry | Automatic BUY |
| **Knife filter** | Reclaim / hold / not elevated-hot tape (R1 shadow) | Live block until GO |
| **Sent real** | Fresh X (or latch) ≥ tryout floor (~0.30 sleeve) at decision | Aged eng ~0 with tile “BUY” |
| **Rank** | Best qualified of top 1–2 doors | Deepest RSI only / random washed name |
| **Entry** | Micro $75, max 2 seats, limit-first, SL on | Full sleeve, market-fee grind |
| **Episode** | `bag_id` / lot ties lifecycle | Soup of unlinked fills |
| **Exit** | TP/trail/time evidence beats ride-to-SL after fees (R2) | Hope fixed TP before SL |
| **Size** | Step-up only after packet (R5) | One green tryout → full risk |
| **Regime** | Soft-down doesn’t host naked alt-wash FOMO (R6 shadow) | Auto basket swap |
| **Promote** | L2 + attribution + process book + GO | Paper green / dual_agree alone |

**Philosophy:** You cannot delete tape variance. You *can* stop manufacturing extra luck (stale sent, knife entries, SL-only exits, fee grind, wrong seat, premature size, wrong regime).

**Where the book often sits today:** doors exist; **sent / armor / RSI** still choke live fills; R0 clock + R1 knife are **shadow collecting**; exit stack is SL-heavy historically — happy path is the *target process*, not a claim that fills are flowing.

### Plain English — core terms

#### Wash

**Oversold / dipped structure** — price sold off enough that RSI (and the chart) look “washed out,” so a bounce *might* be a setup rather than a chase.

- Ops: RSI in a low band (live tryout often allows up to ~55; **RSI-event shadow** uses a stricter wash band ~≤40).
- **Wash ≠ buy signal.** It only means structure is no longer extended up — discount *or* falling knife.
- Opposite vibe: high RSI / melt-up (avoid process-buys into that without other gates).

#### Sent is real

**Sentiment is fresh and strong enough to trust at decision time** — not a stale leftover aged to ~0.

- **Sent** = sentiment score (live **X-primary**; **eng** = engineered/aged path the runner uses on tiles/gates).
- **Real** roughly means: score **≥ tryout floor** (quality_tryout sleeve **0.30**), **not aged-out**, from the **allowed sensor** (paid X path) — free/Adanos remain shadow unless policy says otherwise.
- **Not real:** eng 0.00 while Status shows BUY on RSI alone — structure without a decision-quality crowd/tape read.
- Clock fix (A1/A2): align X refresh with rebalance; short **tryout latch** after a clean X print so 15 minutes of aging doesn’t fake-close the door.

#### Thaw doors

**Time-boxed extra tryout eligibility** under recovery armor — same **micro risk caps**, wider *who may be considered*.

- Recovery mode is normally tight (ledger quality, tier rules, etc.).
- **`basket_tryout_thaw`:** temporary window allowing listed **tier B** basket seats into the tryout funnel under **$75** and **max 2 seats**; hard blocks / missfire / ledger fails still bind.
- **Door** = allowed to *compete* for a tryout — **not** “we bought it.”
- Thaw ≠ promote, ≠ full size, ≠ tier-C free-for-all. When the window expires, those seats can close again unless something else qualifies them.
- Ops: check `config/regime_cash_policy.json` → `quality_tryout.v2.basket_tryout_thaw` (enabled + expiry). Rollback: disable thaw, rewrite scoreboard, restart runner (Brad GO).

#### Knife filter

**Extra structure checks so a wash does not auto-mean “catch the falling elevator.”**

- **Knife** = still making lower lows / no bounce; buy → process tax into continuation → fast SL.
- **R1 shadow** (`phase6/core/knife_filter_shadow.py`) scores arms on R0/tryout would-buy names:
  - `rsi_only` — wash alone (baseline)
  - `rsi_reclaim` — reclaim wash pivot within N 1h bars
  - `rsi_delay_1_3` — wait 1–3 bars, no new low
  - `rsi_standdown_c` — deny when elevated-hot stand-down C tape (r24 primary spirit)
- **Measure-only** by default (`live_gate=false`): cron board + crumbs; **does not** block live buys until explicit GO.
- Read TG lines: `n_pairs`, allow counts, `rsi_only_without_reclaim` (pure knives), `sl_rate` / `mean_r_net` only when `n_r` is meaningful. Tag stays **`ATTENTION_ONLY`** until N is honest.
- Report: `reports/KNIFE_FILTER_SHADOW_LATEST.md`

### Related glossary (same funnel)

| Term | One-liner |
|------|-----------|
| **Tryout** | Micro live sleeve ($75 / ≤2 seats) under quality gates — not full deployment |
| **Door / seat** | Eligibility to be considered for tryout capital |
| **Empty funnel** | Structure or tiles look busy but **no** deployable buys (sent/armor/blocks) |
| **Process tax** | Manufactured loss path (esp. SL leakage / fee grind), not “missing alpha” |
| **Luck ladder** | R0–R6 program to remove *manufactured* luck while idle — see plan above |
| **R0 sensor clock** | RSI-wash + stale eng → shadow top-1–2 would-query; no paid X/orders until GO |
| **Limit-first** | Resting limit preferred; unfilled = skip rather than pay taker for thin edge |
| **Episode / bag_id** | Lot identity across buy → SL → exit → ledger |
| **Promote** | Shadow/paper → live membership or exit path — **Brad GO + evidence only** |
| **dual_agree** | Paper arm agreement signal — **≠ promote** |
| **live_membership_swaps** | Auto basket swap from arms — **stays false** unless Brad GO |

### Ops pointers (happy path / luck ladder)

- Status board: `reports/LUCK_LADDER_STATUS_LATEST.md`  
- Kanban hub: `crypto-bot-project` · `LUCK-LADDER-20260915` / `t_529fe799`  
- R0 cron: `phase6-rsi-event-x-tryout-shadow` · R1 cron: `phase6-knife-filter-shadow`  
- Tryout readiness: `reports/TRYOUT_READINESS_LATEST.md`  
- Cron SSOT: `docs/HERMES_CRON_SSOT.md`  
- Must not from this FAQ alone: paid X probe, live knife block, exit `live_apply`, thaw extension, floor cuts, membership swaps on

---

*Last updated: 2026-09-15 — tryout happy path + wash/sent/thaw/knife glossary; prior 2026-08-30 macro/fee sections retained*
