# Handoff P6-STRUCTURE-BOS-EXIT-SHADOW-20260826

## Done
- structure_bos_exit shadow module + runner hook
- isolation + first CF report
- no live sells (module ignores mode=live)

## Next (separate card when Brad wants)
- Collect would-fire episodes from live book
- Scoreboard vs trail TP / SL on dump legs
- Promote discussion only after Brad go

## Commands
PYTHONPATH=. python3 scripts/phase6/test_isolation_structure_bos_exit.py
PYTHONPATH=. python3 scripts/phase6/backtest_structure_bos_cf.py
