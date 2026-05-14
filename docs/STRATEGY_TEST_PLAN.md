# Strategy Comparison Test — Phase 4 v4

**Status:** Framework created, parallel test pending

**Schemas Updated:**
- ✅ `trader_configs` table (per-trader, per-pair parameters + strategy choice)
- ✅ `strategy_backtest` table (tracks metrics per strategy)

**Test Harness:** `phase4_v4_strategy_test.py`
- Loads 3 strategies from `trader_configs`
- Runs all 3 in parallel on same market data
- Logs exits to `strategy_backtest` table
- Prints running win rate, P&L, avg per strategy

**Current Config (Brad):**
| Strategy | BTC-USD | XRP-USD |
|----------|---------|---------|
| fixed | 1.0% | 1.0% |
| fee_aware | 0.3% | 0.3% |
| pair_specific | 0.5% | 1.5% |

**Alternative: Patch Phase 4 v3**
Since schema migration is complex, we could:
1. Add `strategy` column to trades table
2. Add `min_profit_pct_threshold` to trades at insert time
3. Log which strategy triggered each exit
4. Run v3 with per-pair config from `trader_configs`
5. Report results at EOD

**Next Step:**
Implement strategy parameter loading in v3, run through EOD, compare results.
