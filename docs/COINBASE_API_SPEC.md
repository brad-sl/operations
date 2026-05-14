# Coinbase Advanced Trade API Specification

## Authentication Requirements

**Coinbase Advanced Trade API requires ONLY 2 credentials:**

1. **API Key** (`COINBASE_API_KEY`)
   - Format: `organizations/{org_id}/apiKeys/{key_id}`
   - Example: `organizations/281f24b2-9337-46cf-a107-29d6786cca02/apiKeys/c5604687-444f-4d33-ab2a-9563e449991a`

2. **Private Key** (`COINBASE_API_SECRET`)
   - Format: Ed25519 EC private key (PEM format)
   - Example:
     ```
     -----BEGIN EC PRIVATE KEY-----
     MHcCAQEEIAIFyDLizGQcv+Th+YVmRpscMvMUzPSLl9v0NKMhkpJYoAoGCCqGSM49
     AwEHoUQDQgAEGZ9C9LuhEpvLZe79JhDEibzmELoF4VktN8UrZKDtQzZCvHxp8Khm
     wg51ABEvR4aYFzkWjCmAhDWB19PBv8bF7A==
     -----END EC PRIVATE KEY-----
     ```

## Important Notes

- **NO passphrase required** (that's legacy Coinbase Pro API)
- **NO OAuth tokens** (use private key authentication)
- Authentication: **ES256 signature** over timestamp + HTTP method + path + body
- Base URL (Live): `https://api.coinbase.com`
- Base URL (Sandbox): `https://api-sandbox.coinbase.com`

## .env Configuration

```bash
# Coinbase Advanced Trade API Credentials
COINBASE_API_KEY=organizations/{org_id}/apiKeys/{key_id}
COINBASE_API_SECRET="-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----\n"
```

**That's it. Two fields only.**

## Coinbase API Ecosystem

### 1. Advanced Trade API (v3) — What We Use
- **Purpose:** Retail trading on order book (BTC-USD, ETH-USD, etc.)
- **Auth:** ES256 JWT (ECDSA P-256)
- **Base URL:** https://api.coinbase.com
- **Docs:** https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/
- **Features:** Market orders, limit orders, order management
- **Phase:** 5.1 (current)

### 2. Trade API (Onchain) — Swaps via DeFi ✅ FOR PHASE 6
- **Purpose:** Token swaps on Ethereum, Base, Arbitrum, Optimism, Polygon
- **Auth:** ES256 JWT (same as Advanced Trade)
- **Base URL:** https://api.coinbase.com (same gateway)
- **Docs:** https://docs.cdp.coinbase.com/trade-api/welcome
- **Features:** DEX swaps, arbitrage, market making, slippage protection
- **Use case:** Phase 6 rebalancing (tax-efficient crypto↔crypto swaps)
- **Benefit:** Better tax treatment than sell/buy (single event vs. two taxable events)

### 3. Conversions API (v2) — Stablecoin Conversions
- **Purpose:** USD ↔ USDC, EUR ↔ EURC, etc. (stablecoins only)
- **Auth:** Legacy v2 (OAuth)
- **Docs:** https://docs.cdp.coinbase.com/api-reference/v2/
- **Limitation:** No crypto-to-crypto conversions

## Key Reference Links

- **Advanced Trade API:** https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/
- **Trade API (Swaps):** https://docs.cdp.coinbase.com/trade-api/welcome ✅ **Bookmark this for Phase 6**
- **Conversions API:** https://docs.cdp.coinbase.com/api-reference/v2/

## JWT Authentication (ES256)

```python
import jwt
from cryptography.hazmat.primitives import serialization
import time
import secrets

api_key = "organizations/{org_id}/apiKeys/{key_id}"
private_key_str = "-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----\n"
method = "GET"
path = "/api/v3/brokerage/accounts"
host = "api.coinbase.com"

private_key = serialization.load_pem_private_key(
    private_key_str.encode('utf-8'),
    password=None
)

uri = f"{method} {host}{path}"
now = int(time.time())

jwt_payload = {
    'sub': api_key,
    'iss': 'cdp',
    'nbf': now,
    'exp': now + 120,
    'uri': uri,
}

jwt_token = jwt.encode(
    jwt_payload,
    private_key,
    algorithm='ES256',
    headers={'kid': api_key, 'nonce': secrets.token_hex(16)}
)

# Use as: Authorization: Bearer {jwt_token}
```

---

**Updated:** 2026-04-20 14:50 PT
**Status:** VERIFIED + TRADE API (SWAPS) ADDED
