# Regime gates + Analyst OPT loop (operating model)

**Status:** live 2026-07-18 (flat = option B cautious deploy)  
**Intent (Brad):** automate application of trading gates; analyst studies performance, runs scenarios, tests for highest ROI; creative research is encouraged; **proven** gainers enter the promotion pathway — nothing auto-promotes to live without gates.

---

## Separation of duties

| Role | Owns | Does **not** |
|------|------|----------------|
| **Live runner + REGIME-CASH** | Apply **current** policy every cycle: regime → cash budget → BUY/SELL gates (RSI, sentiment, lockout, cap). Enforce when `enforce=true`. | Invent new strategy mid-cycle; auto-edit policy from one green hour |
| **Analyst / OPT** | Performance review, scenario packs, backtests, parallel/shadow, regime scorecards, param sweeps, creative hypotheses | Write live capital without promotion gates |
| **Promotion pathway** | Leaderboard → shadow → live_param_audit → USDC/hurdle → **operator apply** to `regime_cash_policy.json` / knob_map | Silent auto-apply (`auto_apply: false`) |

```
Markets
   │
   ▼
detect_regime (BTC window + live merge)
   │
   ▼
regime_cash_policy.json  +  regime_knob_map.json
   │
   ▼
LIVE GATES (automated every rebalance)
   • strategy_mode / allow_new_buys
   • rebalance_cap_usd clamp on runner
   • min_sentiment / max_rsi / lockout
   │
   ▼
orders (SELLs always; BUYs only if gates pass)

PARALLEL (research)
scorecard · ANALYST-OPT weekly · regime_cash param sweep · continuous suggestions
   │
   ▼
learnings / leaderboard / proposals
   │
   ▼
PROMOTE only if: beats baseline/USDC · live_param_audit clean · shadow OK · Brad/operator apply
```

---

## Live policy stance (2026-07-18)

| Regime | Stance |
|--------|--------|
| **bull** | Deploy, liberal util, looser entry |
| **flat** | **Option B:** `deploy`, `allow_new_buys=true`, **cap $75**, strict entry (`min_sent` 0.25 / new 0.35, `max_rsi` 55). **Not** full park-off. |
| **bear / unknown** | Park, no new buys, cap 0 |
| **transition** | Prefer cash (scorecard may park) |

**`enforce: true` always for gated deploy.**  
`enforce: false` = emergency open risk (log only) — **not** the thaw path.

---

## What “good” automation looks like

1. **Gates are boring and reliable** — same JSON every cycle; runner restart picks up config; status on dashboard/brief.  
2. **Analyst is creative** — new scenarios, regime window tweaks, entry surface experiments.  
3. **Testing is mandatory before belief** — backtest pack, holdout, parallel/shadow, regime-conditioned metrics.  
4. **Promotion is narrow** — winner must beat production-relevant hurdle on **real overlap** where possible; no “sim green → live” without audit.  
5. **Rollback is easy** — set flat/bear back to `usdc_park` + knob_map cap 0; restart runner.

---

## Operator freeze / thaw

| Action | How |
|--------|-----|
| Full park (flat) | `strategy_mode=usdc_park`, `allow_new_buys=false`, cap 0 in **both** policy + knob_map; restart runner |
| Cautious thaw (B) | deploy + small cap + keep RSI/sentiment; **both** policy + knob_map (knob_map previously forced park) |
| Emergency open | `enforce: false` only if accepting ungated risk |

---

## Related paths

- `config/regime_cash_policy.json` — live knobs  
- `config/regime_knob_map.json` — scorecard overlay (can force park if cap 0 / mode park); **`operator_override.protect`** blocks clobber  
- `phase6/core/regime_cash_policy.py` — resolve + filter + cap clamp  
- `phase6/research/run_regime_cash_continuous.py` / `run_analyst_opt_weekly.py` — research loop  
- `phase6/research/run_regime_cash_validation.py` — live vs modeled window; **latest + history jsonl**  
- Status: `data/state/regime_cash_validation_latest.json`, `regime_cash_validation_history.jsonl`  
- Epic: `docs/epics/REGIME_CASH_EPIC.md`  
- Skill ref: `regime-cash-policy.md` under phase6-capital-and-dashboard-kpis  
- **Trend repair (path health):** `docs/TREND_REPAIR_PLAYBOOK.md` · `phase6/research/trend_repair.py` · `data/state/trend_repair_status.json` · dashboard Account health / `equity_trend`  
  Analyst must monitor deposit-adjusted slope + layer diagnosis, test, and propose tiered fixes (no auto-promote). Evidence clocks ≥14d before Tier 2 design claims.

---

*Last updated: 2026-07-24 — trend repair playbook + equity_trend hooks*

## Test strategy portfolio (2026-07-21)

Analyst **test strategy** (`docs/testing/ANALYST_TEST_STRATEGY.md`) ranks regime-knob, sizing, signal, and methodology experiments → emits `Type: test` onto MASTER → auto-pickup/trial cycle. Live REGIME-CASH remains apply-only; winners still use promotion gates.

- Board: `data/state/trials/TEST_STRATEGY.json`
- CLI: `python3 phase6/research/analyst_test_strategy.py status|emit`
- Weekly cron: `analyst-test-strategy-weekly`
