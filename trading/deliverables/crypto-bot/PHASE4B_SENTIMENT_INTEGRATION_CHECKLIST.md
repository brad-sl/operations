# Phase 4b — X-Sentiment Integration Checklist

**Status:** 🟠 IN IMPLEMENTATION (2026-03-29 21:50 PT)  
**Scope:** 1-hour cadence sentiment fetching + Phase 4b entry signal integration  
**GitHub Tracking:** commits will reference this checklist + spec doc

---

## Implementation Plan (Locked)

### 1. ✅ Sentiment Scheduler Created
- **File:** sentiment_scheduler.py (7 KB)
- **Features:**
  - Fetches sentiment for BTC-USD and XRP-USD on demand
  - Stores to sentiment_schedule DB table
  - Logs to sentiment_log.jsonl for audit trail
  - Designed to run every 1 hour via cron or daemon
- **Status:** Complete, ready for cron scheduling

### 2. 🔄 X-Sentiment Fetcher Update (In Progress)
- **File:** x_sentiment_fetcher.py
- **Changes Required:**
  - Add `cache_hours` parameter (default 1 hour)
  - Update `_is_cache_fresh()` to use `self.cache_hours` instead of hardcoded 6
  - Update docstring to reference PHASE4B_X_SENTIMENT_SPECIFICATION.md
  - Ensure bearer token from .env (no hardcoding)
- **Status:** Needs patch application

### 3. 🔄 Database Schema Update (Ready)
- **File:** SCHEMA_UPDATE_SENTIMENT.sql (1.2 KB)
- **Changes:**
  - Add sentiment columns to trades table:
    - sentiment_score REAL
    - sentiment_fetch_time TEXT
    - sentiment_cached BOOLEAN
  - Create sentiment_schedule table
  - Add indexes for fast lookups
- **Status:** SQL file created, ready to apply with: `sqlite3 phase4_trades.db < SCHEMA_UPDATE_SENTIMENT.sql`

### 4. ⏳ Phase 4b Integration (Pending)
- **File:** phase4b_v1.py (to be created)
- **Integration Approach:**
  - Fetch latest sentiment from sentiment_schedule table for each pair
  - Entry signal rule:
    - sentiment_score > +0.2: boost entry confidence (lower RSI threshold)
    - sentiment_score -0.2 to +0.2: use base threshold
    - sentiment_score < -0.2: reduce entry likelihood (require stronger signal)
  - Exit logic: unchanged from Phase 4 winner strategy
  - Log sentiment_score, sentiment_fetch_time, sentiment_cached with each trade
- **Status:** Specification locked, implementation pending

### 5. ⏳ GitHub Commits & Documentation
- Commit 1: "chore: add sentiment_scheduler.py (1h cadence, sentiment_schedule table)"
- Commit 2: "refactor: update x_sentiment_fetcher.py (cache_hours param, 1h default)"
- Commit 3: "schema: add sentiment columns to trades + sentiment_schedule table"
- Commit 4: "feat: Phase 4b integration (sentiment-driven entry signals)"
- Commit 5: "docs: update PHASE4B_X_SENTIMENT_SPECIFICATION.md with 1h cadence + integration details"

---

## Cron Schedule (1 Hour Cadence)

```bash
# Add to crontab -e
0 * * * * cd /home/brad/.openclaw/workspace/operations/crypto-bot && python3 sentiment_scheduler.py >> sentiment_scheduler.log 2>&1
```

Runs sentiment fetch every hour on the hour, logs to sentiment_scheduler.log.

---

## Data Flow (Phase 4b)

```
X API v2 (every 1h via cron)
    ↓
sentiment_scheduler.py
    ↓
sentiment_schedule (DB table)
sentiment_log.jsonl (audit trail)
    ↓
phase4b_v1.py (reads latest sentiment per pair)
    ↓
Entry Signal Evaluation:
  - RSI signal + sentiment modulation
  - If entry approved: use Phase 4 winner threshold for exit
    ↓
trades table:
  - sentiment_score (from latest sentiment_schedule)
  - sentiment_fetch_time (timestamp)
  - sentiment_cached (cache hit indicator)
  - [Phase 4 winner columns: entry_price, exit_price, pnl, pnl_pct, etc.]
```

---

## Files Modified/Created

| File | Status | Purpose |
|------|--------|---------|
| sentiment_scheduler.py | ✅ Created | 1h cadence fetcher + DB logger |
| x_sentiment_fetcher.py | 🔄 In Progress | Add cache_hours param |
| SCHEMA_UPDATE_SENTIMENT.sql | ✅ Created | DB schema updates |
| phase4b_v1.py | ⏳ Pending | Phase 4b + sentiment integration |
| PHASE4B_X_SENTIMENT_SPECIFICATION.md | 🔄 Needs Update | Add 1h cadence + integration rule |
| PHASE4B_SENTIMENT_INTEGRATION_CHECKLIST.md | ✅ This File | Track implementation status |

---

## Verification Steps

After implementation, verify:

1. **Scheduler Test:**
   ```bash
   cd /home/brad/.openclaw/workspace/operations/crypto-bot
   python3 sentiment_scheduler.py
   # Expect: sentiment_log.jsonl + entries in sentiment_schedule table
   ```

2. **Cache Behavior:**
   - Run sentiment_scheduler.py twice within 1 hour
   - Second run should use cache (cached: true in output)
   - Third run after 1h should fetch fresh (cached: false)

3. **Database:**
   ```bash
   sqlite3 phase4_trades.db "SELECT * FROM sentiment_schedule ORDER BY created_at DESC LIMIT 5;"
   ```

4. **Phase 4b Integration:**
   - Verify phase4b_v1.py fetches latest sentiment correctly
   - Verify entry signals are modulated by sentiment
   - Verify trades table populated with sentiment_score columns

---

## Next Steps

1. Apply x_sentiment_fetcher.py patch (add cache_hours)
2. Run schema update: `sqlite3 phase4_trades.db < SCHEMA_UPDATE_SENTIMENT.sql`
3. Create phase4b_v1.py with sentiment integration
4. Update PHASE4B_X_SENTIMENT_SPECIFICATION.md with 1h cadence note
5. Test sentiment_scheduler.py via cron
6. Commit all changes to GitHub with references to this checklist

---

**Last Updated:** 2026-03-29 21:50 PT  
**Owner:** Brad + AI  
**Spec Link:** PHASE4B_X_SENTIMENT_SPECIFICATION.md
