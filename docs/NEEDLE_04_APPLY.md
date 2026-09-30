# NEEDLE-04 apply — live geometry (Brad GO 2026-09-30)

**Status:** APPLIED. Guard (60m same-session) was already live. Geometry knobs + structure stops written this session.

## Live knobs (`config/trading_config_phase6.json`)

| Knob | Was | Now |
|---|---|---|
| `stop_loss_pct` | 0.03 | **0.08** |
| `sl_base_pct` | 0.03 | **0.08** |
| `sl_min_pct` | 0.02 | **0.06** |
| `sl_max_pct` | 0.05 | **0.12** |

Adaptive cannot return 3%. `enforce` stays true.

## Core sleeve

`data/state/core_skip_sl_pairs.json`: BTC-USD / ETH-USD still listed, but attach is allowed when `sl_pct ≥ 6%`. Tight 3% still skipped.

## Book (post-apply)

| Pair | Stop | Geometry |
|---|---|---|
| BTC-USD | $76,637.70 | ~8% from entry |
| ETH-USD | $2,458.07 | ~8% from entry |
| LINK-USD | $13.244 | 8% (replaced $13.906 / 3%) |
| PAXG-USD | $3,119.03 | E1 preserve — unchanged |

ETH attach lagged one settlement poll after cancel; retried and filled.

## Not done

- Did **not** dump remaining USDC.
- Did **not** size core to 40%.
- LINK 3% was cancelled on purpose so the tryout wears the same 8% floor.

Isolation: `scripts/phase6/test_isolation_needle_04_apply.py`.
