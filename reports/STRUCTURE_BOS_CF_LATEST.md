# Structure BOS exit — offline CF

Generated: 2026-08-26T18:47:23.124992+00:00

## Method
- Timeframe: 1h Coinbase public candles
- Arm: MFE ≥ arm_mfe_pct vs entry
- Exit: close breaks last confirmed swing higher-low
- Compare: hold to path window end; optional 4% arm/2% trail; 3% SL when hit

## Results

| pair | n | fire% | mean BOS | mean hold | Δ BOS−hold | mean MFE |
|------|---|-------|----------|-----------|------------|----------|
| LINK-USD | 12 | 100% | +5.43% | +8.21% | -2.78% | 8.9% |
| BTC-USD | 9 | 100% | +4.73% | +6.04% | -1.31% | 7.3% |
| SOL-USD | 11 | 91% | +5.13% | +6.32% | -1.19% | 9.5% |
| ETH-USD | 11 | 100% | +4.40% | +8.17% | -3.76% | 7.6% |

## Honesty
- Real Coinbase OHLCV only.
- Entries = trough→arm heuristic, not live allocator — shape study not live guarantee.
- mean_bos includes non-fires held to window end.
- Positive Δ vs hold = less giveback on run failures; not auto promote.
- Shadow only — no live structure_bos sells.

JSON: `/home/brad/projects/crypto-trading-bot/data/state/structure_bos_cf_report.json`

## Go/no-go
- **Shadow collect** on live book (runner hook).
- **No live sell** until Brad OK + enough episodes + vs trail/SL scoreboard.

## First-run read (not a promote)

| Pair | Story |
|------|--------|
| LINK poster Aug11 | BOS fired; banked ~+4.7% on that entry path |
| Cross-pair means | BOS mean ret **below** hold-to-window-end → leaves meat in continuation bulls |
| vs trail 4/2 | BOS mean often near trail when both fire |

**Decision:** keep **shadow**. Collect live would-fires. Do not flip live without dump-leg scoreboard + Brad go.
