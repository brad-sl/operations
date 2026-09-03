# Decide — runtime knobs SSOT (hardcode cleanup)

**Date:** 2026-08-18  
**CR:** `runtime_knobs_ssot`  
**Live promote of new risk numbers:** no — only **read path** cleanup so existing config wins  

## Problem
Live paths silently defeated knobs:
- allocator `stop_loss_pct=0.12` while config **3%**
- post-SL block fallbacks **24h** while config **72h**
- reserve fallbacks **$200/$250** while config **$50**
- cap fallback **$200** while config **$150**

## Fix
| Piece | Change |
|-------|--------|
| `phase6/core/runtime_knobs.py` | **NEW** single helper: SL%, cap, reserve, block hours, allocator kwargs |
| `rebalance_coordinator` | create_allocator_from_config; min_reserve/cap/min_rsi from knobs |
| `cycle_coordinator` | mid-cycle shadow allocator from knobs |
| `runner_capital_events` | defaults 72h + hold_cash True |
| `allocator.AllocatorConfig` | defaults 3% / 0.05 score (not 12% / 0.15) |
| `phase6_runner` fresh-start reserve | knobs |
| `trading_config_phase6.json` | explicit `global_settings.allocator` + `deploy_min_rsi` |

## ISO
`scripts/phase6/test_isolation_runtime_knobs.py` PASS  
`scripts/phase6/test_isolation_post_sl_block_enforce.py` PASS  

## Behavior note
Allocator rotation drawdown now aligns with **3%** stop (was 12% in code). That is intentional integrity, not a new experiment. Cap/reserve/block still match written config.

## Must-not
- Do not reintroduce bare `create_allocator(..., stop_loss_pct=0.12)`
- Do not default block hours to 24
