# Handoff — TRAJECTORY-GAP exit stack (TG-01..04) — 2026-07-29

**Status:** partial live  
**Operator:** Brad proceed  
**Live capital risk from this change:** TG-03 only (cash hold + longer rebuy after SL). TG-02 is **shadow** (no auto sells). TP still null.

## Why
7D still ~−3% after park/repair. Diagnosis: exit asymmetry (SL banks losses; no TP; rebuy after SL).

## Done
1. **TG-01** instrumentation — `PYTHONPATH=. python -m phase6.research.run_exit_asymmetry_report`
2. **TG-02** hard exit shadow wire in `regime_cash_policy.apply_to_runner_plan`
3. **TG-03** `hold_cash=true`, rebuy **72h**, disposition adds hold for exchange stops; runner restarted
4. **TG-04** scaffold only — OHLCV path CF not built

## Verify
```bash
# config
python3 -c "import json; g=json.load(open('config/trading_config_phase6.json'))['global_settings']; print(g['capital_event_stop_loss_exchange_hold_cash'], g['capital_event_stop_loss_exchange_block_rebuy_hours'])"
# tests
PYTHONPATH=. python3 scripts/phase6/test_isolation_stop_exchange_disposition.py
PYTHONPATH=. python3 phase6/core/test_isolation_regime_cash_policy.py
# runner
pgrep -af 'phase6.core.phase6_runner'
# artifacts
ls data/state/exit_asymmetry_latest.json reports/EXIT_ASYMMETRY_*.md data/state/regime_hard_exit_shadow.json
```

## Promote later (Brad)
- Set `hard_exit.live_apply=true` and `shadow_only=false` only after shadow review
- Build TG-04 path counterfactual before any live `take_profit_pct`
