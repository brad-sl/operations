# Capital Deployment System

## Overview

The `deploy_capital` module provides a standalone, reusable function for allocating new or freed capital across trading pairs using sentiment-driven logic.

It is designed to be called by multiple systems (harness, monitors, liquidation handlers, deposit detectors) rather than being tightly coupled to the main trading harness.

## Core Function

**Location:** `phase6/scripts/deploy_capital.py`

```python
from phase6.scripts.deploy_capital import deploy_capital

new_allocations = deploy_capital(
    current_allocations=...,   # dict of pair -> dollars
    new_capital=150.0,
    sentiment_scores=...,      # dict of pair -> sentiment
    source="liquidation",      # "deposit", "liquidation", "reserve", "takeover"
    candidate_pairs=...,       # optional list of pairs to consider
    allow_new_pairs=True
)
```

## Key Features

- **Smart Pair Selection**: Opens new pairs only when the current basket is weak or small.
- **Quality Control**: New pairs require stronger sentiment (≥ +0.20) than existing holdings.
- **Capital Preservation**: Total capital is preserved (no renormalization to 1.0).
- **Reserve Discipline**: When `source="reserve"`, only deploys to pairs with non-negative sentiment.

## Interconnected Systems

| System                        | Relationship to Capital Deployment                  | Integration Point |
|-------------------------------|-----------------------------------------------------|-------------------|
| `Phase5Harness`               | Main trading loop                                   | Can call `deploy_capital` after liquidations or deposits |
| `sentiment_scorer.py`         | Provides sentiment scores                           | Input to `deploy_capital` |
| Rebalancing (`_rebalance_if_needed`) | Triggers reserve creation                          | Can call `deploy_capital(source="reserve")` |
| External Monitors             | Detect new deposits or liquidations                 | Primary callers of `deploy_capital` |
| Paper/Live Runners            | Execute the resulting allocations                   | Consume output of `deploy_capital` |

## Example Call Sites

### 1. After a liquidation (in a monitor)

```python
from phase6.scripts.deploy_capital import deploy_capital

freed_capital = 180.0  # from stop-loss
current_allocs = harness.allocations
sentiment = load_latest_sentiment()

new_allocs = deploy_capital(
    current_allocations=current_allocs,
    new_capital=freed_capital,
    sentiment_scores=sentiment,
    source="liquidation",
    candidate_pairs=harness.universe
)

harness.allocations = new_allocs
```

### 2. Reserve redeployment (inside rebalancing)

```python
if self.reserve > 50:
    self.allocations = deploy_capital(
        current_allocations=self.allocations,
        new_capital=self.reserve,
        sentiment_scores=current_sentiment,
        source="reserve",
        min_sentiment=0.0
    )
    self.reserve = 0.0
```

## Testing

Tests are located in `phase6/tests/test_deploy_capital.py`.

Run with:

```bash
python -m pytest phase6/tests/test_deploy_capital.py -v
```