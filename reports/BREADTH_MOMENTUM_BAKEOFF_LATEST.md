# Breadth momentum bake-off (B1–B4)
As of `2026-08-19T17:46:22.464650+00:00`

Tape: **2021-01-01 → 2026-08-15** (2053 BTC daily bars). Universe: BTC-USD, ETH-USD, SOL-USD, XRP-USD, LINK-USD, AVAX-USD, DOGE-USD, ADA-USD. Bear veto BTC 30d ≤ −10%. Fee RT ~20 bps on signal entries.

## Plain English

Primary paper candidate B4 (vol-expand cluster): 7d mean +1.67% vs cash, hit ~54%, N=76. Only +0.41pp vs always-long EW beta — modest, not a free lunch. B3 (BTC breakout+RSI+breadth) loses vs cash — not breadth primary. B1/B1b positive vs cash but FA~48–51%. Exploit live? NO. Next=paper would-fire.

Returns are mean per-signal forward EW of signal names vs cash after fee. Not portfolio APY. N sparse arms are inconclusive. Always-long control shows raw beta available on non-bear days — signal must beat cash with acceptable FA; beating always-long is bonus not required for paper shadow.

## Scoreboard (mean forward return after fee vs **cash**)

| Arm | N sig | 1d mean / hit / N | 3d mean / hit / N | 7d mean / hit / N | FA (7d<0) |
|-----|------:|-------------------|-------------------|-------------------|----------|
| `B1_breadth_thrust_3pct_k4` | 191 | +0.05% / +46.07% / 191 | +0.51% / +51.31% / 191 | +0.62% / +47.64% / 191 | +50.79% |
| `B1b_breadth_2pct_k4` | 294 | +0.11% / +49.32% / 294 | +0.49% / +51.02% / 294 | +1.03% / +50.68% / 294 | +48.30% |
| `B2_median_basket_2_5pct` | 272 | +0.05% / +48.16% / 272 | +0.43% / +50.00% / 272 | +0.71% / +49.26% / 272 | +50.00% |
| `B3_btc_breakout_rsi_breadth` | 104 | -0.08% / +40.38% / 104 | -0.49% / +41.35% / 104 | -0.36% / +40.38% / 104 | +57.69% |
| `B4_vol_expand_cluster` | 76 | -0.04% / +55.26% / 76 | +0.65% / +52.63% / 76 | +1.67% / +53.95% / 76 | +46.05% |
| `C0_always_ew_nonbear` | 1603 | +0.14% / +51.90% / 1603 | +0.49% / +52.53% / 1603 | +1.26% / +52.40% / 1603 | n/a |

Control always-EW non-bear 7d mean: **+1.26%** (this is beta, not a trade signal).

## Decision

- status: **paper_shadow_candidate**
- primary: `B4_vol_expand_cluster`
- secondary: `B1b_breadth_2pct_k4`
- exploit_ready: **false**
- Primary paper candidate B4 (vol-expand cluster): 7d mean +1.67% vs cash, hit ~54%, N=76. Only +0.41pp vs always-long EW beta — modest, not a free lunch. B3 (BTC breakout+RSI+breadth) loses vs cash — not breadth primary. B1/B1b positive vs cash but FA~48–51%. Exploit live? NO. Next=paper would-fire.

## Aug 2026 case flags (calendar days on tape)

```json
{
  "2026-08-15": {
    "B1": false,
    "B2": false,
    "B3": false,
    "B4": false,
    "bear": false,
    "greens_B1": [
      "LINK-USD"
    ]
  }
}
```

JSON: `/home/brad/projects/crypto-trading-bot/data/state/breadth_momentum_bakeoff_latest.json`
