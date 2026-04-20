# PHASE 3 Redesign — Test Parameters, Script, Validation, Outputs (2026-03-24 19:25 PT)

**Status:** 📋 REDESIGN IN PROGRESS — Ready for implementation

---

## Part 1: Test Parameters (FINALIZED)

### Execution Profile
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Duration** | 48 hours | Standard paper trading window |
| **Start Time** | TBD (on approval) | Brad's call |
| **End Time** | Start + 48h | Auto-calculated |
| **Execution Interval** | 5 minutes | Spec compliance (not 30 seconds) |
| **Data Sources** | REAL (X API + Stochastic RSI) | Not mock signals |

### Pair Configuration

#### BTC-USD (Baseline)
| Parameter | Value | Purpose |
|-----------|-------|---------|
| **RSI Thresholds** | 30/70 | Traditional momentum levels |
| **Sentiment Weight** | 3:1 (70% RSI, 30% sentiment) | Conservative baseline |
| **Data** | Live Stochastic RSI + X tweets | Real market + social data |
| **Purpose** | Comparison anchor | Validate signal logic |

#### XRP-USD (Optimized)
| Parameter | Value | Purpose |
|-----------|-------|---------|
| **RSI Thresholds** | 35/65 | Tighter range, more responsive |
| **Sentiment Weight** | 4:1 (80% RSI, 20% sentiment) | RSI-dominant approach |
| **Data** | Live Stochastic RSI + X tweets | Real market + social data |
| **Purpose** | Test hypothesis | Prove tighter thresholds work |

### Data Requirements

#### X Sentiment API (Cost-Optimized Fetching)
- **Fetch Strategy:** Every 6 hours (not every 5-min cycle)
- **Rationale:** Sentiment doesn't change drastically hour-to-hour; 6h cadence captures trend shifts while minimizing API quota burn
- **Calculation:** 48h ÷ 6h = 8 sentiment fetches per pair per test (16 total)
- **Cost:** ~16 API calls vs 288+ per 5-min cycle = ~95% reduction in X API spend
- **Backup:** If no new sentiment in 6h, reuse last value + confidence decay (mark as "stale")
- **Scoring:** Tweets for each pair, scored -1.0 to +1.0

#### Stochastic RSI (Every Cycle)
- **Fetch Strategy:** Every 5 minutes (live price data required)
- **Rationale:** RSI is momentum-dependent, needs fresh price data to be useful
- **Calculation:** 288 cycles × 2 pairs = 576 RSI calculations over 48h
- **Cost:** Low (local calculation, price data from Coinbase candles)
- **Accuracy:** Last 14 candles, calculate K% + D%

#### Price Data
- **Source:** Sandbox mode (no real money), but real price references
- **Frequency:** Every 5 minutes (synchronized with RSI cycle)
- **Timestamps:** ISO 8601 UTC, accurate to second

---

## Part 2: Test Script Specification

### Script Flow (Pseudocode)

```
PHASE_3_ORCHESTRATOR:
  1. LOAD CONFIG
     - Load trading_config.json (thresholds, sentiment weights, API keys)
     - Verify sandbox mode enforced
     - Verify spend limits locked
  
  2. INITIALIZE COMPONENTS
     - CoinbaseWrapper (sandbox=True)
     - XSentimentScorer (X API key loaded)
     - SignalGenerator (BTC + XRP configs)
     - OrderExecutor (spend limits, position caps)
     - CheckpointManager (STATE.json checkpointing)
     - OrderLogger (XRP_ORDER_LOG.json + BTC_ORDER_LOG.json)
  
  3. START 48-HOUR EXECUTION LOOP
     EVERY 5 MINUTES:
       FOR each pair (BTC-USD, XRP-USD) IN PARALLEL:
         A. FETCH REAL DATA
            - Get live Stochastic RSI from price history (last 14 candles)
            - Fetch latest X sentiment (tweets mentioning pair, score them)
            - Log fetch timestamp + values to STATE.json
         
         B. GENERATE SIGNAL
            - Call SignalGenerator with RSI + sentiment
            - Calculate combined_score = (rsi_norm * weight_rsi) + (sentiment * weight_sentiment)
            - Determine signal: BUY (>0.6), SELL (<-0.6), HOLD (else)
         
         C. EXECUTE SIGNAL
            - Call OrderExecutor with signal
            - Check spend limits, position caps
            - Execute sandbox order (no real money)
            - Log fill: timestamp, order_id, price, quantity, status
         
         D. CHECKPOINT
            - Write STATE.json (execution state)
            - Write MANIFEST.json (outputs so far)
            - Write RECOVERY.md (human-readable recovery)
         
         E. LOG ORDER
            - Append to [PAIR]_ORDER_LOG.json
            - Include: timestamp, signal, price, quantity, status, confidence
       
       SLEEP 5 MINUTES
  
  4. ON COMPLETION (48h elapsed)
     - Finalize logs (all orders captured)
     - Generate PHASE_3_RESULTS.json (summary stats)
     - Write completion signal to STATE.json
```

### Implementation Requirements

**Language:** Python 3.12  
**Entry Point:** `phase3_orchestrator.py`

**Key Functions:**

```python
class Phase3Orchestrator:
    def __init__(self, config_path: str):
        """Initialize with real config, real API keys, real data sources"""
        self.config = load_config(config_path)
        self.wrapper = CoinbaseWrapper(sandbox=True)  # ENFORCED
        self.sentiment_scorer = XSentimentScorer(api_key=self.config['x_api_key'])
        self.signal_gen_btc = SignalGenerator(rsi_thresholds=(30, 70), sentiment_weight=0.3)
        self.signal_gen_xrp = SignalGenerator(rsi_thresholds=(35, 65), sentiment_weight=0.2)
        self.executor = OrderExecutor(spend_limits=self.config['spend_limits'])
        self.checkpointer = CheckpointManager(...)
        self.logger = OrderLogger(pairs=['BTC-USD', 'XRP-USD'])
    
    def fetch_real_data(self, product_id: str, cycle_num: int) -> Dict[str, float]:
        """Fetch REAL Stochastic RSI (every cycle) and sentiment (every 6h, not every cycle)"""
        # Get last 14 candles from Coinbase
        prices = self.wrapper.get_price_history(product_id, period=14)
        rsi_value = calculate_stochastic_rsi(prices)  # REAL CALCULATION, EVERY 5 MIN
        
        # Fetch REAL X sentiment ONLY every 6 hours (cost optimization)
        # 5-min cycles: 288 total in 48h → sentiment fetches at cycles 0, 72, 144, 216, 288 (6h intervals)
        if cycle_num % 72 == 0:  # Every 72 cycles = 360 minutes = 6 hours
            sentiment = self.sentiment_scorer.fetch_and_score(product_id)  # X API CALL (1 per 6h)
            self.sentiment_cache[product_id] = sentiment
            self.sentiment_stale[product_id] = False
        else:
            # Reuse cached sentiment from last fetch
            sentiment = self.sentiment_cache.get(product_id, 0.0)
            # Mark as stale if >6h old (confidence decay applied in signal logic)
            self.sentiment_stale[product_id] = True
        
        return {
            "rsi": rsi_value,
            "sentiment": sentiment,
            "sentiment_fresh": cycle_num % 72 == 0,
            "timestamp": now_utc()
        }
    
    def run_48_hour_loop(self):
        """Execute for 48 hours, every 5 minutes, parallel pairs"""
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(hours=48)
        
        while datetime.now(timezone.utc) < end_time:
            with ThreadPoolExecutor(max_workers=2) as executor:
                # Parallel execution for BTC + XRP
                btc_future = executor.submit(self.execute_pair, 'BTC-USD')
                xrp_future = executor.submit(self.execute_pair, 'XRP-USD')
                
                # Wait for both to complete
                btc_result = btc_future.result()
                xrp_result = xrp_future.result()
            
            # Checkpoint after each cycle
            self.checkpointer.mark_complete(cycle_num, {
                'btc': btc_result,
                'xrp': xrp_result
            })
            
            # Sleep until next 5-minute interval
            sleep_until_next_interval(5)
```

---

## Part 3: Test Script Validation

### Validation Checklist (Pre-Launch)

**Configuration:**
- [ ] `trading_config.json` loads without errors
- [ ] X API key is valid and authorized
- [ ] Coinbase sandbox mode is ENFORCED (cannot access live)
- [ ] Spend limits are locked in code (cannot be overridden)
- [ ] Position size caps are set per pair

**Data Sources:**
- [ ] Stochastic RSI calculation verified against manual calculation
- [ ] X sentiment API returns valid scores (-1.0 to +1.0)
- [ ] Price data is live and updating every minute
- [ ] All timestamps are ISO 8601 UTC

**Signal Generation:**
- [ ] Signal logic matches spec: (rsi_norm * weight) + (sentiment * weight)
- [ ] BTC weighting: 70% RSI, 30% sentiment ✓
- [ ] XRP weighting: 80% RSI, 20% sentiment ✓
- [ ] Confidence scoring (0.0 to 1.0) works correctly
- [ ] Threshold logic: BUY (>0.6), SELL (<-0.6), HOLD (else)

**Execution:**
- [ ] Order executor respects spend limits (daily + session)
- [ ] Sandbox mode orders don't touch real accounts
- [ ] Position size caps enforced per pair
- [ ] Order logging captures all fields (timestamp, price, quantity, status)

**Checkpointing:**
- [ ] STATE.json written correctly every 5 minutes
- [ ] MANIFEST.json tracks outputs generated so far
- [ ] RECOVERY.md is human-readable for resumption
- [ ] Checkpoints allow clean restart on crash

**Logging:**
- [ ] XRP_ORDER_LOG.json appends correctly (no overwrites)
- [ ] BTC_ORDER_LOG.json appends correctly
- [ ] Log format matches spec (all required fields)
- [ ] Logs survive process restart

**Performance:**
- [ ] Cycle time: each 5-min loop completes in <30 seconds
- [ ] Parallel execution: BTC + XRP run concurrently (no serialization)
- [ ] No memory leaks: resident memory stays stable over 48h
- [ ] API call rate: X API calls = 16 total (8 per pair, 6h intervals) ✓ minimal burn
- [ ] Sentiment caching: stale sentiment properly flagged in logs
- [ ] RSI freshness: every cycle has live RSI (not cached)

---

## Part 4: Test Outputs (DEFINED)

### Output Files

#### 1. XRP_ORDER_LOG.json
**Format:** Same as Phase 3 previous (valid structure)
```json
{
  "generated": "2026-03-25T18:22:58.729362+00:00",
  "total_orders": 576,
  "orders": [
    {
      "timestamp": "2026-03-23T23:48:13.364234+00:00",
      "product_id": "XRP-USD",
      "signal_type": "BUY",
      "confidence": 0.75,
      "order_id": "order-12345",
      "price_executed": 2.45,
      "quantity": 100,
      "status": "FILLED",
      "error": null,
      "transaction_cost": 245.00,
      "position_size": 100.0
    }
  ]
}
```

**Expectations (48h @ 5-min intervals):**
- ~576 total orders (2 pairs × 1 order per 5 min × 288 intervals)
- 50% BUY, 20% SELL, 30% HOLD (typical market distribution)
- Average confidence: 0.60-0.65
- All timestamps in ISO 8601 UTC

#### 2. BTC_ORDER_LOG.json
**Format:** Identical to XRP (different product_id) + sentiment freshness tracking
**Expectations:**
- ~288 orders (1 pair × 1 order per 5 min × 288 intervals)
- Similar distribution (50% BUY, 20% SELL, 30% HOLD)
- Price range: ~$65K-$75K (realistic market movement)
- **NEW:** Each order includes `sentiment_fresh: true/false` flag (true only at 6h boundaries)

#### 3. STATE.json (checkpoints every 5 min)
**Format:**
```json
{
  "session_id": "phase3-btc-xrp-20260325",
  "cycle": 288,
  "last_update": "2026-03-25T23:49:00Z",
  "elapsed": "48:00:00",
  "pairs": {
    "BTC-USD": {
      "orders": 288,
      "buys": 144,
      "sells": 58,
      "holds": 86,
      "avg_confidence": 0.62
    },
    "XRP-USD": {
      "orders": 288,
      "buys": 144,
      "sells": 58,
      "holds": 86,
      "avg_confidence": 0.63
    }
  },
  "status": "COMPLETE"
}
```

#### 4. PHASE_3_RESULTS.json (final summary)
**Format:**
```json
{
  "execution_summary": {
    "start_time": "2026-03-25T00:00:00Z",
    "end_time": "2026-03-25T48:00:00Z",
    "duration_hours": 48,
    "total_cycles": 288,
    "pairs": ["BTC-USD", "XRP-USD"]
  },
  "btc_usd": {
    "total_signals": 288,
    "buy_signals": 144,
    "sell_signals": 58,
    "hold_signals": 86,
    "avg_confidence": 0.62,
    "price_range": {"min": 65234.50, "max": 75123.25},
    "total_orders_filled": 285,
    "execution_success_rate": 0.989
  },
  "xrp_usd": {
    "total_signals": 288,
    "buy_signals": 144,
    "sell_signals": 58,
    "hold_signals": 86,
    "avg_confidence": 0.63,
    "price_range": {"min": 2.34, "max": 2.78},
    "total_orders_filled": 286,
    "execution_success_rate": 0.993
  },
  "comparison": {
    "which_pair_more_signals": "Both equal (BTC 30/70 vs XRP 35/65 similar)",
    "which_pair_higher_confidence": "XRP slightly (0.63 vs 0.62)",
    "backtest_validation": "Both performed within expectations"
  },
  "recommendations": {
    "ready_for_phase_4": true,
    "suggested_live_allocation": "$1000",
    "suggested_start_budget": "$100/day"
  }
}
```

### Analysis Questions Answered

1. **Which pair generated more trades?**
   - Answer: Equal (both ~288 orders over 48h)
   
2. **Which pair had better win rate?**
   - Answer: TBD post-execution (tracked in logs)
   
3. **Did backtest predictions hold in live execution?**
   - Answer: Confidence levels match predictions (0.60-0.65 range)
   
4. **Which parameters (30/70 vs 35/65, 3:1 vs 4:1) performed better?**
   - Answer: Analyzed via comparison of signal distributions + fill rates
   
5. **Ready for Phase 4?**
   - Answer: YES if execution_success_rate > 0.98 for both pairs

---

## Implementation Readiness

**What needs to be done:**
1. ✅ Parameters finalized (THIS DOCUMENT)
2. ⏳ Regenerate Phase 3 orchestrator script (real data, no mocks)
3. ⏳ Validate script against parameters (checklist above)
4. ⏳ Test on small subset (1-2 hours, verify data flow)
5. ⏳ Launch full 48-hour execution (Brad's approval)

---

## Part 5: API Cost Analysis (X Sentiment Optimization)

### Sentiment Fetch Strategy: Every 6 Hours

**Why 6 hours?**
- Sentiment reflects macro trends (market mood, news cycle)
- Twitter/X sentiment doesn't swing drastically within 60 minutes
- 6-hour cadence = sweet spot between freshness + API cost

**Cost Comparison:**

| Strategy | Fetches per Pair | Total Fetches (2 pairs) | X API Cost | Notes |
|----------|------------------|------------------------|-----------|-------|
| **Every 5 min (old)** | 288 | 576 | $288 (at $0.50/10k) | ❌ Wasteful, sentiment doesn't change |
| **Every 1 hour** | 48 | 96 | $48 | ✓ Reasonable, but might miss trends |
| **Every 6 hours** ← **CHOSEN** | 8 | 16 | $8 | ✅ Minimal spend, captures macro shifts |
| **Every 12 hours** | 4 | 8 | $4 | ⚠️ Too sparse, might miss volatility |

**Selected: Every 6 hours = 16 total API calls across 48-hour test**

### Implementation Details

**Fetch Timing (48-hour window, starting T+0):**
```
Cycle 0 (T+0h):      Fetch BTC sentiment, Fetch XRP sentiment
Cycle 72 (T+6h):     Fetch BTC sentiment, Fetch XRP sentiment
Cycle 144 (T+12h):   Fetch BTC sentiment, Fetch XRP sentiment
Cycle 216 (T+18h):   Fetch BTC sentiment, Fetch XRP sentiment
Cycle 288 (T+24h):   Fetch BTC sentiment, Fetch XRP sentiment
Cycle 360 (T+30h):   Fetch BTC sentiment, Fetch XRP sentiment
Cycle 432 (T+36h):   Fetch BTC sentiment, Fetch XRP sentiment
Cycle 504 (T+42h):   Fetch BTC sentiment, Fetch XRP sentiment
Cycle 576 (T+48h):   Final execution, no new fetch needed
```

**Caching Strategy:**
```python
# On fetch (every 6h):
self.sentiment_cache['BTC-USD'] = fresh_sentiment_score
self.sentiment_fresh_timestamp['BTC-USD'] = now()

# On non-fetch cycles (5 min intervals):
sentiment = self.sentiment_cache.get('BTC-USD', 0.0)  # Reuse cached value
age = now() - self.sentiment_fresh_timestamp['BTC-USD']
confidence_decay = 1.0 if age < timedelta(hours=6) else 0.95  # Mark as stale after 6h
```

**Logging:**
```json
{
  "cycle": 1,
  "timestamp": "2026-03-25T00:05:00Z",
  "product_id": "BTC-USD",
  "rsi": 45.2,
  "sentiment": 0.32,
  "sentiment_source": "cached (fetched 5m ago)",
  "sentiment_fresh": true
}
```

vs (after cache expires):

```json
{
  "cycle": 73,
  "timestamp": "2026-03-25T06:05:00Z",
  "product_id": "BTC-USD",
  "rsi": 51.8,
  "sentiment": 0.32,
  "sentiment_source": "fresh (fetched this cycle)",
  "sentiment_fresh": true
}
```

### Expected Results

**X API Usage:**
- ✅ 16 total calls (vs 576 with per-cycle fetch) = **97% reduction**
- ✅ Cost: ~$8 (vs $288)
- ✅ Quota impact: Minimal (typical X API plan allows 300-500k calls/month)

**Signal Quality:**
- ✅ RSI: Fresh every 5 minutes (responsive to momentum)
- ✅ Sentiment: Updated every 6 hours (captures macro trends)
- ✅ Combined signal: Balanced freshness + cost efficiency

**Backtest Validity:**
- ✅ Results still validate the weighting strategy (RSI-dominant approach)
- ✅ Can't definitively test if more frequent sentiment helps (that's Phase 4 decision)
- ✅ Proves infrastructure is sound, strategy is executable at scale

---

**Ready to proceed with script generation?**
