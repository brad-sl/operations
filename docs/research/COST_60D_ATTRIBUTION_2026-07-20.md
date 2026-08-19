# 60-Day Crypto Spend Attribution Brief

**Date:** 2026-07-20 (PDT)  
**Scope:** Brad trading stack + Hermes agents (`/home/brad/projects/crypto-trading-bot`, `~/.hermes`)  
**Mode:** Read-only research — no production config or runner changes  
**User claim:** Crypto-related spend still **>$50/day** (vendor unclear: X Developer / OpenRouter / xAI / Apify / mix)

**Important billing split (do not conflate):**

| Surface | What it bills | How this stack hits it |
|--------|----------------|-------------------------|
| **X Developer** | Twitter/X API v2 (`api.twitter.com`, bearer) — often pay-per-resource (posts read, expansions) | `fetch_x_sentiment.py` via `refresh_sentiment.py` |
| **xAI / SuperGrok OAuth** | Grok chat/agent completions (`api.x.ai`, `xai-oauth`) | Hermes gateway + chat + ops-triage agent jobs |
| **OpenRouter** | Routed third-party models | Aux vision/compression/approval; `code-reviewer`; `crypto-monitor` profile default |
| **Apify** | Actor compute / platform usage | `fetch_reddit_sentiment.py` (`scrapesmith/reddit-scraper`) |
| **Coinbase** | Trading fees / API (not LLM) | Phase6 runner — out of scope for “AI/data API” spend unless card is exchange fees |

Dollar amounts below are **only** those already documented by user/prior ops notes or arithmetic from schedules. **No invented $ totals.** Where $ is unknown, confidence and verification commands are explicit.

---

## 1. Bill surfaces

### 1.1 Active recurring processes (inventory)

#### System crontab (`crontab -l`)

| Schedule | Command | Billable? | Notes |
|----------|---------|-----------|--------|
| `50 8,20 * * *` | `phase6/scripts/refresh_sentiment.py` | **Yes — X + Apify** | Canonical pre-rebalance X path (08:50 / 20:50 PT). Runs **both** `fetch_x_sentiment.py` and `fetch_reddit_sentiment.py`. |
| `0 */2 * * *` | `fetch_reddit_sentiment.py` | **Yes — Apify** | Every 2h standalone Reddit. |
| `# DISABLED` `0 */2` `fetch_x_sentiment.py` | — | Was X | Disabled 2026-07-17 cost control. |
| `# DISABLED` `4,34 * * * *` half-hourly `refresh_sentiment.py` | — | Was X+Apify | Replaced by 08:50/20:50. |
| `*/30 * * * *` | `scripts/ops/ops_engineer.py` | **Low / none LLM** | Deterministic log/ps checks + Telegram; optional cheap LLM only on new tickets. |
| `*/15` | `monitor_phase6_runner.py` | No AI API | Local process monitor. |
| `*/20` | `phase6_rebalance_monitor.sh` | No AI API | Hermes script wrapper. |
| `*/15` | `backup-kanban-frequent.sh` | No AI API | Local backup. |

#### Hermes cron (`hermes cron list` + `~/.hermes/cron/jobs.json`)

| ID | Name | Schedule | Mode | Billable? |
|----|------|----------|------|-----------|
| `5c1207235cf6` | rsi-15min-refresher | `*/15` | no_agent | **No** (prices only) |
| `1dfedf1dd8c9` | dashboard-live-state-5m | `*/5` | no_agent | **No** (local state) |
| `c16b620103dc` | twice-daily-trading-intelligence-v2 | `0 9,21` | no_agent | **Low** — report is mostly deterministic Python; Telegram deliver |
| `a4541bb6be69` | phase6-ops-triage-daily | `0 6` | **agent** | **Yes — xAI** (`model_snapshot: grok-composer-2.5-fast`) |
| `8909f6a921ae` | ops-issue-loop | `15 7,13,19` | no_agent | **Low** — shell/script path |
| `92d0bbe12216` | daily-git-hermes-management | `30 4` | no_agent | No AI API |
| `a93067255b66` | Daily Kanban Backup | `0 3` | no_agent | No AI API |
| `e039d96c4732` | Phase6 Analyst Optimization Weekly | Sun `0 4` | no_agent | Coinbase/local research (no LLM in script path) |
| `bf79baababb0` | Phase6 Shadow Drift Monitor | daily `0 5` | no_agent | Local |
| `6f3fb1232ec5` | RSI vs StochRSI — 2-week review | once 2026-07-24 | agent | One-shot xAI |
| `8612a817fe55` | sentiment-30min-refresh | `*/30` | no_agent | **`enabled=False`** (paused) — correct under policy |
| `4dcba7aa8f06` | twice-daily-trading-intelligence (legacy) | — | no_agent | **`enabled=False`** |

YAML residual: `~/.hermes/cron/crypto-monitor.yaml` (every 6h, agentic health check, profile `crypto-monitor` → OpenRouter `google/gemini-2.0-flash`). **Not present as an enabled job in `jobs.json` list used by live scheduler** — treat as dormant unless re-registered.

#### Always-on / interactive

| Process | Billable? | Evidence |
|---------|-----------|----------|
| Hermes gateway (`hermes_cli.main gateway run`) | **Yes — xAI primary** + OpenRouter aux | Live PID; `agent.log` API calls |
| OpenClaw gateway (port 18789) | Possible separate spend | Running; not audited as primary crypto path here |
| Phase6 runner | Exchange API only (for this brief) | Live |
| Kanban workers | **Yes when cards spawn agents** | Workspaces under `~/.hermes/kanban/...` (recent dirs Jul 16–17); no hot worker flood on 2026-07-20 snapshot |
| Telegram / CLI chat | **Yes — xAI** | Large multi-turn sessions with 100k–150k+ token contexts |

### 1.2 Model / provider config (verified)

| Profile / layer | Provider | Model | Notes |
|-----------------|----------|-------|--------|
| default (`~/.hermes/config.yaml`) | `xai-oauth` | `grok-composer-2.5-fast` | Primary volume |
| crypto-analyst / engineer / orchestrator | `xai-oauth` | `grok-build-0.1` | Cost-oriented profiles |
| code-reviewer | `openrouter` | `moonshotai/kimi-k2.7-code` | **`base_url: https://api.x.ai/v1`** — **misaligned** (OpenRouter model + xAI base). Risk of failed calls or wrong billing path. |
| crypto-monitor | `openrouter` | `google/gemini-2.0-flash` | Only if that profile/cron is used |
| auxiliary.vision / compression / approval / titles | `openrouter` | `google/gemini-2.5-flash` | Confirmed in default config + `agent.log` |
| `x_search` config | (tool) | `grok-4.20-reasoning` | Expensive if used heavily; little recent log signal |
| fallback_providers | — | `claude-haiku-4.5` | Outage path |
| OpenRouter hard daily limit | — | **Not set** in config (`limit: null` class risk historically) |

Keys present (names only): project `.env` has `X_API_BEARER`, `APIFY_*`; Hermes `.env` has `OPENROUTER_API_KEY`, `XAI_API_KEY`, etc.

### 1.3 Data-path attribution (scripts)

| Script | Vendor | Mechanism |
|--------|--------|-----------|
| `fetch_x_sentiment.py` | **X Developer** | `GET https://api.twitter.com/2/tweets/search/recent` + `Authorization: Bearer`; default `max_results=30`; batched (~2–3 calls for 11-pair basket) + per-pair supplemental if `post_count==0`. **Not Apify.** |
| `phase6/scripts/refresh_sentiment.py` | X + Apify | Subprocess both fetchers → merge `data/state/sentiment_cache.json` |
| `fetch_reddit_sentiment.py` | **Apify** | Actor `scrapesmith/reddit-scraper` (override `REDDIT_APIFY_ACTOR_ID`); **per pair × up to 3 subreddits = up to ~33 `actor().call()` per script run** |
| Intelligence report cron | Mostly local | Deterministic generator + Telegram (`hermes send`) |
| ops_engineer | Mostly local | Rule-based; Telegram Bot API only |

Canonical policy doc: `docs/X_SENTIMENT_COST_CONTROL.md` (2026-07-17): X only 2×/day at 08:50/20:50 PT.

---

## 2. Schedule-driven volume (arithmetic)

**Assumptions (stated):**

- Basket: **11 pairs** in live sentiment cache (config lists 12 including MATIC; runtime cache keys = 11).
- X full refresh: smarter batch → **~2–3** `/search/recent` calls + **0–N** supplemental calls for zero-post pairs; `max_results=30` (25 on supplemental).
- X post bill proxy: posts returned ≤ `calls × max_results` (upper bound; real returns lower — cache snapshot ~102 posts total across pairs after one run).
- Reddit: **11 pairs × 3 subs × 1 keyword** ≈ **33 actor runs** per successful `fetch_reddit_sentiment.py` when not hard-limited.
- Timezone: PT for policy; logs mix UTC.

### 2.1 Current steady-state (post cutover ≈ 2026-07-19+)

| Driver | Runs/day | Est. billable units/day | Notes |
|--------|----------|-------------------------|--------|
| X via refresh 2× | 2 | **~4–12 search calls**; **≲120–360 posts billed (cap)** | Staleness guard can skip if cache <25 min (unlikely at 12h spacing → full fetch expected). |
| Reddit standalone cron | 12 | **up to ~396 actor runs** if healthy | Currently failing: Apify monthly hard limit. |
| Reddit inside refresh | +2 | **up to ~66 actor runs** | Double-path with standalone cron. |
| RSI 15m | 96 | 0 AI | |
| Dashboard 5m | 288 | 0 AI | |
| ops_engineer 30m | 48 | ~0 LLM | |
| ops-triage agent | 1 | 1 multi-turn xAI session | |
| ops-issue-loop | 3 | ~0 LLM | |
| intel brief | 2 | ~0–low LLM | |
| Gateway chat | user-driven | **High variance xAI tokens** | See §3 |

### 2.2 Pre-cutover (documented + log-proven)

| Period | `refresh_sentiment` runs/day (log) | Implication |
|--------|-----------------------------------|-------------|
| 2026-07-09 → 2026-07-17 | **48/day** (exact half-hourly) | Stacked with any other X paths → historical **$50–$150/day X** class (user + prior ops notes) |
| 2026-07-18 | **10** (transition) | Half-hourly still firing early UTC, then 15:50 slots |
| 2026-07-19 → 2026-07-20 | **2/day** | Policy finally reflected in logs |

**X call estimate (order-of-magnitude):**

- Half-hourly era: \(48 \times (2\text{–}4) \approx 96\text{–}192\) search calls/day → multi-thousand posts/day upper bound → **matches prior $75–150/day X narrative**.
- Current 2×/day: ~**8–24× fewer** X search cycles than half-hourly era (if no other X callers).

**Apify volume (theoretical if not capped):**

- Standalone 12/day × 33 ≈ **396 actor runs/day**
- + refresh 2× ≈ **462 actor runs/day**
- Even “cheap” actors at a few cents can reach tens of $/day; **monthly hard limit hit 2026-07-04** proves sustained burn earlier in the month.

### 2.3 LLM token volume (xAI) — measured from `agent.log`

Main-path `API call #N: model=… in=… out=…` aggregates (partial log retention; not full 60d):

| Day | Calls | Input tokens | Output tokens | Dominant model |
|-----|------:|-------------:|--------------:|----------------|
| 2026-07-08 | 635 | 45.9M | 281k | grok-composer-2.5-fast |
| 2026-07-11 | 461 | 33.0M | 213k | composer |
| 2026-07-14 | 218 | 20.9M | 109k | composer |
| 2026-07-15 | 225 | 20.1M | 110k | composer |
| 2026-07-16 | 100 | 18.1M | 66k | **mix grok-4.5 + composer** |
| 2026-07-17 | 213 | 25.1M | 155k | composer |
| 2026-07-18 | 73 | 9.5M | 56k | composer |
| 2026-07-19 | 34 | 3.5M | 22k | composer |
| 2026-07-20 (partial) | 53 | 3.9M | 46k | composer |

**Aux OpenRouter (recent):** few–teens `google/gemini-2.5-flash` compressions/approvals per day — **unlikely alone to drive >$50/day**.

**$ conversion for xAI:** unknown without SuperGrok plan vs metered API dashboard. Large context loops (150k-token compressions, multi-hour Telegram sessions) are the **dominant LLM volume driver**, not the no_agent crons.

---

## 3. Evidence from logs

### 3.1 X / sentiment

- `logs/sentiment_refresh_cron.log`: **48 refresh runs/day through 2026-07-17**; cut to 2/day from 2026-07-19. X and Reddit both report “completed successfully” even when Reddit data is empty.
- Latest X cache (`data/state/x_sentiment_cache.json`, 2026-07-20T15:50Z): 11 pairs, **~102 posts** total, scores non-zero for most — confirms **live X API still returning data**.
- `fetch_x_sentiment.py` code path: Twitter v2 only; Apify X helper exists in `phase6/core/sentiment/fetch_x_sentiment.py` but **root orchestrator uses root `fetch_x_sentiment.py` (bearer)**.
- Pre-rebalance runner: frequent `missing_sent=[]` after warm cache — **not** a second X storm when 08:50/20:50 succeed.
- No clean HTTP 429 lines attributed to X in sampled sentiment logs (billing can still accrue without 429).

### 3.2 Apify

- `sentiment_cron.log`: **`Monthly usage hard limit exceeded`** since **2026-07-04 10:00**, continuing through 2026-07-20.
- Pattern: ~**132 hard-limit error lines/day** × many days (≈ 12 starts × 11 pairs).
- Reddit starts still fire **12×/day** (wasteful retries against a capped account).
- refresh_sentiment also invokes Reddit 2×/day → more failed actor attempts (may or may not bill; still noisy).

### 3.3 Hermes / LLM

- `agent.log`: overwhelming **`xai-oauth` + `grok-composer-2.5-fast`**; secondary **`grok-4.5`** on 2026-07-16.
- Large sessions: repeated context compression at **~150k tokens**; cache hit rates often 90%+ after first call (reduces but does not eliminate cost).
- User messages logged 2026-07-17: *“Daily X Developer Platform fees have slid back up to $50-$75/day”*; *“Openrouter spent $500 on April 1st”*; 2026-07-20: *“Crypto spend is still exceeding $50/day”*.
- OpenRouter aux after mid-July: **gemini-2.5-flash** (good). Earlier June/early July: **`openrouter/owl-alpha`** compression/titles (fixed per ops playbook).
- ops-triage cron 2026-07-19: multi API calls, in≈42k with high cache ratio — moderate daily agent cost, not X-scale by itself.
- No evidence in current logs of Sonnet-as-main (historical trap only).

### 3.4 Rate limits / errors (other)

- True HTTP **429** flood not found (many false positives from timestamps/IDs containing “429”).
- 2026-07-19: xAI `invalid_token` / service unavailable on one session — availability, not spend.
- Apify hard limit is the clearest **vendor quota** signal.

---

## 4. Ranked cost drivers (>$50/day candidates)

Confidence: **High** = schedule + code + logs agree; **Med** = strong indirect; **Low** = possible but unmeasured $.

| Rank | Driver | Est. role vs >$50/day | Confidence | Rationale |
|------|--------|----------------------|------------|-----------|
| **1** | **X Developer via half-hourly `refresh_sentiment` (through ~2026-07-17/18)** | **Primary historical** match to $50–$150/day | **High** | User-stated X fees; docs; **48 runs/day** in log; direct `search/recent` + posts. |
| **2** | **X Developer still on 2×/day path (current)** | **Should be much lower** than half-hourly; may still be tens of $/day depending on X price tier & expansions — **cannot prove still >$50 from logs alone** | **Med** | Still live bearer API; ~2–3 batches × 2/day × posts; billing dashboards not accessible here. If card still >$50 **after several days of only 2×**, look for other X apps/keys or delayed invoices. |
| **3** | **xAI OAuth agent volume (gateway + long Telegram sessions)** | **Can exceed $50/day if metered**; lower if covered by SuperGrok flat sub | **Med** | Multi‑M to **45M input tokens/day** observed; compressions; grok-4.5 spikes. $ unknown without xAI/OpenRouter-style usage export. |
| **4** | **Apify Reddit (per-pair × 3-sub actor spam)** | **Large earlier in month**; **current incremental $ likely ~0** while hard-limited | **High** (that limit hit) / **Med** (dollar size) | Limit since Jul 4; theoretical **~400 actor runs/day** design is aggressive. Failed calls may still have cost before cap. |
| **5** | **OpenRouter aux (gemini-2.5-flash)** | Unlikely sole >$50 driver now | **High** | Single-digit to low-double digit aux calls/day in recent logs. |
| **6** | **OpenRouter historical Sonnet-as-main** | Past catastrophe ($100s–$500/day class) | **High** (historical memory/docs) | Not active as default now; keep OR aux-only. |
| **7** | **code-reviewer / kanban agent bursts** | Spike risk when cards run | **Low–Med** | Misconfigured base_url; sporadic workspaces; not continuous 2026-07-20. |
| **8** | **ops_engineer / RSI / dashboard / intel no_agent** | Negligible AI $ | **High** | No LLM or deterministic. |
| **9** | **Double Reddit path (cron 2h + refresh 2×)** | Amplifies Apify when uncapped | **High** | Code + schedules. |

### Cutover gap (critical for “still >$50” narrative)

Policy dated **2026-07-17**, but **`sentiment_refresh_cron.log` still shows 48 runs on 2026-07-17** and only settles to 2/day on **2026-07-19**.  
→ If the user is looking at **X Developer trailing 24–72h or monthly average**, spend can remain elevated **after** the intended policy date.  
→ If **calendar day 2026-07-20** is truly still >$50 on **X alone** with only 2 successful refreshes, that would be **surprising** under prior “$75–150 at 48×/day” scaling unless (a) X minimums/other apps, (b) different product meter, or (c) **misattributed vendor** (xAI/Apify/OR).

---

## 5. What we cannot know without dashboard login

| Unknown | Why | Where to look |
|---------|-----|----------------|
| Exact **$** by vendor last 60 days | No billing API credentials used in this research | developer.x.com usage; console.apify.com; openrouter.ai/activity; console.x.ai / SuperGrok billing |
| Whether SuperGrok **flat** covers composer/build tokens | Plan-dependent | xAI account subscription vs usage invoice |
| X **price per post/resource** on this app tier | Tier + expansions (`tweet.fields`, etc.) not fully priced here | X developer portal app analytics |
| Whether failed Apify runs after hard limit still bill | Platform policy | Apify usage → “Usage & Billing” |
| Other machines/apps using same X bearer | Only this host audited | X portal “apps” + token last-used |
| OpenClaw / non-Hermes spend | Separate gateway running | OpenClaw config + its provider keys |
| Full 60-day token series | `agent.log` rotated; only ~2 weeks dense | Hermes state.db exports or provider invoices |
| code-reviewer actual billed provider | base_url vs provider mismatch | OpenRouter activity **and** xAI logs when reviewer runs |

---

## 6. Recommended measurement instrumentation

Implement without changing trading risk parameters:

1. **Per-vendor daily counter file** (append-only JSONL):  
   - X: log each `search/recent` → `ts, http_status, result_count, query_hash, source=refresh|manual|pre_rebal`  
   - Apify: log each `actor().call` → `ts, actor_id, pair, subreddit, status, run_id, error`  
   - Hermes: already has `API call #N in/out` — add **daily rollup cron** parsing `agent.log` → `data/state/cost_telemetry/llm_YYYYMMDD.json`

2. **Single sentiment orchestrator ownership**  
   - Prefer **one** Reddit schedule (either 2h cron **or** refresh-embedded, not both).  
   - Batch Reddit into **1 actor run / multi-query** instead of 33 runs.

3. **Hard kill switch env flags**  
   - `ENABLE_X_SENTIMENT=0/1`, `ENABLE_APIFY_REDDIT=0/1` checked at top of fetchers.

4. **OpenRouter spend ceiling**  
   - Set provider dashboard daily limit; keep main agent on xai-oauth only.

5. **Fix code-reviewer config**  
   - Either `provider: openrouter` + empty/default OR base_url, **or** pure xai-oauth model — not mixed.

6. **Invoice ↔ log join weekly**  
   - Spreadsheet: date, X$, Apify$, OR$, xAI$, refresh_count, x_calls, apify_calls, llm_in_tokens.

7. **Alerting**  
   - If `refresh_sentiment` runs > 3/day or X calls > 20/day → Telegram alert (detect cron regressions).  
   - If Apify hard limit → stop retrying (short-circuit after first limit error).

---

## 7. Verification commands (re-run anytime)

```bash
# Schedules
crontab -l | rg -i 'sentiment|fetch_x|fetch_reddit|ops_engineer|refresh'
hermes cron list
python3 - <<'PY'
import json; from pathlib import Path
jobs=json.loads(Path.home().joinpath('.hermes/cron/jobs.json').read_text())
for j in jobs:
    print(j.get('id'), 'en', j.get('enabled'), j.get('name'), j.get('no_agent'), j.get('schedule'))
PY

# X vs Apify code paths
rg -n 'api.twitter.com|ApifyClient|max_results|actor\(' \
  /home/brad/projects/crypto-trading-bot/fetch_x_sentiment.py \
  /home/brad/projects/crypto-trading-bot/fetch_reddit_sentiment.py \
  /home/brad/projects/crypto-trading-bot/phase6/scripts/refresh_sentiment.py

# Refresh frequency (should be ~2/day after 2026-07-18)
rg -n 'Sentiment Refresh @' /home/brad/projects/crypto-trading-bot/logs/sentiment_refresh_cron.log | tail -20

# Apify cap
rg -n 'Monthly usage hard limit|Starting Reddit' \
  /home/brad/projects/crypto-trading-bot/sentiment_cron.log | tail -40

# LLM volume sample
rg -n 'API call #|Auxiliary' ~/.hermes/logs/agent.log | tail -50

# Models
rg -n 'default:|provider:|base_url:' ~/.hermes/config.yaml ~/.hermes/profiles/*/config.yaml | rg -i 'model|provider|base_url|openrouter|grok|gemini|kimi' | head -80

# X cache freshness
python3 -c "import json;print(json.load(open('data/state/x_sentiment_cache.json')))" \
  | head -c 2000
```

**Dashboard logins (human):**

- https://developer.x.com → Usage / billing for app tied to `X_API_BEARER`
- https://console.apify.com → Usage (expect hard limit story from Jul 4)
- https://openrouter.ai/activity → confirm aux-only + no Sonnet main
- xAI / SuperGrok billing → map token volume in §2.3 to $

---

## 8. Executive summary

1. **Separate bills:** X Developer ≠ xAI ≠ OpenRouter ≠ Apify.  
2. **X half-hourly stack is the proven historical >$50/day engine** (48 refreshes/day through Jul 17; user $50–$75 and prior $75–$150 notes).  
3. **Policy cutover lagged the doc date:** logs show **2×/day only from Jul 19**.  
4. **Current X path still uses Twitter API bearer** (not Apify), 2×/day via `refresh_sentiment` — should be far cheaper than half-hourly, but exact $ needs X portal.  
5. **Apify Reddit design is extremely chatty (~33 actor runs/script)** and has been **hard-limited since Jul 4** — stop blind retries; redesign batching.  
6. **LLM spend risk is long Hermes/xAI sessions** (millions of input tokens/day), not RSI/dashboard no_agent crons. OpenRouter is currently aux-flash scale.  
7. **code-reviewer `openrouter` + `base_url: api.x.ai` is a config footgun.**  
8. **Cannot attribute today’s exact >$50 vendor without billing dashboards**; highest-probability remaining explanations: (A) X trailing invoice/average, (B) metered xAI tokens, (C) other app on same cards, (D) residual Apify pre-cap — **not** the no_agent 5m/15m jobs.

---

## 9. Suggested next actions (priority, still read-only until approved)

1. Login X + Apify + xAI + OpenRouter; paste 7-day $ breakdown (closes attribution).  
2. Confirm no other host uses `X_API_BEARER`.  
3. After invoices: if X still high at 2×/day → cut expansions / move X scrape to Apify **or** reduce max_results further / single combined query.  
4. Pause or short-circuit Reddit cron while Apify capped; fix per-pair actor loop.  
5. Fix code-reviewer provider/base_url; set OpenRouter daily cap.  
6. Add X-call counter + daily llm token rollup (§6).

---

*Generated 2026-07-20 by read-only cost attribution pass. Evidence roots: crontab, hermes cron/jobs.json, fetch scripts, config.yaml + profiles, sentiment_refresh_cron.log, sentiment_cron.log, agent.log, docs/X_SENTIMENT_COST_CONTROL.md, hermes-operations cost playbooks.*
