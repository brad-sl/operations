# Basket hot-reload (pairs membership without runner restart)

## What

Live `Phase6Runner` reloads `global_settings.pairs` each cycle when:

1. `config/trading_config_phase6.json` mtime changes, or
2. `data/state/basket_reload.flag` exists (written by promote).

## What it does / does not

| Does | Does not |
|------|----------|
| Update `FIXED_UNIVERSE` + `config_dict["global_settings"]["pairs"]` | Place orders |
| Seed price history for **added** pairs | Liquidate **removed** pairs |
| Log `[BASKET-RELOAD]` + write `data/state/basket_hot_reload_latest.json` | Hot-reload SL / deploy_pct / preserve knobs |

## Guards

- Min 6 pairs
- Sticky **BTC-USD** and **ETH-USD** must remain
- Parse/load failure keeps previous universe

## Operator

```bash
# After promote — same runner PID expected
rg "BASKET-RELOAD" logs/phase6_runner.log | tail -5
cat data/state/basket_hot_reload_latest.json
pgrep -af 'phase6.core.phase6_runner'
```

Still **restart** for runner **code** deploys or non-pairs config changes.

## Code

- `phase6/core/basket_hot_reload.py`
- Hook: `Phase6Runner._run_cycle`
- Promote: `scripts/phase6/promote_basket_proposal.py` → touches flag
- Isolation: `scripts/phase6/test_isolation_basket_hot_reload.py`
