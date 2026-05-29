# Backtest Results Log

**Purpose**: Track every backtest run for the Sentiment-Enhanced Proportional Allocation strategy.  
**Owner**: Brad  
**Last Updated**: 2026-05-27

---

## Index

| Run ID | Date       | Layer Tested                                      | Return   | Notes                                      | Link |
|--------|------------|---------------------------------------------------|----------|--------------------------------------------|------|
| R-001  | 2026-05-27 | Full Pipeline (All components + X Sentiment)      | +9.46%   | 120-day historical                         | [Script](#r-001) |
| R-002  | 2026-05-27 | Layer 0 – Pure Inverse Volatility                 | +9.40%   | Baseline                                   | [Script](#r-002) |
| R-003  | 2026-05-27 | Layer 1 – Inverse Vol + Liquidity Bias            | +9.40%   | No improvement over Layer 0                | [Script](#r-003) |
| R-004  | 2026-05-27 | Layer 2 – + Holding Proportional Bias             | +9.44%   | Small lift from sticky scaling             | [Script](#r-004) |
| R-005  | TBD        | Layer 3 – + Time-Decayed X Sentiment              | -        | Key test                                   | -    |

---

## Run Details

### R-001 — 2026-05-27

**Date Run**: 2026-05-27  
**Software Version**: `sentiment_enhanced_allocation_backtest.py` v1.0  
**Layer Tested**: Full Pipeline  
**Return**: **+9.46%**  
**Test Script**: `backtests/capital_allocation/sentiment_enhanced_allocation_backtest.py`

---

### R-002 — 2026-05-27

**Date Run**: 2026-05-27  
**Software Version**: `layer0_pure_inverse_vol_backtest.py` v1.0  
**Layer Tested**: Layer 0 – Pure Inverse Volatility (Baseline)  
**Return**: +9.40%  
**Test Script**: `backtests/capital_allocation/layer0_pure_inverse_vol_backtest.py`

**Observations**: Clean baseline. No extra biases applied.

---

### R-003 — 2026-05-27

**Date Run**: 2026-05-27  
**Software Version**: `layer1_inv_vol_liquidity_backtest.py` v1.0  
**Layer Tested**: Layer 1 – Inverse Vol + Liquidity Bias  
**Return**: +9.40%  
**Test Script**: `backtests/capital_allocation/layer1_inv_vol_liquidity_backtest.py`

**Observations**: Liquidity bias alone did not improve returns over pure inverse vol in this period.

---

### R-004 — 2026-05-27

**Date Run**: 2026-05-27  
**Software Version**: `layer2_holding_bias_backtest.py` v1.0  
**Layer Tested**: Layer 2 – Inverse Vol + Liquidity + Holding Proportional Bias  
**Return**: +9.44%  
**Test Script**: `backtests/capital_allocation/layer2_holding_bias_backtest.py`

**Observations**: Adding holding proportional bias gave a small lift (+0.04%).

---

## Comparison Template: Layer 0 vs Layer 3

| Metric                        | Layer 0: No Sentiment | Layer 3: With X Sentiment | Delta |
|-------------------------------|-----------------------|---------------------------|-------|
| **Test Period**               | 120 days              | 120 days                  | - |
| **Starting Capital**          | $10,000               | $10,000                   | - |
| **Final Portfolio Value**     | $10,940.44            | TBD                       | TBD |
| **Total Return**              | +9.40%                | TBD                       | TBD |
| **Sharpe Ratio**              | TBD                   | TBD                       | TBD |
| **Max Drawdown**              | TBD                   | TBD                       | TBD |

**Run IDs Compared**: R-002 vs R-005 (pending)

---

**Status**: 4 of 6 layers completed. Ready to continue with R-005 (Layer 3 – Adding X Sentiment) tomorrow.