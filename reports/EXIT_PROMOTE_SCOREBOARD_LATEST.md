# Exit promote scoreboard (GAP-01)

**As of:** 2026-08-21T00:27:40.218852Z  
**Schema:** `exit_promote_scoreboard_v1`  
**MASTER:** `P6-SCALE-GAP-01-EXIT-PROMOTE-SCOREBOARD-20260816`  

## Plain English

**Go/no-go:** NO-GO live exits — calendar 14.26/60d; shadow only.  
**Decision enum:** `collecting_calendar`  
**Flag:** `COLLECTING`  
**Live TP allowed by this board alone:** **False** (Brad OK still required: True)

Shadow calendar: **14.26** / 60 days  
Regime now: **transition**  
Core gates: **5/9** pass  

> Regime **transition** → shadow knobs: TP off, trail off, RSI≥70 watch. Would-fire now: 0 (new episodes this cycle: 0). No orders. Collection day 14.26/60.

## Trade-opt lane: bear ladder (less-loss)

**Decision:** `collecting_live_bear_shadow`  
**Go/no-go:** NO-GO live ladder — keep shadow; need live bear calendar episodes (episodes 0/10, bear_days 1.0/30.0)  
**Edge class:** `LESS_LOSS_VS_SL`  
**Winning path:** `residual_long AND bounce_tags_ge_2_slices AND no_fomo_rebuy`  
**Path CF:** `pursue_shadow` · episodes=0 · bear_days=1.0 · checks 4/6  
**Live ladder allowed by board:** **False**

> Ladder beats ride-to-SL by ~0.94% mean R on N=276. Keep Phase-1 shadow; **not** a live promote. Absolute ladder mean R is still negative (-0.96%) — this is **less-loss vs ride-SL**, not a profit engine. Sample is **synthetic bear entries on real daily bars** (0 ledger legs entered in bear) — treat as design evidence, not live book proof. Note: full +6% TP mean R (-0.88%) also beats ride-SL here; ladder is not uniquely magical vs one-shot TP on this tape.

## Per-regime episodes

| Regime | Episodes | Need | OK | Days seen | Closed legs |
|--------|----------|------|----|-----------|-------------|
| bull | 0 | 5 | no | 0 | 0/15 |
| bear | 0 | 5 | no | 0 | 0/15 |
| flat | 119 | 5 | yes | 15 | 0/15 |

## Gate checklist

- **FAIL** `shadow_days_ge_60` — value=`14.26` need=`60`
- **FAIL** `shadow_days_ge_45_early` — value=`14.26` need=`45`
- **PASS** `flat_episodes_ge_min` — value=`119` need=`5`
- **FAIL** `bull_episodes_ge_min` — value=`0` need=`5`
- **FAIL** `bear_episodes_ge_min` — value=`0` need=`5`
- **FAIL** `multi_regime_bull_bear_flat` — value=`['flat']` need=`['bull', 'bear', 'flat']`
- **PASS** `mode_still_shadow` — value=`{'status_mode': 'shadow', 'map_mode': 'shadow'}` need=`shadow|off`
- **PASS** `auto_promote_false` — value=`False` need=`False`
- **PASS** `tp_not_live` — value=`shadow` need=`shadow|off`
- **PASS** `no_hard_blocks` — value=`[]` need=`[]`

## Non-goals

- Does **not** set `take_profit.mode=live` or map `live_apply`
- Does **not** replace multi-regime offline threshold re-study before Brad OK

Artifacts: `/home/brad/projects/crypto-trading-bot/data/state/exit_promote_scoreboard_latest.json` · `/home/brad/projects/crypto-trading-bot/reports/EXIT_PROMOTE_SCOREBOARD_LATEST.md`

