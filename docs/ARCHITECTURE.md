# Phase 5/6 Trading Bot – Architecture & Configuration

> **LEGACY — not SSOT (banner 2026-08-13).**  
> Paths under `~/.openclaw/workspace/operations/crypto-bot/` and Phase 5 pair lists are **historical**.  
> Current repo: `/home/brad/projects/crypto-trading-bot`. Config: `config/trading_config_phase6.json`. Index: `docs/SPECS_INDEX.md`.

## Overview

The trading bot is **fully configurable** – pairs, capital, risk parameters are loaded from JSON config files, not hardcoded.

### Key Design Principle
- **No hardcoding**: All operational parameters external (config files)
- **Dynamic scaling**: Add/remove pairs by editing JSON
- **Reloadable**: Config changes require bot restart only (fast)
- **Phase separation**: Distinct configs for Phase 5 (paper) vs Phase 6 (live multi-pair)

---

## Configuration Architecture

### File Structure
```
/home/brad/.openclaw/workspace/operations/crypto-bot/config/
├── trading_config_phase5.json      # Phase 5: Paper trading (6 pairs, $1K capital)
├── trading_config_phase6.json      # Phase 6: Live trading (12+ pairs, $1K+ capital)
├── sentiment_config.json           # Sentiment sources + weights
└── settings.py                     # Python constants (fallback)
```

### Config Loading Flow
```
Phase5Harness.__init__()
  ↓
config_path = /config/trading_config_phase5.json
  ↓
_load_config() → Parse JSON
  ↓
self.config.get('global_settings', {}).get('pairs', [])
  ↓
self.pairs = ["BTC-USD", "XRP-USD", "ETH-USD", ...]
```

---

## Phase 5 Configuration (Current)

**File**: `config/trading_config_phase5.json`

```json
{
    "global_settings": {
        "total_capital": 1000,
        "pairs": ["BTC-USD", "XRP-USD", "ETH-USD", "DOGE-USD", "ADA-USD", "SOL-USD"],
        "cycle_interval_seconds": 1800
    },
    "risk_management": {
        "max_daily_loss_pct": 2.0,
        "var_threshold": 0.015,
        "stop_loss_pct": 2.0,
        "take_profit_pct": 5.0
    },
    "sentiment": {
        "sources": ["x_api", "reddit", "news_api"],
        "weight": 0.4
    },
    "phase_5_specific": {
        "entry_conditions": {
            "rsi_periods": [14, 21],
            "sentiment_threshold": 0.3,
            "volatility_filter": true
        }
    }
}
```

### Current Pairs (6)
| Pair | Rationale | Correlation |
|------|-----------|-------------|
| BTC-USD | Anchor, highest volume | - |
| XRP-USD | Low correlation | <0.3 |
| ETH-USD | Smart contract base | - |
| DOGE-USD | Low correlation, sentiment | <0.3 |
| ADA-USD | Low correlation | <0.3 |
| SOL-USD | Alternative L1 | <0.3 |

### Batch Fetching for Phase 5
- **Requests per cycle**: 1 batch call (all 6 pairs in one API request)
- **API efficiency**: 6x faster than individual calls
- **Rate limit risk**: Minimal (well within Coinbase limits)

---

## Phase 6 Configuration (Template)

**File**: `config/trading_config_phase6.json`

**Expansion Rules**:
- Add up to 12 pairs (2x Phase 5)
- Correlation <0.3 (low interdependence)
- Capital allocation: $1K per pair minimum ($12K total suggested)
- Weekly rebalance cycle (vs 300s Phase 5 cycles)

### Phase 6 Expanded Config Template

```json
{
    "global_settings": {
        "total_capital": 12000,
        "pairs": [
            "BTC-USD", "XRP-USD", "ETH-USD", "DOGE-USD", "ADA-USD", "SOL-USD",
            "LINK-USD", "MATIC-USD", "AVAX-USD", "ARB-USD", "OP-USD", "UNI-USD"
        ],
        "cycle_interval_seconds": 604800
    },
    "risk_management": {
        "max_daily_loss_pct": 1.0,
        "var_threshold": 0.01,
        "stop_loss_pct": 3.0,
        "take_profit_pct": 8.0,
        "rebalance_frequency_days": 7
    },
    "sentiment": {
        "sources": ["x_api", "reddit", "news_api"],
        "weight": 0.5,
        "cache_ttl_minutes": 60
    },
    "phase_6_specific": {
        "expansion_rules": {
            "max_pairs": 12,
            "correlation_threshold": 0.3,
            "min_capital_per_pair": 1000,
            "reserve_min_pct": 0.2
        },
        "multi_client_strategy": {
            "client_count": 3,
            "pairs_per_client": 4,
            "load_balancing": "round_robin"
        },
        "rebalance_strategy": {
            "type": "weekly",
            "target_allocation": "equal_weight",
            "volatility_adjustment": true
        }
    }
}
```

### Recommended Phase 6 Pairs (12)

**Tier 1 (Core, Low Correlation)**:
1. BTC-USD – Bitcoin (anchor, highest volume)
2. XRP-USD – Ripple (payment, low corr)
3. DOGE-USD – Dogecoin (meme, low corr)
4. ADA-USD – Cardano (L1, low corr)

**Tier 2 (Secondary, Emerging)**:
5. ETH-USD – Ethereum (smart contracts)
6. SOL-USD – Solana (L1 alternative)
7. AVAX-USD – Avalanche (L1 alt)

**Tier 3 (DeFi/Infra)**:
8. LINK-USD – Chainlink (oracles)
9. UNI-USD – Uniswap (DEX)
10. AAVE-USD – Aave (lending) **[Alternative]**

**Tier 4 (L2/Emerging)**:
11. ARB-USD – Arbitrum (L2 scaling)
12. OP-USD – Optimism (L2 scaling)

**Alternatives** (if correlation >0.3):
- MATIC-USD (Polygon, often corr with ETH)
- ICP-USD (Internet Computer, lower volume)
- NEAR-USD (Near Protocol)

---

## Scaling Path

### From Phase 5 → Phase 6

**Step 1: Prepare Config**
```bash
cp config/trading_config_phase5.json config/trading_config_phase6_working.json
# Edit: Add 6 new pairs (LINK, MATIC, AVAX, ARB, OP, UNI)
# Edit: Increase total_capital to 12000 ($1K per pair)
# Edit: Change cycle_interval to 604800 (weekly rebalance)
# Edit: Adjust risk_management thresholds (tighter stops)
```

**Step 2: Point Bot to Phase 6 Config**
```python
# In phase5_multi_pair.py, change:
config_path='config/trading_config_phase6.json'
# OR pass as argument:
python3 phase5_multi_pair.py --config config/trading_config_phase6.json
```

**Step 3: Batch Fetch Auto-Handles Scaling**
- 6 pairs: 1 batch request (current)
- 12 pairs: 1 batch request (still under MAX_BATCH_SIZE=20)
- 50 pairs: 3 batch requests (auto-chunking)

---

## Batch Fetching Strategy

### Current Phase 5
- **Pairs**: 6
- **Batch size**: 6 (1 request per cycle)
- **Request overhead**: ~200ms
- **Efficiency**: 6x vs individual calls

### Phase 6 Scaling
- **Pairs**: 12
- **Batch size**: 12 (1 request per cycle)
- **Efficiency**: 12x improvement

### Future Scaling (>20 pairs)
- **Example**: 50 pairs
- **Chunks**: [1-20] → [21-40] → [41-50]
- **Requests**: 3 per cycle
- **Efficiency**: Still 16x+ better than individual calls

**Code handles automatically** (see `_fetch_all_pairs_batch()` with MAX_BATCH_SIZE=20)

---

## Configuration Parameters Reference

### global_settings
| Param | Type | Phase 5 | Phase 6 | Usage |
|-------|------|--------|--------|-------|
| total_capital | int | 1000 | 12000 | Total $ to allocate |
| pairs | array | 6 items | 12 items | Trading pairs |
| cycle_interval_seconds | int | 1800 | 604800 | Cycle frequency (300s = 5min paper, 604800 = 1 week live) |

### risk_management
| Param | Type | Phase 5 | Phase 6 | Usage |
|-------|------|--------|--------|-------|
| max_daily_loss_pct | float | 2.0 | 1.0 | Circuit breaker % loss |
| stop_loss_pct | float | 2.0 | 3.0 | Hard stop-loss per trade |
| take_profit_pct | float | 5.0 | 8.0 | Hard take-profit per trade |
| rebalance_frequency_days | int | - | 7 | Weekly rebalance (Phase 6 only) |

### sentiment
| Param | Type | Phase 5 | Phase 6 | Usage |
|-------|------|--------|--------|-------|
| sources | array | X, Reddit, News | X, Reddit, News | Data sources |
| weight | float | 0.4 | 0.5 | Sentiment importance vs RSI |

### phase_6_specific (Phase 6 only)
- `multi_client_strategy`: Split pairs across clients for parallelism
- `rebalance_strategy`: Weekly equal-weight or vol-adjusted rebalancing
- `expansion_rules`: Max pairs (12), correlation threshold (0.3)

---

## Deployment Checklist

### Phase 5 → Phase 6 Transition
- [ ] Validate Phase 5: 50% win rate, Sharpe ≥0.9 (24h test)
- [ ] Create Phase 6 config (add 6 pairs)
- [ ] Backtest Phase 6 with 1-year data
- [ ] Expand sentiment cache (all 12 pairs)
- [ ] Allocate $12K capital (verify account balance)
- [ ] Update Prometheus dashboards (12 pairs)
- [ ] Deploy VPS (DigitalOcean: 4GB, 2vCPU, $24/mo)
- [ ] Enable systemd service (`phase5.service`)
- [ ] 48h Phase 6 paper test
- [ ] User approval: Real capital deployment
- [ ] Go live on Coinbase Advanced Trade API

---

## Code Integration

### Using Different Config
```python
# Default (Phase 5)
harness = Phase5Harness()  # Uses config/trading_config_phase5.json

# Custom (Phase 6)
harness = Phase5Harness(config_path='config/trading_config_phase6.json')

# Or via CLI
python3 phase5_multi_pair.py --config config/trading_config_phase6.json
```

### Accessing Pairs in Code
```python
# Pairs loaded from config
pairs = self.pairs  # ["BTC-USD", "XRP-USD", ...]

# Batch fetch auto-adapts
batch_prices = self._fetch_all_pairs_batch()  # 1 or N requests based on size
```

---

## Documents Reference
- **API Batch Limits**: See `API_BATCH_LIMITS.md`
- **Sentiment Setup**: See `sentiment_aggregator.py` + sentiment_config.json
- **Authentication**: See `AUTH_NOTES.md` (ECDSA JWT)
- **VPS Deployment**: See `VPS_MIGRATION_PLAYBOOK.md`
