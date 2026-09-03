# Handoff — ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902

**Status:** QUEUED (Brad GO 2026-09-02)  
**MASTER:** `ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902`  
**Trial:** `ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902`  
**Protocol:** `docs/testing/trials/ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902_PROTOCOL.md`  
**Predecessor:** `ANALYST-20260627-024`  
**Regimen:** `docs/testing/TEST_REGIMEN_E2E.md`  
**Role:** crypto-analyst

## Why re-run (mandatory context)

024 scored Polymarket influence on a **degenerate sensor**: historical `risk_on_bias` stuck at **0.5** (Gamma `outcomePrices` JSON-string parse bug + polarity collapse). That is **bad test data**, not a valid “no edge” close.

- CR 024: `docs/testing/decisions/CR_ANALYST-20260627-024_PROCESSED_INCONCLUSIVE.md` → **no promote**, class **sensor_degenerate**
- Code seal done: parse helpers, polarity, `sensor_preflight`, isolation
- **Historical log not rewritten** → this **new trial** scores **post-fix stamps only**

Do **not** re-open 024 on the old log. Do **not** promote from stuck history.

## Hypothesis

Fresh post-fix Polymarket bias has real range and joins to closed sells with measurable bucket lift (observe-only bar) — still no silent live promote.

## Kind / family

`offline_analysis` · `polymarket_influence` · duration **14d** collect then score (earlier if sensor_ok + min_n)

## Frozen success_criteria

```json
{
  "primary_window": "post_fix_collect",
  "sensor_preflight_ok": true,
  "min_unique_bias_3dp": 5,
  "min_bias_stdev": 0.02,
  "forbid_all_bias_equal": 0.5,
  "min_joined_sells": 15,
  "min_join_rate": 0.10,
  "lift_attention": "risk_on_mean_pnl - neutral >= 0 with n>=5 each",
  "sparse_is": "inconclusive_not_promote",
  "live_promote_allowed": false,
  "fix_cutoff_utc": "2026-09-02T00:00:00+00:00"
}
```

## Commands

```bash
cd /home/brad/projects/crypto-trading-bot
export OPENBLAS_CORETYPE=GENERIC PYTHONPATH=.

# Isolation (must stay green)
.venv/bin/python3 phase6/research/test_isolation_sensor_preflight.py

# Health during collect (empty stdout when OK)
.venv/bin/python3 phase6/research/run_polymarket_influence_health.py

# Final score — POST-FIX ONLY
.venv/bin/python3 phase6/research/run_polymarket_influence_backtest.py \
  --since 2026-09-02T00:00:00+00:00 \
  --out-stem POLYMARKET_INFLUENCE_RERUN_20260902

# Lifecycle
.venv/bin/python3 phase6/research/trial_cycle.py finalize-report \
  ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902 \
  --report reports/POLYMARKET_INFLUENCE_RERUN_20260902.md \
  --json data/state/analyst_polymarket_influence_rerun_latest.json \
  --enum continue_observe_only \
  --outcome-class ATTENTION_ONLY \
  --primary-pass false \
  --n-primary 0 \
  --plain-english '…'
# (enums/classes from actual run — do not copy placeholders)
.venv/bin/python3 phase6/research/trial_cycle.py review-request ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902
# Brad: trial_cycle.py decide … --follow-on …
```

## Must

- Sensor preflight **before** WR/ROI  
- `--since` cutoff enforced  
- Plain-English go/no-go first  
- Real sells only; no synthetic bias backfill  
- live_promote_allowed false  

## Must not

- Score pre-2026-09-02 influence rows as primary evidence  
- Call 024 “inconclusive edge” in the new report without noting sensor_degenerate  
- Live allocator/knob writes  

## Done when

- Honest outcome.class + preflight + n_joined  
- finalize-report → review → Brad decide + follow_on + decision packet  
