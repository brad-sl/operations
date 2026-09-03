# Decide packet — P6-SCALE-GAP-06-PERF-API-SOAK-20260816

**Date:** 2026-08-18  
**Outcome enum:** **`ship`**  
**Live book / config:** unchanged (dash serve path only)

## Hypothesis (restated)
`/api/performance` timeout→N/A is a product class bug; concurrent polls at N accounts recreate it without soak + cache contract.

## Evidence

| Gate | Result | Detail |
|------|--------|--------|
| Honesty (no silent wrong 0) | **PASS** | Periods None or real; timeout never paints 0.0 |
| Cold &lt; 8s | **PASS** | **6.71s** (full soak after fix); ISO **6.54s** |
| Warm p95 &lt; 1s | **PASS** | **~0.11s** |
| Concurrent ×8 | **PASS** | all HTTP 200, max **0.96s**, honesty clean |
| ISO kpi_truth | **PASS** | ALL PASSED |
| ISO perf soak | **PASS** | enum=ship |

Artifacts:
- `data/state/perf_api_soak_latest.json`
- `data/state/perf_api_soak_isolation_evidence.json`
- `reports/PERF_API_SOAK_LATEST.md`
- `scripts/phase6/run_perf_api_soak.py`
- `scripts/phase6/test_isolation_perf_api_soak.py`

## Code shipped (dash only)

1. **Single-flight** cold compute (`perf_compute_lock`) — stops UI stampede starving `/api/balances`.
2. **Always cache** populated (60s) or empty/timeout (**15s** anti-stampede) — ends death spiral where nulls never cached → every poll cold.
3. Tighter sequential DB timeouts (3.5s each) vs dual parallel 6s thrash on 371MB SQLite.
4. Inflight responders get explicit `cache=inflight` + None tiles (not fake 0).

## Incident during pilot (user-visible)

Aggressive concurrent soak + prior parallel dual-read left dash at ~100% CPU; Portfolio showed **$0 / --** while `phase6_live_state.json` still had ~$2418. Root cause: request stampede + no negative cache. Fixed + restarted; verified:
- `/api/balances` → total_usd **~$2418**, ~0.15s
- `/api/performance` warm hit with numeric periods

## Decision

| Field | Value |
|-------|--------|
| CR | **accept / ship** |
| Follow-on | GAP-05 staged next (less-loss offline) |
| Live promote | N/A (ops/ISO only) |
| Residual risk | Cold still ~6–7s (under 8s bar); large DB remains structural — monitor if cold creeps &gt;8s |

## Backup rule (operator)

If GAP-06 later **indeterminate** (cold &gt;8s or honesty fail on re-soak): **do not thrash dash** — staff **`P6-SCALE-GAP-05-POST-SL-REENTRY-EFF`** immediately (ledger N≥15 already feasible).
