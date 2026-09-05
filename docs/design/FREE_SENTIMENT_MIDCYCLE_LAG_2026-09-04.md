# Free mid-cycle sentiment (lag thesis) — 2026-09-04

## Product problem
Sentiment contributes to **entry gates / size haircuts** (quality_tryout floors, `sent_only` haircut, ignition boost).  
Live X is **2×/day** (08:50 / 20:50 PT) for cost control (~$50–75/day when stacked).  
~12h between X refreshes can leave decisions on **stale social** for force rebalances and mid-day cycles.

**Note (2026-09-04 fix):** main rebalance path now loads **aged** scores via canonical `load_sentiment_scores` (X HL **15m**, Reddit HL **60m**). Prior bug: raw X sat at full strength for hours. Without Reddit bridge, aged X correctly fades mid-cycle; free 2h shadow is the cheap bridge candidate (not live until promote + Brad GO).

## Cost constraint
- Do **not** resume Hermes `sentiment-30min-refresh` / frequent X without Brad cost GO.
- Reddit Apify stays **OFF**.
- `last30days` = research briefs, **not** pair-score deploy input.

## Cheap path (in flight)
| Layer | Cadence | Writes live? |
|-------|---------|----------------|
| X live | 2×/day pre-rebalance | **Yes** → `sentiment_cache.json` |
| Free hybrid (RSS + funding + F&G) | **every 2h @:40 PT** | **No** → `sentiment_cache_free.json` + correlate vs X |
| Cron | `phase6-free-sentiment-shadow-2h` `655188d1df61` | shadow only |

Free refresh cost: ~**8s**, no X/Apify bill.

## Promote gate (before any live mid-cycle free)
Multi-day `free_vs_x_correlation_*`:
- sign agreement, Spearman, coverage
- `promote_ready` true on a streak (not one snapshot)
- Optional CF: would free mid-cycle have changed haircuts/blocks vs stale X?

### Candidate live uses (needs Brad GO after gate)
1. **Blend mid-cycle only** when X age > N hours (e.g. free reinforce haircuts, not sole BUY veto).
2. **Replace aged X** for quality floors after hours with free (conservative).
3. Keep X as **anchor** at 09:00/21:00 rebalance slots forever.

## Explicit non-goals (now)
- Wiring free or last30days into live scorer without multi-day proof.
- Faster runner cycle as a substitute for fresher scores.
- Claiming free == X alpha.

## Ops
```bash
bash scripts/phase6/run_free_sentiment_shadow.sh
cat data/state/free_vs_x_correlation_latest.json | jq '{promote_ready,sign_agreement,spearman_all,n_overlap}'
```
