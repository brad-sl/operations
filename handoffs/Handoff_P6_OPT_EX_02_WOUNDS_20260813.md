# Task Handoff Document

**Task ID:** `P6-OPT-EX-02-WOUNDS-20260813`  
**Parent Task:** `P6-OPT-EXAMINE-PACK-20260813`  
**Assigned To:** crypto-analyst  
**Date Assigned:** 2026-08-13  

### Objective
Measure whether the **armed-stop race fix** stopped manufactured same-session SL, using a **3-day post-gate** window (not the 30d pre-fix ledger).

### Context
Brief still showed Same-session SL (<2h): 5 pairs / <5m: 4 on 30d history. Ops finding should only fire if 3d count > 0. Dust after SL ≠ armed PAXG.

### Must Do
- Use `phase6/core/same_session_sl.py` (`summarize`, `ops_finding_if_any` lookback_days=3)
- Split: events **after** race-fix deploy (2026-08-13) vs older
- Note dust residuals after SL (not a new PAXG arm)
- Optional: if 3d count > 0, say whether cluster is small alts vs BTC/PAXG (sizing hint only — no new grid)
- Write `reports/OPT_EX_02_WOUNDS_2026-08-13.md`
- Call: `watch` if 3d=0 (watchdog only) / `pursue` if 3d>0 after fix / `drop` if metric broken

### Must Not
- Change SL %, rebalance, or basket
- Treat 30d pre-fix count as a new crisis
- Fake fills

### Files
- Read: `phase6/core/same_session_sl.py`, `data/state/same_session_sl_latest.json`, ledger
- Write: report only

### Success
Plain English: “3-day post-fix count = N. Crisis? yes/no.” List pairs if N>0.

### Validation
```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. .venv/bin/python3 -c "from phase6.core.same_session_sl import summarize, ops_finding_if_any; s=summarize(); print(s); print(ops_finding_if_any(s, lookback_days=3.0))"
```

### Skills
`offline-strategy-honesty`, `phase6-sl-exits-and-dust`, `phase6-ops-triage`
