# Market structure S/R shadow — 20260815

**Family:** support & resistance / market-structure price action  
**Arms:** bounce vs break+retest (separate). Optional RSI add-on.  
**Live writes:** none

## Plain English

### `last_14d` (2026-08-01 → 2026-08-15)
- **Headline:** Best structure arm `SR_BREAK_RSI` still sparse/inconclusive on last_14d
- SR_BOUNCE: inconclusive (N=4 trades) — not promote
- SR_BOUNCE_RSI: inconclusive (N=4 trades) — not promote
- SR_BREAK_RETEST: inconclusive (N=2 trades) — not promote
- SR_BREAK_RSI: inconclusive (N=1 trades) — not promote

| Arm | Mean ret | Mean maxDD | Trades |
|-----|----------|------------|--------|
| BH | +5.80% | -2.94% | 5 |
| BASE_RSI | +5.80% | -2.94% | 5 |
| SR_BOUNCE | -1.52% | -3.03% | 4 |
| SR_BOUNCE_RSI | -1.52% | -3.03% | 4 |
| SR_BREAK_RETEST | -0.20% | -0.23% | 2 |
| SR_BREAK_RSI | -0.13% | -0.22% | 1 |

### `last_90d` (2026-05-17 → 2026-08-15)
- **Headline:** Best structure arm `SR_BREAK_RSI` still sparse/inconclusive on last_90d
- SR_BOUNCE: no_go vs BASE (-6.0pp, class unstable_or_no_edge)
- SR_BOUNCE_RSI: no_go vs BASE (-4.6pp, class unstable_or_no_edge)
- SR_BREAK_RETEST: inconclusive (N=10 trades) — not promote
- SR_BREAK_RSI: inconclusive (N=2 trades) — not promote

| Arm | Mean ret | Mean maxDD | Trades |
|-----|----------|------------|--------|
| BH | -13.55% | -27.33% | 5 |
| BASE_RSI | -14.92% | -20.36% | 18 |
| SR_BOUNCE | -20.90% | -21.74% | 16 |
| SR_BOUNCE_RSI | -19.56% | -20.42% | 15 |
| SR_BREAK_RETEST | -8.10% | -9.49% | 10 |
| SR_BREAK_RSI | -1.80% | -1.96% | 2 |

### `long_tape` (2021-01-01 → 2026-08-15)
- **Headline:** Best structure arm `SR_BREAK_RSI` less-loss vs BASE only on long_tape
- SR_BOUNCE: no_go vs BASE (-4.3pp, class unstable_or_no_edge)
- SR_BOUNCE_RSI: no_go vs BASE (-3.6pp, class unstable_or_no_edge)
- SR_BREAK_RETEST: no_go vs BASE (-6.6pp, class unstable_or_no_edge)
- SR_BREAK_RSI: weak/observe — beats BASE by +9.6pp ret (class unstable_or_no_edge)

| Arm | Mean ret | Mean maxDD | Trades |
|-----|----------|------------|--------|
| BH | +48.20% | -86.31% | 5 |
| BASE_RSI | -93.13% | -97.46% | 421 |
| SR_BOUNCE | -97.43% | -97.70% | 318 |
| SR_BOUNCE_RSI | -96.70% | -97.01% | 305 |
| SR_BREAK_RETEST | -99.73% | -99.74% | 724 |
| SR_BREAK_RSI | -83.52% | -85.07% | 283 |

## Overall

- **Primary window:** `long_tape`
- **Call:** Best structure arm `SR_BREAK_RSI` less-loss vs BASE only on long_tape
- **Enum:** `drop`
- **14d context:** Best structure arm `SR_BREAK_RSI` still sparse/inconclusive on last_14d

## Frozen knobs

- Swing pivot: **N=3** bars each side (confirmed with lag N)
- Zone half-width: **0.35×ATR**
- Bounce: touch support band + close back above band top
- Break/retest: close > resist band high; or retest hold within 5d after break
- Regime allow: BTC 30d bull/flat only; RSI caps flat≤55.0 bull≤70.0
- Exit: structure target/fail, SL 3%, max hold 30d
- Data: Coinbase daily; fee 5 bps/side; equal-weight pair mean

## Go / no-go rules

- Promote only if long-tape structure arm beats BASE on ret **and** DD, N≥15, then multi-week shadow — never auto-live.
- Bounce and breakout stay **separate** arms forever.
- Sparse short windows → inconclusive.

JSON: `SR_STRUCTURE_ENTRY_SHADOW_20260815.json`
