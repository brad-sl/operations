# REGIME-CASH Implementation Plan

> **For Hermes:** Implement remaining slices task-by-task; RC-01/RC-02 foundation is in tree.

**Goal:** Regime-gated cash + entry/exit with optimizable params and continuous scenario OPT.

**Architecture:** `regime_detector` → `regime_cash_policy` (+ knob_map park) → filter TradePlan BUYs → status JSON → OPT sweeps.

**Tech:** Phase 6 Python, `config/regime_cash_policy.json`, ARCH-4 scorecard/OPT.

---

### Task RC-01: Policy module + isolation (DONE 2026-07-17)

**Files:**
- `config/regime_cash_policy.json`
- `phase6/core/regime_cash_policy.py`
- `phase6/core/test_isolation_regime_cash_policy.py`
- `docs/epics/REGIME_CASH_EPIC.md`

**Verify:**
```bash
PYTHONPATH=. .venv/bin/python3 phase6/core/test_isolation_regime_cash_policy.py
# expect: regime_cash_policy isolation PASS
```

---

### Task RC-02: Wire rebalance path (DONE 2026-07-17)

**Files:**
- `phase6/core/rebalance_coordinator.py` — after manual cooldown filter

**Verify:** status file after resolve:
```bash
PYTHONPATH=. .venv/bin/python3 -c "from phase6.core.regime_cash_policy import resolve_regime_cash, persist_status; print(persist_status(resolve_regime_cash()))"
# data/state/regime_cash_status.json
```

**Ops:** Restart phase6 runner process so coordinator code reloads before next rebalance slot.

---

### Task RC-03: Dashboard + daily brief

**Objective:** Show active regime, strategy_mode, allow_new_buys, blocked buys.

**Files:**
- Modify dashboard serve helpers / HTML tiles
- Modify daily brief builder

**Step:** Read `data/state/regime_cash_status.json`; tile “Regime: flat · park · no new buys”.

---

### Task RC-04: OPT param sweep

**Objective:** Sweep `optimization.sweep_fields` in policy JSON on historical windows; rank by return vs USDC and max DD.

**Files:**
- Create: `phase6/research/run_regime_cash_param_sweep.py`
- Hook weekly OPT or separate cron

---

### Task RC-05: Fresher detector input

**Objective:** Detector uses live BTC closes when historical OHLCV lags (window end stale).

**Files:**
- Modify: `phase6/research/regime_detector.py`
- Isolation: extend test with mock series

---

### Task RC-06: Continuous analyze → optimize attributes

**Objective:** Automated loop: scorecard → knob_map → cash policy suggestions → leaderboard → human/gate promote.

**Files:**
- Extend ANALYST-OPT / regime scorecard pipeline
- Learning chain jsonl → MASTER proposals only when gates pass

---

## Flags

| Key | Default | Effect |
|-----|---------|--------|
| `enabled` | true | Load + status |
| `enforce` | true | Drop failing BUYs |
| `shadow_log_only` | false | (reserved; enforce=false keeps buys but logs) |

Emergency open risk: set `"enforce": false` or `"enabled": false` in `config/regime_cash_policy.json` and restart runner.
