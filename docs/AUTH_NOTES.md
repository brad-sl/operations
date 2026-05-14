# Coinbase Advanced Trade API Authentication (ECDSA JWT)

## Decision Log (2026-04-18)
- **Migration**: Coinbase Pro API (deprecated, returning 503s) → Advanced Trade API v3
- **Auth**: ECDSA P256 JWT signing (replaces HMAC)
- **Keys**: EC private key format (-----BEGIN EC PRIVATE KEY-----) in .env
- **Status**: Code updated, SDK ready (coinbase_advanced_client.py), Phase 5 integration pending

## Key Format
```
API_KEY=3bNyoPw4dHIF3c47az0CmpjQYARfSSDb
API_SECRET=-----BEGIN EC PRIVATE KEY-----
MHcCAQEEIGyhHGK7nW1REs6UUdwZ2ROFeOTgWZfFlo+yfdCRk9R7oAoGCCqGSM49
AwEHoUQDQgAEHcl8tLNKgxdgwK0VFTVlzoE995dHe3rUJfO1IB6FbHVnrOQ065KV
hT7tTgGCRGAi2DEzD3zsNavrZVB4AEIxTQ==
-----END EC PRIVATE KEY-----
```

**IMPORTANT**: EC private key MUST be P256 (NOT Ed25519). Multiline in .env requires quotes or \n escaping.

## SDK Integration
- **Library**: coinbase-advanced-py (pip install)
- **Client**: RESTClient(api_key=..., api_secret=...)
- **Auth**: Automatic JWT signing (ES256, no passphrase)
- **Endpoints**: /accounts, /products, /orders (v3 REST)

## Phase 5 Integration Path
1. Replace PublicExchangePriceWrapper with CoinbaseAdvancedClient
2. Update price_fetch() to use client.get_product(product_id)
3. Update trade_execute() to use client.create_order()
4. Test with --test-mode (small trade sizes)
5. Deploy live (sandbox=False requires real API credentials)

## References
- Coinbase Docs: https://docs.cdp.coinbase.com/advanced-trade/docs/welcome
- JWT Signing: ES256 (ECDSA P256)
- Error Handling: 503s (transient) → retry + fallback to CoinGecko

## Future: Phase 6
Phase 6 will extend Phase 5 with multi-pair sentiment + correlation analysis + dynamic rebalancing.
Same auth mechanism, scaled to 12+ pairs, $1K per pair.
