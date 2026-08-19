# Protocol — ANALYST-STOCH-SL-PREDICTOR-20260803

**Master task:** `ANALYST-STOCH-SL-PREDICTOR-20260803`  
**Type:** test  
**Kind:** `offline_analysis`  
**Family:** `stoch_sl_predictor`  
**Parent:** `STOCH-RSI-PARALLEL-20260721` (scoped follow-on; does not replace parent final)  
**Cycle:** `docs/testing/ANALYST_TEST_CYCLE.md`  
**Handoff:** `handoffs/analyst/Handoff_ANALYST-STOCH-SL-PREDICTOR-20260803.md`

---

## 1. Intent (locked)

Determine whether **StochRSI %K at buy/arm** predicts **higher subsequent stop-loss rate**, beyond plain RSI — i.e. **leading risk utility**, not only **trailing** confirmation after price has already moved against the position.

Brad framing (2026-08-03): Stoch may be a good **leading** and **trailing** stress marker due to higher sensitivity, but is hard as a **direction** signal vs straight RSI. This test scores **SL prediction only**, not entry direction / allocator swap.

## 2. Hypothesis

Buys with entry `stoch_k < X` (X∈{20,30}) show materially higher SL hit rate within 3/7/14d than buys with higher entry Stoch, **including inside RSI-neutral band** (additive information).

## 3. Non-goals

- No live Coinbase SL % / stop replace
- No allocator / REGIME-CASH knob change
- No Stoch period optimization loop
- No promote Stoch as primary entry signal
- Does not auto-close parent Stoch parallel trial

## 4. Method

| Piece | Detail |
|-------|--------|
| Fills | `trades/phase6_trades.jsonl` (real) |
| Entry ind | `indicators_at_trade` else nearest `rsi_indicator_history.jsonl` (≤90m before / ≤10m after) |
| Label | First `stop_loss*` on **same pair** after buy within horizon |
| Primary | Entry Stoch&lt;30 vs ≥30 @ **7d** SL rate + lift + Wilson CI |
| Controls | RSI&lt;35 split; RSI 40–60 × Stoch split (additive) |
| Trailing check | Exit Stoch on SL hits vs entry Stoch on same episodes |
| Windows | Primary: parent launch `2026-07-21T21:54:57Z` → now; optional dig: full history-overlap |

## 5. Success / fail

**Analytical success:** Explicit enum with caveats (not endless monitor).

| Enum | Meaning |
|------|---------|
| `scoped_shadow_sl_risk` | Entry lift strong enough → design log-only shadow next |
| `weak_keep_observe` | Mild/noisy — re-run after more tagged buys |
| `extend_collect` | n too small |
| `no_utility_drop` | No material leading utility (trailing-only or flat lift) |

**Fail:** Invented prices; live config write; claiming direction edge from this SL test alone.

## 6. Duration

Offline one-shot (+ optional dig after parent final / more buys). Not a multi-week instrumentation slot.

## 7. Commands

```bash
cd /home/brad/projects/crypto-trading-bot
OPENBLAS_CORETYPE=GENERIC .venv/bin/python3 phase6/research/test_isolation_stoch_sl_predictor.py
OPENBLAS_CORETYPE=GENERIC .venv/bin/python3 phase6/research/run_stoch_sl_predictor.py --phase offline
# optional wider window once history exists:
# OPENBLAS_CORETYPE=GENERIC .venv/bin/python3 phase6/research/run_stoch_sl_predictor.py --phase dig --start 2026-07-11T00:00:00+00:00
```

Brad decide (after review):

```bash
.venv/bin/python3 phase6/research/trial_cycle.py decide ANALYST-STOCH-SL-PREDICTOR-20260803 <enum> --note '...'
```

## 8. Artifacts

- Module: `phase6/research/stoch_sl_predictor.py`
- Runner: `phase6/research/run_stoch_sl_predictor.py`
- Isolation: `phase6/research/test_isolation_stoch_sl_predictor.py`
- Reports: `reports/STOCH_SL_PREDICTOR_*.md` (+ `.json`)
- State: `data/state/trials/ANALYST-STOCH-SL-PREDICTOR-20260803.json`

## 9. Close-out

1. Report + enum on disk  
2. MASTER updated  
3. Brad `decide` → CLOSED  
4. If `scoped_shadow_sl_risk`: open shadow design task (log-only) — still no live SL  
5. Parent Stoch final (2026-08-04) remains independent close path  
