# Protocol — ANALYST-REGIME-TRANSITION-20260727-TRIAL

**Master task:** `ANALYST-REGIME-TRANSITION-20260727`  
**Type:** test (auto-pickup)  
**Kind:** `offline_analysis`  
**Family:** `regime_transition`  
**Cycle:** `docs/testing/ANALYST_TEST_CYCLE.md`  
**Handoff:** `handoffs/analyst/Handoff_ANALYST-REGIME-TRANSITION-20260727.md`  

## Hypothesis
(Fill from handoff objective — pickup scaffold.)

## Non-goals
- No live trading config changes without Brad + gates.
- Real data only.

## Duration
- Kind offline_analysis: complete in one analyst run (tiers in handoff).
- Kind parallel_instrumentation: **2** days mid/final.

## Success
- Report under `reports/` with recommendation enum.
- MASTER updated; trial CLOSED via `trial_cycle.py decide` after Brad (or offline auto-report → REVIEW_PENDING).

## Commands
See handoff. Generic:
```bash
cd /home/brad/projects/crypto-trading-bot
python3 phase6/research/trial_cycle.py status ANALYST-REGIME-TRANSITION-20260727-TRIAL
```
