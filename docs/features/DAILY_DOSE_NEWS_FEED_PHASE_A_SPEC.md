# Feature Spec — Daily Dose News Feed (Phase A)

**Status:** PHASE_A_RUNNABLE — coded · disk publish only · not Telegram/dash · not trading
**Handoff:** `handoffs/platform/Handoff_FEAT-DAILY-DOSE-NEWS-20260803.md`  
**Built:** 2026-08-03  
**Date:** 2026-08-03  
**Owner:** Brad · platform / product  
**Origin session:** Telegram collab (sentiment backend Q → daily dose idea)  
**Related:**  
- Sentiment ops: skill `phase6-sentiment-pipeline`  
- RSS scorer: `fetch_rss_sentiment.py` → `data/state/rss_sentiment_cache.json` (scores only today)  
- Free shadow: `docs/FREE_SENTIMENT_SHADOW.md`  
- Strategic brief (different product): `data/state/intel_strategic_brief.json` · `/api/brief`  
- Dashboard: `serve_dashboard.py` (:8502)  
**North star (product):** Surface a short, readable set of *significant* crypto news items for humans (and later trader status pages) — **not** a new trading signal and **not** a replacement for X/RSS sentiment scores.

---

## 0. Plain English

### What problem this solves
We already pull crypto RSS for **sentiment numbers**, then throw the text away.  
Brad wants a **“daily dose”**: a few **important** stories surfaced to **dashboard and/or Telegram**, eventually next to each trader’s positions on a status page.

### What Phase A is
A **viability probe**, not a full product:

1. Fetch the same public RSS basket we already trust for free sentiment.  
2. Keep **lightweight item cards** (title, link, short summary, tickers, rank why).  
3. Rank → top **N (5–10)** per day.  
4. Write a **JSON artifact** + optional **dry-run Telegram text file** (or local-only delivery).  
5. **Human reads for ~1 week** and decides: keep / iterate / drop.

### What Phase A is *not*
- Not live trading input  
- Not blended into `sentiment_cache.json` / allocator  
- Not full article body archive  
- Not LLM-on-every-headline  
- Not trader multi-tenant pages yet (Phase C)  
- Not a replacement for `intel_strategic_brief` (that’s regime/rebalance intel)

### Success in one sentence
> “Would I actually read these 5–8 bullets with coffee for a week without muting it?”

---

## 1. Goals & non-goals

### Goals (Phase A)
| ID | Goal |
|----|------|
| G1 | Persist ranked **item cards** for inspection (24–72h rolling or daily snapshot) |
| G2 | Dedupe near-duplicate headlines across feeds |
| G3 | Bias toward **basket-relevant** and **event-shaped** stories |
| G4 | Produce a stable artifact path the dashboard/Telegram *can* consume later |
| G5 | Document quality verdict after probe window (viable / not / needs better sources) |

### Non-goals (Phase A)
| ID | Non-goal |
|----|----------|
| NG1 | Change live sentiment primary (`x_with_free_fallback`) |
| NG2 | Store full HTML article bodies |
| NG3 | Per-trader filtered pages |
| NG4 | Paid news APIs / Apify on by default |
| NG5 | Auto-post to Telegram production home without Brad OK after dry-run |
| NG6 | Use daily-dose rank as a buy/sell feature |

---

## 2. Background — current RSS backend (as of 2026-08-03)

```
~9 public RSS feeds
  → title + description/summary only (no article page crawl)
  → TextBlob polarity
  → pair keyword map (config/sentiment_keywords.json)
  → 72h half-life weights
  → OVERWRITE data/state/rss_sentiment_cache.json
     (per-pair sentiment, post_count, confidence — NO headlines kept)
```

**Feeds (working set):** CoinTelegraph, CoinDesk, Decrypt, CryptoSlate, NewsBTC, Bitcoinist, U.Today, Blockworks, Bitcoin Magazine.  
**Dropped:** DL News 404, Glassnode 403.

**Quality snapshot (live sample 2026-08-03):** Real wire-style headlines (policy, ETF, Strategy, BlackRock, hacks) mixed with noise (meme/listicle). Fine as a **firehose**; weak as a **curated brief** without ranking + dedupe.

**Implication:** Daily dose must be a **parallel artifact**, not a re-read of `rss_sentiment_cache.json`.

---

## 3. Product vision (phased)

| Phase | Name | Deliverable | Gate to next |
|-------|------|-------------|--------------|
| **A** | Viability probe | Ranked cards JSON + human read for ≥5 trading days | Brad: “worth shipping v0” |
| **B** | Ship v0 | Dashboard panel + 1×/day Telegram (after OK) | Habit loop without mute |
| **C** | Trader status pages | Same store filtered by trader symbols + positions strip | Multi-trader UX need |
| **D** | Enrich | Optional LLM one-liner on **top-N only**; extra sources if A/B thin | Cost/quality review |

This spec freezes **Phase A** only. B–D are roadmap context so we don’t lose the thread.

---

## 4. Phase A — functional design

### 4.1 Item card schema (canonical)

```json
{
  "id": "sha1(normalized_title|source|day)[:16]",
  "ts_published": "2026-08-03T12:00:00+00:00|null",
  "ts_seen": "2026-08-03T15:40:00+00:00",
  "source": "coindesk.com",
  "source_url": "https://www.coindesk.com/...",
  "title": "...",
  "summary": "≤240 chars from RSS description, stripped HTML",
  "url": "https://...",
  "tickers": ["BTC-USD", "ETH-USD"],
  "event_tags": ["etf", "regulation"],
  "scores": {
    "relevance": 0.0,
    "source_tier": 0.0,
    "event": 0.0,
    "recency": 0.0,
    "novelty": 0.0,
    "composite": 0.0
  },
  "why": ["basket:BTC-USD", "event:etf", "tier:A"],
  "cluster_id": "optional-dupe-group"
}
```

**Retention:** Phase A keeps:
- `data/state/daily_dose_latest.json` — today’s top-N + meta  
- `data/state/daily_dose_history.jsonl` — one line per run (or per day) for the probe week  
- **No** full article bodies  

Optional dry-run: `data/state/daily_dose_telegram_preview.txt` (exact text that *would* send).

### 4.2 Ingest

| Rule | Detail |
|------|--------|
| Sources | Same `FEEDS` list as `fetch_rss_sentiment.py` (single source of truth — extract shared module if implementing) |
| Fields | title, link, description/summary, pubDate |
| Soft-fail | Per-feed errors skip; never invent items |
| Dedup input | Prefer shared fetch with RSS sentiment in same process **or** sequential call; avoid double HTTP when easy |
| Max age for ranking window | Default **36h** lookback for “daily” dose (configurable 24–48h) |

### 4.3 Ranking model (deterministic, no LLM in A)

Composite score (weights frozen for probe; tune only after week-1 review):

| Component | Weight | Rule (sketch) |
|-----------|--------|----------------|
| **Relevance** | 0.35 | +1.0 if any basket ticker/keyword hit; +0.5 extra if hit ∈ open positions (if positions file readable; else 0) |
| **Source tier** | 0.15 | A: CoinDesk, CoinTelegraph, Blockworks, Bitcoin Mag = 1.0; B: Decrypt, CryptoSlate, NewsBTC = 0.7; C: other = 0.4 |
| **Event shape** | 0.25 | Keyword hits in title+summary: `etf, sec, regulat, hack, exploit, liquidat, bankrupt, unfold, rate cut, fomc, approval, lawsuit, outage, depeg, unlock, listing` (case-insensitive). Cap 1.0 |
| **Recency** | 0.15 | Exponential decay, half-life **18h** within window |
| **Novelty** | 0.10 | 1.0 if first in cluster; 0.2 if near-dupe of higher-ranked item |

**Near-dupe clustering:** normalize title (lowercase, strip punctuation, collapse whitespace); similarity via token Jaccard ≥ 0.55 **or** shared significant token set — pick one simple method and lock it in code comments.

**Top-N:** default **8** (min 3 if fewer qualify with composite ≥ threshold).  
**Floor:** drop items with composite &lt; 0.15 unless fewer than 3 items exist (then take best available and flag `thin_day: true`).

### 4.4 Outputs

#### `data/state/daily_dose_latest.json`
```json
{
  "schema_version": 1,
  "generated_at": "...",
  "window_hours": 36,
  "top_n": 8,
  "thin_day": false,
  "feeds_ok": 8,
  "feeds_total": 9,
  "candidates": 120,
  "items": [ /* item cards, ranked */ ],
  "meta": {
    "method": "rss_rank_v1",
    "basket": ["BTC-USD", "..."],
    "positions_boost": false,
    "note": "Phase A probe — not a trading signal"
  }
}
```

#### Telegram preview (Phase A default = file only)
```
Daily dose · 2026-08-03
1. Title — source
   why: basket:BTC · event:etf
   url
...
(not a trade signal)
```

### 4.5 Delivery (Phase A)

| Channel | Phase A behavior |
|---------|------------------|
| Disk JSON/JSONL | **Required** |
| Telegram preview file | **Required** |
| Telegram send | **Off** unless Brad enables a dry-run deliver once |
| Dashboard | **Out of scope for A** (Phase B). Optional read-only peek via existing static file is fine for manual open |
| `/api/brief` | **Do not overload** — different product (strategic/rebalance intel) |

### 4.6 Schedule (when implemented)

| Job | Cadence | Notes |
|-----|---------|-------|
| `run_daily_dose.py` (name TBD) | **1×/day** morning PT (e.g. 07:15) | After or independent of 08:40 free sentiment; A can be manual |
| Probe window | **≥5 trading days** | Then write viability note |

Phase A may start as **manual CLI only** — no cron until first successful local runs.

---

## 5. Explicit separation from sentiment

| Concern | Sentiment path | Daily dose path |
|---------|----------------|-----------------|
| Purpose | Numeric tilt / fallback scores | Human-readable significance |
| Storage | Aggregates only | Top-N item cards |
| Failure mode | Zeros / free fallback | Thin day / empty list OK |
| Live trading | May influence via cache | **Never** in Phase A–B without separate PRD |
| Quality metric | Correlation vs X, non-zero coverage | “Would humans read this?” |

Shared code allowed: feed list, HTML strip, keyword map, HTTP fetch helper.

---

## 6. Viability test plan (Phase A acceptance)

### 6.1 Setup
- Implement runner + schemas above.  
- Run once/day for **5–7 calendar days** (or batch backfill last 3 days if pubDates allow — optional).  
- Brad (or designee) skims `daily_dose_latest.json` or preview text each day.

### 6.2 Scorecard (fill after probe)

| Question | Pass bar | Result (TBD) |
|----------|----------|--------------|
| ≥4 useful items most days? | ≥4/5 days | |
| Dupe rate in top-N | ≤2 obvious dupes/day | |
| Noise in top-N (meme/listicle) | ≤2/day | |
| Basket relevance | ≥50% items touch book or BTC macro | |
| Time to read | ≤2 minutes | |
| Worth Phase B (dash + TG)? | Yes / No / Iterate sources | |

### 6.3 Exit decisions

| Outcome | Action |
|---------|--------|
| **Viable** | Open Phase B mini-spec; add dash panel + Telegram OK |
| **Iterate** | Adjust weights/feeds; one more probe week |
| **Not viable** | Freeze spec as rejected; keep RSS scores-only; revisit with better sources (Phase D) |

---

## 7. Implementation sketch (for when coded)

Suggested layout (not created until build):

| Piece | Path |
|-------|------|
| Shared RSS parse | `phase6/core/rss_feeds.py` (extract from `fetch_rss_sentiment.py`) |
| Ranker + writer | `phase6/scripts/run_daily_dose.py` |
| Latest artifact | `data/state/daily_dose_latest.json` |
| History | `data/state/daily_dose_history.jsonl` |
| Preview | `data/state/daily_dose_telegram_preview.txt` |
| Isolation test | `phase6/tests/test_isolation_daily_dose_rank.py` (fixture XML → stable top-N) |
| Probe report | `reports/DAILY_DOSE_PHASE_A_VIABILITY_YYYY-MM-DD.md` |

**Deps:** stdlib + existing keyword config; TextBlob **not required** for dose rank (event/relevance based).  
**OPENBLAS_CORETYPE=GENERIC** if any numpy sneaks in — prefer no numpy in A.

### CLI (proposed)
```bash
cd /home/brad/projects/crypto-trading-bot
.venv/bin/python3 phase6/scripts/run_daily_dose.py
.venv/bin/python3 phase6/scripts/run_daily_dose.py --top 8 --window-hours 36
```

---

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| RSS full of junk | Event + tier + relevance weights; hard top-N |
| Copyright / bulk store | Titles + short RSS blurb + link only; no body archive |
| Feed breakage | Soft-skip; meta `feeds_ok`; thin_day flag |
| Confused with trade signals | Banner on every artifact; no runner wiring |
| Scope creep to LLM/trader pages | Phased gates; this doc is A-only |
| Double-fetch cost | Share fetch helper with RSS sentiment when both run |

---

## 9. Open questions (resolve at build or end of probe)

1. Morning PT slot vs evening “close of day” dose? (Default: morning)  
2. Positions boost in A or wait until B? (Default: **off** in A if it complicates first run)  
3. Should Bitcoin-only macro stories always pass a floor even without alt tickers? (Default: **yes**, BTC keyword or “bitcoin” in title counts as basket-relevant)  
4. Telegram production chat vs Brad DM for B? (Defer to B)

---

## 10. Roadmap hooks (do not implement in A)

### Phase B (after viable)
- `GET /api/daily_dose` on dashboard server  
- Small UI panel (title + source + link; hover = why)  
- Cron + Telegram deliver once/day with Brad OK  
- Still not a trading input  

### Phase C
- Trader status page section: filter items where `tickers ∩ trader.symbols`  
- Place beside positions / PnL / sentiment pill  

### Phase D
- Optional LLM one-line “so what” on top-N only  
- Extra sources only if probe showed thin quality  

---

## 11. Decision log

| Date | Decision |
|------|----------|
| 2026-08-03 | Brad: Phase A is the right start; capture as feature spec before build |
| 2026-08-03 | RSS remains scores-only for sentiment; daily dose is parallel human surface |
| 2026-08-03 | No coding until explicit build go-ahead |
| 2026-08-03 | Brad go-ahead: build Phase A + handoff; disk-only publication |

---

## 12. MASTER / tracking

**MASTER id (planned, not auto_pickup):** `FEAT-DAILY-DOSE-NEWS-2026-08`  
**Type:** feature / product probe (not Type:test analyst trial)  
**Status:** PHASE_A_RUNNABLE — probe week (human skim)  
**Spec path:** `docs/features/DAILY_DOSE_NEWS_FEED_PHASE_A_SPEC.md` (this file)

When building, create handoff + optional short protocol; do **not** put on analyst test auto_pickup lane.

---

## 13. One-page checklist for implementer

- [ ] Extract or reuse RSS feed list + strip/parse  
- [ ] Emit item cards with tickers + event_tags + why[]  
- [ ] Dedupe clusters  
- [ ] Rank with frozen weights; write `daily_dose_latest.json` + history jsonl + telegram preview  
- [ ] Isolation test with fixture XML  
- [ ] Run ≥5 days; fill viability scorecard §6.2  
- [ ] Brad decide: Phase B / iterate / reject  
- [ ] **Never** wire into deploy_capital / sentiment primary in A  

---

*End of Phase A feature spec.*

---

## 14. Publication process (implemented)

### Phase A (current)
```
RSS feeds → rank → write disk artifacts
  ├─ data/state/daily_dose_latest.json          (overwrite)
  ├─ data/state/daily_dose_history.jsonl      (append run summary)
  └─ data/state/daily_dose_telegram_preview.txt (would-be TG body)
```
- **No** Telegram API send  
- **No** dashboard endpoint yet  
- **No** sentiment_cache / allocator writes  
- Human “subscribes” by reading preview/JSON or `--print-preview`

### Phase B (not built)
1. Cron 1×/day morning PT → runner  
2. `GET /api/daily_dose` + small UI panel  
3. Telegram send of preview text **only after Brad OK**

### Phase C
Filter `items` by trader symbols on status pages.


