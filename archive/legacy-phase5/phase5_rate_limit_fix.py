"""
Rate Limit Fix for Phase 5

Problem: 7 processes calling batch simultaneously triggers 429s
Solution: Add exponential backoff + no individual fallback

This patch should be integrated into phase5_multi_pair.py _fetch_all_pairs_batch() method

Quick fix: Replace the exception handler with this:

```python
except Exception as e:
    attempt += 1
    if '429' in str(e) and attempt < 3:
        # Rate limited: exponential backoff + jitter (1s, 2s, 4s)
        wait_time = (2 ** attempt) + uniform(0, 1)
        self.logger.warning(f"Rate limited (429). Retry {attempt}/3 in {wait_time:.1f}s")
        time.sleep(wait_time)
    else:
        # Other error or max retries: skip chunk (don't fallback to individual)
        self.logger.error(f"Batch {chunk_idx} failed: {e}")
        break
```

Root cause: Individual pair fetches trigger immediate 429 when batch is already rate-limited.
Better solution: Use Phase5 Scalable (1 process, no redundancy, no rate limits).
"""

# Workaround: Add staggered sleep between processes
# Each process sleeps N seconds based on its own PID/supervisor timing
import os
import time
from random import uniform

def add_startup_stagger():
    """Stagger process startup to avoid thundering herd on Coinbase API"""
    stagger = uniform(0, 5)  # Random 0-5 second stagger
    print(f"Process startup stagger: {stagger:.1f}s")
    time.sleep(stagger)

# Call this at the start of Phase5Harness.run()
