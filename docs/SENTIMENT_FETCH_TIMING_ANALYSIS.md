# Sentiment Fetch Timing Analysis

**Question:** When is the X API request initiated? I would think it would be upon initiation of the trading bot code.

**Short Answer:** The X API request is NOT automatically triggered by the trading bot itself. It's designed to run on a fixed **1-hour schedule** via the separate `sentiment_scheduler.py` script, which must be run independently (via cron, systemd timer, or manual invocation).

---

## The Actual Architecture

### Two Separate Processes

**1. Trading Bot (`phase4b_v1.py`)**
- Runs in a continuous loop (5-minute cycles)
- **Pulls** sentiment from the `sentiment_schedule` database table
- Does NOT fetch from X API — it only reads what's already in the DB
- Falls back to neutral (0.0) if the table is empty
- Caches sentiment locally for 1 hour to avoid repeated DB hits

**2. Sentiment Scheduler (`sentiment_scheduler.py`)**
- Runs independently (designed for cron every 1 hour)
- **Pushes** fresh sentiment data to the `sentiment_schedule` table
- Calls the X API via `XSentimentFetcher.get_sentiment(pair)`
- Logs all fetches to `sentiment_log.jsonl` for audit trail

### Why This Design?

**Benefits:**
- Decoupling: Trading logic doesn't depend on API availability
- Cost efficiency: X API called once per hour (16 times in 48h), not every 5 min (576 times)
- Graceful degradation: Bot continues trading with UTC-hour fallback sentiment if scheduler is down
- Flexibility: Can adjust fetch frequency independently of cycle interval

### The Problem Right Now

**Your bot is running, but the sentiment scheduler is NOT running.** So:
- ✅ Trading cycles execute every 5 minutes
- ✅ Cycles pull from the `sentiment_schedule` table
- ❌ The table is empty (no data was pushed there)
- ✅ Bot gracefully falls back to neutral (0.0) and continues trading

---

## Code Walkthrough

### Phase 4b Bot Startup (`phase4b_v1.py`)

```python
def main():
    orchestrator = Phase4bOrchestrator(phase4_winner_strategy='fee_aware')
    orchestrator.run_48h()  # Start the 48-hour loop

if __name__ == '__main__':
    main()
```

**What happens:**
1. Creates orchestrator
2. Enters `run_48h()` loop (576 cycles × 5 minutes)
3. Each cycle calls `run_cycle()`
4. Each cycle calls `_get_latest_sentiment(pair)` to read from DB
5. **No X API call is made here**

### Sentiment Fetch During Each Cycle

```python
def run_cycle(self):
    """Execute one trading cycle (5 minutes)"""
    
    for pair in ['BTC-USD', 'XRP-USD']:
        # This reads from the database, doesn't fetch from X API
        sentiment_score, sentiment_meta = self._get_latest_sentiment(pair)
        
        # sentiment_meta will be:
        # - Empty dict with 'source': 'No_data' if table is empty ← THIS IS YOUR CASE
        # - Or real data if sentiment_schedule table has rows
```

### The Actual Sentiment Fetch (Separate Script)

```python
# sentiment_scheduler.py
def main():
    scheduler = SentimentScheduler('.')
    results = scheduler.fetch_all_pairs()  # ← THIS IS WHERE X API IS CALLED

scheduler.fetch_all_pairs():
    for pair in ['BTC-USD', 'XRP-USD']:
        # THIS IS THE X API CALL
        sentiment, metadata = self.fetcher.get_sentiment(pair, force_refresh=False)
        
        # Store in DB for trading bot to read later
        self._store_sentiment_in_db(pair, sentiment, metadata)
```

**Key point:** The trading bot NEVER calls `fetcher.get_sentiment()` directly. It only calls `scheduler.get_latest_sentiment()`, which reads from the database.

---

## Timeline: What Should Happen vs What IS Happening

### What SHOULD Happen (Designed Architecture)

```
T=00:00  → Start sentiment_scheduler (cron job 1)
          → Fetch BTC + XRP sentiment from X API
          → Store in sentiment_schedule table

T=05:00  → Trading bot cycle 1: reads BTC=+0.15, XRP=-0.05 from table ✅

T=05:05  → Trading bot cycle 2: reads BTC=+0.15, XRP=-0.05 (1-hour cache, no new fetch)

T=05:10  → Trading bot cycle 3: same...

...

T=60:00  → Start sentiment_scheduler (cron job 2)
          → Fetch BTC + XRP sentiment again
          → Update sentiment_schedule table

T=60:05  → Trading bot cycles now read NEW sentiment values ✅
```

### What IS Actually Happening (Right Now)

```
T=09:07  → You start phase4b_v1.py manually
          → Bot enters run_48h() loop
          → Bot tries to read from sentiment_schedule table
          → Table is EMPTY ← Nothing ever wrote to it
          → Bot falls back to neutral (0.0) ✅ GRACEFULLY

T=09:12  → Bot cycle 2: still reads empty table, uses 0.0

...

T=10:52  → (RIGHT NOW) Bot still running
          → sentiment_schedule table still empty
          → All cycles using 0.0 fallback sentiment ← YOUR OBSERVATION

```

**Why? Because no one started the sentiment scheduler.**

---

## How to FIX THIS: Start the Sentiment Scheduler

### Option 1: Manual One-Shot (Test Now)

```bash
cd /home/brad/.openclaw/workspace/operations/crypto-bot
python3 sentiment_scheduler.py
```

**Output:**
```
============================================================
🔄 SENTIMENT SCHEDULER RUN
Timestamp: 2026-03-30T18:52:00+00:00
============================================================

📊 Fetching sentiment for BTC-USD...
✅ BTC-USD: +0.156 (X API)

📊 Fetching sentiment for XRP-USD...
✅ XRP-USD: -0.042 (X API)

============================================================
✅ SCHEDULER RUN COMPLETE
============================================================
```

**Next cycle of the trading bot will then read real sentiment instead of 0.0.**

### Option 2: Automated (Production)

**Setup cron to run every 1 hour:**

```bash
# Edit crontab
crontab -e

# Add this line:
0 * * * * cd /home/brad/.openclaw/workspace/operations/crypto-bot && python3 sentiment_scheduler.py >> sentiment_scheduler.cron.log 2>&1
```

**This ensures sentiment data is refreshed automatically every hour throughout the 48-hour test.**

### Option 3: Spawn as Background Sub-Agent (My Recommendation)

```bash
# Start scheduler as a long-running background process
nohup python3 /home/brad/.openclaw/workspace/operations/crypto-bot/sentiment_scheduler.py &
```

Then modify the scheduler to run every 1 hour in a loop:

```python
# Wrap main() in a while True loop
import time

if __name__ == '__main__':
    while True:
        try:
            scheduler = SentimentScheduler('.')
            results = scheduler.fetch_all_pairs()
            print(f"Fetched sentiment at {datetime.now()}")
            time.sleep(3600)  # Sleep 1 hour between fetches
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            time.sleep(60)  # Retry after 1 minute on error
```

---

## Verification: Check What's Currently in the DB

```bash
cd /home/brad/.openclaw/workspace/operations/crypto-bot

# See if sentiment_schedule table has any data
sqlite3 phase4_trades.db "SELECT pair, sentiment_score, created_at FROM sentiment_schedule ORDER BY created_at DESC LIMIT 5;"

# Should return empty OR
# BTC-USD | 0.156 | 2026-03-30 18:52:00
```

---

## Summary: Answer to Your Question

**"When is the X API request initiated? I would think it upon initiation of the trading bot code."**

**Actual:** The X API request is NEVER initiated by the trading bot. It's a separate process.

**Design:**
- Trading bot calls `_get_latest_sentiment()` which reads from the database
- Sentiment scheduler (separate process) calls X API and writes to database
- Trading bot continues with fallback (0.0) if database is empty

**Why this design:** Decoupling trading from external API availability, cost efficiency (fetch once per hour, not per cycle).

**What to do now:** Run `python3 sentiment_scheduler.py` once to populate the table, or set up cron to run it every hour.

**Expected impact:** Next cycle will show real sentiment instead of neutral, and entry thresholds will be modulated accordingly.
