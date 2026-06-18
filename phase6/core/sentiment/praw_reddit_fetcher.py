#!/usr/bin/env python3
"""
PRAW Reddit Fetcher

Primary Reddit data source using the official Reddit API via PRAW.
This is the recommended production approach (OAuth-based, reliable).

Falls back to DirectRedditFetcher if PRAW is not configured.
"""

import logging
import os
from typing import List, Optional, Dict, Any

from nltk.sentiment.vader import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)


class PrawRedditFetcher:
    """
    Reddit fetcher using PRAW (official API).
    Requires Reddit app credentials (client_id, client_secret, user_agent).
    """

    def __init__(self):
        self.analyzer = SentimentIntensityAnalyzer()
        self.reddit = None
        self._init_praw()

    def _init_praw(self):
        """Initialize PRAW client if credentials are available."""
        try:
            import praw

            client_id = os.getenv("REDDIT_CLIENT_ID")
            client_secret = os.getenv("REDDIT_CLIENT_SECRET")
            user_agent = os.getenv("REDDIT_USER_AGENT", "HermesTradeBot/1.0")

            if not client_id or not client_secret:
                logger.warning("Reddit OAuth credentials not found. PRAW fetcher disabled.")
                return

            self.reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
            logger.info("PRAW Reddit client initialized successfully")

        except ImportError:
            logger.warning("PRAW not installed. Install with: pip install praw")
        except Exception as e:
            logger.error(f"Failed to initialize PRAW: {e}")

    def fetch_pair_sentiment(
        self, 
        pair: str, 
        subreddits: Optional[List[str]] = None
    ) -> float:
        """Fetch and score sentiment using PRAW."""
        if not self.reddit:
            return 0.0

        if subreddits is None:
            subreddits = ["CryptoCurrency", "Bitcoin", "ethereum"]

        keywords = self._get_keywords_for_pair(pair)
        all_scores = []

        try:
            for subreddit_name in subreddits:
                subreddit = self.reddit.subreddit(subreddit_name)
                for keyword in keywords[:1]:
                    submissions = subreddit.search(keyword, limit=20, sort="new")
                    for submission in submissions:
                        text = submission.title + " " + (submission.selftext or "")
                        if text.strip():
                            compound = self.analyzer.polarity_scores(text)["compound"]
                            all_scores.append(compound)
        except Exception as e:
            logger.warning(f"PRAW fetch error for {pair}: {e}")
            return 0.0

        if not all_scores:
            return 0.0

        return sum(all_scores) / len(all_scores)

    def _get_keywords_for_pair(self, pair: str) -> List[str]:
        mapping = {
            "BTC-USD": ["bitcoin", "btc"],
            "ETH-USD": ["ethereum", "eth"],
            "SOL-USD": ["solana", "sol"],
            "XRP-USD": ["ripple", "xrp"],
            "DOGE-USD": ["dogecoin", "doge"],
        }
        return mapping.get(pair, [pair.split("-")[0].lower()])
