# Phase 3 Pilot Test Plan — 1-Hour Validation Run (2026-03-24 19:40 PT)

**Goal:** Validate data flow + prove functionality without waiting for full 48h execution

---

## Pilot Execution Plan

### Duration
- **Target:** 1 hour (12 cycles × 5 minutes)
- **Start:** Brad's approval
- **End:** T+1h (auto-terminate)

### What Gets Tested

| Component | Test | Expected Result |
|-----------|------|-----------------|
| **RSI Fetch** | Fetch Stochastic RSI from Coinbase every 5 min | ✅ 12 RSI values (BTC + XRP) |
| **Sentiment Cache** | Fetch sentiment at T+0, cache for remaining 55 min | ✅ 2 sentiment fetches (BTC + XRP) |
| **Signal Generation** | Generate BUY/SELL/HOLD signals | ✅ ~6-12 signals per pair |
| **Order Logging** | Log orders to JSON files | ✅ XRP_ORDER_LOG.json + BTC_ORDER_LOG.json with sentiment_fresh flag |
| **Checkpointing** | Write STATE/MANIFEST/RECOVERY every cycle | ✅ 12 checkpoint iterations |
| **Parallel Execution** | Both pairs run concurrently | ✅ <30s per 5-min cycle |
| **Error Handling** | Graceful API failures (if any) | ✅ Logs but continues |

### Test Execution Checklist

```bash
# 1. Verify setup
cd /home/brad/.openclaw/workspace/operations/crypto-bot
source venv/bin/activate
python -c "from coinbase_wrapper import CoinbaseWrapper; print('✓ Imports work')"

# 2. Check config
cat trading_config.json | grep -E '"sandbox"|"spend_limit"|"rsi_"'

# 3. Run 1-hour pilot
python phase3_orchestrator_v2.py --duration 3600 --verbose

# 4. Monitor output
tail -f BTC_ORDER_LOG.json XRP_ORDER_LOG.json STATE.json

# 5. Validate after 1h
python scripts/validate_pilot.py --verify_logs --check_timestamps
```

### Success Criteria

**Must have all 5:**
1. ✅ No crashes (graceful error handling)
2. ✅ BTC_ORDER_LOG.json has ≥6 orders (min 1 per cycle)
3. ✅ XRP_ORDER_LOG.json has ≥6 orders (min 1 per cycle)
4. ✅ sentiment_fresh flag = true at T+0 only, false for cycles 1-11
5. ✅ STATE.json updates every cycle with cycle count increasing

**Nice to have:**
- Signal distribution: 50% BUY, 20% SELL, 30% HOLD (or similar)
- All timestamps ISO 8601 UTC format
- Average cycle time <30 seconds

---

## If Pilot Succeeds

**Immediate next step:** Launch full 48-hour execution

```
python phase3_orchestrator_v2.py --duration 172800  # 48 hours in seconds
```

**Expected completion:** 2026-03-25 23:49 UTC (Wed 4:49 PM PT)

---

## If Pilot Fails

**Debug steps:**
1. Check logs: `grep ERROR phase3.log`
2. Verify API connections: Coinbase sandbox, X API key
3. Check spend limits: `cat trading_config.json | jq .spend_limits`
4. Review STATE.json: Did execution start? How far did it get?
5. Restart with `--debug` flag for verbose output

---

## What NOT to Worry About

- ❌ **No actual trades happening** — Sandbox mode, no real money
- ❌ **Price/sentiment accuracy** — Pilot just validates infrastructure
- ❌ **Win rate metrics** — Too early (wait for full 48h)
- ❌ **Orders being small/zero** — That's fine, point is data flow works

---

## Timeline

| Time | Action |
|------|--------|
| T+0 | Start pilot, monitor console |
| T+30 min | Check STATE.json (should be at cycle ~6) |
| T+55 min | Verify sentiment still cached (no new fetch) |
| T+60 min | Pilot ends, validate all logs |
| T+61 min | Decision: proceed to 48h or debug |

---

**Ready to launch pilot? Reply with timestamp + we'll kick it off.**
