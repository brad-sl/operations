# Liquidation redeploy — shadow scoreboard

**As of:** 2026-08-16T22:26:10.390770Z  
**Cut:** 2026-07-01T00:00:00+00:00  
**Orders placed:** **0** (shadow only)

## Best-case outcome (what “good” looks like)

1. **Product best case:** On eligible **rotation** free-cap events, shadow would-fire a **≤$75 / 25%** hop into a gate-passing pair; over ≥30 days and ≥15 fires, **net PnL after fees > hold-cash ($0 hop)**, second-stop rate no worse than baseline, and this is not only a bull artifact.  
2. **Oracle upper bound (this report):** If we had perfect hindsight and always bought the best 7d pair in-universe at shadow size, what net $ after fees? If *that* is ≤0, live partial cannot be justified.  
3. **Ops best case:** Skip reasons are explainable by regime (bear park, RSI gate, deny SL proceeds) — not silent bugs.

## Overall backfill

| Metric | Value |
|--------|------:|
| Free-cap events | 33 |
| Policy eligible (rotation allow-list + size + not bear-block) | 7 (0.212) |
| Shadow notional sum | $360.44 |
| Fee sum @ cfg | $2.16 |
| Oracle n / sum net PnL / mean / WR | 6 / **2.54** / 0.42 / 0.833 |
| Actual follow-buy SL PnL (live path) | -243.2 |

## By regime proxy (BTC ~30d path at event)

| Regime | n | eligible | oracle sum net | oracle WR | actual follow SL $ |
|--------|--:|---------:|---------------:|----------:|-------------------:|
| flat | 33 | 7 | 2.54 | 0.833 | -243.2 |

_Historical policy eligibility = reason allow-list + size + bear proxy block. Entry RSI/sent gates need live/cache at event time (not fully reconstructed); oracle_net_pnl is an upper-bound if we always picked the best 7d pair in-universe._

## Live-once (latest rotation-class sell + current RSI/sent)

- Trigger: `{'ts': '2026-08-16T16:01:00.817302+00:00', 'pair': 'BTC-USD', 'reason': 'rotation_exchange', 'usd': 1992.27}`  
- Regime: `{'regime': 'flat', 'allow_new_buys': True, 'rebalance_cap_usd': 75.0, 'label': 'Flat — cautious gated deploy (operator thaw 2026-07-18 B)'}`  
- **Would fire:** **False** · skip=`no_eligible_candidate`  
- Size `$75.0` → `None` score=None fee=$0.45  
- Orders placed: **0**

## Go/no-go

Shadow collection only. **No live_partial** until product gates in `docs/features/LIQUIDATION_ROTATION_REDEPLOY_POLICY.md` §5.

Regen: `bash scripts/phase6/run_liquidation_redeploy_shadow.sh`

