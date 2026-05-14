# Scalability Analysis: Polling vs Push Notifications

**Question:** For multiple accounts/pairs, do we poll or use push? How many accounts per call?

**Answer:** Both exist. **WebSocket + Webhooks > Polling** for scalability. Here's the breakdown:

---

## Option 1: Polling (Current Approach)

### Method: REST API `/orders` Endpoint

**Current orchestrator:** Calls `GET /orders` every cycle to check status

```python
response = client.get_orders(product_id="BTC-USD", limit=100)
```

### Limitations

| Limit | Value | Impact |
|-------|-------|--------|
| **Rate limit** | 10,000 req/hour per API key | ~2.8 req/sec avg |
| **Per-call scope** | Single account only | 1 account = 1 call |
| **Response latency** | ~100-500ms | Polling adds delay |
| **Multiple accounts** | Need sequential calls | Account1, then Account2, then Account3... |

### Scalability Math

**If you want to monitor:**
- 10 accounts
- 2 pairs per account
- Every 5 minutes

```
Calls per cycle:     10 accounts × 1 call = 10 calls
Calls per hour:      10 × (60/5) = 120 calls
Calls per day:       120 × 24 = 2,880 calls
Daily quota usage:   2,880 / 10,000 = 28.8%
```

✅ **Verdict:** Polling works fine for <20 accounts

❌ **Problem:** 100+ accounts = polling becomes impractical

---

## Option 2: WebSocket (Real-Time Push)

### Method: Advanced Trade WebSocket `/user` Channel

**Coinbase Advanced Trade API supports WebSocket:**

```python
# Subscribe to user channel for order updates
ws.subscribe({
    "type": "subscribe",
    "product_ids": ["BTC-USD", "XRP-USD"],
    "channels": ["user"]
})

# Receive push notifications:
# {
#   "type": "done",
#   "order_id": "...",
#   "reason": "filled",
#   "side": "buy",
#   "price": 67523.50
# }
```

### Advantages

| Aspect | Benefit |
|--------|---------|
| **Real-time updates** | Instant order fills (not polled) |
| **One connection** | Single WebSocket handles all pairs for account |
| **Lower latency** | Push <10ms vs poll ~500ms |
| **Rate limits** | N/A (streaming doesn't count against quota) |
| **Multiple pairs** | Subscribe to BTC, ETH, XRP, SOL in one connection |
| **Scalability** | 100+ accounts = 100 WebSocket connections |

### Implementation

```python
import websocket
import json

class OrderTracker:
    def __init__(self, api_key, secret):
        self.ws = websocket.WebSocket()
        self.ws.connect("wss://advanced-trade-ws.coinbase.com")
        self.authenticate(api_key, secret)
    
    def authenticate(self, api_key, secret):
        # Ed25519 signing for Coinbase authentication
        auth_message = self.build_auth_message(api_key, secret)
        self.ws.send(json.dumps(auth_message))
    
    def subscribe_to_orders(self, product_ids):
        subscription = {
            "type": "subscribe",
            "product_ids": product_ids,
            "channels": ["user"]  # User channel = order updates
        }
        self.ws.send(json.dumps(subscription))
    
    def listen_for_fills(self):
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("type") == "done":
                # Order filled/cancelled
                self.on_order_fill(msg)
    
    def on_order_fill(self, fill_event):
        print(f"Order filled: {fill_event['order_id']} @ {fill_event['price']}")
        # Calculate P&L, log outcome event
```

---

## Option 3: Webhooks (Serverless Push)

### Method: Coinbase CDP Webhooks

**Coinbase can POST directly to your endpoint:**

```python
# Register webhook at: https://www.coinbase.com/developer-platform/discover/launches/introducing-webhooks

# Coinbase POSTs to your endpoint whenever an order fills:
POST https://yourdomain.com/webhooks/coinbase
{
    "type": "order_filled",
    "order_id": "...",
    "product_id": "BTC-USD",
    "filled_amount": 0.01,
    "filled_price": 67523.50,
    "timestamp": "2026-03-25T08:23:45Z"
}
```

### Advantages

| Aspect | Benefit |
|--------|---------|
| **No polling** | Events pushed directly |
| **Serverless friendly** | Lambda/Cloud Functions can process |
| **Multiple accounts** | Same endpoint handles all |
| **Lower infrastructure** | No need to maintain WebSocket connections |
| **Audit trail** | HTTP logs for all fills |

### Disadvantages

| Drawback |
|----------|
| Requires public HTTP endpoint (security concern) |
| Retry logic for failed deliveries (you handle) |
| Eventual consistency (not guaranteed order) |

---

## Option 4: Hybrid (Recommended for Scale)

**Combine WebSocket + Polling fallback:**

```
Primary:  WebSocket for real-time fills (instant)
Fallback: Poll every 5 min to catch missed messages
```

### Architecture

```
┌─────────────────────────────────────────┐
│ Crypto Bot (Phase 4 Multi-Account)      │
├─────────────────────────────────────────┤
│                                         │
│  WebSocket Pool                         │
│  ├─ Account A connection (BTC, ETH)    │
│  ├─ Account B connection (XRP, SOL)    │
│  └─ Account C connection (ADA)         │
│                                         │
│  Polling Fallback (every 5 min)        │
│  └─ Check all accounts for missed fills│
│                                         │
│  Order Tracker                          │
│  ├─ Real-time fills (from WS)          │
│  ├─ Missed fills (from poll)           │
│  └─ P&L calculation                    │
│                                         │
└─────────────────────────────────────────┘
```

---

## Scalability Comparison

### Single Account (Current Phase 3)

| Method | Calls/Hour | Cost | Latency | Feasibility |
|--------|-----------|------|---------|-------------|
| Polling (5-min) | 12 | $0 (included) | 500ms | ✅ Perfect |
| WebSocket | 0 | $0 (included) | 10ms | ✅ Overkill |

### 10 Accounts (Phase 4 Start)

| Method | Calls/Hour | Cost | Latency | Feasibility |
|--------|-----------|------|---------|-------------|
| Polling (5-min) | 120 | ~$0 (1.2% quota) | 500ms | ✅ Fine |
| WebSocket | 0 | $0 | 10ms | ✅ Optimal |
| Hybrid | 30 | ~$0 (0.3%) | 10-500ms | ✅ Best |

### 100 Accounts (Future Scale)

| Method | Calls/Hour | Cost | Latency | Feasibility |
|--------|-----------|------|---------|-------------|
| Polling (5-min) | 1,200 | ~$0 (12% quota) | 500ms | ⚠️ Tight |
| WebSocket | 0 | $0 | 10ms | ✅ Essential |
| Hybrid | 100 | ~$0 (1%) | 10-500ms | ✅ Scalable |

### 1,000 Accounts (Enterprise Scale)

| Method | Calls/Hour | Cost | Latency | Feasibility |
|--------|-----------|------|---------|-------------|
| Polling (5-min) | 12,000 | **Exceeds quota** | 500ms | ❌ Impossible |
| WebSocket | 0 | $0 | 10ms | ✅ Only option |
| Hybrid | 1,000 | ~$0 (10% quota) | 10-500ms | ✅ Production |

---

## Recommendation

### For Phase 4 (1-10 Accounts)
**Use WebSocket for each account**

```python
# Connect one WebSocket per trading account
accounts = ["account_1", "account_2", "account_3"]
websockets = {acc: create_ws_connection(acc) for acc in accounts}

# Each WS monitors multiple pairs
for ws in websockets.values():
    ws.subscribe(product_ids=["BTC-USD", "XRP-USD", "ETH-USD"])
```

**Why:**
- ✅ Instant order fill notifications
- ✅ No polling overhead
- ✅ Future-proof for scaling
- ✅ Better latency for risk management

### For Enterprise (100+ Accounts)
**Use Hybrid + Webhook**

```
WebSocket pool (100 connections) for real-time
+ Webhook endpoint (serverless) for redundancy
+ Fallback polling (1/hour) for recovery
```

---

## Implementation Priority

**Phase 3 (Current):**
- ✅ Polling every 5 min (works fine)

**Phase 4 (Next):**
- ⏳ Add WebSocket support
- ⏳ One WS per account
- ⏳ Real-time fill notifications

**Phase 5+ (Enterprise):**
- ⏳ Webhooks for event-driven architecture
- ⏳ Remove polling entirely
- ⏳ Scale to 1000+ accounts

---

## Code Reference

**WebSocket docs:** https://docs.cdp.coinbase.com/advanced-trade/docs/ws-overview  
**User channel:** Sends order updates + account balance changes  
**Rate limits:** Polling = 10,000 req/hour | WebSocket = unlimited  

---

**Bottom line:** For scaling past 20 accounts, WebSocket is non-negotiable. For Phase 4, add WebSocket support while keeping polling as fallback.
