# Phase 6.01 Deployment Checklist

**Status:** Ready for sandbox deployment after checklist completion

---

## Pre-Deployment Phase (DO THIS FIRST)

### Code Review & Preparation

- [ ] **Remove Mock Objects**
  - File: `phase6.py` (original lines 156-165)
  - Action: Remove unittest.mock() setup
  - Replace with: Real `CoinbaseAdvancedClient`, `StateManager`, `OrderExecutor` instances
  - Verify: Code runs without mocks

- [ ] **Verify API Methods**
  - [ ] `cb_client.get_account_history()` - verify method exists and signature
  - [ ] `cb_client.get_current_price()` - verify or implement wrapper
  - [ ] `order_exec.place_market_sell()` - verify signature matches
  - [ ] `order_exec.place_sl_tp()` - decide on standard signature (3 or 4 params)
  - Document findings in `API_VERIFICATION_REPORT.md`

- [ ] **Integrate StateManager**
  - [ ] Import: `from phase6_state_manager import StateManager`
  - [ ] Initialize in `phase6.py` main loop
  - [ ] Call on cycle start/end
  - [ ] Call on liquidation events
  - [ ] Test: State file created and persisted

- [ ] **Implement Entry Price Tracking**
  - [ ] Create callback: `on_order_fill(pair, fill_price)`
  - [ ] Call: `liquidation_manager.update_entry_price(pair, fill_price)`
  - [ ] Verify: Entry prices tracked in PAIN_SCORE calculation

- [ ] **Config Validation**
  - [ ] Load production config
  - [ ] Verify: reserve_pct + deploy_pct <= 1.0
  - [ ] Verify: sl_pct < tp_pct
  - [ ] Verify: min_reserve_usd > 0
  - [ ] Create: `CONFIG_VALIDATION_REPORT.md`

- [ ] **Dependency Check**
  - [ ] numpy installed: `python3 -c "import numpy; print(numpy.__version__)"`
  - [ ] coinbase_advanced_client available: `python3 -c "from coinbase_advanced_client import CoinbaseAdvancedClient"`
  - [ ] All imports work: `python3 -c "from phase6 import *"`

---

## Sandbox Testing Phase (BEFORE LIVE)

### 24+ Hour Paper Trading Test

- [ ] **Setup**
  - [ ] Create sandbox Coinbase account
  - [ ] Get sandbox API credentials
  - [ ] Configure `phase6.py` with sandbox credentials
  - [ ] Set mode: PAPER_TRADE
  - [ ] Set config: production-like settings

- [ ] **Execution**
  - [ ] Start bot: `python3 phase6.py --config config.json --mode PAPER_TRADE`
  - [ ] Monitor for 24+ hours
  - [ ] Check logs every 2 hours
  - [ ] No errors expected

- [ ] **Monitoring During Test**
  - [ ] Check: Trading cycles running
  - [ ] Check: No API errors in logs
  - [ ] Check: State file being updated
  - [ ] Check: Liquidation logic triggered (if applicable)
  - [ ] Check: PAIN_SCORE calculated
  - [ ] Check: Orders placed and filled (paper)
  - [ ] Check: No memory leaks (process size stable)
  - [ ] Check: CSV trade log entries created

- [ ] **Verification After Test**
  - [ ] Run: `python3 -m pytest test_phase6_state_manager.py -v`
  - [ ] Verify: 14+ tests passing
  - [ ] Check: State file valid JSON
  - [ ] Check: No corrupted state records
  - [ ] Check: Liquidation history populated
  - [ ] Check: PAIN_SCORE records present

---

## Security & Risk Assessment

- [ ] **API Credentials**
  - [ ] Credentials loaded from environment (not hardcoded)
  - [ ] Test: Using SANDBOX_KEY not LIVE_KEY
  - [ ] Verify: No secrets in logs

- [ ] **Order Limits**
  - [ ] Max order size capped in config
  - [ ] Min position size enforced
  - [ ] Daily loss limit configured
  - [ ] Circuit breakers in place

- [ ] **State Management**
  - [ ] Atomic writes verified: No corruption on crash
  - [ ] State file readable/writable
  - [ ] Backup strategy: Copy state to separate dir daily
  - [ ] Recovery tested: Kill process mid-write, restart

---

## Documentation Review

- [ ] **Release Notes Reviewed**
  - [ ] Understand all 11 critical issues
  - [ ] Understand current fixes/workarounds
  - [ ] Understand deployment blockers

- [ ] **Deployment Runbook Created**
  - [ ] Start procedure documented
  - [ ] Stop procedure documented
  - [ ] Restart procedure documented
  - [ ] Emergency liquidation procedure documented
  - [ ] Rollback procedure documented

- [ ] **Monitoring Plan**
  - [ ] Who monitors what metrics
  - [ ] How often to check
  - [ ] Alert thresholds defined
  - [ ] Escalation procedure documented

---

## Production Deployment (DO THIS LAST)

### Final Checks Before LIVE

- [ ] **All Previous Checklists Complete**
  - [ ] Pre-deployment phase: DONE
  - [ ] Sandbox testing: DONE (24+ hours successful)
  - [ ] Security review: DONE
  - [ ] Documentation: DONE

- [ ] **Configuration for LIVE**
  - [ ] Mode set to: LIVE (not PAPER_TRADE)
  - [ ] Credentials: LIVE API keys (not sandbox)
  - [ ] Capital allocation: Conservative (10% or less)
  - [ ] Stop loss configured
  - [ ] Daily loss limit set appropriately

- [ ] **Initial Deployment**
  - [ ] Start with LIVE_KEY but very small capital
  - [ ] Monitor logs: Every 5 minutes for first hour
  - [ ] Monitor: Order placements in account
  - [ ] Monitor: State file updates
  - [ ] No orders placed yet: Just verify integration

- [ ] **Gradual Ramp**
  - [ ] Day 1: Observe, no trading
  - [ ] Day 2-3: Allow small trades (1% of capital)
  - [ ] Day 4-7: Increase to 5% if stable
  - [ ] Week 2: Increase to 10% if no issues
  - [ ] Beyond: Gradual increase as confidence grows

---

## Ongoing Operations

### Daily Checks

- [ ] Check state file size reasonable
- [ ] Check for stuck orders
- [ ] Review liquidation history
- [ ] Verify trades logged correctly
- [ ] Monitor memory/CPU usage
- [ ] Backup state file daily

### Weekly Review

- [ ] Review all trades for anomalies
- [ ] Check PAIN_SCORE calculations
- [ ] Verify capital allocation
- [ ] Review logs for warnings
- [ ] Test emergency stop procedure

### Monthly Review

- [ ] Performance metrics analysis
- [ ] Risk assessment update
- [ ] Configuration tuning if needed
- [ ] Unit test re-run
- [ ] Documentation update

---

## Rollback Procedure

If critical issues arise during LIVE deployment:

1. [ ] **Immediate Stop**
   - Stop bot: `Ctrl+C`
   - All open orders: Close immediately in web UI
   - No new orders: Verify in account

2. [ ] **Assessment**
   - Check logs for errors
   - Review state file for corruption
   - Assess PnL impact

3. [ ] **Recovery**
   - Restore state file from backup if corrupted
   - Restart in PAPER_TRADE mode
   - Investigate root cause
   - Do NOT resume LIVE until fixed

4. [ ] **Escalation**
   - Notify deployment team
   - Document incident
   - Create fix issue in backlog
   - Plan for 6.02 fix

---

## Sign-Off

| Role | Name | Date | Status |
|------|------|------|--------|
| Code Review | _____ | _____ | ⬜ |
| Sandbox Test Lead | _____ | _____ | ⬜ |
| Security Review | _____ | _____ | ⬜ |
| Deployment Lead | _____ | _____ | ⬜ |
| Operations Lead | _____ | _____ | ⬜ |

**Overall Status:** 🔴 READY FOR DEPLOYMENT AFTER CHECKLIST

---

## References

- `PHASE_6_01_RELEASE_NOTES.md` - Complete release notes
- `PHASE_6_01_SUMMARY.md` - Implementation summary
- `phase6_code_review.md` - Original code review findings
- `phase6.py` - Main entry point
- `phase6_state_manager.py` - State persistence
- `test_phase6_state_manager.py` - Unit tests

---

**Last Updated:** 2026-04-30  
**Version:** 6.01  
**Status:** READY FOR DEPLOYMENT AFTER PREP
