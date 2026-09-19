# Luck Ladder ∥ Scale-up parallel compare

**As of:** 2026-09-19T20:52:31.334035+00:00
**Mode:** R0/R1 measure · R5 live-path **ARMED** · money CLI-only · CF require ON

## Side-by-side

| Lane | Signal now | Blocks |
|------|------------|--------|
| **R0 sensor clock** | univ 8 · trigger 1 · would_buy_if_x 0 · prod_ok 1 | live_gate OFF; X floor; ZEC same_day |
| **R1 knife** | n_pairs=1 · ATTENTION_ONLY_knife_filter | measure-only; thin n_r |
| **R5 scale shadow** | scanned 3 · would_scale **0** | ZEC hold/r/phase5; LINK hold/r/phase3 |
| **R5 live path** | **armed=True** · planned **0** | CF n=0<8; no would_scale |

## R5 decisions
- **ZEC-USD**: skip · ['already_paper_scaled_cf_leg']
- **PAXG-USD**: sticky · ['sticky_ballast']
- **LINK-USD**: skip · ['already_paper_scaled_cf_leg']

## R1 arm_table
```
{
  "rsi_only": {
    "n_allow": 1,
    "n_sl": 0,
    "sl_rate": 0.0,
    "mean_r_net": -0.3690328083012354,
    "n_r": 1,
    "claim": "ATTENTION_ONLY"
  },
  "rsi_reclaim": {
    "n_allow": 1,
    "n_sl": 0,
    "sl_rate": 0.0,
    "mean_r_net": null,
    "n_r": 0,
    "claim": "ATTENTION_ONLY"
  },
  "rsi_delay_1_3": {
    "n_allow": 1,
    "n_sl": 0,
    "sl_rate": 0.0,
    "mean_r_net": null,
    "n_r": 0,
    "claim": "ATTENTION_ONLY"
  },
  "rsi_standdown_c": {
    "n_allow": 1,
    "n_sl": 0,
    "sl_rate": 0.0,
    "mean_r_net": -0.3690328083012354,
    "n_r": 1,
    "claim": "ATTENTION_ONLY"
  }
}
```
plain: Knife filter shadow · n_pairs=1 · live_gate=False | rsi_only: allow=1 sl=0 sl_rate=0.0 mean_r_net=-0.3690328083012354 [ATTENTION_ONLY] | rsi_reclaim: allow=1 sl=0 sl_rate=0.0 mean_r_net=None [ATTENTION_ONLY] | rsi_delay_1_3: allow=1 sl=0 sl_rate=0.0 mean_r_net=None [ATTENTION_ONLY] | rsi_standdown_c

## R0 plain
1 event-gap door(s); top 2 → ZEC-USD RSI=35.74 x_raw=0.0833 pass_est=False last_x_ok=False buy_if_pass=False Would-buy-if-X-clears: 0. Live gate OFF. | prod_entry_ok_now=1/8

## E2E gaps still open
- CF chicken-egg: scores only after would_scale registers paper lot AND later exit; would_scale=0 => CF n=0 => live plan blocked while require=true
- R5 gates (hold>=2h, r in [1.5%,3.8%], phase in {1,2}) reject ZEC phase5 / LINK phase3 flat bags — may never scale these seats
- Armed path still needs operator CLI for money; no runner hook / no auto-apply (intentional)
- same_day_pair_buy is entry gate (R0); scale uses OrderExecutor direct — live SL reattach + bag_id on add not E2E proven
- tryout_tagged_buy false / empty entry_reason on live lots — weak episode tagging for scale registry
- R2 exit geometry / R3 fee tax / R4 seat lottery / R6 regime tryout still scheduled/blocked
- No dedicated parallel-compare cron; board is on-demand
- R0 spend_x false on shadow board; paid probe separate — entry crumbs slow

## How to get quality data (without degen)
1. Keep shadow cron — wait hold>=2h; if r/phase never clear, loosen **measure** gates so paper would_scale can register CF legs.
2. Or waive CF require for first 1–2 operator steps (separate GO) — still 1/day $25 caps.
3. Or synthetic scale-vs-stay on every tryout exit (code) — best N, bigger change.

State: `data/state/luck_ladder_parallel_compare_latest.json`
