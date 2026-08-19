# REGIME-CASH Epic — Regime-gated cash, entry/exit, continuous optimization

**ID:** REGIME-CASH  
**Status:** FOUNDATION COMPLETE (RC-01..RC-06 2026-07-17)  
**Owner:** Brad + Phase 6 / crypto-engineer  
**Related:** `config/regime_knob_map.json`, `phase6/research/regime_detector.py`,  
`docs/epics/SCALING-1000_EPIC.md` (multi-tenant later), ANALYST-OPT weekly  

---

## Goal

Make **regime → cash budget → trade entry/exit** explicit, parameterizable, and continuously  
optimized so the bot **minimizes downside** (stop recycle into losers) and **maximizes upside**  
(deploy only when regime + signals allow).

---

## Principles

1. **Clear regimes** — bull / bear / flat / transition with numeric BTC-window definitions (params).  
2. **Clear active regime** — single detector output for a period (`detect_regime` + status JSON).  
3. **Clear entry/exit** — each BUY/SELL must pass **regime cash budget** + **RSI + sentiment + lockout**.  
4. **All knobs are variables** — stored in `config/regime_cash_policy.json` for OPT/sweeps.  
5. **Continuous loop** — scenarios run → scorecard → knob map → cash policy → live/shadow enforce → learn.

---

## Architecture

```
BTC OHLCV / live proxy
        │
        ▼
 regime_detector.detect_regime()     ← thresholds are params
        │
        ▼
 regime_cash_policy.resolve()        ← merges detector + knob_map + cash_policy
        │
        ├─► cash_budget (max_util, rebalance_cap, park)
        ├─► entry_gates (min_sentiment, max_rsi_buy, require_lockout_clear)
        └─► exit_gates (min_rsi_sell_bias, overbought_rsi, etc.)
        │
        ▼
 filter_trade_plan_regime_cash()     ← rebalance path (live when enforce=true)
        │
        ▼
 data/state/regime_cash_status.json  ← dashboard / brief / OPT
```

### Continuous optimization loop

```
run_regime_scorecard + ANALYST-OPT weekly
        → apply_regime_knob_map_from_scorecard
        → (future) sweep regime_cash_policy params on historical windows
        → leaderboard / learnings
        → promote only if beats USDC + live gates
```

---

## Regime definitions (defaults — all overridable in config)

| Regime | BTC lookback return | Cash stance | Re-entry |
|--------|---------------------|-------------|----------|
| **bull** | ≥ `bull_return_pct` (default +15% / 30d) | Liberal util | Standard gates |
| **bear** | ≤ `bear_return_pct` (default −10%) | **USDC/cash park** | Strict / no new BUY default |
| **flat** | \|ret\| ≤ `flat_abs_pct` (default 8%) | **Park or low util** | High bar |
| **transition** | else | Conservative | Prefer cash |

Scorecard may override **strategy_mode** (`usdc_park` vs deploy) via `regime_knob_map`.

---

## Entry / exit (per trade)

### Entry (BUY) — all must pass when enforce=true

1. Regime cash budget allows new risk (`allow_new_buys`, cap, util).  
2. Pair **not** on rebuy/manual lockout.  
3. **Sentiment ≥** `entry.min_sentiment` (regime-specific).  
4. **RSI ≤** `entry.max_rsi` (regime-specific; block overbought adds).  
5. Optional: `entry.min_sentiment_new_pair` for pairs not already held.

### Exit (SELL) — bias, not forced flatten unless park mode

1. RSI ≥ `exit.overbought_rsi` → prefer reduce.  
2. Sentiment ≤ `exit.max_sentiment_hold` → prefer reduce.  
3. Park regimes: allow SELLs freely; block BUYs.

---

## Parameter file

Canonical: **`config/regime_cash_policy.json`**

Every threshold that affects money is a named field (for OPT sweeps).  
Do not hardcode live magic numbers outside that file + detector params.

---

## Feature flags

| Flag | Meaning |
|------|---------|
| `enabled` | Load policy + write status |
| `enforce` | Actually filter TradePlan BUYs |
| `shadow_log_only` | If enforce false, log what would block |

Default for production pain mitigation: `enabled=true`, `enforce=true`.

---

## Deliverables / slices

| Slice | Deliverable |
|-------|-------------|
| **RC-01** | Policy schema + `regime_cash_policy.py` + isolation tests |
| **RC-02** | Wire rebalance_coordinator filter + status JSON |
| **RC-03** | Dashboard / daily brief regime + cash budget line |
| **RC-04** | OPT param sweep over cash policy fields |
| **RC-05** | Fresher BTC for detector (live closes) |
| **RC-06** | Continuous scenario gen → analyze → optimize attributes |

---

## Success criteria

- Active regime always recorded and explainable.  
- In bear/flat park: **no new BUYs** while enforce=true (unless explicit override).  
- Entry denials cite **which gate** failed.  
- Params only in config; isolation tests cover bull vs bear filters.  
- OPT/scorecard path can change knobs without code edits.

---

## Non-goals (this epic)

- Multi-tenant SaaS (SCALING-1000).  
- Guaranteed profit.  
- Synthetic OHLCV.  
- Auto-promote to live without USDC + live_param gates.
