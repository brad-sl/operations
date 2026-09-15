# Luck Ladder Status — LATEST

**Plan:** `docs/plans/2026-09-15-luck-ladder-platform-refine.md`  
**Updated:** 2026-09-15  
**Mode:** measure-only · no live knobs · no auto-buy · no promote

## Board

| Rung | Factor | Status | Gate / next |
|------|--------|--------|-------------|
| **R0** | Sensor clock | **OBSERVE 24h** | Closeout ~2026-09-16 15:21 PT; high bar → X probe discuss only |
| **R1** | Knife vs wash | **SHIPPED shadow** | 7d crumbs → then R4/R6 unlock review |
| **R2** | Exit geometry | SCHEDULED | After R0 decision; extend PC-02 CF arms |
| **R3** | Fee / path tax | SCHEDULED | With/after R2; PC-05 tryout slice |
| **R4** | Seat lottery | BLOCKED | Needs R1 crumbs |
| **R5** | Size ladder | BLOCKED | Needs fills / hist N |
| **R6** | Regime tryout | BLOCKED | Needs R1 arms stable |

## R0 snapshot
- Cron: `phase6-rsi-event-x-tryout-shadow` 07:20/11:20/15:20/19:20 PT
- Closeout job: `phase6-rsi-event-x-shadow-observe-24h-close`
- Live_gate: OFF · paid_x: OFF

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

## Decisions log
- 2026-09-15: Brad GO save full ladder + Kanban + execute on schedule; R0 24h observe; R1 shipped shadow.
