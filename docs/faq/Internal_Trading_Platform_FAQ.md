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

**No — not by default.** Signals BUY/HOLD/SELL is **allocator context**, not an order. After a large free-capital event the disposition path is usually **hold cash** (plus pair rebuy cooldown). Flat option-B still only deploys small cash slices under entry gates (`rebalance_cap_usd`, RSI/sent floors). Mid-cycle `ROTATE_IN` logs are proposals, not fills.

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

*Last updated: 2026-08-16 — liquidation rotation redeploy policy + study; sentiment split*
