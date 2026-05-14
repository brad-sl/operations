# 🚨 URGENT: Missing Apify Reddit Implementation

**Date Discovered:** 2026-04-22 14:52 PT  
**Status:** CODE MISSING, IMPLEMENTATION LOST  
**Owner:** Brad Slusher  

---

## What Happened

Brad mentions: **"This was written and implemented and tested thoroughly over the last 2 weeks."**

**Apify-based Reddit sentiment fetching** was built 2 weeks ago but is **NOT in current git**.

---

## Current State

### What's Missing
- ✅ Apify credentials exist: `APIFY_USER_ID`, `APIFY_API_TOKEN` (in .env)
- ❌ `fetch_reddit_sentiment.py` uses PRAW (old implementation)
- ❌ PRAW version looks for `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` (not configured)
- ❌ Reddit sentiment disabled as result

### Expected Behavior
- Reddit sentiment should fetch via Apify API actor
- Combined with X sentiment in aggregator
- Both sources weighted (X: 50%, Reddit: 50%)
- Half-life decay applied

### Current Behavior
- X sentiment: ✅ Working (BTC 0.04, XRP 0.09, etc.)
- Reddit sentiment: ❌ Disabled (returns empty)
- Aggregator: ✅ Handles gracefully (uses X 100% as fallback)

---

## Search Strategy

### 1. Check Remote Branches
```bash
git log origin/develop --oneline | grep -i "apify\|reddit"
git log origin/feature/crypto-bugfix-phase4 --oneline | grep -i "apify\|reddit"
git log origin/feature/CA-CRYPTO-BACKTEST-001 --oneline | grep -i "apify\|reddit"
```

### 2. Check for Stashed Work
```bash
git stash list
git log --all --grep="apify" --oneline
git log --all --grep="reddit" --oneline
```

### 3. Search Local Filesystem
```bash
find /home/brad -name "*apify*reddit*" -o -name "*reddit*apify*" 2>/dev/null
find /home/brad/Desktop -name "*.py" | xargs grep -l "ApifyClient" 2>/dev/null
```

### 4. Check Backup Locations
```bash
ls -la /backups/
ls -la ~/.local/share/Trash
find /tmp -name "*.py" -newer 2026-04-07
```

---

## What We Know

- Implementation: **Exists somewhere** (Brad knows how it works)
- Testing: **Done thoroughly** (2 weeks of work)
- Status: **Production ready** (tested)
- Location: **UNKNOWN** (not in git, not in current filesystem)

---

## Recovery Plan

### If Code Found
1. **Restore file** to `fetch_reddit_sentiment_apify.py`
2. **Test thoroughly** with Apify credentials
3. **Commit to git**: `git add fetch_reddit_sentiment_apify.py && git commit -m "..."`
4. **Document**: `APIFY_REDDIT_IMPLEMENTATION.md`
5. **Update sentiment_aggregator_v2.py** to call Apify version
6. **Add to TECHNICAL_DEBT.md**: Mark as recovered

### If Code Not Found
1. **Reconstruct from scratch** (Brad + AI pair programming)
2. **Use Apify API actor** for Reddit sentiment
3. **Test immediately**
4. **Commit + document**
5. **Add to git staging** so it never disappears again

---

## Why This Matters

**2 weeks of validated work** is at risk of being lost permanently.

This is **exactly the problem Brad asked to solve** with documentation and git hygiene:
> "I'm very tired of losing all the changes as we proceed and having to re-invent them later."

**Current Prevention:** TECHNICAL_DEBT.md will track this until recovered.

---

## Next Steps

1. **Search for the code NOW**
2. **Report findings** (found / not found)
3. **If found:** Restore, test, commit
4. **If not found:** Brad + I rebuild it (2h max)
5. **Commit to git + document forever**

---

**DO NOT LET THIS DISAPPEAR AGAIN.**

All subsequent work on Reddit sentiment MUST be:
1. In git (committed immediately)
2. In TECHNICAL_DEBT.md (tracked)
3. In a .md file (documented)

---

**Created:** 2026-04-22 14:52 PT  
**Status:** URGENT — Missing Work Alert  
**Action:** Search + Recover
