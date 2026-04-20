# Crypto Trading Bot Documentation

## Cycle Mechanics

### 1-Hour Cycle Workflow

The trading bot operates on a 1-hour (3600-second) cycle mechanism designed to provide systematic, disciplined trading decisions. Each cycle performs a comprehensive market analysis without guaranteeing a trade in every interval.

#### Cycle Purpose
- Market condition assessment
- Price history update
- Technical indicator computation
- Trade signal evaluation
- Sentiment analysis
- Risk management checks

#### Cycle Characteristics
- **Duration**: 1 hour per cycle
- **Trading Frequency**: Selective, not mandatory
- **Market Approach**: Conservative, waiting for strong signals

#### Key Checks in Each Cycle
1. **Current Price Retrieval**
   - Fetch latest prices for monitored pairs (BTC-USD, XRP-USD, etc.)

2. **Technical Indicators**
   - Calculate StochRSI (Stochastic Relative Strength Index)
   - Identify oversold/overbought conditions
   - Assess trend momentum

3. **Sentiment Analysis**
   - Integrate external sentiment data
   - Weight market sentiment alongside technical indicators

4. **Risk Management**
   - Compute Average True Range (ATR) for stop-loss
   - Check daily loss cap
   - Evaluate position sizing

#### Trading Decision Logic
- **Hold Conditions (Conservative)**
  - Sideways or downtrend markets
  - Insufficient signal strength
  - Negative or neutral sentiment

- **Trade Conditions**
  - Strong oversold signal
  - Positive sentiment
  - Clear trend confirmation
  - Risk parameters met

#### Example Cycle Progression
- **7:00 AM**: Market check, no trade (HOLD)
- **8:00 AM**: Continued assessment, still HOLD
- **9:00 AM**: Potential trade if all conditions satisfied

### Configuration Parameters
- `CYCLE_INTERVAL`: 3600 seconds (1 hour)
- `RSI_THRESHOLDS`: 35/65 (tight, responsive)
- `SENTIMENT_WEIGHT`: Adjustable impact on trading decisions

**Note**: Trading frequency prioritizes risk management over trade volume.