# Phase 6 Decision Log

**Owner:** Brad Slusher  
**Purpose:** Record all major decisions, assumptions, risks accepted  
**Started:** 2026-04-21

---

## Decision 1: Phase 4d Algorithm for Production

**Date:** 2026-04-21  
**Decision:** Deploy Phase 4d (RSI<30 entry, RSI>70 exit, 2% SL) instead of Phase 5 Full Spec  

**Rationale:**
- Real-data backtest 2025-04-20 to 2026-04-20 (bearish market)
- Phase 4d: +$192.84 (19.3% ROI, 78 trades, 33.3% win)
- Phase 5 Full (StochRSI + 2×ATR): +$64.18 (6.4% ROI, 65 trades, 50.8% win)
- Phase 4d beat Phase 5 Full by $128.66 (3x better)
- Simpler logic, tighter stops, better for this market

**Risk:** Phase 5 Full might be better in bull markets  
**Mitigation:** Monitor live results, can switch strategies if underperforming

**Status:** ✅ Implemented (Phase 5 multi-pair running Phase 4d logic)

---

## Decision 2: Delete All Synthetic Data Backtests

**Date:** 2026-04-21  
**Decision:** Remove all phase3/4/4b/backtest files using synthetic data (60 files deleted)

**Rationale:**
- NO_FAKE_DATA_POLICY (2026-03-31) violated by synthetic backtests
- Synthetic Phase 5 backtest showed +$5,799 (579% ROI) vs. real data -$20.68
- Fake data created false confidence, led to pursuing inferior strategy
- Must use only real OHLCV data going forward

**Risk:** Lost historical backtesting capability  
**Mitigation:** Archived experimental code in ./archived/ for reference

**Status:** ✅ Completed (committed to git)

---

## Decision 3: Archive vs. Delete Experimental Code

**Date:** 2026-04-21  
**Decision:** Archive 26 experimental files to ./archived/ instead of hard delete

**Rationale:**
- Preserve development history
- Allow future reference if needed
- Keep root directory clean (8 active files only)
- Maintain option to revive if needed

**Risk:** Might clutter git history  
**Mitigation:** ./archived/ excluded from production builds

**Status:** ✅ Completed

---

## Decision 4: Skip Full StochRSI Implementation for Phase 6

**Date:** 2026-04-21  
**Decision:** Use Phase 4d (simple RSI) for Phase 6, not Phase 5 Full Spec (StochRSI)

**Rationale:**
- Phase 4d outperformed Phase 5 Full on real data (Decision 1)
- StochRSI crossover detection added complexity without benefit
- Keep Phase 6 focused on order execution, not signal refinement
- Can revisit signal algorithm in Phase 7

**Risk:** StochRSI might be better long-term  
**Mitigation:** Log all signals, can A/B test later

**Status:** ✅ Confirmed

---

## Decision 5: Proceed with Phase 6 (order_executor Integration)

**Date:** 2026-04-21  
**Decision:** Move forward with integrating order_executor.py for live trading

**Rationale:**
- order_executor.py production-ready (17KB, complete error handling)
- Phase 5 signals stable (backtested +$192.84 real data)
- Coinbase API proven working (real orders placed 2026-04-20)
- Capital available ($750 deployed, $250 reserve)
- Risk mitigated by sandbox testing (Task 5)

**Risk:** Real capital loss if order execution fails  
**Mitigation:** 
- Sandbox testing 48-72h (Task 5)
- Slow rollout (start with $250, scale to $750)
- 72h monitoring before full scale
- Continuous error logging + alerts

**Status:** ⏳ Approval Pending (Brad's sign-off required)

---

## Decision 6: Capital Allocation Strategy

**Date:** 2026-04-21 (Proposed)  
**Decision:** Start Phase 6 live trading with $250, scale to $750 after 48h success

**Rationale:**
- $1,000 total available ($750 already deployed, $250 reserve)
- Reduce risk of catastrophic failure
- Validate live execution with smaller amounts first
- Build confidence before full scale

**Risk:** Slower profitability during ramp-up  
**Mitigation:** None needed; risk acceptable

**Status:** ⏳ Decision Pending (Brad's choice: $250 initial or $750 direct)

---

## Decision 7: Sandbox Testing Duration

**Date:** 2026-04-21 (Proposed)  
**Decision:** Run 48-72h sandbox test before live (Task 5)

**Rationale:**
- 24h: verify basic order execution
- 48h: catch edge cases, market conditions
- 72h: high confidence in stability

**Risk:** Delay to live trading  
**Mitigation:** No risk if Phase 5 continues during sandbox testing

**Status:** ⏳ Decision Pending (Brad's choice: 24h/48h/72h)

---

## Decision 8: Portfolio Tracker Status

**Date:** 2026-04-21 (Pending Task 2)  
**Decision:** TBD - depends on portfolio_tracker.py inspection

**Options:**
- A: Complete (integrate immediately)
- B: Missing/incomplete (build new in Phase 6)
- C: Defer to Phase 6.2 (focus on order_executor first)

**Impact:** 
- A: +0 hours
- B: +4-6 hours
- C: Basic portfolio tracking only

**Status:** ⏳ Decision Pending (Task 2 findings)

---

## Decision 9: Git Branch Strategy

**Date:** 2026-04-21  
**Decision:** Phase 6 work on feature branch, merge to main after sandbox success

**Rationale:**
- Keep main production-ready
- Allows parallel work on other features
- Clean history of what was tested

**Branches:**
- `feature/CA-CRYPTO-BACKTEST-001-regression-test` (cleanup + Phase 5 docs)
- `feature/phase-6-order-executor` (Phase 6 integration)
- Merge to main after sandbox approval

**Status:** ✅ Cleanup branch created, Phase 6 branch pending

---

## Decision 10: Live Deployment Gate

**Date:** 2026-04-21  
**Decision:** Live deployment (Task 6) requires explicit Brad approval AFTER sandbox success

**Rationale:**
- Real capital at risk
- Not automatic even if sandbox passes
- Gives Brad control point before going live

**Gate Criteria:**
- Sandbox test passed (48h+ no failures)
- All orders executed correctly
- P&L calculations verified
- Position state in sync with Coinbase
- Brad's written approval

**Status:** ✅ Policy established

---

## Decision 11: Error Response Protocol

**Date:** 2026-04-21  
**Decision:** On any execution error during live trading, pause and alert

**Protocol:**
- Order fails → Log, alert Brad, wait for approval to retry
- Position desync → Stop new orders, reconcile state, alert Brad
- API rate limit → Backoff, retry, log
- Network timeout → Retry with exponential backoff

**Status:** ⏳ To be implemented in order_executor integration

---

## Decision 12: Monitoring & Alerting

**Date:** 2026-04-21  
**Decision:** Continuous 24/7 monitoring with daily summary + alert on errors

**Cadence:**
- Error alerts: Immediate (Telegram)
- Hourly summary: Every 60 min (logs)
- Daily digest: 6 PM PT (Telegram, HEARTBEAT)
- Weekly review: Fridays at 5 PM PT

**Status:** ⏳ To be implemented in phase5_multi_pair integration

---

## Assumptions

1. **Coinbase API stable:** No degradation assumed for 72h+ monitoring period
2. **ES256 JWT auth continues working:** No auth changes assumed
3. **Network connectivity stable:** No 10+ hour outages assumed
4. **Sentiment sources available:** X API + Reddit accessible
5. **Capital available:** $750 remains deployed, no margin calls
6. **Market conditions:** No flash crashes or extreme volatility
7. **No regulatory changes:** Coinbase Advanced Trade API remains available in US

---

## Risk Acceptance

**Brad Slusher acknowledges:**
- [ ] Real capital ($750) is at risk during Phase 6
- [ ] Order execution failures could result in losses
- [ ] Sentiment data sources may become unavailable
- [ ] Monitoring may miss edge cases
- [ ] No guarantee of profitability
- [ ] Decision to proceed is voluntary and informed

---

## Approval Sign-Offs

### Cleanup & Documentation (Completed)
- **Decision 1-4:** ✅ Completed 2026-04-21
- **Decision 9:** ✅ Branch created

### Pre-Phase 6 Approval (Pending)
- **Decision 5:** ⏳ Brad approval required
- **Decision 6-7:** ⏳ Brad choices required
- **Decision 8:** ⏳ Task 2 findings required
- **Decision 12:** ⏳ Implementation approval

---

## Future Decisions (Post-Phase 6)

**Phase 7 candidates:**
- Switch from Phase 4d to Phase 5 Full (if data supports it)
- Implement machine learning sentiment scoring
- Add portfolio rebalancing logic
- Expand to additional pairs or crypto assets
- Deploy to additional exchanges (Kraken, Coinbase Pro, etc.)

---

**Last Updated:** 2026-04-21 13:45 PT  
**Next Review:** Upon completion of Phase 6 Task 2 (portfolio_tracker inspection)
