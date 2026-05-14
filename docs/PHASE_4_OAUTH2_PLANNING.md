# Phase 4: Coinbase Business API OAuth2 Integration

**Status:** 📋 PLANNING (Post-Phase 3)  
**Timestamp:** 2026-03-25 21:57 PDT  
**Context:** Multi-account trading platform requires OAuth2 delegation

---

## Requirements

### Current State (Phase 3)
- **Auth Method:** Direct API Key + Secret (single account)
- **Scope:** Self-managed account only
- **Module:** `coinbase_wrapper.py` (Module 4)
- **Security:** Keys stored in `.env` file

### Phase 4 Goal
- **Auth Method:** OAuth2 (delegated permissions)
- **Scope:** Manage multiple user accounts via bot
- **Multi-tenancy:** One bot instance, many trading accounts
- **Security:** Token vault with refresh handling

---

## API Reference

**Coinbase Business API Documentation:**
- URL: https://docs.cdp.coinbase.com/coinbase-business/introduction/welcome
- OAuth2 Standard: RFC 6749 (Auth Code Flow)
- Scope: `trading:manage` (or appropriate business scopes)
- Token Endpoint: Coinbase Business API v1

---

## Implementation Plan (Phase 4)

### New Module: `coinbase_business_auth.py`

```python
class CoinbaseBusinessAuth:
    """OAuth2 handler for Coinbase Business API"""
    
    def __init__(self, client_id, client_secret, redirect_uri):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
    
    async def initiate_flow(self, user_id):
        """Generate auth URL for user consent"""
        pass
    
    async def exchange_code(self, auth_code):
        """Exchange auth code for access + refresh tokens"""
        pass
    
    async def refresh_token(self, refresh_token):
        """Automatically refresh expired access tokens"""
        pass
    
    async def get_user_accounts(self, access_token):
        """List all trading accounts user has authorized"""
        pass
```

### Integration Points

1. **Extended `coinbase_wrapper.py`**
   - Constructor: Accept OAuth2 token (vs API key)
   - Token refresh: Automatic on 401 responses
   - Multi-account support: Dynamic account selection

2. **New `token_vault.py`**
   - Store refresh tokens securely (encrypted at rest)
   - Automatic expiry tracking
   - Token rotation logging

3. **Updated `order_executor.py` (Module 6)**
   - Per-user account context
   - Rate limiting per account
   - Audit trail: who (which user) did what (which account)

---

## Security Considerations

**Token Storage:**
- ❌ Plain-text environment variables
- ✅ Encrypted vault (AES-256)
- ✅ Key derivation from master secret

**Token Lifecycle:**
- Automatic refresh 5 minutes before expiry
- Audit log: all token operations
- Revocation: user can disconnect account instantly

**Scopes (Least Privilege):**
- `trading:manage` (only if needed for live trading)
- `accounts:list` (read-only account enumeration)
- No admin/account-creation scopes

---

## Phase 4 Deployment Timeline

| Task | Estimate | Dependencies |
|------|----------|--------------|
| OAuth2 auth handler | 2-3 hours | None (Phase 3 complete) |
| Token vault | 1-2 hours | OAuth2 handler |
| Coinbase wrapper extension | 1-2 hours | OAuth2 + token vault |
| Order executor multi-account | 1-2 hours | Wrapper extension |
| Integration tests | 2-3 hours | All modules |
| Security audit | 1-2 hours | Full integration |
| **Total** | **8-14 hours** | Sequential |

---

## Next Steps (When Phase 4 Begins)

1. Register bot application at Coinbase Business Developer Portal
2. Obtain client_id + client_secret
3. Set redirect_uri (localhost:8000/oauth/callback for dev, production URL for live)
4. Build OAuth2 auth handler + token vault
5. Extend existing modules with multi-account support
6. Deploy to staging environment
7. Security audit + pen test
8. Production rollout

---

## Reference Documents

- **Coinbase Business API Docs:** https://docs.cdp.coinbase.com/coinbase-business/introduction/welcome
- **OAuth2 RFC:** https://tools.ietf.org/html/rfc6749
- **Phase 3 Complete:** `/operations/crypto-bot/PHASE_2_FINAL_REPORT.md`
- **Phase 3 Paper Trading:** Phase 3 runs until 2026-03-25 23:49 UTC

---

**Status:** Planning document created for Phase 4 OAuth2 integration  
**Decision Owner:** Brad Slusher  
**Approval Required:** Before Phase 4 development begins
