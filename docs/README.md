# Crypto Bot Phase 5.1 + Phase 6

## Run Tests
```bash
cd operations/crypto-bot
python test_phase6.py
# Expected: 100% passed (3 tests: Fresh Start, Takeover 2, Ready Start)
```

## Test Integration
```bash
python phase5_1_multi_pair.py --dry-run --cycles 1
# Expected logs: Phase 6 init, scenario, budget, dry-run trades with SL/TP
```

## Live Trading (TODO: connect real CBClient, State, OrderExec)
```bash
python phase5_1_multi_pair.py
```

## Files
- `phase6.py`: Initializer logic + scenario detection
- `test_phase6.py`: 3 passing unit tests (mocks + env patches)
- `phase5_1_multi_pair.py`: Integrated trading loop
- `PHASE6_INTEGRATION.md`: Spec followed exactly
