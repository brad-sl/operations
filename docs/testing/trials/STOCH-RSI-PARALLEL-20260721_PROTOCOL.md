# Protocol — STOCH-RSI-PARALLEL-20260721

**Trial ID:** `STOCH-RSI-PARALLEL-20260721`  
**Role:** Crypto-Analyst  
**Cycle:** `docs/testing/ANALYST_TEST_CYCLE.md`  
**Status at write:** LAUNCHING → RUNNING after baseline  

---

## 1. Intent (original, locked)

From MASTER 2026-07-07 + reminder cron 2026-07-10:

1. Run **StochRSI in parallel** with plain longer-term (~100-pt) RSI via the 15m refresher.
2. Surface Stoch on intel / SL risk scorer (`stoch_k` boosts when very low).
3. **Do not** change production allocator / core entry logic without evidence + Brad go.
4. After a defined window, produce an honest recommendation:
   - continue observe-only  
   - extend trial  
   - propose scoped experiment (e.g. SL shadow only)  
   - drop  
   - (rare) promote blend / primary  

## 2. Hypothesis

StochRSI (%K/%D) disagrees with plain RSI often enough, and aligns with SL / poor rotation outcomes often enough, that it **adds risk information** beyond RSI alone — without needing to become the allocator signal.

## 3. Non-goals

- Not a live allocator swap to Stoch.
- Not full Kelly / sizing work (blocked until this trial closes).
- Not optimizing Stoch parameters in-loop (fixed 14/14/3 for the trial).

## 4. Duration

| Milestone | When (PT) |
|-----------|-----------|
| Launch + baseline | **2026-07-21** (immediate) |
| Mid report | **2026-07-28** ~09:00 |
| Final report | **2026-08-04** ~09:00 |
| Review / close | within 48h of final |

Prior partial data (2026-07-10 → launch) may appear as **appendix only**; primary window = launch → final.

## 5. Instrumentation

| Component | Requirement |
|-----------|-------------|
| `scripts/refresh_rsi_prices.py` | Full basket + RSI + `stoch_k`/`stoch_d` + history append |
| `~/.hermes/scripts/refresh_rsi_prices.py` | **Must stay in sync** (cron actually runs this) |
| `data/state/rsi_cache.json` | schema ≥2, stoch fields present |
| `data/state/rsi_indicator_history.jsonl` | growing with stoch |
| `phase6/core/sl_risk_scorer.py` | reads stoch (already) |
| Allocator | unchanged (plain RSI path) |

## 6. Data sources (analysis)

1. `data/state/rsi_indicator_history.jsonl`
2. `data/state/decision_context_log.jsonl` (indicator_snapshot when present)
3. `trades/phase6_trades.jsonl` (`indicators_at_trade`)
4. Trial state `data/state/trials/STOCH-RSI-PARALLEL-20260721.json`

## 7. Success / fail

**Instrumentation success (launch gate):**
- ≥11 pairs (or full configured basket) with RSI
- ≥90% of those with `stoch_k`
- cache age &lt; 45m after refresher
- isolation tests PASS

**Analytical success (final):**  
Enough sample to choose a recommendation enum with explicit caveats — not “still monitoring” forever.

**Fail / kill early:**
- Stoch missing from cache &gt; 24h after alert
- Refresher desync (hermes copy stale) unresolved 48h
- Brad aborts trial

## 8. Commands

```bash
cd /home/brad/projects/crypto-trading-bot
# isolation
.venv/bin/python3 phase6/research/test_isolation_stoch_rsi_trial.py
# refresher — hermes path MUST be thin wrapper → project script (do not copy full body)
.venv/bin/python3 ~/.hermes/scripts/refresh_rsi_prices.py
# health + lifecycle
.venv/bin/python3 phase6/research/run_stoch_rsi_trial_health.py; echo exit:$?
.venv/bin/python3 phase6/research/trial_cycle.py status STOCH-RSI-PARALLEL-20260721 | head -40
# reports
.venv/bin/python3 phase6/research/run_stoch_rsi_trial_report.py --phase baseline
.venv/bin/python3 phase6/research/run_stoch_rsi_trial_report.py --phase mid
.venv/bin/python3 phase6/research/run_stoch_rsi_trial_report.py --phase final
# Brad close only:
# .venv/bin/python3 phase6/research/trial_cycle.py decide STOCH-RSI-PARALLEL-20260721 <enum> --note '...'
```

## 9. Crons (expected)

| Job | Schedule | Mode |
|-----|----------|------|
| rsi-15min-refresher | `*/15 * * * *` | no_agent → hermes script |
| stoch-trial-health | daily 09:15 PT | no_agent; DEGRADED/KILLED after 3 fails |
| stoch-trial-mid | once 2026-07-28 09:00 PT | skill `analyst-trial-report` |
| stoch-trial-final | once 2026-08-04 09:00 PT | skill `analyst-trial-report` → review inbox |

Legacy one-shot removed. Cycle v2: `docs/testing/ANALYST_TEST_CYCLE.md` + `trial_cycle.py`.

## 10. Close-out

1. Final report → `REPORT_READY` + `docs/testing/inbox/REVIEW_*.md`  
2. Brad: `python3 phase6/research/trial_cycle.py decide STOCH-RSI-PARALLEL-20260721 <enum> --note '...'`  
3. Status `CLOSED` (function, not vibe)  
4. Unblock `ANALYST-KELLY-SIZING-TEST-20260721`  
5. Pause/remove trial health/mid/final crons (keep rsi refresher)  
6. Optional skeptical evaluator pass before decide if recommendation is promote_*


## 11. Cycle v2 deltas (2026-07-21)

- State machine + INDEX registry
- Health consecutive-fail → DEGRADED → KILLED (N=3)
- Stale detector past final_at+48h
- Skillized mid/final (`analyst-trial-report`)
- Decision via `trial_cycle.py decide` + inbox
