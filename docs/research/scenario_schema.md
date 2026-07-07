# Scenario pack schema (ANALYST-OPT)

Version: **1.0** (R0 — backtest engine knobs only; ARCH knobs added in R1)

## File layout

- Packs live under `phase6/research/scenarios/*.json`
- One pack = one optimization experiment (matrix or explicit list)

## Top-level object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | string | yes | `"1.0"` |
| `pack_id` | string | yes | Stable id, e.g. `r0_smoke_three` |
| `description` | string | no | Human summary |
| `primary_metric` | string | yes | `sharpe_ratio` \| `total_return_pct` \| `max_drawdown_pct` (for max_dd, lower is better) |
| `baseline_scenario_id` | string | yes | Scenario id to compare against for promotion |
| `date_range` | object | yes | `start` / `end` as `YYYY-MM-DD` |
| `scenarios` | array | yes | List of scenario objects |

## Scenario object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique within pack |
| `label` | string | no | Display name |
| `backtest` | object | yes | Maps to `BacktestConfig` (R0) |

### `backtest` fields (R0)

| Field | Type | Default |
|-------|------|---------|
| `initial_capital` | number | 1000 |
| `enable_pair_expansion` | bool | false |
| `candidate_universe` | string[] | [] |
| `rebalance_frequency_days` | int | 7 |
| `rebalance_cap_usd` | number | 200 |

## Future (R1) — reserved keys

Do not use in R0 runners until ARCH wires them:

- `evaluation.mode`, `allocator.strategy`, `signals.weights`, `env.min_reserve`, `shadow_only`

## Gates (R2 promotion)

Document in pack optional `gates`:

```json
"gates": {
  "max_drawdown_slack_pct": 2.0,
  "min_sharpe_delta_vs_baseline": 0.05,
  "require_holdout": true
}
```

## Example

See `phase6/research/scenarios/r0_smoke_three.json`.