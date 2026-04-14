# Crypto Trading Bot — Functional Specification v1.0
**Date:** 2026-04-01
**Status:** APPROVED — Defines behavior for Phase 5 (live trading) implementation
**Author:** Brad Slusher

---

## 1. Funding & Wallet Architecture

### 1.1 Cash Account (Source of Funds)
- All trading capital originates from a Coinbase **Cash Account**, either:
  - **USD** (fiat)
  - **USDC** (stablecoin)
- The cash account type is **configurable per trader** in `trader_config`
- Initial funding into the cash account is done manually by the user via bank transfer (outside bot scope)
- The bot never initiates deposits or withdrawals from the bank — it only moves funds between the cash account and crypto pairs within Coinbase

### 1.2 Trade Funding Flow
```
Bank (manual) → Coinbase Cash Account (USD or USDC)
                         ↓  [BOT: buy order]
                   Crypto Pair (e.g., ETH-USD)
                         ↓  [BOT: sell order]
                   Coinbase Cash Account (USD or USDC)
```

### 1.3 Auto-Scaling Trade Size
- The bot **reads the real available balance** from the configured cash account at startup and before each trade
- Trade size is calculated as: `min(configured_capital_per_pair, available_cash / num_active_pairs)`
- If available cash is **less than** the configured capital, trade size scales **down** proportionally
- If available cash is **more than** configured capital, trade size uses the configured amount (does not auto-scale up to prevent unintended overexposure)
- If available cash is **zero or insufficient** for a minimum trade, the bot skips that cycle and logs a warning — it does **not** halt entirely

### 1.4 Configuration
```json
{
  "cash_account": {
    "type": "USD",          // "USD" or "USDC" — configurable per trader
    "min_trade_usd": 10.0   // minimum trade size before skipping
  }
}
```

---

## 2. Approval Thresholds

### 2.1 Default Behavior: Fully Automatic
- **No per-trade approval required** — the bot executes all signals autonomously
- Safety is enforced via **stop-loss** (default: -2% per trade) and **daily loss cap** (configurable)
- This is the expected default for all traders

### 2.2 Optional Override (Future Feature — implement on demand)
- A `require_approval_above_usd` config flag can be set per trader
- If a trade notional exceeds this threshold, the bot sends a Telegram confirmation request and waits up to N minutes for approval before skipping
- **Status:** Not built in Phase 5. Spec reserved for future demand.

```json
// Future optional config (not active)
{
  "approval": {
    "require_approval_above_usd": null,  // null = disabled
    "approval_timeout_minutes": 5
  }
}
```

---

## 3. Multi-Trader Framework (Light — Phase 5)

### 3.1 Scope
- Build a lightweight multi-trader framework sufficient to support:
  - Multiple independent traders (each with their own config, pairs, wallet)
  - UI and reporting development
  - Future SaaS/OAuth integration in Phase 6+
- **No OAuth in Phase 5** — traders are configured manually via config files or admin DB entry
- **Target scale:** 1–10 traders for Phase 5

### 3.2 Trader Registry
Each trader is a row in a `traders` table (SQLite for Phase 5):

```sql
CREATE TABLE traders (
    trader_id     TEXT PRIMARY KEY,   -- UUID
    name          TEXT,               -- display name
    api_key       TEXT,               -- Coinbase API key (encrypted at rest)
    api_secret    TEXT,               -- Coinbase API secret (encrypted at rest)
    cash_account  TEXT DEFAULT 'USD', -- "USD" or "USDC"
    capital_total REAL,               -- total allocated capital in USD
    status        TEXT DEFAULT 'active', -- active | paused | suspended
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3.3 Trader Pair Configuration
Each trader has their own set of trading pairs:

```sql
CREATE TABLE trader_pairs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trader_id       TEXT REFERENCES traders(trader_id),
    pair            TEXT,              -- e.g., "ETH-USD"
    capital_usd     REAL,              -- capital allocated to this pair
    strategy        TEXT DEFAULT 'dynamic_rsi',
    buy_threshold   INTEGER DEFAULT 30,
    sell_threshold  INTEGER DEFAULT 70,
    stop_loss_pct   REAL DEFAULT 0.02,
    daily_loss_cap  REAL DEFAULT 50.0,
    enabled         BOOLEAN DEFAULT 1
);
```

### 3.4 Per-Trader Position & P&L Tracking
```sql
CREATE TABLE positions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trader_id     TEXT,
    pair          TEXT,
    entry_price   REAL,
    entry_time    DATETIME,
    size_usd      REAL,
    side          TEXT,  -- "BUY" or "SELL"
    status        TEXT,  -- "open" | "closed"
    exit_price    REAL,
    exit_time     DATETIME,
    pnl_usd       REAL,
    exit_reason   TEXT   -- "stop_loss" | "take_profit" | "signal" | "timeout"
);

CREATE TABLE daily_pnl (
    trader_id   TEXT,
    date        DATE,
    pair        TEXT,
    pnl_usd     REAL,
    trades      INTEGER,
    wins        INTEGER,
    PRIMARY KEY (trader_id, date, pair)
);
```

### 3.5 Bot Orchestration
- One bot process can manage **multiple traders** by iterating over active traders each cycle
- Each trader's signal evaluation, position management, and order execution is fully independent
- Log output is namespaced by `trader_id`
- Cycle cadence: 5 minutes (shared across all traders for efficiency)

### 3.6 Startup Validation
On each bot startup:
1. Load all `active` traders from registry
2. For each trader: verify Coinbase API key is valid, fetch real cash balance
3. Warn if cash balance < configured capital (scale down, don't halt)
4. Log trader roster and pair configs

---

## 4. Trading Pairs

### 4.1 Configurability
- Trading pairs are **fully configurable** per trader in `trader_pairs` table
- Hard-coded pairs in Python source are **not allowed** (Phase 5 requirement)
- Pairs are loaded from config/DB at startup

### 4.2 Initial Deployment (Brad's Account)
- **BTC-USD and XRP-USD are reserved for Brad's personal Coinbase account** — do NOT use these
- Brad will select 2 different pairs for the bot's initial live trading deployment
- **Pairs TBD** — Brad to specify before Phase 5 go-live
- Starting capital per pair: TBD based on available cash balance at time of deployment

### 4.3 Supported Pairs (Phase 5)
- Maximum: 2 pairs per trader in Phase 5 (matches current architecture)
- Maximum: 10 pairs per trader in Phase 6+ (original design target)
- All Coinbase Advanced Trade pairs with sufficient liquidity are eligible

---

## 5. Order Execution

### 5.1 Order Routing
- All orders route to the trader's Coinbase Advanced Trade account
- Order type: `limit` (default, per existing config) — reduces slippage and fees
- Destination is always the Coinbase matching engine for the given `product_id`
- No cross-exchange routing in Phase 5

### 5.2 Order Authentication
- Ed25519 signing via `CoinbaseWrapper` (already implemented)
- API key scoped to: view, trade (no transfer/withdrawal permissions)

### 5.3 Fee Model
- Entry fee: 0.4% (Coinbase maker rate for limit orders)
- Exit fee: 0.4%
- Round-trip cost: ~0.8% of notional
- Fee applied to P&L calculation on every trade close

---

## 6. Safety Controls

| Control | Default | Configurable |
|---------|---------|-------------|
| Stop loss | -2% per trade | ✅ per trader/pair |
| Daily loss cap | $50 per pair | ✅ per trader/pair |
| Min cash check | Warn + scale down | Fixed behavior |
| Max pairs per trader | 2 (Phase 5) | Hardcoded for Phase 5 |
| Approval threshold | None (auto) | ✅ future feature |
| Kill switch | Telegram `/stop` command | To be built |

---

## 7. What's NOT in Phase 5

| Feature | Phase |
|---------|-------|
| OAuth / user self-onboarding | Phase 6 (SaaS) |
| Web UI for trader management | Phase 6 |
| Approval threshold enforcement | On-demand post-Phase 5 |
| >2 pairs per trader | Phase 6 |
| Cross-exchange trading | Not planned |
| Tax/accounting integration | Not planned |

---

---

## 9. Dynamic Account Rebalancing (Subscriber Upsell — Future Module)

### 9.1 Purpose
Automatically shift capital between trading pairs to maximize returns based on live performance signals. Reduces manual intervention and captures regime shifts faster than static allocation.

### 9.2 Conversion Mechanism
Coinbase does not support direct crypto-to-crypto swaps via the Advanced Trade API. The actual flow is always:
```
Crypto A → sell → Cash (USD/USDC) → buy → Crypto B
```
This means every rebalance incurs **two sets of fees** (~0.4% each = ~0.8% round trip). The rebalancer must only trigger when the expected performance gain from reallocation exceeds that round-trip cost.

**API support status:** Coinbase Advanced Trade API supports this via sequential `sell` + `buy` limit orders. No direct conversion endpoint exists. The module will abstract this as a single `convert(from_pair, to_pair, amount_usd)` operation.

### 9.3 Triggers
| Trigger Type | Condition | Notes |
|---|---|---|
| Performance drift | Win rate spread between pairs > 15% over 14-day window | Primary trigger |
| Regime change | A pair enters DOWNTREND for 3+ consecutive regime checks | Defensive reallocation |
| Compound overflow | Compound gains exceed per-pair allocation cap | Redirect excess to next-best pair |
| Time-based | Daily evaluation at 18:00 PT | Minimum rebalance interval: 24h |
| Manual override | Admin/user command via API or Telegram `/rebalance` | Always available |

### 9.4 Rebalancing Method
1. Compute `pair_score = (win_rate × 0.6) + (avg_pnl_pct × 0.3) − (drawdown_pct × 0.1)` over last 14 days
2. Rank pairs by score
3. Calculate target allocation: top-ranked pair gets up to 60% of total capital; others split the remainder
4. If current allocation differs from target by > 5% (minimum rebalance threshold), trigger rebalance
5. Liquidate excess from underperformer → hold in cash → deploy into outperformer
6. Log rebalance event with: timestamp, from_pair, to_pair, amount_usd, fees_usd, rationale, score_delta

### 9.5 Frequency & Constraints
- Minimum interval between rebalances: **24 hours** (prevents churn)
- Maximum single rebalance: **30% of total capital** (prevents overexposure)
- Maximum allocation to one pair: **60%**
- Minimum allocation per active pair: **20%** (keeps diversification)
- Rebalance only when expected gain > 2× round-trip fee cost

### 9.6 Tracking & Attribution
```sql
CREATE TABLE rebalance_events (
    event_id     TEXT PRIMARY KEY,
    trader_id    TEXT,
    timestamp    DATETIME,
    from_pair    TEXT,
    to_pair      TEXT,
    amount_usd   REAL,
    fee_usd      REAL,
    rationale    TEXT,   -- e.g. "win_rate_drift: ETH 68% vs SOL 41%"
    score_before TEXT,   -- JSON: {pair: score}
    score_after  TEXT,   -- JSON: {pair: score}
    net_impact   REAL    -- running P&L delta attributed to this rebalance
);
```

### 9.7 Showing Long-Term Impact
- **Counterfactual comparison:** Run a parallel simulation at each rebalance point showing what P&L would be if allocation had stayed static → display "Rebalancing added $X (+Y%)" on dashboard
- **Cumulative rebalance P&L chart:** time-series line showing capital growth with vs. without rebalancing
- **Fee drag tracker:** total fees paid for rebalances vs. gains generated — keeps the feature honest

### 9.8 Product Positioning
- **Tier:** Subscriber upsell (Pro or Max tier)
- **Default:** Disabled; opt-in per trader
- **Phase:** Not in Phase 5. Designed for Phase 6 (SaaS).

---

## 10. Compound Trading Engine

### 10.1 Concept
When a trade closes with a profit, the gain is not returned to the base capital pool equally — it is preferentially allocated to the **highest win-rate pair** over the recent lookback window. This creates a compounding loop where the best-performing pair receives more capital, which generates more trades, which generates more gains.

### 10.2 Allocation Logic
```
On trade close (pnl > 0):
  1. Identify best_pair = pair with highest win_rate (last 30 trades or 14 days, whichever has more data)
  2. If best_pair allocation < max_pair_allocation (60%):
     → Add gain to best_pair capital
  3. Else:
     → Add gain to next_best_pair (rank 2)
  4. If all pairs at max allocation:
     → Add gain to cash reserve (withdrawn to base capital)
  5. Log compound event: amount, target_pair, win_rate_at_time
```

### 10.3 Safety Floor
- No pair can receive compound allocation if its daily loss cap has been hit for the day
- Minimum cash reserve maintained: 5% of total capital (liquidity buffer)
- Compound gain per cycle capped at 10% of existing pair allocation (prevents runaway single-pair concentration)

### 10.4 Tracking
```sql
CREATE TABLE compound_events (
    event_id       TEXT PRIMARY KEY,
    trader_id      TEXT,
    timestamp      DATETIME,
    source_trade   TEXT,       -- position.id that generated the gain
    gain_usd       REAL,
    target_pair    TEXT,
    win_rate_used  REAL,       -- win rate at time of allocation
    new_allocation REAL        -- target pair capital after compound
);
```

### 10.5 Dashboard Display
- "Compound Growth" widget: shows total capital growth attributable to compounding vs. flat allocation
- Per-pair compound received: how much each pair has gained from compounding
- Projected 30/60/90-day trajectory at current compound rate

### 10.6 Product Positioning
- **Tier:** Core feature (available Phase 5, enabled by default with opt-out)
- **Default:** ON (most traders will want fully automatic with stop-loss)
- **Phase:** Build in Phase 5 alongside multi-trader framework

---

---

## 11. Rebalancing Module — Architecture Decisions (2026-04-01)

### 11.1 Scope
- **Coinbase only** — no cross-exchange trading. Single exchange, single API. Keeps complexity manageable and adoption realistic.
- **Not part of the intraday trading bot** — Rebalancing is a separate, independently deployable module.

### 11.2 Two Operating Modes

**Mode A: Active Trading Pool Overlay**
- Rebalancer operates on the same Coinbase account as the intraday bot
- Runs on a separate cadence (threshold-triggered or calendar-based) that does NOT conflict with open intraday positions
- Coordination rule: rebalancer skips any pair that has an open intraday position; waits for it to close first
- Useful for: traders who want dynamic allocation management on their active pairs

**Mode B: Standalone Pool**
- User designates a separate USD/USDC pool specifically for rebalancing
- Intraday bot has no access to this pool
- Rebalancer manages percentage-based target allocations across configured pairs
- Useful for: users who want a "buy and hold + rebalance" strategy separate from active trading

### 11.3 Configuration
```json
{
  "rebalancing": {
    "enabled": true,
    "mode": "standalone",           // "active_pool" | "standalone"
    "pool_usd": null,                // null = use full cash balance; or specify amount
    "threshold_pct": 12.0,           // rebalance when any pair drifts ±12% from target
    "calendar_trigger": "monthly",   // "weekly" | "monthly" | "none"
    "ai_filter": true,               // gate on RSI + sentiment before executing
    "min_gain_over_fees": true        // skip if expected gain < round-trip fee cost
  }
}
```

### 11.4 Target Allocation Methodology (TBD)
- Allocation percentages are user-configurable per pair
- A codified allocation methodology is being developed (sourced from AI-assisted analysis of volatility profiles, liquidity, and asset class mix)
- Until methodology is codified: allocations are set manually in config
- **Open item:** Brad to share Grok's allocation reasoning → we will extract the logic and build a `generate_target_allocations(pairs, total_capital, risk_profile)` function that replicates it reproducibly

### 11.5 Supported Pairs (Phase 5, Coinbase only)
Coinbase Advanced Trade supports: XRP, DOGE, NEAR, GRT, FIL, and others
Pairs like SHIB, WIF, AIOZ, RNDR, TAO, SOLX are **not on Coinbase** → excluded from Phase 5
Phase 6 can add ccxt multi-exchange support if demand exists

### 11.6 Fee Accounting
- Every rebalance is: sell overweight pair → USD/USDC → buy underweight pair
- Round-trip cost: ~0.8% (0.4% × 2 maker rate)
- Bot skips rebalance if projected gain from realignment < 0.8% (fee break-even)
- All rebalance actions logged with: fee_usd, expected_gain_usd, net_impact_usd

### 11.7 What the $10K modeling figure means
- $10K is a **reference figure for projection modeling only** — not an actual capital commitment
- Real pool size is whatever the user designates in config or their actual Coinbase cash balance
- The allocation percentages (XRP 15%, DOGE 12%, etc.) were AI-generated by Grok as a starting model
- These will be codified into a reproducible methodology function once Brad shares the underlying reasoning

---

## 12. Open Items (Awaiting Brad Input)

- [ ] **Which 2 trading pairs** for initial live deployment?
- [ ] **Cash account preference:** USD or USDC?
- [ ] **Starting capital per pair** (based on available Coinbase balance)?
- [ ] **Live API keys** for Coinbase (to be provided securely when ready)
