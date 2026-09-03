# Return entropy shadow (latest)

- **ts:** 2026-08-31T02:56:27.587761+00:00
- **plain:** Return-entropy shadow only — concentration of recent returns, not a buy signal. structure=low H_norm, noise=high H_norm. No orders, no promote.
- **window / bins:** 48 / 10
- **cutoffs:** structure < 0.35 ; noise > 0.7
- **counts:** {"structure": 0, "mid": 3, "noise": 0, "insufficient": 0}

| pair | H_norm | label | n_ret | last_ret |
|------|--------|-------|-------|----------|
| BTC-USD | 0.399 | mid | 149 | -0.0033 |
| ETH-USD | 0.494 | mid | 149 | -0.0045 |
| SOL-USD | 0.587 | mid | 149 | -0.0031 |

## Doctrine
- Shadow only. No seat / buy / promote.
- Success metrics: see `reports/RETURN_ENTROPY_SUCCESS_METRICS.md`.
- Offline dig: `phase6/research/return_entropy_filter_shadow.py`.
