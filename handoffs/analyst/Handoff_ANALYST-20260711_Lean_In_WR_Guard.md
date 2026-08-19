# Handoff — ANALYST-OPT `r3_lean_in_exposure_wr_guard`

**ID:** ANALYST-20260711-LEAN-IN  
**Owner:** Crypto-Analyst (Hermes intelligence / weekly OPT)  
**User ask:** Lean into active trades for better return without giving up much of the **live Exit WR** (~66%, 19/29 realizing exits).

## Production anchor (ground truth)

| Metric | Value | Source |
|--------|-------|--------|
| Exit WR | **65.5%** (UI 66%) | `19/29` sells with non-zero `pnl` in last 100 ledger rows |
| Deploy | `deploy_pct=0.72`, `rebalance_cap_usd` per live config | `config/trading_config_phase6.json` |
| Shadow overlay | REGIME-ADAPTIVE (often defensive 21d in flat) | `config/regime_knob_map.json` |

**Note:** Old ~55% backtests are **not** the same metric (harness has no exit-WR; different window/engine). Compare like-for-like only.

## Pack

`phase6/research/scenarios/r3_lean_in_exposure_wr_guard.json`

Sweeps **wired ARCH-4 knobs**: `rebalance_frequency_days`, `rebalance_cap_usd`, rotation vs rebalance, plus **recent 90d** slice.

## Analyst procedure

1. OHLCV extend + `sync_pack_dates_to_ohlcv.py` if needed.
2. `run_param_audit.py` — gate before promotion narrative (`fail_count==0`, `confidence>=0.85`).
3. Run leaderboard:
   ```bash
   cd /home/brad/projects/crypto-trading-bot
   python3 phase6/research/run_scenario_leaderboard.py \
     --pack phase6/research/scenarios/r3_lean_in_exposure_wr_guard.json \
     --compare-production --refresh-param-audit
   ```
4. **WR guard (mandatory for this pack):** After leaderboard, compute **live exit WR** on pack overlap:
   ```bash
   PYTHONPATH=. python3 -c "
   from phase6.core.trade_ledger import TradeLedger
   led = TradeLedger()
   trades = led.get_recent_trades(limit=200)
   closed = [t for t in trades if t.get('pnl') is not None and float(t.get('pnl') or 0) != 0]
   w = sum(1 for t in closed if float(t.get('pnl') or 0) > 0)
   print('exit_wr', round(w/len(closed),3) if closed else None, 'n', len(closed))
   "
   ```
   In the honest brief: **only recommend shadow** for scenarios that beat baseline **Sharpe** *and* do not imply lower churn quality — flag if `avg_exposure_pct` rises >10pp vs baseline with worse `max_drawdown_pct`.
5. `run_winner_regime_stress.py` if any lean scenario wins headline rank.
6. `format_honest_assessment` — cite `run_id`; compare return vs production overlap, not full pack window only.
7. Proposals → `analyst_proposed_backlog.json` (**shadow only**). Live `deploy_pct` / cap changes need user + Kimi evaluator.

## Follow-on engineering (if pack inconclusive)

| Gap | Why it matters for “lean in” |
|-----|------------------------------|
| `deploy_pct` not in scenario_knobs | Live 0.72→0.80 is main lever; harness uses full deploy via allocator |
| `min_move_usd` not passed to `run_arch4_backtest` | `rebalance_cap_usd` only partially maps (ANALYST-OPT-R5) |
| No harness exit-WR / SL simulation | Cannot directly optimize 66%-style WR in backtest — use live ledger guard + regime stress |
| `mid_cycle_allocator_enabled` | Intra-cycle adds; Path B gap per `BACKTEST_LIVE_GAP_MATRIX.md` |

Recommend backlog item **ANALYST-OPT-R6**: replay ledger FIFO on harness sells → `sim_exit_win_rate` per scenario row.

## Success criteria

- Leaderboard JSON + `analyst_scenario_runs.jsonl` line with `pack_id=r3_lean_in_exposure_wr_guard`
- Brief states: best **risk-adjusted** lean candidate vs **prod_like_rotation_7d_cap200**, WR guard pass/fail, regime stress summary
- No live config writes from this handoff