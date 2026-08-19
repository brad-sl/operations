# Protocol — ANALYST-KELLY-SIZING-TEST-20260721-TRIAL

**Master task:** `ANALYST-KELLY-SIZING-TEST-20260721`  
**Type:** test (auto-pickup)  
**Kind:** `offline_analysis`  
**Family:** `kelly_sizing`  
**Cycle:** `docs/testing/ANALYST_TEST_CYCLE.md`  
**Handoff:** `handoffs/analyst/Handoff_ANALYST-KELLY-SIZING-TEST-20260721.md`  

## Hypothesis
(Fill from handoff objective — pickup scaffold.)

## Non-goals
- No live trading config changes without Brad + gates.
- Real data only.

## Duration
- Kind offline_analysis: complete in one analyst run (tiers in handoff).
- Kind parallel_instrumentation: **3** days mid/final.

## Success
- Report under `reports/` with recommendation enum.
- MASTER updated; trial CLOSED via `trial_cycle.py decide` after Brad (or offline auto-report → REVIEW_PENDING).

## Commands
See handoff. Generic:
```bash
cd /home/brad/projects/crypto-trading-bot
python3 phase6/research/trial_cycle.py status ANALYST-KELLY-SIZING-TEST-20260721-TRIAL
```
