# Crypto Trading Bot — Phase 1: Credentials Setup

**Target:** Get API credentials for X (Twitter) and Coinbase Pro  
**Timeline:** ~30 minutes total  
**Status:** Ready for Brad to execute

---

## Task 1: X (Twitter) Developer API Setup — 10 minutes

### What You're Getting
- Bearer Token (read-only access to tweets)
- No writing, no moderation powers — sentiment scraping ONLY

### Steps

1. **Go to X Developer Portal**
   - URL: https://developer.twitter.com/en/portal/dashboard
   - Sign in with your Twitter account

2. **Create/Access Project**
   - Click "Create project" (or use existing)
   - Project name: `CryptoTradingBot` (or your choice)
   - Use case: `Academic research & data analysis` (honest choice)

3. **Create App**
   - Within your project, click "Create an app"
   - App name: `CryptoTradingBot`
   - Click "Create"

4. **Get Bearer Token**
   - Go to app settings → "Keys and tokens"
   - Under "Authentication Tokens and Keys":
     - Click "Generate" next to "Bearer Token"
     - **COPY THIS** (you won't see it again)
     - **DO NOT share or commit to git**

5. **Set Permissions**
   - App permissions: `Read` only (no write needed)
   - Save

### Save This
```
X_BEARER_TOKEN=xxxxxxxxxxxxxx...
```
(You'll paste it into `.env` in a moment)

---

## Task 2: Coinbase Advanced Trade API Setup — 15 minutes

### What You're Getting
- **Key ID** (your API key identifier, UUID format)
- **Private Key** (cryptographic signing key, PEM format)
- Sandbox & Production keys (separate credentials)

### Why Advanced Trade API?
- Newer, more secure (uses OAuth + Ed25519 signatures instead of secrets)
- Better for automated trading
- Clearer documentation

### Steps

1. **Go to Coinbase Developer Dashboard**
   - URL: https://cdp.coinbase.com/access/api
   - Sign in with your Coinbase account

2. **Create API Key**
   - Click "Create API Key"
   - Or existing key: Click "Manage" → add new key

3. **Configure Key Permissions**
   - **API Name:** `CryptoTradingBot_Sandbox` (for sandbox first)
   - **Permissions:** Select these ONLY:
     - ✅ View account details
     - ✅ Trade (place/cancel orders)
     - ❌ DO NOT select Withdraw or Transfer
   - **Environment:** Choose "Sandbox" (for testing)

4. **Copy Your Credentials (appears ONCE)**
   - You'll see:
     - **Key ID** — Copy this
     - **Private Key** (PEM format) — Copy this **EXACTLY** (with newlines)
   - Click "Done"

5. **Save This**
```
COINBASE_API_KEY_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
COINBASE_PRIVATE_KEY=-----BEGIN EC PRIVATE KEY-----
MHcCAQEEIIGlh/C...
(full PEM key, multiple lines)
-----END EC PRIVATE KEY-----
COINBASE_SANDBOX=true
```

**Important:** The Private Key is a multi-line PEM string. Keep it as-is with newlines intact.

6. **For Live Trading (Phase 4)**
   - Repeat steps 2-5 but:
     - **Environment:** Choose "Production"
     - **API Name:** `CryptoTradingBot_Production`
   - Keep separate from sandbox keys
   - **Only switch to production after Phase 3 security audit**

7. **Optional: Organization ID**
   - If you have multiple organizations, your Organization ID appears in the dashboard
   - Add to `.env` if needed:
   ```
   COINBASE_ORGANIZATION_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```

---

## Security Rules (IMPORTANT)

❌ **NEVER**
- Commit `.env` to git
- Share API keys in messages/emails
- Use production keys before security audit

✅ **DO**
- Store in `.env` (git-ignored)
- Use Sandbox first (paper trading)
- Rotate keys quarterly
- Restrict IP access (Coinbase Pro → API → IP Whitelist)

---

## What's Next

Once you have both credentials:
1. **Reply with:** "Credentials ready"
2. I'll provide `.env` template
3. You paste your keys in
4. We move to Phase 2 (code architecture)

**Time check:** ~30 min total. Let me know when you're done! 👍
