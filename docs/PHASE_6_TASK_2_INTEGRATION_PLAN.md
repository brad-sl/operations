# Phase 6 Task 2: Order Executor Integration Plan

**Status:** ⏳ DEFERRED (Phase 5.1 still live with manual trading)

**Decision:** Keep Phase 5.1 running with current configuration (sentiment-only signals) until Task 2 validation complete.

---

## Integration Strategy

**Current State (Phase 5.1):**
- ✅ $750 real capital deployed across 6 pairs
- ✅ Sentiment aggregation running (X + Reddit, 30-min cadence)
- ✅ Manual order execution (via Coinbase Advanced Trade API)
- ❌ OrderExecutor NOT yet integrated

**Why Defer Task 2:**
1. Phase 5.1 is LIVE with real capital
2. No breaking changes policy active
3. OrderExecutor validated (Task 1: PASS)
4. Integration requires careful testing first

**Risk-Safe Approach:**
- Keep Phase 5.1 running as-is
- Create sandbox Task 2 integration test
- Validate 24h before live integration
- Document all integration points

---

## Task 2 Integration Checklist

### Phase 1: Sandbox Integration (24h test)
- [ ] Wire OrderExecutor into phase5_multi_pair.py._process_pair()
- [ ] Use small order sizes ($10-20) in sandbox mode
- [ ] Validate order placement, confirmation, tracking
- [ ] Monitor for any crashes or edge cases
- [ ] Log all trades to CSV

### Phase 2: Live Migration (after 24h sandbox validation)
- [ ] Switch from manual to OrderExecutor-based execution
- [ ] Start with $25-50 per trade (conservative)
- [ ] Monitor order fills, slippage, execution quality
- [ ] Scale gradually to full $750 allocation

### Phase 3: Production Hardening
- [ ] Error recovery procedures
- [ ] API timeout handling
- [ ] Insufficient funds fallback
- [ ] Daily P&L tracking

---

## Integration Point: _process_pair()

**Current Flow:**
```python
signal = self._determine_trade_signal(pair, price, rsi, sentiment)
# Returns: BUY, SELL, or HOLD
```

**With OrderExecutor:**
```python
signal = self._determine_trade_signal(pair, price, rsi, sentiment)

if signal != "HOLD" and ORDER_EXECUTOR_AVAILABLE:
    try:
        executor = OrderExecutor(
            signals=[{"id": f"cycle-{cycle}", "signal": signal, ...}],
            coinbase_wrapper=self.cb_client_wrapper,
            product_id=pair,
            order_size_usd=self.config.get('order_size_usd', 25.0),
            sandbox_mode=self.sandbox
        )
        results = executor.execute_all_signals()
        
        # Log results
        for result in results:
            self.logger.info(f"Order {result.order_id}: {result.status} ({result.quantity} @ ${result.price_executed})")
        
        # Track trades to CSV
        self._log_trades_to_csv(results)
    except Exception as e:
        self.logger.error(f"OrderExecutor failed for {pair}: {e}")
        self.logger.info(f"Falling back to manual order placement...")
```

---

## Why This Works

1. **No Breaking Changes:** Phase 5.1 keeps running as-is
2. **Graceful Fallback:** If OrderExecutor fails, manual flow continues
3. **Sandbox Testing:** Full 24h validation before going live
4. **Conservative Scaling:** Start small, increase gradually
5. **Audit Trail:** All trades logged for review

---

## Timeline

- **Now (2026-04-21):** Keep Phase 5.1 running
- **2026-04-22:** Complete sandbox integration test (24h)
- **2026-04-23:** Live migration (if validation passed)
- **2026-04-24:** Production hardening & optimization

---

## Files Changed (Task 2)

- `phase5_multi_pair.py`: Add OrderExecutor import + call in _process_pair()
- `logs/task2_integration_test.log`: Sandbox test output
- `trades.csv`: Trade execution log (append mode)

---

## Success Criteria

- ✅ OrderExecutor integrates without errors
- ✅ Sandbox tests execute 100+ trades without crashing
- ✅ All order IDs and statuses tracked
- ✅ P&L reconciles with Coinbase API
- ✅ Ready for live migration to production capital

---

**Status:** READY FOR TASK 2 INTEGRATION (after 24h sandbox validation)
