"""
X (Twitter) Sentiment Analyzer for Crypto Assets
Fetches recent tweets about Bitcoin/crypto and scores sentiment
on a scale from -1.0 (very bearish) to +1.0 (very bullish)
"""

import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import requests
from dataclasses import dataclass, asdict


@dataclass
class SentimentResult:
    """Structured sentiment analysis result"""
    timestamp: str
    tweet_id: str
    author: str
    text: str
    sentiment_score: float
    reasoning: str

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


class XSentimentScorer:
    """
    Fetches X (Twitter) posts about Bitcoin/crypto and scores sentiment.

    Sentiment Scale:
    - -1.0 to -0.5: Very bearish (crash, dump, liquidation)
    - -0.5 to 0.0: Bearish (weakness, fear, concerns)
    - 0.0: Neutral
    - 0.0 to 0.5: Bullish (strength, adoption, gains)
    - 0.5 to 1.0: Very bullish (pump, rally, breakout, FOMO)
    """

    # Sentiment keyword weights
    BEARISH_KEYWORDS = {
        "crash": -1.0,
        "dump": -0.9,
        "rug": -0.95,
        "rug pull": -1.0,
        "liquidation": -0.9,
        "liquidating": -0.9,
        "weakness": -0.7,
        "weak": -0.6,
        "fear": -0.8,
        "sell off": -0.8,
        "selling": -0.5,
        "decline": -0.6,
        "fallen": -0.6,
        "falling": -0.6,
        "bearish": -0.7,
        "bear": -0.6,
        "risk": -0.4,
        "concern": -0.5,
        "worried": -0.6,
        "bad": -0.5,
        "negative": -0.5,
        "down": -0.4,
        "loss": -0.6,
        "losing": -0.6,
        "bottom": -0.5,
        "collapse": -0.9,
        "capitulation": -0.85,
    }

    BULLISH_KEYWORDS = {
        "pump": 0.9,
        "pumping": 0.85,
        "rally": 0.85,
        "breakout": 0.8,
        "breaking out": 0.8,
        "strength": 0.7,
        "strong": 0.7,
        "bullish": 0.75,
        "bull": 0.6,
        "fomo": 0.8,
        "adoption": 0.75,
        "adoption growing": 0.8,
        "institutional": 0.7,
        "institutions": 0.7,
        "whale": 0.6,
        "accumulation": 0.75,
        "buy": 0.6,
        "buying": 0.6,
        "gain": 0.7,
        "gains": 0.75,
        "moon": 0.85,
        "mooning": 0.85,
        "rocket": 0.85,
        "breakthrough": 0.8,
        "surging": 0.8,
        "surge": 0.75,
        "recovery": 0.7,
        "recovering": 0.7,
        "positive": 0.6,
        "up": 0.5,
        "upside": 0.6,
        "optimistic": 0.65,
        "excellent": 0.7,
        "fantastic": 0.7,
        "amazing": 0.7,
        "great": 0.65,
        "best": 0.7,
        "opportunity": 0.65,
        "deal": 0.6,
        "partnership": 0.65,
        "approval": 0.75,
        "approved": 0.75,
    }

    NEUTRAL_KEYWORDS = {
        "bitcoin",
        "eth",
        "ethereum",
        "btc",
        "cryptocurrency",
        "crypto",
        "trading",
        "market",
        "price",
        "analysis",
    }

    def __init__(self, bearer_token: str):
        """
        Initialize X Sentiment Scorer

        Args:
            bearer_token: X API Bearer Token (from .env)

        Raises:
            ValueError: If bearer_token is empty or invalid
        """
        if not bearer_token or len(bearer_token) < 10:
            raise ValueError("Invalid X Bearer Token")

        self.bearer_token = bearer_token
        self.base_url = "https://api.twitter.com/2"
        self.session = requests.Session()
        self._setup_headers()

    def _setup_headers(self) -> None:
        """Setup default request headers with Bearer token"""
        self.session.headers.update({
            "Authorization": f"Bearer {self.bearer_token}",
            "User-Agent": "CryptoBot-Sentiment-Scorer/1.0",
        })

    def fetch_tweets(
        self,
        query: str,
        max_results: int = 100,
        tweet_fields: str = "created_at,author_id,public_metrics"
    ) -> List[Dict]:
        """
        Fetch recent tweets matching query from X API

        Args:
            query: Search query (e.g., "Bitcoin breakout")
            max_results: Number of tweets to fetch (1-100, default 100)
            tweet_fields: Additional tweet fields to include

        Returns:
            List of tweet dictionaries with id, text, author_id, created_at

        Raises:
            requests.RequestException: If API call fails
            ValueError: If query is empty or invalid
        """
        if not query or len(query.strip()) < 3:
            raise ValueError("Query must be at least 3 characters")

        if not (1 <= max_results <= 100):
            raise ValueError("max_results must be between 1 and 100")

        # Construct query with filters
        # lang:en - English only
        # -is:retweet - Exclude retweets (focus on original analysis)
        # -is:reply - Exclude replies (focus on main posts)
        search_query = f"{query} lang:en -is:retweet -is:reply"

        params = {
            "query": search_query,
            "max_results": max_results,
            "tweet.fields": tweet_fields,
            "expansions": "author_id",
            "user.fields": "username,verified",
        }

        try:
            response = self.session.get(
                f"{self.base_url}/tweets/search/recent",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            # Extract tweets with user data
            tweets = []
            user_map = {user["id"]: user for user in data.get("includes", {}).get("users", [])}

            for tweet in data.get("data", []):
                author_id = tweet.get("author_id")
                username = user_map.get(author_id, {}).get("username", "unknown")

                tweets.append({
                    "id": tweet["id"],
                    "text": tweet["text"],
                    "author_id": author_id,
                    "author": f"@{username}",
                    "created_at": tweet.get("created_at"),
                    "public_metrics": tweet.get("public_metrics", {}),
                })

            return tweets

        except requests.exceptions.Timeout:
            raise requests.RequestException("X API request timed out (30s)")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                raise requests.RequestException("X API rate limit exceeded")
            elif e.response.status_code == 401:
                raise requests.RequestException("X API authentication failed (invalid bearer token)")
            elif e.response.status_code == 403:
                raise requests.RequestException("X API access forbidden (insufficient permissions)")
            else:
                raise requests.RequestException(f"X API error ({e.response.status_code}): {e.response.text}")
        except requests.exceptions.RequestException as e:
            raise requests.RequestException(f"Network error: {str(e)}")

    def score_sentiment(self, text: str) -> Tuple[float, str]:
        """
        Score sentiment of a single tweet text

        Args:
            text: Tweet text to analyze

        Returns:
            Tuple of (sentiment_score: float [-1.0 to 1.0], reasoning: str)
        """
        if not text or len(text.strip()) == 0:
            return 0.0, "Empty text"

        text_lower = text.lower()
        score = 0.0
        reasoning_parts = []
        keyword_hits = []

        # Check bearish keywords
        for keyword, weight in self.BEARISH_KEYWORDS.items():
            if keyword in text_lower:
                score += weight
                keyword_hits.append((keyword, weight))

        # Check bullish keywords
        for keyword, weight in self.BULLISH_KEYWORDS.items():
            if keyword in text_lower:
                score += weight
                keyword_hits.append((keyword, weight))

        # Clamp score to [-1.0, 1.0]
        score = max(-1.0, min(1.0, score))

        # Build reasoning string
        if keyword_hits:
            # Sort by absolute weight (strongest signals first)
            keyword_hits.sort(key=lambda x: abs(x[1]), reverse=True)
            # Show top 3 signals
            top_hits = keyword_hits[:3]
            reasoning = "Keywords: " + ", ".join(
                [f"{kw} ({weight:+.2f})" for kw, weight in top_hits]
            )
        else:
            reasoning = "No strong sentiment signals detected"

        return score, reasoning

    def score_batch(self, tweets: List[Dict]) -> List[Dict]:
        """
        Score sentiment for a batch of tweets

        Args:
            tweets: List of tweet dictionaries (from fetch_tweets)

        Returns:
            List of SentimentResult dictionaries with scores and reasoning
        """
        if not tweets:
            return []

        results = []
        for tweet in tweets:
            sentiment_score, reasoning = self.score_sentiment(tweet["text"])

            result = SentimentResult(
                timestamp=tweet.get("created_at", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
                tweet_id=tweet["id"],
                author=tweet["author"],
                text=tweet["text"],
                sentiment_score=sentiment_score,
                reasoning=reasoning,
            )

            results.append(result.to_dict())

        return results

    def analyze(
        self,
        query: str,
        max_results: int = 100
    ) -> Dict:
        """
        End-to-end analysis: fetch tweets and score sentiment

        Args:
            query: Search query (e.g., "Bitcoin price prediction")
            max_results: Number of tweets to fetch (1-100)

        Returns:
            Dictionary with:
            - timestamp: Analysis timestamp
            - query: Original search query
            - tweets_fetched: Number of tweets fetched
            - average_sentiment: Mean sentiment across all tweets
            - sentiment_distribution: Distribution of scores
            - results: List of individual tweet scores
        """
        tweets = self.fetch_tweets(query, max_results)
        scored_tweets = self.score_batch(tweets)

        if not scored_tweets:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "query": query,
                "tweets_fetched": 0,
                "average_sentiment": 0.0,
                "sentiment_distribution": {
                    "very_bearish": 0,
                    "bearish": 0,
                    "neutral": 0,
                    "bullish": 0,
                    "very_bullish": 0,
                },
                "results": [],
            }

        # Calculate statistics
        scores = [r["sentiment_score"] for r in scored_tweets]
        avg_sentiment = sum(scores) / len(scores)

        # Distribution
        distribution = {
            "very_bearish": sum(1 for s in scores if s < -0.5),  # < -0.5
            "bearish": sum(1 for s in scores if -0.5 <= s < 0.0),  # -0.5 to 0
            "neutral": sum(1 for s in scores if s == 0.0),  # exactly 0
            "bullish": sum(1 for s in scores if 0.0 < s <= 0.5),  # 0 to 0.5
            "very_bullish": sum(1 for s in scores if s > 0.5),  # > 0.5
        }

        return {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "query": query,
            "tweets_fetched": len(scored_tweets),
            "average_sentiment": round(avg_sentiment, 3),
            "sentiment_distribution": distribution,
            "results": scored_tweets,
        }


# Example usage
if __name__ == "__main__":
    # Example with placeholder token (won't work without real X API key)
    token = "placeholder_bearer_token_from_env"

    try:
        scorer = XSentimentScorer(token)
        print("✅ XSentimentScorer initialized successfully")

        # Example sentiment scoring (no API call, local only)
        example_tweets = [
            {
                "id": "1234567890",
                "text": "Bitcoin breaking out above $50k! Major bullish momentum 🚀",
                "author": "@analyst",
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
            {
                "id": "1234567891",
                "text": "Crypto market crash concerns rising. Liquidation fears growing 😟",
                "author": "@trader",
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
            {
                "id": "1234567892",
                "text": "Bitcoin analysis: Trading sideways between $45k-$50k",
                "author": "@technical",
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
        ]

        results = scorer.score_batch(example_tweets)
        print("\n📊 Sentiment Scoring Results:")
        print(json.dumps(results, indent=2))

        # Calculate average sentiment
        if results:
            avg_score = sum(r["sentiment_score"] for r in results) / len(results)
            print(f"\n📈 Average Sentiment: {avg_score:+.3f}")
            print(f"   Interpretation: {'🟢 BULLISH' if avg_score > 0.2 else '🔴 BEARISH' if avg_score < -0.2 else '⚪ NEUTRAL'}")

    except ValueError as e:
        print(f"❌ Error: {e}")
