# Comparative Analysis: virattt/ai-hedge-fund vs Phase 6 Crypto Trading Bot

**Date:** 2026-07-11  
**Source:** [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (main branch; README, VISION.md, ROADMAP.md)  
**Requested by:** Brad (friend suggestion — structure/methodology review)  
**Disposition:** **Methodology borrow only — no integration.** Do not run their stack on Coinbase; do not replace Phase 6 scorers with LLM persona voting.

---

## Executive summary

The AI Hedge Fund project is an **educational equities POC** evolving toward a **persistent fund** with pluggable **alpha models**, a single **`run_cycle`** pipeline (backtest / paper / live), and a **research lab** that promotes winners through validation gates. Asset class, data, and execution are **not transferable** to Phase 6.

What **is** transferable:

1. **Views vs orders** — LLMs/analysts emit opinions; deterministic code sizes and executes; risk is a hard gate.
2. **Uniform signal contract** — every analyst returns the same shape (conviction + thesis) for logging and backtests.
3. **Org chart** — analysts → portfolio construction → allocator (CIO) → master risk → execution → ledger.
4. **Research lab beside production** — shadow/scenario optimization with **human-gated promotion** (their CPCV/PBO; our deploy gate + isolation tests).
5. **Point-in-time / no lookahead** discipline in backtests (spirit applies to sentiment timestamps and rebalance-as-of data).

Phase 6 is **ahead on live crypto ops** (capital events, crons, real fills, dashboard). The hedge-fund repo is **ahead on plug-in theory and reasoning UX**. This doc maps the two and lists a bounded **steal / ignore** list.

---

## What the upstream project is

### Shipped today (v1)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Educational; **does not place real trades** (README disclaimer) |
| **CLI** | `poetry run python src/main.py --ticker AAPL,MSFT,NVDA` (+ optional `--ollama`, date range) |
| **Backtester** | Separate `src/backtester.py` harness |
| **Agents** | 13 LLM “legend investor” personas + Valuation, Sentiment, Fundamentals, **Technicals** |
| **Synthesis** | **Risk Manager** (limits) → **Portfolio Manager** (final buy/sell/hold) |
| **Data** | Financial Datasets API; multiple LLM providers (incl. Kimi in recent releases) |
| **UI** | Web app + `--show-reasoning` style transparency |

### Vision / roadmap (v2 — aspirational)

From [VISION.md](https://github.com/virattt/ai-hedge-fund/blob/main/VISION.md) and [ROADMAP.md](https://github.com/virattt/ai-hedge-fund/blob/main/ROADMAP.md):

```
FUND (mandate, capital, always-on)
  └─ CIO / Allocator (capital across strategies)
       └─ STRATEGY pods (analyst bundle + portfolio policy + capital slice)
            └─ ANALYST = AlphaModel → Signal(conviction ∈ [-1,+1], thesis)
  → Master risk → Execution (broker) → Ledger (positions, NAV, every decision)
```

**Principles they refuse to compromise on:**

- Point-in-time honesty (no lookahead in backtests).
- **Same pipeline** for backtest and live (`run_cycle` — partially shipped; backtester still separate).
- **LLM never touches the trade** — models form views; code sizes and places orders.
- Self-improvement **gated** (CPCV/PBO; human-approved promotion to live).
- Paper before live; open interfaces.

**Roadmap status (high level):** `AlphaModel` / `Signal` interface ✅; backtester ✅ (to be rebuilt on `run_cycle`); fund object, persistent ledger, validation gate, multi-strategy allocator ⬜/🚧.

---

## Phase 6 mapping (org chart)

| AI hedge fund (vision) | Phase 6 today | Notes |
|------------------------|---------------|--------|
| Technicals agent | RSI scorer, StochRSI (observe), `refresh_rsi_prices.py` | Allocator uses **plain RSI**; Stoch for SL + logs |
| Sentiment agent | X/Reddit caches, `sentiment_scorer` | Observed sentiment only; FULL coverage rules |
| Macro / regime | Polymarket `risk_on_bias`, PM tilt (tie-breaker when neutral) | **0** historical tie-breaker activations — evidence-first |
| Valuation / fundamentals | N/A (crypto rotation, not DCF) | — |
| Portfolio manager | `rebalance_coordinator`, rotation plan, `deploy_capital` | ARCH-4 + legacy paths |
| Risk manager | `sl_risk_scorer`, deploy cap, max loss, dust, USDC park | Hard gates on live path |
| Allocator (CIO) | Single strategy `rotation_catch_wave`; regime-adaptive shadow | Not multi-pod yet |
| Execution | Coinbase Advanced Trade, `order_executor`, SL attach | Real fills + reconcile |
| Ledger + thesis | `trade_ledger`, `decision_context`, `param_audit`, `influence_stack_log` | Strong alignment with their “books” |
| Research lab | ANALYST-OPT, scenario packs, shadow drift, `promotion_gates` | Learning chain in `MEMORY_AND_LEARNING.md` |
| Validation gate | `live_param_audit_gate`, isolation tests, 48h ANALYST observation | Lighter than CPCV/PBO; same intent |

---

## Separation: views vs orders (strongest alignment)

**Their rule:** Language models form **views** and **narrate**; deterministic code **sizes** and **places** orders; risk limits are **hard gates**.

**Phase 6 alignment:**

| Layer | Role |
|-------|------|
| Crypto-analyst brief, intelligence report | Narrative + proposals (not direct order API) |
| `allocator` / `rebalance_coordinator` | Deterministic sizing from scores + caps |
| Deploy evaluator, Kimi review, param audit | Promotion / confidence gates |
| `record_rebalance_decision` + `indicator_snapshot` | Audit trail (thesis + numbers at rebalance) |

**Risk:** Brief or ANALYST proposals drifting into config without scenario/shadow proof — same class of bug as letting Portfolio Manager LLM skip risk caps.

**Borrow:** Document explicitly in operator docs: *“LLM proposes; code disposes.”* (Already implicit; worth one canonical paragraph in `docs/research/MEMORY_AND_LEARNING.md` or FAQ.)

---

## Uniform signal contract (gap + opportunity)

**Their contract:** `AlphaModel.predict(...) → Signal { conviction, thesis }`.

**Phase 6 today:** Multiple implicit outputs:

- `runner.rsi_values` (float per pair)
- `influence_stack` (nested dict)
- `proposals_summary` in decision context
- `indicator_snapshot` (rsi + stoch_k/d per pair, 2026-07-11+)
- PM tie-breaker flags (when wired)

**Gap:** No single typed interface per source → harder to backtest “what if we dropped X signal?” in one framework.

**Borrow (future, evidence-gated):** Optional `AlphaSignal` dataclass in `phase6/core/` (source, pair, conviction, confidence, thesis_snippet, as_of_ts) appended to `decision_context` without changing allocator math until promoted via ANALYST-OPT.

**Not a priority** until RSI/Stoch and PM tilt retrospectives justify blending changes.

---

## Research lab and promotion (parallel philosophies)

| Concept | virattt | Phase 6 |
|---------|---------|---------|
| Run candidate mandate in history | Backtester / future `run_cycle` | `run_scenario_leaderboard`, ARCH-4 scenario runner |
| Compare to production | Fund hot-swaps mandate | Shadow configs, `promotion_gates`, weekly OPT |
| Overfitting control | CPCV, PBO (planned) | Walk-forward packs, `fail_count==0`, `confidence>=0.85`, verified fills |
| Human approval | Default for live promotion | User proceed + deploy evaluator |

**Borrow:** When promoting PM tilt or Stoch into allocator, add a **checklist** inspired by their validation gate: min sample size, walk-forward window, register in `analyst_learnings.json` — no new dependency on their repo.

---

## What NOT to import

| Upstream feature | Reason |
|------------------|--------|
| 13 LLM investor personas per ticker | Token cost; poor fit for 11-pair crypto rotation; hard to validate |
| Equity fundamentals / earnings agents | Wrong asset class |
| Financial Datasets dependency | Not Coinbase/OHLCV path |
| Portfolio Manager as LLM final order authority | Violates evidence-first and deterministic execution |
| Running their CLI against live Coinbase | Explicitly out of scope (**no integration**) |

---

## Steal list (max 3 — actionable, no code required yet)

1. **Governance doc line:** “Analysts emit signals; allocator and risk emit orders” — link to `decision_context` and param audit.
2. **Promotion checklist** for any core scorer change (RSI/Stoch/PM): min trades/rebalances, shadow period, rollback knob — mirror PBO *intent* without implementing CPCV immediately.
3. **Interface sketch:** One-page `Signal` shape for new influence sources (see BACKTEST_LIVE_GAP_MATRIX) so scenario packs can toggle sources consistently.

---

## Ignore list

- Clone repo into production path or Hermes cron.
- Replace `sentiment_scorer` / RSI with multi-agent LLM votes.
- Stock tickers, broker plugins (IB/Alpaca) from their roadmap.

---

## Related Phase 6 artifacts

| Artifact | Relevance |
|----------|-----------|
| `docs/research/MEMORY_AND_LEARNING.md` | Learning chain ↔ their research lab |
| `docs/research/BACKTEST_LIVE_GAP_MATRIX.md` | Path B vs live — same “one pipeline” goal |
| `docs/research/CRYPTO_ANALYST_PERSONALITY.md` | Our “analyst” is one persona + tools, not 18 agents |
| `data/state/decision_context_log.jsonl` | Decision + thesis ledger |
| `data/state/rsi_indicator_history.jsonl` | Parallel trial data (RSI vs Stoch) |
| `phase6/scripts/analyze_pm_tilt_retrospective.py` | Regime tilt evidence (PM) |
| Cron `6f3fb1232ec5` | RSI vs StochRSI 2-week review (2026-07-24) |

---

## References

- Repository: https://github.com/virattt/ai-hedge-fund  
- Vision: https://github.com/virattt/ai-hedge-fund/blob/main/VISION.md  
- Roadmap: https://github.com/virattt/ai-hedge-fund/blob/main/ROADMAP.md  
- External context: Ethan Mollick notes on “quasi-organizational” agent configs (LinkedIn, 2025) — useful for *structure*, not PnL claims.

---

## Revision history

| Date | Change |
|------|--------|
| 2026-07-11 | Initial comparative analysis; MASTER tagged methodology-only |