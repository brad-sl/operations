# Sentiment + Rebalancing Integration (2026-05-31)

## Logic Applied

**File:** `phase6/scripts/sentiment_rebalance_integration.py`

**Core Function:** `apply_sentiment_to_allocations()`

### Flow
1. Rebalancing trigger fires (every 7 cycles when correlation > 0.7).
2. Correlation-based reserve shift occurs first (50% of high-corr pairs moved to reserve).
3. `apply_sentiment_to_allocations()` is called on the resulting allocations.
4. Sentiment scores are loaded via `sentiment_scorer.load_sentiment_scores()`.
5. Weights are adjusted using `get_sentiment_adjusted_weights()` with **20% sentiment influence**.
6. Allocations are renormalized to sum to 1.0.
7. Result is logged and returned to the harness.

### Parameters
- `sentiment_weight = 0.20` (20% influence) — matches current `sentiment_scorer` default.
- Graceful degradation: if sentiment loading fails, original allocations are returned unchanged.

### Test Results
- Module imports cleanly when project root is in `sys.path`.
- Falls back safely when sentiment scorer is unavailable.
- Logs before/after allocations for auditability.

## How to Wire into `phase5_multi_pair.py`

Add this single line inside `_rebalance_if_needed` after the correlation reserve shift:

```python
self._apply_sentiment_adjustment()   # NEW: sentiment-weighted redeployment
```

Or call the standalone function:

```python
from phase6.scripts.sentiment_rebalance_integration import apply_sentiment_to_allocations

self.allocations = apply_sentiment_to_allocations(
    self.allocations, self.pairs
)
```

## Preparation for Live Testing

1. Ensure `sentiment_cache.json` (or the new unified cache) has recent data.
2. Run the harness with `--cycles 20` or higher so at least one rebalance cycle triggers.
3. Monitor logs for:
   - "Sentiment scores loaded"
   - "Applying sentiment adjustment"
   - "Allocations AFTER sentiment"

## Next Steps
- Add unit test for `apply_sentiment_to_allocations` with mocked sentiment.
- Wire the one-line call into the main harness.
- Add Prometheus metric for "sentiment_adjustment_applied".