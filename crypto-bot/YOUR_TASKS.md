# Your Action Items — Brad's Crypto Trading Bot Tasks

**Start:** Now (Sunday Mar 22, 7:41 PM PT)  
**Deadline:** Whenever ready (no rush, ~30 min of actual work)  
**Status:** Awaiting your action

---

## 🚨 IMMEDIATE: Phase 1 Credential Setup

### Task 1: Get X (Twitter) Bearer Token
**Time:** ~5-10 min

**What to do:**
1. Open: https://developer.twitter.com/en/portal/dashboard
2. Follow the steps in `/operations/crypto-bot/PHASE_1_CREDENTIALS_SETUP.md` (Task 1)
3. **COPY** your Bearer Token (appears once, don't lose it)
4. **DO NOT SHARE** anywhere public

**Save this somewhere safe for now:**
```
X_BEARER_TOKEN=your_token_here
```

---

### Task 2: Get Coinbase Pro API Credentials
**Time:** ~10-15 min

**What to do:**
1. Go to: https://pro.coinbase.com (or https://app.coinbase.com if new UI)
2. Sign in / create account (if needed)
3. Follow the steps in `/operations/crypto-bot/PHASE_1_CREDENTIALS_SETUP.md` (Task 2)
4. **COPY all three:**
   - API Key
   - API Secret
   - Passphrase
5. **DO NOT SHARE** anywhere public

**Save this somewhere safe for now:**
```
COINBASE_API_KEY=your_key
COINBASE_API_SECRET=your_secret
COINBASE_API_PASSPHRASE=your_passphrase
```

---

### Task 3: Confirm $1K Starting Capital
**Time:** 30 seconds

**What to do:**
Reply with confirmation:
```
Credentials ready. $1K sandbox capital approved.
```

---

## 📋 When You're Done With Phase 1

**I will:**
1. Create `.env` file with your credentials (securely stored, git-ignored)
2. Implement Phase 2 (core trading logic)
3. Have you review the code structure

**Timeline for Phase 2:** 1-2 days

---

## 🗂️ Reference Files

All files are already created in `/home/brad/.openclaw/workspace/operations/crypto-bot/`:

- `PHASE_1_CREDENTIALS_SETUP.md` — Detailed instructions for both APIs
- `PROJECT_STRUCTURE.md` — Architecture overview
- `.env.example` — Template (safe to commit)
- `YOUR_TASKS.md` — This file

---

## ⚠️ Important Security Notes

### DO NOT
- ❌ Commit `.env` to git
- ❌ Share API keys in Telegram, email, or public chat
- ❌ Use production keys before Phase 3 security audit
- ❌ Run trades with real capital before Phase 4 sandbox test

### DO
- ✅ Use Sandbox API for everything until Phase 4
- ✅ Store `.env` locally on your HP 8000
- ✅ Rotate keys quarterly
- ✅ Review the security audit checklist before going live

---

## Next Communication

When ready:
1. Get both credentials
2. Send me: `Credentials ready`
3. I'll create `.env` and confirm setup
4. We move to Phase 2 (implementation)

**Questions?** Ask now before you start. Otherwise, go grab those API keys! 🔑

---

**Expected timing:**
- Phase 1: You complete (~30 min)
- Phase 2: Me + you review (~1-2 days)
- Phase 3: Security audit (~4 hrs)
- Phase 4: Sandbox trading + monitoring (~2 days)
- Phase 5: Production launch (after all audits pass)

You're in control of the pace. Let me know when ready! 👍
