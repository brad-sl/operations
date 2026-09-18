# RSI-event → single-pair X → tryout shadow (2026-09-15)

## Goal
Reduce clock luck between 09:00/21:00 X slots: when a **tryout-eligible** door is RSI-washed and eng is stale, shadow-log a **top-K (≤2)** would-query / would-tryout path. Measure only.

## Universe (not XRP-only)
- All `quality_tryout` v1/v2 **eligible doors** (scoreboard / `recovery_tryout_pairs_effective`)
- Includes Option D thaw seats while active
- **Not** full basket; **not** tier-C universe expansion

## Trigger (event gap)
1. RSI in wash band: default **0–40** (stricter than tryout max 55)
2. Eng stale: missing, |eng|≤0.05 dust, or under tryout floor 0.30 with aged/unknown age
3. Tryout eligible, not buy_block

## Rank + cap
- Deeper wash ranks higher; last-X clear-floor hints boost/penalize
- **Top K = 2** would-query if many flip together
- Never sprays X across the whole door list

## What shadow does / does not
| Does | Does not |
|------|----------|
| Log would_query / last_x_clears / buy_if_x_pass via `evaluate_buy_entry(sent=floor)` | Place orders |
| Use cached X only (`spend_x=false`) | Paid on-demand X |
| Write latest + jsonl + MD report | Mutate config / knobs |
| Quiet TG when top-K non-empty | Wire runner mid-cycle buy |

## Edge class
`ATTENTION_ONLY_sensor_clock` — not HIT abs, not promote. Live wire needs Brad GO + spend caps.

## Artifacts
- `phase6/core/rsi_event_x_tryout_shadow.py`
- `scripts/phase6/run_rsi_event_x_tryout_shadow.py`
- `scripts/phase6/test_isolation_rsi_event_x_tryout_shadow.py`
- `data/state/rsi_event_x_tryout_shadow_latest.json`
- `data/state/rsi_event_x_tryout_shadow_events.jsonl`
- `reports/RSI_EVENT_X_TRYOUT_SHADOW_LATEST.md`
- Cron: `phase6-rsi-event-x-tryout-shadow` `36a4ade79e1c` · `20 7,11,15,19 * * *` PT · no_agent quiet TG

## Live first board (2026-09-15)
- Trigger pool: 6 doors
- Top-2: ADA (RSI~33, last X 0.62) + WLD (RSI~35, last X 0.49) → buy_if_x_pass=True under full gates
- XRP (RSI~29, last X 0.06) in pool but **not** top-K prefer / last_x fails floor — proves ranking, not XRP-special-case

## Next (not this ship)
1. Optional `--spend-x` single-pair probe with hard daily budget (Brad GO)
2. Live mid-cycle tryout seat only after shadow N days + no process-tax spike
3. Align any live path with existing $75 / 2-seat / SL stack — no side door

## Post-PASS switch plan (Brad 2026-09-16)
**Armed:** after this observe **completes and passes**, switch per  
`docs/plans/2026-09-16-rebalance-book-vs-rsi-buy-x-split.md`

- Rebalance → **book only** (not new buys)
- New buys → **RSI-event path**
- X → RSI-filtered prospects + rebalance candidates only (**replace** full-pool 2×, do not stack)
- Live cutover still needs explicit Brad GO after PASS — plan save ≠ cutover GO

## 24h observe (Brad 2026-09-15)
- Mode: **observe only** through ~2026-09-16 15:21 PT
- Recurring shadow cron remains 4×/day; no paid X; no orders
- Closeout one-shot: `phase6-rsi-event-x-shadow-observe-close` `17289c281af6` @ **2026-09-17 19:35 PT**
- Observe window **extended** Brad GO 2026-09-16 → through tomorrow (~48h total); prior 24h closeout `63b055a00372` removed
- Bar to *discuss* X probe (not promote): ≥3 ticks, ≥2 trigger hits, ≥2 top-K hits
- Graduate ladder: shadow evidence → single-pair X probe (GO) → live tryout only with evidence

## Validate 2026-09-18 (Brad GO)

- Paid X probe shipped: `scripts/phase6/run_rsi_event_x_probe.py --go`
- Budget SSOT: `phase6/core/x_query_budget.py` (rsi ≤2 pair-queries/day, cooldown 6h)
- Cron: `phase6-rsi-event-x-probe` (same slots as shadow, spends only on wash+budget)
- `place_orders` remains **false**; live buy still full gate stack
- Observe verdict was OBSERVE_PASS_discuss_X_probe → this is the discuss/validate step

