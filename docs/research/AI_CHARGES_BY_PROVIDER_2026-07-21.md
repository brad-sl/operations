# AI / data charges by provider — vendor evidence 2026-07-20/21

**Sources:** OpenRouter CSV · Apify Billing screens · **X API payment txs (Jul 12–19)** · Hermes agent.log (xAI tokens; $ TBD)

## Executive ranking (what actually hits the card)

| Rank | Provider | Evidence | Burn | Status after our fixes |
|------|----------|----------|------|------------------------|
| **1** | **X Developer API** | **11 × $25 = $275** Succeeded VISA top-ups **Jul 12–18** (filter Jul 12–19) | **~$39–42/day** during high-freq era | Cut to **2×/day** from ~Jul 19; expect sharp drop — verify next window |
| **2** | **xAI / Grok API** | Usage **Jul 13–20: $95.69** total · avg **$11.96**/day · peak **$59.29** (Jul 16) · Jul 19 **$2.16** | **Spiky #2** — one bad day ≈ $60 | Phase1 cuts; target avg ≤$5–8 |
| **3** | **Apify** | Period Jun 30–Jul 30 **$70.66** (Actors $70.55; scrapesmith **$58.85**) | **~$2–3.5/day** avg; overage $41.66 | **Kill-switched OFF** |
| **4** | **OpenRouter** | CSV last 7d | **~$0.75 / 7d (~$0.11/day)** | Keep aux flash only |

**“>$50/day” explained:** X auto top-ups **~$40/day** steady + Grok **can spike to $59** (Jul 16) + Apify. Stacked peak days easily clear $50. OpenRouter is noise.

---

## X Developer API (screen: transactions Jul 12–19)

All **Succeeded** · **VISA …0320** · **$25.00** each:

| # | Date (UTC) | Amount |
|---|------------|-------:|
| 1 | Jul 18, 2026, 11:53 PM | $25 |
| 2 | Jul 18, 2026, 01:34 AM | $25 |
| 3 | Jul 17, 2026, 10:04 AM | $25 |
| 4 | Jul 16, 2026, 06:34 PM | $25 |
| 5 | Jul 16, 2026, 04:00 AM | $25 |
| 6 | Jul 15, 2026, 12:34 PM | $25 |
| 7 | Jul 14, 2026, 10:04 PM | $25 |
| 8 | Jul 14, 2026, 05:34 AM | $25 |
| 9 | Jul 13, 2026, 02:34 PM | $25 |
| 10 | Jul 12, 2026, 10:34 PM | $25 |
| 11 | Jul 12, 2026, 06:34 AM | $25 |
| | **Visible total** | **$275** |

- Cadence: roughly **1–2 top-ups/day** while search was dense → **~$35–50/day** card pace matches your complaint.
- Aligns with logs: **~48 refresh/day through ~Jul 17**; policy 2×/day only clean from **~Jul 19**.
- **Action:** leave X at 08:50/20:50 only; after 3–5 days post-cut, re-check same UI (expect <<$25/day if pay-as-you-go tracks usage). If top-ups continue at $25/day after cut, something else is still calling X — audit then.

---

## Apify (invoices + usage — same as prior shot)

| Item | $ |
|------|--:|
| Platform usage Jun 30–Jul 30 | **70.66** |
| scrapesmith results 73,560 × $0.0008 | **58.85** |
| fatihtahta fast results | 7.99 |
| Actor starts | 3.71 |
| Visible invoices page (mixed May–Jul top-ups + $30 monthly) | ~225 listed p1 |

**Do not increase Apify limit.** Code kill-switch is live.

---

## OpenRouter (CSV) — last 7 days

**Total ~$0.75** · Gemini 2.5 Flash $0.55 · DeepSeek V4 Flash $0.20 · not material.

---

## xAI / Grok console — detail usage **Jul 13–20, 2026** (API keys team view)

| Metric | Value |
|--------|------:|
| Window total | **$95.69** |
| Average | **$11.96**/day |
| Peak day | **$59.29** (Jul 16) |
| Credits remaining (prior overview) | **$8.62** |

### Daily Cost (USD) — All APIs

| Date | Cost |
|------|-----:|
| Jul 12 | $0.00 |
| Jul 13 | $5.06 |
| Jul 14 | $8.43 |
| Jul 15 | $0.48 |
| **Jul 16** | **$59.29** |
| Jul 17 | $13.76 |
| Jul 18 | $6.52 |
| Jul 19 | $2.16 |
| **Sum (table)** | **$95.70** |

- Filter UI: **All** (Text / Voice / Image / Grok Build available as separate tabs).
- **Jul 16 spike** = main Grok bill risk (heavy agent/tool day; also same night as OR DeepSeek long tool loop in CSV).
- **Jul 19 $2.16** already much healthier — aligns with fewer long sessions / early Phase1 hygiene.
- Ex-peak average (drop Jul 16): ~($95.69 − $59.29) / 6 ≈ **$6.07**/day — still real, manageable with discipline.
- **Implication for “>$50/day”:** Grok can **single-day** hit ~$60, but week average ~$12. X top-ups (~$40/day that week) were the steadier card burn; Grok is **spiky second place**.

### Actions (Grok) — reinforced
1. Prefer **short `/new` sessions**; avoid 100k-context chains.
2. Keep **delegation / Kanban on `grok-build-0.1`**; chat = composer only when interactive.
3. No overnight goal workers; max turns capped (Phase1).
4. Watch next Jul 20–27 window — target **avg ≤$5–8/day**, peak **≪$20**.
5. Optional: check **Grok Build** tab alone vs Text API to see which surface ate Jul 16.

---

## Target envelope (post-fix)

| Surface | Target |
|---------|--------|
| X API | ≪$5–10/day at 2×/day (verify) |
| Apify | **$0** (disabled) |
| OpenRouter | ≤$0.50/day |
| Free shadow | $0 |
| xAI | sub-included preferred; else measure |

**Combined sustainable target:** ≤$10–15/day once X post-cut confirms + Grok known.

---

## Refs
- Kill-switch: `fetch_reddit_sentiment.py`, `refresh_sentiment.py`
- Shadow: `docs/FREE_SENTIMENT_SHADOW.md`
- Plan: `docs/research/COST_REDUCTION_EXECUTION_PLAN_2026-07-20.md`
