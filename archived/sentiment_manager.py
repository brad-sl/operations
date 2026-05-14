# [Previous content remains the same, add import and update sources]

from poly_sentiment import PolymarketSentimentFetcher

# In the available_sources dictionary in SentimentManager.__init__():
self.available_sources = {
    'x_api': XApiSentiment,
    'reddit': RedditSentiment,
    'news_api': NewsApiSentiment,
    'on_chain': OnChainSentiment,
    'polymarket': PolymarketSentimentFetcher  # Add this line
}

# Update the default sentiment sources
self.sentiment_sources = os.getenv(
    'SENTIMENT_SOURCES', 
    'x_api,reddit,news_api,on_chain,polymarket'  # Include polymarket
).split(',')