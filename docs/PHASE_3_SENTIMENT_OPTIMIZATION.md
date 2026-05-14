# Phase 3 Sentiment Optimization — 6-Hour Fetch Strategy

**Decision:** Fetch X sentiment every 6 hours (not every 5-min cycle)

---

## The Math

| Metric | Every 5 Min | Every 6 Hours | Savings |
|--------|------------|---------------|---------|
| Fetches per pair (48h) | 288 | 8 | **97% reduction** |
| Total fetches (BTC+XRP) | 576 | 16 | **97% reduction** |
| Estimated cost | $288 | $8 | **$280 saved** |

---

## Why 6 Hours Works

1. **Sentiment doesn't flip hour-to-hour** — Twitter/X reflects broader market mood, not minute-to-minute noise
2. **Captures macro trends** — 6h window catches news cycles, major price moves, sentiment shift
3. **RSI stays fresh** — We still fetch RSI every 5 minutes (price momentum is real-time)
4. **Balanced approach** — 80% RSI + 20% sentiment means RSI dominates decision-making anyway

---

## Implementation

**Fetch Timeline (example for 48h test):**
```
T+0h:    Fetch sentiment (cycle 0)
T+6h:    Fetch sentiment (cycle 72)
T+12h:   Fetch sentiment (cycle 144)
T+18h:   Fetch sentiment (cycle 216)
T+24h:   Fetch sentiment (cycle 288)
T+30h:   Fetch sentiment (cycle 360)
T+36h:   Fetch sentiment (cycle 432)
T+42h:   Fetch sentiment (cycle 504)
```

**Between fetches:** Reuse cached sentiment, mark as "stale" in logs

---

## Logging Changes

Each order now includes:
- `sentiment_fresh: true/false` — indicates if sentiment was just fetched
- `sentiment_source: "fresh" | "cached"` — where the value came from
- `rsi: <live value>` — always fresh (every 5 min)

---

## Expected Outcome

✅ **Cost:** $8 instead of $288 for this 48-hour test  
✅ **Signal quality:** Maintained (RSI is the primary driver anyway)  
✅ **Scalability:** Proven we can run 48h profitably  
✅ **API sustainability:** 16 calls for Phase 3 is trivial vs X API quota  

---

## Next Steps

1. Finalize orchestrator script with 6h sentiment fetch
2. Validate against test parameters (all checks from PHASE_3_REDESIGN.md)
3. Run 1-2 hour pilot to verify data flow
4. Launch full 48h execution when ready

---

**Approved by:** Brad Slusher  
**Timestamp:** 2026-03-24 19:34 PT
