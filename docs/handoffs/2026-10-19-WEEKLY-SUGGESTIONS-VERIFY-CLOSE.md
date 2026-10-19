# Handoff: Weekly suggestions verify/close (reverse-stack already live)

**Date:** 2026-10-19  
**Assignee:** crypto-engineer  
**Priority:** P1  
**Source:** Analyst Weekly 2026-10-18 OPEN carries that overlap reverse-stack GO 2026-10-17

---

## Objective

Prove and document that these weekly GO carries are **already live** (or still measure-only), so the board does not re-implement them:

| Analyst ID | Expected state after 2026-10-17 GO |
|------------|-------------------------------------|
| **W-TRYOUT-INTAKE-VS-KINDLING** | Intake discipline raised (eng≥0.40 / setup≥1.7 / conf≥0.60); live_apply on discipline path |
| **W-FLAT-BALLAST-BEFORE-SHELL** | D2 `flat_deploy_priority` live_apply=true — block new tryout shells while ballast gap |
| **W-BALLAST-PROFIT-GATE** | C2 `ballast_under_target_floor` live_apply=true — BTC/ETH max_add floor inject (~$75) |
| **W-PROCESS-TAX-ETH-SL** | Career shipped 2026-10-12; demoted P1; **no** new SL knob |

## Must Do

1. Smoke-read configs + latest state:
   - `config/tryout_decision_discipline.json` (or effective discipline thresholds)
   - `config/flat_deploy_priority.json` → live_apply true
   - `config/ballast_under_target_floor.json` → live_apply true
   - `data/state/membership_sizing_matrix_latest.json` dig_out / c2 inject on BTC/ETH
   - `data/state/rsi_event_tryout_seat_composer_latest.json` d2 block if present
2. Re-run isolation if cheap:
   - `scripts/phase6/test_isolation_ballast_under_target_floor.py`
   - `scripts/phase6/test_isolation_flat_deploy_priority.py`
3. Write short receipt:
   - `reports/WEEKLY_SUGGESTIONS_VERIFY_CLOSE_2026-10-19.md`
   - `data/state/weekly_suggestions_verify_close_latest.json`
4. MASTER append under `WEEKLY-SUGGESTIONS-20261018` with pass/fail per ID.
5. Explicit residual gaps only (e.g. bank-trail still measure, W2 still OFF) — no silent “all green.”

## Must Not Do

- Do not flip new money knobs
- Do not re-implement C2/D2/intake
- Do not touch PAXG / scale-window / dwell live_apply / global SL%
- Do not complete the Analyst alt-shell RCA card (separate assignee)

## Success Criteria

- [ ] Each of the four IDs has status: LIVE / PARTIAL / MEASURE / CAREER_DONE with evidence path
- [ ] Isolation tests pass (or honest skip + reason)
- [ ] Receipt on disk; MASTER updated

## Validation

```bash
cd /home/brad/projects/crypto-trading-bot
.venv/bin/python scripts/phase6/test_isolation_ballast_under_target_floor.py
.venv/bin/python scripts/phase6/test_isolation_flat_deploy_priority.py
test -f reports/WEEKLY_SUGGESTIONS_VERIFY_CLOSE_2026-10-19.md
```

## References

- `reports/SOFT_DOWN_REVERSE_STACK_GO_LATEST.md`
- `data/state/soft_down_reverse_stack_go_latest.json`
- `reports/ANALYST_WEEKLY_TRADE_REVIEW_AGENT_LATEST.md`
