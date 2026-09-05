# Adanos + RSS/free bakeoff + last30days role (2026-09-04)

**Status:** shadow tooling live; **Adanos pull blocked until `ADANOS_API_KEY`**.  
**Live path unchanged:** X 2×/day + source-aware aging (X 15m / Reddit 60m).

## Goal

Find a **cheap Reddit-shaped bridge** for the mid-cycle gap after X ages out (~15m HL).

## Candidates

| Source | Cost | Shape | Role |
|--------|------|-------|------|
| **Adanos** Reddit crypto API | Free 250 req/mo (no CC) | True Reddit `sentiment_score` [-1,1] + buzz | Primary **true-Reddit** shadow |
| **RSS** (9 feeds) | $0 | Headline polarity, 72h HL | Free Reddit-shaped stand-in (already in free hybrid) |
| **Free hybrid** | $0 | RSS + funding (+ F&G damp) | 2h mid-cycle shadow |
| **last30days** | Research keys / free paths | Engagement-ranked multi-source **findings**, not pair schema | Briefs / offline dig only |

## Scripts

```bash
# 1) Adanos (needs ADANOS_API_KEY in .env)
python fetch_adanos_sentiment.py
# → data/state/adanos_sentiment_cache.json

# 2) Free/RSS refresh (already on 2h cron)
python phase6/scripts/refresh_sentiment_free.py

# 3) Multi-way correlate
python phase6/scripts/correlate_adanos_rss_free_x.py
# → data/state/adanos_rss_free_x_correlation_latest.json
# → reports/ADANOS_RSS_FREE_X_CORR_LATEST.md

# 4) last30days shape probe (research only)
python phase6/scripts/probe_last30days_pair_scores.py
# → data/state/last30days_pair_score_probe_latest.json
```

## Quota

- Compare endpoint: ≤10 symbols/call → ~2 calls per full basket.
- Free 250/mo → **≤2×/day** Adanos shadow is comfortable (~60–120 calls/mo).
- **Cron (live):** `phase6-adanos-reddit-shadow-2x` `539424468b36` · `35 8,20 * * *` PT (08:35/20:35 pre-X) · `no_agent` · deliver=local · failure_deliver=origin · script `run_adanos_shadow.sh`
- Do **not** put Adanos on the 2h free cron (would burn free tier).

## last30days potential role (honest)

**Yes, limited:**

1. **Weekly / operator brief** — narrative color on basket names (what it is good at).
2. **Offline dig** — crude pair-score probe vs X/Adanos/RSS sign agreement for research.
3. **Not** mid-cycle live gate input — wrong schema, episodic runs, cost/latency, house boundary `research ≠ deploy`.

Promote path for any last30days→pair score would need the same multi-day bakeoff as free/Adanos, plus Brad GO. Default = stay research.

## Promote gate (Adanos or free reinforce)

Multi-day streak of:

- coverage ≥ 0.5
- sign vs X ≥ ~0.55
- not anti-Spearman
- optional: Adanos vs RSS agreement (Reddit-shaped consistency)

Then optional: **mid-cycle bridge** when X age > ~30–45m (co-weight, not replace X at 09:00/21:00).

## Key

Register free: https://adanos.org/register  
Set: `ADANOS_API_KEY=sk_live_...` in project `.env` (see `.env.example`).
