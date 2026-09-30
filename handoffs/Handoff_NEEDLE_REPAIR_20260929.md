# Handoff: P&L Needle Repair (2026-09-29)

**Owner:** performance-analyst (measurement + board) · crypto-engineer (implementation) · Brad (live GO)  
**Board:** `crypto-bot-project`  
**Workspace:** `/home/brad/projects/crypto-trading-bot` only  
**Trigger:** Last month flat (MTD −0.04%) while BTC +8.0%; book 97% cash; original USDC/sentiment designs never wired.

## Objective

Make the live book able to earn again **without** recreating the −69% go-live bleed: restore the USDC→USD→deploy cycle, RSI-gated X spend, washout re-entry, measurement truth, then a conservative BTC/ETH core.

## Current state (2026-09-30 01:54 UTC)

| Fact | Value |
|------|--------|
| Equity | $2,287 |
| USD / USDC / PAXG | $200 / $2,008 / $78.53 (+5.6%) |
| Open crypto risk | ~0% |
| Spendable cash (`cash_usd`) | **$200** (USDC excluded) |
| Park util | **91.3%** (counts USDC as crypto) |
| Regime | transition / soft_up, deploy open, cap $75, util target 55% |
| Tryout floor | sentiment 0.30; engine 0.00–0.07 (X 9.9h stale, 15m HL) |
| LINK tonight | X raw 0.31, RSI 34.7, blocked post-TP ~13.6h |
| Last 30d crypto | ~$1,046 buys, realized ~$2.30, LINK-dominated |
| Lifetime | 82 stop-loss vs 4 take-profit |
| Coinbase | Intro 0.9% taker / 0.5% maker |
| `phase6.db` trades | frozen 2026-07-06 (121k rows) |
| Runner | live, pid 1950441 |

## Original design (Brad, 2026-09-29) — not executed

1. **USDC is a temporary yield parking lot, not a perm bank.** Excess cash → USDC to earn a small return while the market is closed. When a door opens, USDC → USD → deploy. Unwind-to-spendable was never implemented; park util treats USDC as risk.
2. **Sentiment is expensive.** Full-bag X ≤ 2×/day. When **RSI opens the door**, spend X on **that pair only** to justify the trade. Do not refresh the whole bag. `rsi_event_x_probe` exists (LUCK-R0 done, `place_orders: false`); live floor still reads the decayed 2×/day cache.

## Hard rules for every card

- Canonical tree only: `/home/brad/projects/crypto-trading-bot`
- **No live orders. No `enforce: false`. No `force_rebalance`.** Shadow + isolation first.
- Do not write live knobs in `config/regime_cash_policy.json` / `trading_config_phase6.json` unless the card is explicitly a Brad-GO apply card.
- Do not duplicate parked work: `t_858d29a9` USDC+PAXG W0 shipped LIVE-OFF; `t_1f6450d7` LUCK-R0 sensor clock done. **Extend** those paths.
- Isolation tests for every behavior change. Cite file + command in the completion summary.

## Task graph (board `crypto-bot-project`)

```
t_d7a0706e NEEDLE-01 USDC→USD cycle            crypto-engineer        ready P0
t_0acee260 NEEDLE-02 RSI-gated pair X          crypto-engineer        ready P0
t_04d8e2e6 NEEDLE-06 post-TP washout rebuy     crypto-engineer        ready P0
t_796527c6 NEEDLE-10 phase6.db + util truth    performance-analyst    ready P0
t_e59e4dc0 NEEDLE-04 SL×fee + same-session SL  crypto-engineer        ready P1
t_362fe9d0 NEEDLE-07 dust/orphan               crypto-engineer        ready P1
t_dc324c27 NEEDLE-03 BTC/ETH beta core spec    crypto-engineer        ready P2
t_d73b7d45 NEEDLE-08 ignition ranking shadow   crypto-engineer        ready P2
t_0f973909 NEEDLE-05 size core vs tryout       crypto-engineer        todo  P3  parents 03, 04
t_273bff0a NEEDLE-09 fee/venue research        crypto-analyst         ready P4
t_c4fc7acb NEEDLE-REV first wave               code-reviewer          todo      parents 01, 02, 06, 10
```

## Success (program)

- Spendable buying power includes USDC when deploy is open (or USDC is a valid quote for *-USD).
- Util = non-stable crypto / equity (USD+USDC+PAXG excluded).
- An RSI-wash pair can get a **fresh pair-level X** without a full-bag refresh, and that score is what the live floor reads.
- Post-green-TP washout (RSI&lt;40) can re-enter on a short block; stop-exits keep the long block.
- `phase6.db` trades dual-write from the live ledger (`trades/phase6_trades.jsonl`).
- No live BTC/ETH core or size-up until Brad GO after 01+04.
