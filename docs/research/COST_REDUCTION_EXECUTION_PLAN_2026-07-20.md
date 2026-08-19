# Cost Reduction Research Pack — 2026-07-20

**Owner:** Brad  
**Trigger:** Crypto-related spend still **>$50/day**.  
**Goal:** Cut to a sustainable band (**target ≤$10–15/day** where possible) using **free/sub agents**, **near-free sentiment**, and schedule hygiene — without fake market data.

**Research pack (complete):**
| Doc | Role |
|-----|------|
| `docs/research/COST_60D_ATTRIBUTION_2026-07-20.md` | 60d bill surfaces + volume |
| `docs/research/FREE_SENTIMENT_OPTIONS_2026-07-20.md` | Free sentiment ranked + hybrid |
| `docs/research/FREE_AGENT_ROUTING_2026-07-20.md` | Agent F0–P2 routing |
| **This file** | Unified **execution plan** |

---

## 0. Executive decision map

| If primary $ is… | First moves (Phase 1) |
|------------------|------------------------|
| **X Developer** | Confirm 2× stuck (was 48×/day until ~Jul 17–19); free hybrid shadow → flag off X; stop any other Twitter consumers |
| **xAI / Grok** | Shrink Telegram context; Kanban **no `--goal` default**; triage script-first; delegation → `grok-build-0.1` |
| **Apify** | Reddit **2×/day only** (not 12×); drop dead all-zero runs |
| **OpenRouter** | Daily key limit; fix code-reviewer provider/base_url mismatch; never Sonnet main |

**Host fact:** No GPU/Ollama — local free LLMs are **not** day-1.

**Live probes (research):** F&G API OK; Binance futures **geo-blocked** here → use **Bybit** funding/OI; Reddit public JSON blocked; Apify Reddit cache often **all zeros**.

---

## 1. Two billing surfaces (never conflate)

| Surface | What it bills | Our current stack |
|---------|---------------|-------------------|
| **A. Social data** | X Developer, Apify | X: Twitter bearer **2×/day** (`fetch_x_sentiment.py`); Reddit Apify **12×/day** + again inside refresh |
| **B. LLM / agents** | xAI OAuth, OpenRouter | Chat **composer-2.5-fast**; profiles **build-0.1**; aux **gemini-2.5-flash**; code-reviewer **kimi** (misconfig risk) |

---

## 2. Baseline evidence

### 2.1 X schedule reality (attribution brief)
- Through **~Jul 17**: `refresh_sentiment` still fired **~48×/day** in logs (policy lag).
- From **~Jul 19**: **2×/day** only (08:50/20:50 PT) — matches cost-control doc.
- X path is still **paid Twitter API**, not Apify.
- If invoice still shows X >$50 **after several full days on 2×**, check trailing billing, other apps, or mislabeled xAI.

### 2.2 LLM tokens (`agent.log*`, ~18 days)
| Day | Calls | Tokens |
|-----|------:|-------:|
| Jul 8 | 635 | ~46M |
| Jul 11 | 461 | ~33M |
| Jul 17 | 213 | ~25M |
| Jul 19 | 34 | ~3.5M |

Dominant: `xai-oauth` / `grok-composer-2.5-fast` with **~95–100k in/call** on long sessions.

### 2.3 Must confirm (Brad, 5 min)
1. X Developer — 7d $  
2. xAI / SuperGrok — 7d $  
3. OpenRouter — 7d $  
4. Apify — 7d $  

---

## 3. Free sentiment hybrid (from FREE_SENTIMENT brief)

| Priority | Source | Role | Cost |
|----------|--------|------|------|
| 1 | **Bybit funding + OI** | Pair-level positioning | $0 |
| 2 | **alternative.me F&G** | Market-wide dampener only | $0 |
| 3 | **RSS + TextBlob/VADER** | Partial pair text | $0 |
| 4 | StockGeist / Adanos free tiers | Pair social if quota allows | ~$0 |
| Optional S | X API | Boost if bill allows | paid |

**Merge:** text/funding → pair scores; F&G scales empty/global only; **0 = no signal**.  
**MVP:** F&G + Bybit funding (hours) → +RSS → shadow 7–14d vs DB X (~164k rows) → disable X if gates pass.  
**Do not** promote anti-correlated noise.

---

## 4. Free / cheap agent routing (from FREE_AGENT brief)

| Tier | Use |
|------|-----|
| **F0 no_agent** | RSI, dashboard, intel, OPT, ops_engineer, issue-loop script, triage discovery |
| **F1 grok-build-0.1** | Kanban implementers, multi-turn fixes |
| **F1 composer-fast** | Short interactive Telegram only |
| **P1 OR flash / kimi** | Aux compress/vision; code-review gate only |
| **Banned volume** | Sonnet/Opus main; 25-turn goal on medium; unlimited OR |

**Kanban policy:** default **single-shot / max 12 turns**; `--goal` only priority_rank≤1; no overnight auto-spawn medium; concurrent ops workers ≤1 night.

---

## 5. Execution phases

### Phase 0 — Measure (Day 0)
- [ ] Four vendor $ screenshots  
- [ ] `scripts/ops/llm_token_daily_rollup.py` → `data/state/llm_token_daily.jsonl`  
- [ ] `rg` for any non-policy X consumers  

### Phase 1 — Stop bleed (Day 1) — **DONE 2026-07-20**
1. [x] Reddit crontab **2h → 08:50/20:50 only** (via refresh_sentiment)
2. [x] `ops_issue_loop`: **no `--goal` default**; `--goal` only rank≤1; max 12 turns; `--force-goal` escape
3. [x] `delegation.model` → **`grok-build-0.1`**
4. [ ] OpenRouter **daily key limit** (Brad in OR dashboard) — pending user
5. [x] Fix **code-reviewer** `base_url` (was xAI with OR provider → `''`)
6. [x] Morning triage: **`ops_triage_discover.py` no_agent** (`a4541bb6be69`)
7. [x] Token rollup: `scripts/ops/llm_token_daily_rollup.py` + cron `9505b498cd6d` @ 05:05
8. Soft: Telegram `/new` when context drives in≫40k (habit; not automated)  

### Phase 2 — Free sentiment shadow (Days 2–5) — **DONE 2026-07-21**
1. [x] `fetch_fng_sentiment.py` + `fetch_funding_sentiment.py` (OKX; Bybit blocked) + `fetch_rss_sentiment.py`
2. [x] `refresh_sentiment_free.py` → `data/state/sentiment_cache_free.json` (shadow only)
3. [x] `correlate_free_vs_x_sentiment.py` + history jsonl + gates
4. [x] Cron **08:40/20:40 PT** system crontab `run_free_sentiment_shadow.sh`
5. [x] Doc `docs/FREE_SENTIMENT_SHADOW.md`
6. First live sample: free_nz=11/11, spearman_all≈0.27, **sign_agreement≈0.22** → `promote_ready=False` (expected; need multi-day + maybe funding sign policy)  

### Phase 3 — Cutover (Days 5–7)
1. Config `sentiment.primary = free_hybrid | x | off`  
2. Live read free hybrid; X optional or off  
3. Apify off or 2× max  
4. Watch rebalance + REGIME-CASH 7d  

### Phase 4 — Maturity (Week 2+)
- Local LLM only if hardware improves  
- Overnight Kanban freeze except critical labels  
- Weekly cost telegram from rollup  

---

## 6. Success metrics

| Metric | Baseline | Target 14d |
|--------|----------|------------|
| Stack $ / day | >$50 | ≤$15 (stretch ≤$10) |
| Busy-day agent tokens | 15–45M | ≤5M |
| X calls / day | ~4 (post-cut) or was 48 | 0 if hybrid passes |
| Apify runs / day | ~12 + refresh doubles | ≤2 |
| Sentiment usable pairs @ rebalance | 8–11 | ≥6 documented sources |

---

## 7. Risks

- Free pair signal weaker → more cash park — accept vs burn  
- Geo blocks (Binance) — Bybit path required on this host  
- No-goal Kanban slows fixes — offset with better audit scripts  
- Trailing X invoice lag after 48→2 cut  

---

## 8. Ordered next actions

1. **Brad:** 4× vendor $ (Phase 0)  
2. **Agent on go:** Phase 1 items 1–3, 5–6 (no trading config risk)  
3. **Agent:** free sentiment MVP shadow  
4. **Decision:** X off vs 2× keep  

---

## Document control

| Ver | Date | Note |
|-----|------|------|
| 0.1 | 2026-07-20 | Baseline + skeleton |
| 0.2 | 2026-07-20 | Merged research team A/B/C findings |
