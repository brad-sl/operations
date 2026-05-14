# Phase 4: End-User Account Management UI Specification

**Status:** 📋 PLANNING (Post-Phase 3)  
**Timestamp:** 2026-03-25 22:04 PDT  
**Context:** Multi-trader SaaS platform requires professional end-user dashboard

---

## Core UI Elements (Evolving List)

### 1. Trading Pair Picker
**Purpose:** Select which crypto pairs to trade (BTC, ETH, XRP, SOL, etc.)

**Features:**
- Searchable dropdown / autocomplete (50+ trading pairs)
- Show current price, 24h change %, volume
- Favorite/pin frequently traded pairs
- Filter by volatility, volume, correlation
- Quick-add buttons for common pairs (BTC, ETH, stablecoins)

**Inputs:**
- Pair name (BTC/USD, ETH/USDT, XRP/USDC)
- Allocation (% of portfolio for this pair)
- Strategy preset (Momentum, Mean Reversion, Trend-Following)

**Output:**
- Selected pairs list with allocations
- Risk score for portfolio composition

---

### 2. Trading Pair Leaderboard
**Purpose:** Show most volatile / highest momentum pairs (real-time rankings)

**Metrics Tracked:**
- **Top Movers (24h):** % change, volume, price
- **Most Volatile:** Standard deviation of returns
- **Highest Volume:** USD trading volume
- **Trending Up/Down:** Technical signals (RSI, MACD)
- **Correlation Matrix:** Which pairs move together (avoid over-concentration)

**Display:**
- Sortable table: price, change %, volume, volatility score
- Color coding: green (up), red (down), yellow (neutral)
- Time periods: 1h, 24h, 7d, 30d
- Heatmap view: volatility bubbles (size = volume, color = momentum)

**User Actions:**
- Click pair → add to trading list
- Drag-and-drop ranking to reorder watchlist
- Alert: notify when pair enters top 10 movers

---

### 3. Active Trading Pairs Dashboard
**Purpose:** Real-time status of all pairs currently trading

**For Each Pair, Show:**

#### Basic Status
- **Pair Name & Price:** BTC $48,250 (↑ 2.3% today)
- **Entry Price & P&L:** Bought at $47,500 → +$750 unrealized gain (+1.6%)
- **Daily/Weekly/Monthly Performance:**
  - Win rate (% of trades profitable)
  - Cumulative P&L (daily, weekly, monthly)
  - Total positions open/closed

#### Trading Details
- **Position Size:** $5,000 (5% of portfolio)
- **Entry Date/Time:** 2026-03-25 14:30 PDT
- **Current Price:** Real-time
- **Stop Loss / Take Profit:** If set ($47,000 / $50,000)
- **Next Signal Eta:** "RSI overbought in 2h" or "MACD flip expected soon"

#### Visual Indicators
- Sparkline: 7-day price action
- Signal lights: 🟢 Hold, 🟡 Watch, 🔴 Exit Soon
- Risk meter: Low / Medium / High (based on volatility + allocation)

#### Performance Breakdown
- Win/Loss ratio (this month)
- Average gain per win, average loss per loss
- Sharpe ratio / risk-adjusted return
- Max drawdown on this pair

---

### 4. Exit Trading for One or More Pairs
**Purpose:** Close positions, either all-at-once or selective partial exits

**Single Pair Exit:**
- Click "Exit" button on pair card
- Confirmation: "Close BTC position? Current P&L: +$750"
- Options:
  - Exit entire position (100%)
  - Partial exit (sell 50%, 75%, custom %)
  - Market order (immediate) vs Limit order (specific price)
- Real-time execution feedback

**Bulk Exit:**
- Multi-select pairs (checkbox interface)
- "Exit Selected Pairs" button
- Batch confirmation with total P&L impact
- Execute all orders simultaneously or sequentially

**Exit Reasons (Optional Logging):**
- Take profit target hit
- Stop loss triggered
- Manual decision
- Strategy signal
- Portfolio rebalancing

**Result Display:**
- Position closed: timestamp, exit price, final P&L
- Updated portfolio allocation (freed capital)
- Archived to history (for tax + performance review)

---

### 5. Manual Rebalance Pairs
**Purpose:** Adjust allocations across pairs without closing positions

**Rebalance Workflows:**

#### Option A: Slider Interface
- Horizontal sliders for each pair (0-100% allocation)
- Total must sum to 100%
- Real-time calculation: "This will allocate $X to BTC, $Y to ETH, ..."
- Before/after allocation visualization (pie charts)

#### Option B: Table Edit
- Current allocation | New allocation | Change
- Type new % directly in cells
- Validate total = 100%
- Show execution plan: buy/sell orders to execute rebalancing

#### Option C: Drag-and-Drop
- Visual drag handles for each pair
- Resize blocks to redistribute
- Hover to see $USD amounts

**Rebalancing Execution:**
- Show orders to execute (e.g., "Sell 20% ETH, Buy 20% SOL")
- Confirm: "This will cost ~$25 in fees"
- Execute rebalance (automated order placement)
- Progress bar: "Rebalancing... 3/5 orders filled"

**Rebalance History:**
- Log of all rebalances (date, from/to allocation, reason)
- Performance impact: portfolio delta vs target allocation

---

## Supporting UI Features

### Dashboard Overview (Top-Level View)
```
┌─────────────────────────────────────────────────────┐
│  Portfolio Summary                                  │
│  Total Value: $50,000 | Daily P&L: +$750 (+1.5%)   │
│  Win Rate: 62% | Sharpe: 1.24 | Max Drawdown: -8%  │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Active Pairs (3)                                   │
├─────────────────────────────────────────────────────┤
│ BTC   $48,250  ↑2.3%   $5,000 (10%)    +$750 ✅    │
│ ETH   $2,850   ↓1.1%   $3,000 (6%)     -$150 ⚠️    │
│ SOL   $120.50  ↑5.2%   $2,000 (4%)     +$420 ✅    │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Leaderboard: Top Movers (24h)                      │
├─────────────────────────────────────────────────────┤
│ PEPE  ↑28.5%  | DOGE  ↑12.3%  | AVAX  ↑8.7%       │
└─────────────────────────────────────────────────────┘
```

### Real-Time Updates
- WebSocket connection for price updates (sub-second latency)
- P&L updates on each tick
- Signal notifications (new entry/exit signal generated)
- Execution feedback (order filled, partially filled, rejected)

### Notifications & Alerts
- **Signal Alert:** "RSI oversold on BTC → BUY signal generated"
- **Exit Alert:** "ETH hit stop loss → Position closed"
- **Rebalance Reminder:** "Portfolio drift 8% from target → Rebalance now?"
- **Performance Alert:** "Win rate dropped to 45% this week"

### Performance Analytics (Secondary Screens)
- **Daily/Weekly/Monthly Reports:** Win rate, P&L, top/bottom pairs
- **Historical Trades:** Closed positions with entry/exit, duration, P&L
- **Correlation Matrix:** Which pairs move together (risk concentration)
- **Drawdown Analysis:** Max loss from peak, recovery time

### Mobile Responsive
- Touch-friendly buttons and dropdowns
- Vertical layout for pair cards
- Swipe to see leaderboard, active pairs, analytics
- One-tap exit for emergency close

---

## Competitor Research TODO

**Platforms to Analyze (for UX/feature ideas):**
- **3Commas** (trading bot aggregator)
  - Dashboard layout, pair management
  - Strategy preset UI
  - Portfolio rebalancing interface
- **CryptoHopper** (automated trading)
  - Leaderboard/rankings
  - Real-time status cards
  - Alert/notification design
- **TradingView** (chart + alert platform)
  - Watchlist interface
  - Alert configuration
  - Multi-timeframe displays
- **Coinbase Advanced Trade** (pro trading)
  - Order book UI
  - Position management
  - Portfolio allocation visualization

**Research Deliverables (Phase 4):**
1. Screenshot comparison: Pair picker (3Commas vs CryptoHopper vs TradingView)
2. Feature matrix: Which competitors have rebalancing, leaderboards, etc.
3. UX patterns: Common layouts, terminology, interaction models
4. Gaps & opportunities: What's missing that traders need

---

## Tech Stack (Suggested)

### Frontend
- **Framework:** React 18 (or Vue 3 for alternative)
- **Real-Time:** WebSocket (Socket.io or native WS)
- **UI Library:** shadcn/ui or Material-UI for professional polish
- **Charts:** TradingView Lightweight Charts or Recharts
- **State:** Redux Toolkit or Zustand (for portfolio state)
- **Mobile:** React Native or responsive web (Tailwind CSS)

### Backend
- **API:** REST + WebSocket (real-time updates)
- **Database:** PostgreSQL (trades, positions) + Redis (real-time cache)
- **Auth:** JWT + OAuth2 (for multi-user/multi-account)
- **Market Data:** Coinbase WebSocket (price, trade execution events)

### Hosting
- **Frontend:** Vercel or Netlify (auto-deploy from git)
- **Backend:** AWS Lambda + API Gateway, or self-hosted (Docker)
- **Real-Time:** Socket.io server (can scale with Redis adapter)

---

## Phase 4 Implementation Plan

### Sprint 1: UI Prototypes (2-3 days)
- Figma mockups: all 5 core screens
- Usability testing: ask 2-3 traders for feedback
- Competitor analysis: feature gap assessment

### Sprint 2: Frontend Shell (3-5 days)
- React components: PairPicker, Leaderboard, Dashboard, RebalanceUI
- Mock data: realistic portfolio state
- Responsive layout (desktop + mobile)
- WebSocket integration (stub)

### Sprint 3: Backend Integration (3-5 days)
- API endpoints: get pairs, get performance, exit trade, rebalance
- WebSocket: real-time price/P&L updates
- Database: trades, positions, rebalance history
- Authentication: multi-user account linking

### Sprint 4: Real-Time Execution (2-3 days)
- Coinbase order placement integration
- Execution feedback (filled, partial, rejected)
- Error handling (slippage, insufficient funds, etc.)
- Audit trail logging

### Sprint 5: Analytics & Polish (2-3 days)
- Performance charts and reports
- Historical trade review
- Correlation matrix visualization
- Mobile optimization

**Total Estimate:** 12-19 days (3-4 weeks with parallel work)

---

## Success Metrics (Phase 4)

| Metric | Target | Notes |
|--------|--------|-------|
| **Dashboard Load Time** | <1s | WebSocket connection established |
| **Price Update Latency** | <500ms | From exchange to UI |
| **Mobile Responsiveness** | >90 Lighthouse | Accessible on all devices |
| **Order Execution Speed** | <2s | From click to API submission |
| **User Session Duration** | >15 min avg | Engagement indicator |
| **Feature Adoption** | >80% use rebalance | Adoption of core features |

---

## Open Questions for Brad

1. **Leaderboard Timeframe:** Show top 10 by 1h, 24h, or all? Recommendation: 24h default, toggleable.
2. **Rebalance Confirmation:** Auto-execute or require manual confirm? Recommendation: Manual confirm (risk mitigation).
3. **Exit Reasons:** Optional logging or required? Recommendation: Optional (UX friction reduction).
4. **Mobile App:** Native (iOS/Android) or responsive web-only? Recommendation: Start with responsive web, port to native after Phase 5.
5. **Notifications:** In-app only or push notifications (email/SMS)? Recommendation: In-app + browser push (no email spam).
6. **Historical Data:** Show all trades ever, or last 90 days? Recommendation: Last 90 days paginated, with archive access.

---

**Status:** UI specification document created for Phase 4 development  
**Next Steps:** 
1. Competitor research (3Commas, CryptoHopper, TradingView, Coinbase)
2. Figma mockups for 5 core screens
3. Trader feedback on feature priorities
4. Frontend prototype sprint
