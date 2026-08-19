# Trader Registry ERD (T0-01)

```mermaid
erDiagram
    TRADERS ||--o| TRADER_CONFIGS : has
    TRADERS ||--o| OAUTH_TOKENS : has
    TRADERS ||--o{ JOB_RUNS : "executes"

    TRADERS {
        uuid id PK
        string ghl_contact_id UK
        string ghl_location_id
        string portfolio_uuid UK
        string coinbase_account_id UK
        string tier "starter|pro|elite"
        string billing_status
        string coinbase_status "disconnected|connected|..."
        string auth_mode "oauth|api_key"
        datetime created_at
        datetime updated_at
        datetime last_cycle_at
        json flags
        text notes
    }

    TRADER_CONFIGS {
        uuid id PK
        uuid trader_id FK UK
        json pairs
        json risk_params
        json allocation_overrides
        string rebalance_frequency
        float max_deploy_usd
        int pair_count_cap
        json tier_template_snapshot
        json overrides
        datetime created_at
        datetime updated_at
    }

    OAUTH_TOKENS {
        uuid id PK
        uuid trader_id FK UK
        text access_token_enc
        text refresh_token_enc
        datetime expires_at
        json scopes
        string portfolio_uuid
        datetime created_at
        datetime updated_at
    }

    JOB_RUNS {
        uuid id PK
        uuid trader_id FK
        string run_id
        datetime started_at
        datetime ended_at
        string status "pending|running|success|failed"
        json metrics
        text error_summary
        float duration_seconds
    }
```

**Notes:**
- Isolation: queries always filter on traders.id or portfolio_uuid
- Encryption: oauth_tokens.*_enc columns only (see db/models.py encrypt/decrypt)
- GHL: mirrors subset of fields (rounded) in TradingAccount custom object. No secrets.
- Future: trade_alerts, shared_intel_cache possible extensions.
- Alembic 002 creates these tables (Postgres JSONB in mig, JSON portable in ORM)

**Usage in T0:**
See test_t0_registry.py for insert 2 accounts + query validation.
