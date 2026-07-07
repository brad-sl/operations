# Backtest vs live vs ARCH-4 — gap matrix (ANALYST-OPT R1)

**Purpose:** Every scenario knob must map to a **named surface** on each execution path. Gaps block promotion from `analyst_scenario_leaderboard` to shadow/live.

**Canonical mapper:** `phase6/research/scenario_knobs.py`  
**Isolation:** `phase6/research/test_isolation_scenario_knob_parity.py`

---

## Execution paths

| Path | Entry | Stack | Used by ANALYST-OPT |
|------|--------|-------|---------------------|
| **A — R0 simple** | `run_scenario_leaderboard.py` | `BacktestEngine` + `DailyDataLoader` | R0 leaderboard (default today) |
| **B — ARCH-4 isolated** | `backtest_arch4_isolation_harness.py` | `evaluate_universe` → `create_allocator(rotation)` → simulated fills | R1+ authoritative for strategy |
| **C — Live / shadow** | `phase6_runner.py` (--rebalance-only / live) | ARCH-4 chain → `OrderExecutor` / Coinbase | Production |

---

## Knob mapping (R1)

| Scenario field (`backtest.*`) | Path A `BacktestConfig` | Path B ARCH-4 harness | Path C live config |
|------------------------------|-------------------------|------------------------|-------------------|
| `initial_capital` | ✅ | ✅ `--capital` / `run_arch4_backtest(initial=)` | ✅ `global_settings.total_capital` (reference) |
| `rebalance_frequency_days` | ✅ | ✅ `rebal_freq` step stride | ⚠️ **GAP:** live uses `scheduler.daily_rebalance_times` (clock), not day stride |
| `rebalance_cap_usd` | ✅ per expansion buy | ⚠️ **GAP:** harness uses `MIN_TRADE_USD` / allocator `min_move_usd`, not cap | ✅ `global_settings.rebalance_cap_usd` |
| `enable_pair_expansion` | ✅ stub sentiment/RSI | ⚠️ **GAP:** expansion via basket size only, not same `select_new_pairs` | ⚠️ `phase_6_specific.expansion_rules` partial |
| `candidate_universe` | ✅ | ✅ basket filter if pairs have OHLCV | ✅ `opportunity_pool` / `pairs` |

### Path A internal gaps (must fix before trusting A for promotion)

| Issue | Evidence | Severity |
|-------|----------|----------|
| Stub sentiment/RSI on expansion | `backtest_engine.py` ~108–110 hardcoded `0.28`, `47` | **High** |
| No ARCH evaluation / rotation | Only add-pair on rebalance day | **High** |
| No stop-loss / reserve | Live has `min_reserve_usd`, SL, AgentKit | **High** |
| No fees | ARCH-4 sim uses `FEE_RATE=0.001` | Medium |

### Path B vs Path C

| Issue | Notes |
|-------|--------|
| Sentiment source | B uses **price-momentum proxy**, C uses **cached X/Reddit** (`sentiment_scorer`) |
| RSI | B computes Wilder from OHLCV; C uses `rsi_cache.json` |
| Execution | B sim at close; C market orders + slippage + min notional |
| Mid-cycle allocator | C config `mid_cycle_allocator_enabled`; B only on rebalance steps |
| Signals “log only” | C runner may still not wire all signal paths to allocator (ARCH audit) |

---

## Promotion rule (R1 → R2)

| Tier | Allowed use |
|------|-------------|
| **Leaderboard from Path A** | Relative ranking smoke tests only |
| **Leaderboard from Path B** | Proposals + shadow experiments when knob parity test passes |
| **Live param change** | Requires Path C overlay + monitor green + cited `run_id` |

---

## Next engineering tasks (ordered)

1. **ANALYST-OPT-R1b** — Add `engine: "arch4"` to scenario schema; leaderboard calls `run_arch4_from_knobs()` (Path B).
2. **ARCH-0** — `test_isolation_current_signals.py` + rebalance path baselines (MASTER).
3. **Align expansion** — Real sentiment/RSI series in Path A or deprecate A for promotion.
4. **Clock vs stride** — Document conversion: `rebalance_frequency_days` ↔ cron anchors (09:00/21:00 PT).

---

## References

- `docs/research/scenario_schema.md` (R1 `engine` field reserved)
- `phase6/scripts/backtest_arch4_isolation_harness.py`
- `config/trading_config_phase6.json`
- `docs/phase6/ARCHITECTURE_ISOLATED_COMPONENTS.md`