# Phase 4b 48-Hour Test — Digest Schedule

**Test Window:** 2026-03-29 23:10 UTC → 2026-03-31 23:10 UTC (48 hours)  
**Digest Interval:** Every 4 hours  
**Status:** ACTIVE

---

## Scheduled Digest Checkpoints

| # | Time (PT) | Time (UTC) | Status | Notes |
|---|-----------|-----------|--------|-------|
| 1 | Sun 16:10 (approx) | Sun 23:10 | ✅ LAUNCH | Test started; cycle 0 |
| 2 | Sun 20:10 | Mon 04:10 | ⏳ PENDING | First 4h checkpoint (cycle 48) |
| 3 | Mon 00:10 | Mon 08:10 | ⏳ PENDING | 8h checkpoint (cycle 96) |
| 4 | Mon 04:10 | Mon 12:10 | ⏳ PENDING | 12h checkpoint (cycle 144) |
| 5 | Mon 08:10 | Mon 16:10 | ⏳ PENDING | 16h checkpoint (cycle 192) |
| 6 | Mon 12:10 | Mon 20:10 | ⏳ PENDING | 20h checkpoint (cycle 240) |
| 7 | Mon 16:10 | Tue 00:10 | ⏳ PENDING | 24h checkpoint (cycle 288) |
| 8 | Mon 20:10 | Tue 04:10 | ⏳ PENDING | 28h checkpoint (cycle 336) |
| 9 | Tue 00:10 | Tue 08:10 | ⏳ PENDING | 32h checkpoint (cycle 384) |
| 10 | Tue 04:10 | Tue 12:10 | ⏳ PENDING | 36h checkpoint (cycle 432) |
| 11 | Tue 08:10 | Tue 16:10 | ⏳ PENDING | 40h checkpoint (cycle 480) |
| 12 | Tue 12:10 | Tue 20:10 | ⏳ PENDING | 44h checkpoint (cycle 528) |
| 13 | Tue 16:10 | Wed 00:10 | ⏳ PENDING | FINAL: 48h complete (cycle 576) |

---

## Digest Template

Each digest will include:

### 📊 Execution Status
- Elapsed time and cycles completed
- Process health check (PID, memory, uptime)
- Expected cycles vs actual cycles
- Any errors or anomalies

### 📈 Trading Performance (Last 4h window)
- Trades executed (count)
- Wins / Losses / Win Rate
- Net P&L (by pair and total)
- Average P&L per trade
- Sentiment correlation (if available)

### 🔍 Sentiment Integration
- Latest sentiment fetches (BTC-USD, XRP-USD)
- Sentiment score distribution (24h)
- Cache freshness status
- X API fetch success rate

### 🔧 System Health
- Database integrity (trades table size)
- Log file size and errors
- Sentiment schedule updates (count)
- Any exceptions or warnings

### 📌 Quick Notes
- Any notable patterns or anomalies
- Confidence level in Phase 4b integration
- Preliminary go/no-go indicator

---

## How to Trigger Manual Digest

Between scheduled checkpoints, you can request a digest manually:
```bash
# Check cycle count and recent trades
sqlite3 phase4_trades.db "SELECT COUNT(*) as total_trades FROM trades;"
sqlite3 phase4_trades.db "SELECT pair, COUNT(*) as trades, SUM(pnl) as pnl, AVG(pnl) as avg_pnl FROM trades GROUP BY pair;"

# Check sentiment freshness
sqlite3 phase4_trades.db "SELECT pair, MAX(fetch_time) as last_fetch FROM sentiment_schedule GROUP BY pair;"

# Tail logs
tail -n 50 phase4b_48h_run.log
```

---

## Final Digest (End of Test)

At 2026-03-31 23:10 UTC, the final digest will include:

- **Complete 48h Summary:**
  - Total trades, win rate, total P&L, Sharpe estimate
  - Per-pair breakdown
  - Sentiment contribution to performance

- **Go/No-Go Decision:**
  - Meet success criteria? (Sharpe ≥ 0.9, win rate 50-70%)
  - Recommendation for Phase 4b → Production rollout
  - Action items for next phase

- **Artifacts:**
  - PHASE4B_FINAL_RESULTS.md (full report)
  - PR-ready summary for GitHub merge
  - Lessons learned and edge cases

---

**Digest delivery method:** Inline chat messages at each checkpoint (4-hour intervals)  
**Test control:** You can pause, resume, or cancel anytime via console kill command  
**Questions/anomalies:** Escalate to chat between checkpoints if needed

