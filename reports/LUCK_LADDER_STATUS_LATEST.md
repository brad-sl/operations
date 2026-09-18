# Luck Ladder Status — LATEST

**Plan:** `docs/plans/2026-09-15-luck-ladder-platform-refine.md`  
**Updated:** 2026-09-16  
**Mode:** measure-only · no live knobs · no auto-buy · no promote

## Board

| Rung | Factor | Status | Gate / next |
|------|--------|--------|-------------|
| **R0** | Sensor clock | **OBSERVE EXTENDED** | Closeout **2026-09-17 19:35 PT**; reliability check through tomorrow |
| **R1** | Knife vs wash | **SHIPPED shadow** | 7d crumbs → then R4/R6 unlock review |
| **R2** | Exit geometry | SCHEDULED | After R0 decision; extend PC-02 CF arms |
| **R3** | Fee / path tax | SCHEDULED | With/after R2; PC-05 tryout slice |
| **R4** | Seat lottery | BLOCKED | Needs R1 crumbs |
| **R5** | Size ladder | BLOCKED | Needs fills / hist N |
| **R6** | Regime tryout | BLOCKED | Needs R1 arms stable |

## R0 snapshot
- Cron: `phase6-rsi-event-x-tryout-shadow` 07:20/11:20/15:20/19:20 PT
- Window: **2026-09-15 15:21 PT → 2026-09-17 19:35 PT** (~48h extended)
- Closeout job: `phase6-rsi-event-x-shadow-observe-close` @ 2026-09-17 19:35 PT
- Live_gate: OFF · paid_x: OFF
- Mid-extend (2026-09-16): ticks with pool/topK present early; quiet when RSI left wash band — looks viable as clock alternative, not yet reliability-proven
- Brad GO 2026-09-16: extend through tomorrow for pattern reliability (still discuss-only after closeout)

## R1 snapshot
- **SHIPPED** measure-only: `phase6/core/knife_filter_shadow.py`
- Arms: rsi_only · rsi_reclaim · rsi_delay_1_3 · rsi_standdown_c
- Isolation: 10/10 · Cron: `phase6-knife-filter-shadow` 07:30/19:30 PT
- Kanban: `t_caa744ee`

## Kanban ids (`crypto-bot-project`)
| Card | id |
|------|-----|
| HUB | `t_529fe799` |
| R0 | `t_1f6450d7` |
| R1 | `t_caa744ee` |
| R2 | `t_38978231` |
| R3 | `t_c4cdbb75` |
| R4 | `t_dd19b4f6` |
| R5 | `t_ed05d5fb` |
| R6 | `t_b21b3108` |

## Post-R0 switch (PROPOSED — armed)
**Plan:** `docs/plans/2026-09-16-rebalance-book-vs-rsi-buy-x-split.md`  
**Brad GO save:** 2026-09-16 · **Cutover GO:** only after R0 PASS + explicit GO  
**Target:** rebalance = book only · new buys = RSI-event · X = prospects + rebalance candidates (replace full-pool 2×)

## Decisions log
- 2026-09-15: Brad GO save full ladder + Kanban + execute on schedule; R0 24h observe; R1 shipped shadow.
- 2026-09-16: Brad GO extend R0 observe through tomorrow (~48h total) for pattern reliability; paid X / live gate still OFF.
- 2026-09-16: Brad GO **save** post-R0 switch plan (rebalance/X split). Switch only if shadow passes closeout; cutover not yet authorized.

## R0 validate 2026-09-18 (Brad GO)

- Observe closed PASS → **paid X probe ON** under budget (rsi ≤2 pair-q/day, cooldown 6h)
- CLI: `python3 scripts/phase6/run_rsi_event_x_probe.py [--go]`
- Cron: `phase6-rsi-event-x-probe` @ :25 after shadow ticks
- X-split Task1: `rebalance_x_candidates` + budget SSOT live; **full-book 2× still runs** until cutover GO (`x_query_split.rebalance_candidates_only`)
- `place_orders` still **false** — probe feeds cache/latch only; buys still gate stack

