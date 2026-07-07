# Handoff: ANALYST-OPT R4 — Shadow pipeline + regime-adaptive knobs

**Date:** 2026-07-07  
**Status:** Complete

## Regime-specific settings (your ask)

**Yes — in scope**, as **shadow-only** until scorecard fills `regime_knob_map.json`:

1. Offline: bull/bear/flat/recent scorecard → per-regime winners  
2. Map: `config/regime_knob_map.json`  
3. Runtime: `detect_regime()` (BTC 30d proxy) → swap overlays on shift when `--regime-adaptive`  
4. Safety: drift monitor rolls back **entire** overlay if live ≠ backtest prediction  

Doc: `docs/research/REGIME_ADAPTIVE_KNOBS.md`

## R4 deliverables

| Component | Role |
|-----------|------|
| `shadow_overlay_store.py` | activate / rollback; snapshots under `config/shadow_overlays/` |
| `config_overlay.py` | Runner merges overlay in RAM |
| `shadow_drift_monitor.py` | return & DD vs prediction → learnings + rollback |
| `run_shadow_drift_check.py` | Daily cron `bf79baababb0` (05:00 PT) |
| `activate_shadow_trial.py` | From gated proposal id |

## Activation (when a proposal exists)

```bash
python3 phase6/research/activate_shadow_trial.py --proposal-id ANALYST-YYYYMMDD-NNN --regime-adaptive
```

Current gates still block ingest (negative Sharpe winner) — no proposal to activate yet.

## Verification

- `test_isolation_shadow_r4.py` PASS  
- Drift check: `status: inactive` when no overlay  

## Next

**R5** — analyst personality / skills evolution in brief + proposals.