#!/usr/bin/env python3
"""
Direct Reddit JSON API Fetcher

Fallback for when Apify is unavailable or consistently failing (403s).
Uses Reddit's public JSON endpoints with proper rate limiting and User-Agent.
"""

import logging
import time
import requests
from typing import List, Optional, Dict, Any
from nltk.sentiment.vader import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)


class DirectRedditFetcher:
    """
    Fetches Reddit posts directly via public JSON API.
    Designed as a reliable fallback for the crypto sentiment system.
    """

    def __init__(self):
        self.session = requests.Session()
        # Reddit requires a descriptive, non-default User-Agent
        self.session.headers.update({
            "User-Agent": "HermesTradeBot/1.0 (by u/hermestradebot) - Crypto Sentiment"
        })
        self.base_url = "https://www.reddit.com"

    def fetch_pair_sentiment(
        self, 
        pair: str, 
        subreddits: Optional[List[str]] = None
    ) -> float:
        """
        Fetch and score sentiment for a trading pair.
        Returns a score between -1.0 and 1.0.
        """
        if subreddits is None:
            subreddits = ["CryptoCurrency", "Bitcoin", "ethereum"]

        keywords = self._get_keywords_for_pair(pair)
        all_posts: List[Dict[str, Any]] = []

        for subreddit in subreddits:
            for keyword in keywords[:1]:  # Limit to avoid rate limits
                try:
                    posts = self._fetch_posts(subreddit, keyword)
                    all_posts.extend(posts)
                    time.sleep(1.2)  # Respect Reddit rate limits
                except Exception as e:
                    logger.debug(f"Direct fetch error r/{subreddit} {keyword}: {e}")
                    continue

        if not all_posts:
            logger.warning(f"No posts found via direct Reddit for {pair}")
            return 0.0

        return self._calculate_sentiment(all_posts)

    def _get_keywords_for_pair(self, pair: str) -> List[str]:
        mapping = {
            "BTC-USD": ["bitcoin", "btc"],
            "ETH-USD": ["ethereum", "eth"],
            "SOL-USD": ["solana", "sol"],
            "XRP-USD": ["ripple", "xrp"],
            "DOGE-USD": ["dogecoin", "doge"],
            "ADA-USD": ["cardano", "ada"],
        }
        return mapping.get(pair, [pair.split("-")[0].lower()])

    def _fetch_posts(self, subreddit: str, keyword: str) -> List[Dict[str, Any]]:
        """Fetch posts using Reddit's search.json endpoint."""
        url = f"{self.base_url}/r/{subreddit}/search.json"
        params = {
            "q": keyword,
            "restrict_sr": "on",
            "sort": "new",
            "limit": 25,
        }

        resp = self.session.get(url, params=params, timeout=12)
        if resp.status_code != 200:
            logger.debug(f"Reddit returned {resp.status_code} for r/{subreddit}")
            return []

        data = resp.json()
        children = data.get("data", {}).get("children", [])
        return [child.get("data", {}) for child in children if "data" in child]

    def _calculate_sentiment(self, posts: List[Dict[str, Any]]) -> float:
        """VADER-based sentiment scoring (preferred for social media)."""
        if not posts:
            return 0.0

        scores = []
        for post in posts:
            text = post.get("title", "") + " " + post.get("selftext", "")
            if text.strip():
                compound = self.analyzer.polarity_scores(text)["compound"]
                scores.append(compound)

        if not scores:
            return 0.0

        return sum(scores) / len(scores)
