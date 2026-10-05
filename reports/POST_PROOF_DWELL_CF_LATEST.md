# Post-Proof Dwell CF (Tier A + B)

**As of:** 2026-10-05T05:57:31.723482Z
**Edge class:** `ATTENTION_ONLY_less_loss_path` (forced — not HIT_10)
**live_apply:** false (CF pack never arms money)

## Plain English

Post-proof dwell CF: blocking tryout re-seats after TP would have stopped several same-name shells (see ban arms). Hold-after-TP 7d marks are context only (1/3 green after RT fee estimate). Edge stays ATTENTION_ONLY_less_loss_path until live shadow cycles clear.

## Tier A — block tryout re-seat after TP

| Arm | Blocked buys | USD blocked | Eject-after | Est fees avoided | TP-after (miss) | Net sketch |
|-----|-------------:|------------:|------------:|-----------------:|----------------:|-----------:|
| ban_168h | 8 | 228.89 | 4 | 1.7961 | 3 (6.1924) | -4.3963 |
| ban_24h | 1 | 24.91 | 1 | 0.4483 | 0 (0.0) | 0.4483 |
| ban_48h | 5 | 124.77 | 3 | 1.3475 | 2 (3.835) | -2.4874 |

_Net sketch = est eject RT fees avoided − TP pnl on shells after a blocked buy. Not alpha._

## Tier B — hold-after-TP mark @7d

- TP events: **5** · with OHLCV mark: **3**
- Mark green after RT fee est: **1** (0.333)
- Path hit ~−3% SL band: **1** (0.333)

Mark CF is path context only — not lot PnL, not proof of buy/hold alpha. Green run-up + red end = trap; always report both mark and path min.

### Tier B rows

| Pair | TP ts | TP pnl | Mark 7d | Mark−fee | Path min | SL path |
|------|-------|-------:|--------:|---------:|---------:|:-------:|
| SOL-USD | 2026-10-02T07:21:56 | 2.4314438784000023 | 0.005 | -0.013 | -0.0285 | False |
| LINK-USD | 2026-09-18T13:50:39 | 4.5408000000000035 | 0.1614 | 0.1434 | -0.0072 | False |
| LINK-USD | 2026-09-29T15:30:38 | 2.3573800000000027 | -0.0539 | -0.0719 | -0.0874 | True |
| ZEC-USD | 2026-09-21T01:54:42 | 0.6231838251999998 | None | None | None | False |
| ZEC-USD | 2026-09-22T23:07:14 | 1.477591976400001 | None | None | None | False |

## Per-pair tax sketch

| Pair | n TP | TP $ | n eject | eject $ | post-TP tryout≤48h |
|------|-----:|-----:|--------:|--------:|-------------------:|
| ADA-USD | 0 | 0 | 0 | 0 | 0 |
| AVAX-USD | 0 | 0 | 0 | 0 | 0 |
| BTC-USD | 0 | 0 | 0 | 0 | 0 |
| DOGE-USD | 0 | 0 | 0 | 0 | 0 |
| ETH-USD | 0 | 0 | 0 | 0 | 0 |
| HYPE-USD | 0 | 0 | 2 | -1.0739 | 0 |
| LINK-USD | 2 | 6.8982 | 3 | -0.4959 | 3 |
| SOL-USD | 1 | 2.4314 | 1 | -0.0774 | 1 |
| TIA-USD | 0 | 0 | 2 | -1.3381 | 0 |
| UNI-USD | 0 | 0 | 0 | 0 | 0 |
| XRP-USD | 0 | 0 | 0 | 0 | 0 |
| ZEC-USD | 2 | 2.1008 | 0 | 0 | 1 |

## Ledger rebuild → would-be graduated (as-of now)

- Proof sells hist: **5**
- Active graduated (if stamped continuously): **2** → ['LINK-USD', 'SOL-USD']

## Honesty bars

**Can support:** less tryout reincarnation after TP, lower eject fee thrash on proven names, multipair process-tax reduction

**Cannot prove:** long-term higher returns, buy/hold beats TP banking on every path, fee-blind MTM as profit

## Next

1. Shadow crumbs accumulate on composer + scale-window (`live_apply=false`).
2. Re-run this CF weekly; promote only after multipair less-tax holds.
3. Brad GO required for `config/post_proof_dwell.json` → `live_apply: true`.

