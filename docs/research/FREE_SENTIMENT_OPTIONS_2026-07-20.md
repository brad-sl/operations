# Free / Near-Free Crypto Sentiment Options — Phase 6 Backstop for Paid X

**Date:** 2026-07-20  
**Status:** Research only (no live config changes)  
**Goal:** Replace or backstop paid X API sentiment while keeping **reasonable confidence** for Phase 6 pair-level scores.  
**Constraints:** Essentially free · not pure noise · prefer existing scorer cache schema · zeros already mean “no signal” (never invent prices or fake sentiment).

**Related:** `docs/X_SENTIMENT_COST_CONTROL.md`, `docs/SENTIMENT_STRATEGY_SPEC.md`, `docs/research/COST_REDUCTION_EXECUTION_PLAN_2026-07-20.md`

---

## 0. Current Phase 6 reality (in-repo)

| Piece | Location / behavior |
|-------|---------------------|
| Primary fetch | `fetch_x_sentiment.py` → TextBlob polarity, writes `data/state/x_sentiment_cache.json` (rich: `sentiment`, `post_count`, `confidence`) |
| Reddit fill | `fetch_reddit_sentiment.py` (Apify `scrapesmith/reddit-scraper`) → `reddit_sentiment_cache.json`; often **all zeros** today |
| Merge | `phase6/scripts/refresh_sentiment.py` → canonical `data/state/sentiment_cache.json` **schema_version 3** |
| Loader | `phase6/core/sentiment_scorer.py`: X primary; Reddit only if posts>0; file fallback if still zero; aging **half-life 60 min** |
| Score range | Effective **[-1, +1]**; labels at ±0.1 / ±0.3; weight adj `base * (1 + 0.2 * sent)` |
| Cadence | X **2×/day** ~08:50 / 20:50 PT (pre-rebalance); Reddit every 2h |
| Basket | ~11 pairs (`BTC/ETH/SOL/XRP/DOGE/ADA/AVAX/LINK/UNI/ARB/OP-USD`) |
| Zero semantics | **No signal** — do not treat as “neutral conviction” |

### Canonical cache schema (must preserve / extend compatibly)

```json
{
  "timestamp": "ISO-8601",
  "schema_version": 3,
  "sentiment": {
    "BTC-USD": { "sentiment_score": 0.10, "source": "x" }
  },
  "meta": { "source": "...", "basket_size": 11 }
}
```

Optional forward-compatible fields per pair (scorer already tolerant of extra keys):  
`confidence`, `post_count`, `source_detail`, `tier` (`A|B|C`).

### Historical gold for validation (local)

| Asset | Span | Notes |
|-------|------|-------|
| `data/phase6.db` → `sentiment_scores` | **2026-06-12 → 2026-07-20** | ~**164k** rows |
| Sources | `x` (~15.7k, mean score ~0.17), `runner` (~148k), sparse `apify` | Pair coverage strong on majors |
| Live snapshot 2026-07-20 | X non-zero on most pairs; Reddit cache all 0.0 | Confirms Reddit is not carrying load |

---

## 1. Ranked options (2026-07 research)

Ranking = fit for **essentially free + pair-level Phase 6 + confidence**, not vendor marketing.  
Costs and free tiers checked ~2026-07; re-verify before build.

| Rank | Source | Cost (2026-07) | Pair-level? | Latency | Confidence | ToS / risk | Integration effort |
|------|--------|----------------|-------------|---------|------------|------------|--------------------|
| 1 | **Bybit public funding + OI** (perp tickers) | **$0** public REST | **Yes** (map `BTCUSDT`→`BTC-USD`) | Seconds–minutes | **Med–high as positioning proxy** (not social text) | Low (public market data); **Binance blocked** from some geos (this host got CF/country block) | **Low** — new fetcher + map |
| 2 | **Alternative.me Fear & Greed** | **$0**, no key (`api.alternative.me/fng/`) | **No** (market-wide; BTC-centric composite) | **Daily** (~00:00 UTC refresh) | **Med–high macro regime** | Low; attribution polite | **Very low** |
| 3 | **RSS/Atom crypto news + local TextBlob/VADER** | **$0** (Cointelegraph, CoinDesk RSS verified reachable) | **Partial** via keyword/ticker map | Minutes–hours | **Low–med** (headline noise; better for shocks) | Low if feed ToS allow non-commercial aggregation | **Med** — parser + keyword map (reuse `sentiment_keywords`) |
| 4 | **StockGeist crypto** | **Free:** 10k REST credits/mo + **1 free crypto SSE stream forever**; packs from ~$75 | **Yes** (400+ coins) | Real-time stream / REST | **Med** (multi-source social; need calibrate vs X) | Confirm commercial clause for bot use | **Med** — new client; SSE optional |
| 5 | **Adanos Reddit crypto** | **Free 250 req/mo**; Hobby $29; Pro $299 | **Yes**; `sentiment_score` already **[-1,1]** + buzz | **Hourly** | **Med** (Reddit-only; transparent BuzzScore) | Free/Hobby non-commercial; commercial on Pro | **Low–med** — `/v1/compare?symbols=` ≈ 2 calls/day for 11 pairs |
| 6 | **Existing Apify Reddit** (status quo fill) | Apify Free **$5/mo credit**; actors ~$3–4/1k results; Starter $29 if over | **Yes** when posts found | Hours (2h cron) | **Med when non-empty**; **currently often zero** | Actor + Reddit ToS gray | **Done** — improve actor/params or replace |
| 7 | **In-repo Direct Reddit JSON + VADER** (`phase6/core/sentiment/direct_reddit_fetcher.py`) | **$0** | **Yes** | Minutes (rate-limit sleep) | **Med** if not blocked | **High** — Reddit blocks unauth JSON (403 observed); ToS / commercial risk | **Low code** / **high ops risk** |
| 8 | **CoinGecko free Demo** (trending + markets) | **$0** Demo ~10k calls/mo, attribution | **Partial** (trending buzz, not polarity) | Minutes | **Low as polarity**; **med as attention** | Attribution required; commercial → paid | **Low** |
| 9 | **Santiment free GraphQL** | **1k calls/mo**, lagged history | **Yes** | ~5 min (paid real-time) | **Med–high metrics** if quota enough | Free heavily gated; resale needs corporate | **Med–high** (GraphQL + metric ACL) |
| 10 | **Google Trends (pytrends)** | **$0** unofficial | Partial (search interest) | Hours; flaky | **Low–med** slow signal | Unofficial; 429s / breakage common 2026 | **Med** fragile |
| 11 | **Local LLM classify free text dumps** | **$0** CPU if small model available | Yes if text gathered | Slow on CPU | **Med** if good prompt + cal | Depends on text source ToS | **High** |
| 12 | **LunarCrush** | Free = **market data only**; social ~**$72–90/mo** | Yes | Near real-time | High social breadth | Paid for sentiment | **Skip for free stack** |
| 13 | **CryptoPanic API** | Free Developer **discontinued ~2026-04-01**; Growth **~$199/mo** | Yes (currencies + votes) | Real-time paid | Med | Paid only now | **Skip for free** |
| 14 | **CryptoCompare / CoinDesk social** | Free key often required; social endpoints metered | Partial | Varies | Med | License / key | Low priority |
| 15 | **Paid X API (current primary)** | Was **$50–75/day** when stacked; policy cut to **2×/day** | Yes | Minutes | **Highest social trader signal** in stack | Official | Keep as **optional Tier S** if budget returns |

### Notes on live probes (this host, 2026-07-20)

- F&G API: **value 29 (Fear)** — works, no key.  
- CoinGecko trending: works (ADI, PENGU, …, BTC, SOL).  
- Cointelegraph / CoinDesk RSS: HTTP OK.  
- Binance futures public: **geo-restricted** here → prefer **Bybit** (or Coinbase Advanced if already credentialed for trading — funding may differ).  
- Reddit public JSON: blocked / 403 without careful UA + backoff.  
- Reddit Apify cache: all pairs **0.0** at sample time.

---

## 2. Recommended hybrid stack (“essentially free”)

Design principle: **stack independent signal families** so one outage does not zero the basket, and **never invent scores**. Prefer damping weak sources toward 0 (already how X `min_posts` / `confidence` works).

### Confidence tiers

| Tier | Role | Sources | Weight in merge (suggested) | When used |
|------|------|---------|-----------------------------|-----------|
| **S** (optional paid) | Trader social primary | X API 2×/day | 1.0 if non-zero | Budget allows |
| **A** | Pair social / text | StockGeist stream **or** Adanos compare **or** RSS+VADER mapped | 0.7–1.0 | Default free primary |
| **B** | Pair **positioning** | Bybit funding rate + OI Δ (optional L/S if free) | 0.4–0.6 as additive / fallback | Always free; orthogonal to text |
| **C** | Market-wide regime | Alternative.me F&G (+ optional CoinGecko BTC.D / trending breadth) | Cap |±0.15| as soft bias only when A&B empty | Backstop so basket not all-zero in panic/euphoria |
| **R** | Reddit legacy | Apify or Direct Reddit | Same as today: fill zeros only | Keep until A stable |

### Concrete free default (no X spend)

```
For each pair:
  1. A_text  = StockGeist (preferred) OR Adanos OR RSS+VADER   # pair polarity [-1,1]
  2. B_pos   = f(funding_z, oi_change_z) clamped to [-0.5, 0.5]
  3. If A_text != 0:  score = 0.65*A_text + 0.35*B_pos
     Elif B_pos != 0: score = B_pos * 0.8   # positioning-only, damped
     Else:            score = C_fg_bias * pair_beta   # see below; may still be 0
  4. confidence = g(volume, agreement(A,B), age)
  5. If confidence < 0.15 OR insufficient samples: score *= damping → often ~0
```

**F&G → pair bias (Tier C only):**

```
fg ∈ [0,100]
c_raw = (fg - 50) / 50          # [-1, +1]
c_damped = 0.15 * c_raw         # never dominate pair ranking
pair_beta: BTC/ETH 1.0, large alts 0.7, thin alts 0.4
# Apply only when A and B both empty for that pair (or as tiny additive ±0.05 max always — prefer empty-only)
```

### Why this is “reasonable confidence” not noise

1. **Orthogonal families:** text social ≠ perp positioning ≠ daily F&G composite. Agreement increases confidence.  
2. **Zeros remain legal:** thin alts with no headlines and flat funding stay 0 → scorer already treats as no signal.  
3. **Macro without pair fiction:** F&G never fabricates LINK vs UNI dispersion; it only unblocks total blackout.  
4. **Calibrate once vs X history** in DB (section 4) before cutting X.

### Cost envelope (target)

| Component | Est. monthly $ |
|-----------|----------------|
| F&G + Bybit + RSS + CoinGecko Demo | **$0** |
| StockGeist free credits/stream | **$0** (watch credit burn; 2×/day × 11 ≪ 10k) |
| Adanos free 250/mo | **$0** if ≤ ~4 compare calls/day (use batch compare) |
| Apify Reddit every 2h | **$0–5** on free credit; often waste if zeros — **throttle to 2×/day** with A |
| X API | **$0** if paused; optional restore 2×/day |
| **Total free path** | **~$0–5/mo** infra |

---

## 3. Phase 6 integration design (files + fallback order)

### 3.1 Fallback order (loader / merge)

Match mental model of today’s scorer; extend without breaking consumers:

```
load_sentiment_scores(universe):
  1. X cache (if enabled & fresh)           # Tier S
  2. Free social cache (StockGeist/Adanos/RSS)  # Tier A — NEW
  3. Reddit/Apify (posts > 0 only)         # Tier R
  4. Positioning cache (funding/OI)        # Tier B — NEW (or blend earlier)
  5. Canonical file non-zero leftovers
  6. Optional F&G soft-fill only if still zero  # Tier C
  7. Leave 0.0
get_aged_sentiment_scores(..., half_life=60)
```

**Do not** average F&G into strong pair scores.  
**Do** record `source` as: `x | stockgeist | adanos | rss | funding | fng | reddit | hybrid`.

### 3.2 Files to touch (implementation phase — not done in this research)

| Action | Path |
|--------|------|
| **New** | `fetch_funding_sentiment.py` — Bybit `v5/market/tickers` linear; map symbols; write `data/state/funding_sentiment_cache.json` |
| **New** | `fetch_fng_sentiment.py` — alternative.me; write `data/state/fng_cache.json` (market + optional per-pair expansion at merge) |
| **New** | `fetch_rss_sentiment.py` — feeds + TextBlob/VADER + `phase6/core/sentiment_keywords.py` |
| **New (pick one A)** | `fetch_stockgeist_sentiment.py` **or** `fetch_adanos_sentiment.py` |
| **Extend** | `phase6/scripts/refresh_sentiment.py` — call free fetchers; merge order above; set `meta.sources` |
| **Extend** | `phase6/core/sentiment_scorer.py` — load free caches before Reddit; keep zero gate + aging |
| **Config** | `sentiment_config.yaml` or `config/trading_config_phase6.json` flags: `x_enabled`, `free_stack_enabled`, source weights |
| **Cron** | Prefer **08:45 / 20:45 PT** free stack (before rebalance); drop Reddit 2h → 2×/day once A works |
| **Optional** | Wire existing `direct_reddit_fetcher.py` only behind feature flag + circuit breaker on 403 rate |
| **Tests** | Extend `phase6/core/test_sentiment_zero_gate.py` / failover tests for hybrid zeros |

### 3.3 Suggested per-source → score maps

| Source | Raw | Map to `sentiment_score` |
|--------|-----|---------------------------|
| Text / Adanos / RSS / TextBlob | polarity or vendor `sentiment_score` | clip [-1,1]; damp if mentions < N |
| StockGeist pos/neu/neg | fractions | `(pos - neg) / max(pos+neu+neg,1)` |
| Funding rate | e.g. +0.01% / 8h | `tanh(funding / k)` with k≈0.0005–0.001 (calibrate); **positive funding → crowded long → slightly bearish contrarian OR momentum** — **pick one policy and lock after backtest** (default proposal: **mild contrarian** for rebalance weights: `score = -tanh(funding/k)`) |
| OI change 24h | % | small additive ±0.1 on direction of price if available — else skip |
| F&G | 0–100 | see Tier C only |

**Policy note:** Funding-as-sentiment is ambiguous (momentum vs contrarian). Default for Phase 6 **weight tilt** should be validated in section 4; if correlation with future returns is wrong-signed, flip sign once.

### 3.4 Schema extension (backward compatible)

Keep `schema_version: 3`. Optional:

```json
"BTC-USD": {
  "sentiment_score": 0.12,
  "source": "hybrid",
  "components": {
    "text": 0.18,
    "funding": -0.05,
    "fng": 0.0
  },
  "confidence": 0.41,
  "tier": "A"
}
```

Scorer continues to read `sentiment_score` only unless upgraded.

### 3.5 Cadence vs rebalance (PT)

| Time | Job |
|------|-----|
| 08:45 / 20:45 | Free stack refresh (A+B+C) → merge canonical |
| 08:50 / 20:50 | Optional X (if enabled) → overwrite non-zero pairs |
| 09:00 / 21:00 | Rebalance (aged scores, 60m HL → ~0.89–0.94 decay if 10–15 min old) |
| Midday | Optional cheap A/B refresh **without** X (no need every 2h if cost is $0) |

---

## 4. Backtest / validation plan (correlation vs last 30–60d X — not live trading change)

### 4.1 Data available

- Gold: `sentiment_scores` where `source IN ('x','x_refresh')` and/or runner snapshots aligned to rebalance times.  
- Span: **~2026-06-12 → 2026-07-20** (~5–6 weeks continuous; denser mid-July).  
- Also: `data/state/x_sentiment_cache.json` snapshots are thin; **prefer DB**.  
- Prices: existing Phase 6 OHLCV / ledger paths (no synthetic prices).

### 4.2 Offline experiment design

1. **Replay free fetchers historically where possible**  
   - F&G: free history `?limit=0` / high limit — full daily series.  
   - Funding: Bybit/Binance historical funding endpoints (Bybit preferred if Binance geo-blocked).  
   - Adanos: free history window ~30d on free tier — partial.  
   - StockGeist: free credits for recent window only.  
   - RSS: generally **not** deep history → skip or use only forward paper window.

2. **Align timestamps** to PT rebalance slots 09:00 / 21:00 (and 08:50 X stamps).

3. **Metrics (per pair and basket-average)**  
   - Pearson / Spearman **corr(free_score, x_score)** at same stamp.  
   - Sign agreement rate: `sign(free)==sign(x)` when both \|score\| > 0.1.  
   - Coverage: fraction non-zero vs X non-zero.  
   - **Forward** 12h/24h return correlation of free vs X (which predicts better?) — research only.  
   - Weight-path stability: `get_sentiment_adjusted_weights` with free vs X → L1 distance of weights.

4. **Gates before cutting X**

| Gate | Pass criterion (suggested) |
|------|----------------------------|
| G1 Coverage | Free stack non-zero on ≥60% of pair-stamps where X was non-zero |
| G2 Correlation | Basket mean \|Spearman\| ≥ 0.25 **or** sign agreement ≥ 55% on \|x\|>0.1 |
| G3 Not anti-signal | Free 24h return corr not significantly opposite to X’s |
| G4 Zero honesty | No increase in “false neutral” that forces bad full-risk when X would have damped |
| G5 Aging | With 60m HL, free scores at T−10m still move weights < X noise band |

5. **Deliverables (future PR)**  
   - `phase6/research/run_free_sentiment_correlation.py`  
   - Report JSON under `data/state/free_sentiment_validation_YYYYMMDD.json`  
   - Go/no-go note in this folder.

### 4.3 Shadow mode (before disable X)

1. Write free scores to `data/state/sentiment_cache_free_shadow.json` only.  
2. Log side-by-side in refresh log: `x vs free vs hybrid`.  
3. After 7–14 days shadow + offline gates pass → set `x_enabled: false` in config.  
4. Keep X credentials; one-flag restore for 08:50/20:50.

---

## 5. Source deep-dives (decision bullets)

### Tier B — Funding / OI (priority build #1)

- **Why first:** True $0, pair-level, already “market truth,” works when social scrapers die.  
- **This host:** Binance fapi blocked; use **Bybit v5** (or other unrestricted venue).  
- **Output:** positioning score, labeled `funding`, confidence from |funding| and OI level.  
- **Risk:** Not social; can disagree with Twitter hype (feature, not bug).

### Tier C — F&G (priority build #2, ~1 hour)

- Endpoint verified: `GET https://api.alternative.me/fng/?limit=1` → e.g. 29 Fear.  
- Use as **regime prior**, not pair ranker.  
- History free for backtests.

### Tier A — pick path

| Path | Choose when |
|------|-------------|
| **StockGeist free stream** | Want multi-network social continuously; 1 forever crypto stream is unique |
| **Adanos free compare** | Want Reddit-shaped scores already in [-1,1]; 250/mo OK if batched 2×/day |
| **RSS + VADER/TextBlob** | Zero signup; in-repo already uses TextBlob on X/Reddit; VADER in `direct_reddit_fetcher.py` |
| **Hybrid A** | RSS always-on + Adanos/StockGeist 2×/day for polish |

**Avoid as “free primary”:** LunarCrush social (paid), CryptoPanic API (free gone), Santiment free (1k/mo too thin for experimentation + prod).

### Reddit

- Apify: keep as **backup**, cut cadence to match rebalance until non-zero rate improves.  
- Direct JSON: code exists; treat as **last resort** (block risk).  
- PRAW official free: rate-limited; commercial gray — not better than Adanos free for pair scores.

### Local LLM

- Only after free text dumps exist (RSS bodies).  
- CPU small model for bull/bear/neutral 3-class can beat TextBlob on headlines; validate on labeled week.  
- Do not block free stack on GPU.

### Dead ends

- **Nitter** and most X frontends: dead / unstable 2025–2026.  
- Scraping X HTML: ToS + brittle; defeats cost-control purpose.  
- Placeholder random or constant “0.1 bullish”: **forbidden** (same class as fake prices).

---

## 6. Recommended implementation sequence

| Step | Work | Est. effort | $ |
|------|------|-------------|---|
| 0 | Shadow logging of current X vs empty free | 0.5 d | 0 |
| 1 | `fetch_fng_sentiment.py` + merge Tier C empty-fill | 0.5 d | 0 |
| 2 | `fetch_funding_sentiment.py` (Bybit) + blend B | 1 d | 0 |
| 3 | `fetch_rss_sentiment.py` + keywords | 1–2 d | 0 |
| 4 | StockGeist **or** Adanos client | 1 d | 0 |
| 5 | Correlation notebook/script vs DB X (30–60d) | 1–2 d | 0 |
| 6 | Shadow 7–14 d → gate review | calendar | 0 |
| 7 | Disable X in cron if gates pass; keep flag | 0.5 d | 0 |
| 8 | Optional: throttle Apify to 2×/day | 0.5 h | saves credits |

**MVP that already beats “all zeros when X down”:** steps **1+2** only (F&G + funding).  
**MVP with pair text diversity:** + step **3**.  
**MVP social-competitive with X:** + step **4** + validation.

---

## 7. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Funding sign wrong for weight tilt | Offline gate G3; config `funding_sign: -1\|+1` |
| Free social vendor kills free tier | Multi-A (RSS always) + B+C |
| All sources correlated in crash | Accept; F&G and funding still informative; zeros OK |
| Geo blocks (Binance) | Bybit / multi-venue adapter |
| Reddit ToS / blocks | Prefer Adanos/StockGeist over scraping |
| Over-confidence on low N | Reuse X damping: `min_posts`, `confidence`, scorer `min_confidence=0.15` |
| Schema break | Additive fields only; keep `sentiment_score` |
| Live trading change too early | Shadow file + gates; this doc is research-only |

---

## 8. Decision summary

| Question | Answer |
|----------|--------|
| Can we run Phase 6 sentiment at ~$0? | **Yes**, with hybrid **funding + F&G + RSS/Adanos/StockGeist**. |
| Is it as good as X? | **Unlikely on trader-microstructure**; aim for **reasonable** pair tilt + non-zero coverage. |
| Best first code? | **Bybit funding + F&G** (hours, $0, no ToS drama). |
| Best free pair social? | **StockGeist free stream** or **Adanos batch compare**; RSS as always-on baseline. |
| Keep X? | **Optional Tier S** behind flag after validation; 2×/day already cost-controlled. |
| Fake data? | **Never** — empty → 0.0 remains correct. |

---

## 9. References (checked ~2026-07-20)

- Alternative.me F&G API: `https://api.alternative.me/fng/`  
- Adanos comparison / Reddit API: adanos.org (free 250/mo, hourly, `sentiment_score` [-1,1])  
- StockGeist API pricing: 10k free credits + 1 free crypto stream  
- LunarCrush: free tier market-data-only; social paid ~$72–90/mo  
- Santiment: free ~1k calls/mo, lagged  
- CryptoPanic: free Developer plan removed Apr 2026; Growth ~$199/mo  
- Apify: $5 free monthly credit; Reddit actors ~few $/1k results  
- In-repo: `phase6/core/sentiment_scorer.py`, `phase6/scripts/refresh_sentiment.py`, `fetch_x_sentiment.py`, `fetch_reddit_sentiment.py`, `phase6/core/sentiment/direct_reddit_fetcher.py`  
- DB gold: `data/phase6.db` / `sentiment_scores` (2026-06-12 → 2026-07-20)

---

*End of research. No production config, cron, or scorer behavior was modified by this document.*
