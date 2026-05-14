# End-to-End Sentiment-Driven Trading Workflow
This document outlines the complete workflow for the cryptocurrency trading bot, demonstrating how to fetch sentiment, aggregate data, apply trading strategies, make decisions, and log results.

## Workflow Overview
1. **Fetch Sentiment**: Use the `XSentimentFetcher` class to fetch live sentiment data from the X API.
   - **Key Method**: `fetch_sentiment(pair)` returns sentiment score and associated tweet data.

2. **Aggregate Sentiment**: The fetched sentiment data is processed using the `SentimentAggregator`.
   - **Key Method**: `process_sentiment(data)` analyzes and aggregates sentiment data for trading decisions.

3. **Apply Trading Strategy**: Utilize `SignalGenerator` to generate trading signals based on aggregated sentiment and technical indicators.
   - **Key Methods**: `generate_all_signals()` produces trading signals incorporating sentiment and RSI logic.

4. **Trade Decision**:
   - Determine whether to buy, sell, or hold based on the signals generated from the `SignalGenerator`.
   - Signals are classified with corresponding confidence levels.

5. **Log Results**: Successful trades and their associated metadata are recorded in the SQLite database.
   - **Key Method**: `_log_trade(...)` logs trades with details like entry price, sentiment score, and signal used.

## Detailed Workflow - Code Integration
- Root script to execute the end-to-end test:
```python
# Import necessary classes
from x_sentiment_fetcher import XSentimentFetcher
from sentiment_aggregator import SentimentAggregator
from signal_generator import SignalGenerator

# Setup for "End to End Test"
fetcher = XSentimentFetcher(bearer_token='Your_Bearer_Token')
aggregator = SentimentAggregator()
trading_strategy = SignalGenerator()

# Fetch sentiment
sentiment_data = fetcher.fetch_sentiment('BTC-USD')
aggregated = aggregator.process_sentiment(sentiment_data)

# Generate signals
signals = trading_strategy.generate_all_signals()

# Log trades based on signals
...
```

## Recommendations
- Ensure the `.env` file contains valid credentials for the X API to fetch sentiment data.
- Always run the test in a controlled environment to avoid affecting live trades.
- Regularly review logged trades for any anomalies or insights that can improve strategy accuracy.