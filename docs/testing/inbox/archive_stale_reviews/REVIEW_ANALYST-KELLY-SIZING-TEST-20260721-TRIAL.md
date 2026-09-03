# Review request — ANALYST-KELLY-SIZING-TEST-20260721-TRIAL

**Status:** REVIEW_PENDING  
**Master:** `ANALYST-KELLY-SIZING-TEST-20260721`  
**Final report:** `reports/KELLY_SIZING_TEST_2026-07-21.md`  
**JSON:** `reports/KELLY_SIZING_TEST_2026-07-21.json`  
**Proposed recommendation:** `drop`  
**Shadow go:** **false**  
**Unblocks if closed:** []  
**Live config writes:** none

## Key numbers (real ledger)

| Metric | Value |
|--------|-------|
| n (plausible closed sells) | 70 |
| p (WR) | 0.429 (Wilson 95%: 0.32–0.55) |
| b (mean win r / \|loss r\|) | 1.87 |
| f_full / f_half | 0.123 / 0.062 |
| f_half after 0.5 multi haircut | 0.031 |
| Jul+ n / p / f_full | 37 / 0.19 / **0** (neg edge) |
| Baseline path growth / maxDD | +22.1% / 24.0% |
| Half-Kelly-capped growth / maxDD | +44.7% / **39.5%** (worse DD) |

**Why drop:** Recent window has non-positive Kelly; full-sample edge is unstable. Kelly-capped paths raise growth but **worsen max DD**; regime/max_position envelopes bind so full≈half path. Full Kelly live: REJECT.

## Artifacts

- `phase6/research/kelly_sizing.py`
- `phase6/research/test_isolation_kelly_sizing.py` (PASS)
- `phase6/research/run_kelly_sizing_test.py`

## Decide

```bash
cd /home/brad/projects/crypto-trading-bot
python3 phase6/research/trial_cycle.py decide ANALYST-KELLY-SIZING-TEST-20260721-TRIAL drop --note 'offline kelly: recent edge neg; DD worse; no shadow'
```

Enums: `continue_observe_only` | `extend_trial` | `propose_scoped_experiment` | `drop` | `promote_blend` | `promote_primary` | `abort`
