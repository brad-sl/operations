# Task Handoff Document

**Task ID:** `P6-SAME-SESSION-SL-METRIC-20260813`  
**Parent Task:** none (sibling of `P6-NEAR-STOP-REBALANCE-RACE-20260813`; may share auditor)  
**Assigned To:** crypto-engineer  
**Reviewer:** crypto-orchestrator  
**Date Assigned:** 2026-08-13  
**Kanban:** `t_9ae1063a` · review `t_7c8b2a6e`  
**GitHub:** https://github.com/brad-sl/operations/issues/23  
**Ops:** `P6-OPS-20260813-002`  
**Source:** `reports/PLATFORM_PROFITABILITY_REVIEW_2026-08-13.md` §8 #2  
**Priority:** P0 (observability — stop flying blind on manufactured SL)

### Objective
Make **same-session / short-window BUY then stop-loss on the same pair** a first-class, honest metric on the daily intel brief (and ops triage), not a screenshot forensics job.

### Context & Background
- RAVE 2026-08-11 and BTC 2026-08-12: rebalance BUY then SL minutes later.
- Exit WR 6/50; SL dominates 30d realizes. Without a count, we cannot tell if the race fix worked.
- Brief already has Health / Actionable / TREND-REPAIR. Add a small **Same-session SL** line (count + pairs), quiet when 0.

### Scope & Boundaries

**Must Do:**
- Define window (default **<2h** BUY→`stop_loss_exchange` same pair; also report **<5m** if cheap).
- Source: `trades/phase6_trades.jsonl` / TradeLedger — real sides + reasons. Newest-first already law.
- Emit:
  - `data/state/same_session_sl_latest.json` (counts, pairs, examples, window, as_of)
  - One/two lines in `phase6/scripts/generate_trading_intelligence_report.py` Health section
  - Optional: ops_triage_discover hook if count > 0 → medium finding (no spam if 0)
- Isolation test with fixture ledger (known BUY+SL pair in/out of window).
- MASTER verification when done.

**Must Not Do / Touch:**
- Do **not** change live risk knobs, SL %, TP, basket, or cash hold.
- Do **not** implement the rebalance race fix here (sibling ticket).
- Do **not** Telegram-spam every would-be event (brief line is enough; ops only if count>0).
- Do **not** invent fills.

**Files / Directories to Work In:**
- `phase6/scripts/generate_trading_intelligence_report.py`
- New small module e.g. `phase6/core/same_session_sl.py` or `phase6/research/` if read-only
- `scripts/phase6/test_isolation_same_session_sl.py`
- Optional: `scripts/phase6/ops_triage_discover.py`
- `docs/MASTER_TASK_TRACKING.md` (this block)

**Files / Directories to Leave Untouched:**
- Live `trading_config` / regime / exit_automation knobs
- Dashboard KPI tile math (optional hover later — out of scope unless one-line)

### Expected Deliverables
1. Auditor function + JSON state.
2. Brief Health line: e.g. `Same-session SL (<2h): 0` or `2 (BTC-USD, RAVE-USD)`.
3. Isolation **PASS**.
4. MASTER → DONE with sample brief snippet.

### Success Criteria
- Window and reason strings documented (`stop_loss_exchange` included; not only `stop_loss`).
- 0 events → quiet / `0` (not omitted in a lying way).
- Replay of Aug 11–12 class events appears in a backfill/report if still in ledger.
- Intel cron still exit 0 (`cron_intelligence_telegram.sh` stdout-only).

### Constraints & Requirements
- Deposit-adj / KPI honesty: this is a **count**, not a return %.
- No extra Coinbase API on brief path — ledger only.

### Validation Method
```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. python3 scripts/phase6/test_isolation_same_session_sl.py
PYTHONPATH=. python3 -c "from phase6.core.same_session_sl import summarize; print(summarize())"
# or whatever public API you name
env -i HOME=/home/brad PATH=/usr/bin:/bin USER=brad \
  bash phase6/scripts/cron_intelligence_telegram.sh | rg -n "Same-session|session SL"
```

### Notes & Warnings for Sub-Agent
- Intelligence cron is `no_agent` + stdout = Telegram body. Keep the new line **short**.
- Sibling race ticket may add the same auditor — prefer **one module**, two callers.
- Reviewer re-runs isolation + greps brief output.
