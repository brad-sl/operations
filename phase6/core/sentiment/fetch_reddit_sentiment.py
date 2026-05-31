#!/usr/bin/env python3
"""
Reddit Sentiment Fetcher (Production)
Uses TwqHBuZZPHJxiQrTU with native sentiment when available,
falls back to keyword scoring.
"""

import logging
import os
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

try:
    from apify_client import ApifyClient
    APIFY_AVAILABLE = True
except Exception:
    APIFY_AVAILABLE = False
    ApifyClient = None

logger = logging.getLogger(__name__)

REDDIT_CACHE_FILE = Path(__file__).parent / 'reddit_sentiment_cache.json'
APIFY_API_TOKEN = os.getenv('APIFY_API_TOKEN')

# Production actor with best parameters found
REDDIT_ACTOR_ID = 'TwqHBuZZPHJxiQrTU'

BULLISH_KEYWORDS = [
    'moon', 'pump', 'buy', 'bull', 'gain', 'surge', 'hodl', 'strong',
    'opportunity', 'gem', 'rocket', 'green', 'up', 'ath'
]
BEARISH_KEYWORDS = [
    'crash', 'dump', 'sell', 'bear', 'loss', 'scam', 'rug', 'warning',
    'red', 'down', 'dip', 'fear'
]

PAIR_KEYWORDS = {
    'BTC-USD': ['bitcoin', 'btc'],
    'ETH-USD': ['ethereum', 'eth'],
    'SOL-USD': ['solana', 'sol'],
    'XRP-USD': ['ripple', 'xrp'],
    'DOGE-USD': ['dogecoin', 'doge'],
    'ADA-USD': ['cardano', 'ada'],
}


def _normalize_post(post):
    """Handle both string and dict output from the actor."""
    if isinstance(post, str):
        return {"title": post, "body": "", "score": 0}
    if not isinstance(post, dict):
        return {"title": "", "body": "", "score": 0}
    return {
        "title": str(post.get("title") or post.get("query") or ""),
        "body": str(post.get("body") or post.get("selftext") or ""),
        "score": int(post.get("score") or 0),
    }


def _calculate_sentiment(posts):
    """Keyword-based fallback scorer."""
    if not posts:
        return 0.0

    total = 0.0
    count = 0

    for p in posts:
        p = _normalize_post(p)
        text = (p["title"] + " " + p["body"]).lower()
        bull = sum(1 for w in BULLISH_KEYWORDS if w in text)
        bear = sum(1 for w in BEARISH_KEYWORDS if w in text)
        if bull + bear > 0:
            total += (bull - bear) / (bull + bear)
            count += 1

    return round(total / count, 4) if count > 0 else 0.0


class RedditSentimentFetcher:
    def __init__(self):
        self.client = None
        if not APIFY_AVAILABLE or not APIFY_API_TOKEN:
            logger.warning("Apify not available")
            return
        try:
            self.client = ApifyClient(APIFY_API_TOKEN)
        except Exception as e:
            logger.error(f"Apify init failed: {e}")

    def fetch_pair(self, pair):
        if not self.client:
            return 0.0

        keywords = PAIR_KEYWORDS.get(pair, [pair.split('-')[0].lower()])
        keyword = keywords[0]

        run_input = {
            "queries": [keyword],
            "subredditName": "CryptoCurrency",
            "sort": "relevance",
            "timeframe": "week",
            "maxPosts": 20,
            "sentiment_analysis": True,
            "scrapeComments": False,
            "maximize_coverage": True,
        }

        try:
            run = self.client.actor(REDDIT_ACTOR_ID).call(run_input=run_input)
            output = getattr(run, "output", {}) or {}
            items = output.get("results", [])

            # Try native sentiment first
            scores = []
            for item in items:
                if isinstance(item, dict):
                    if "sentiment_score_normalized" in item:
                        scores.append(float(item["sentiment_score_normalized"]))
                    elif "sentiment_label" in item:
                        label = str(item["sentiment_label"]).lower()
                        if label == "positive":
                            scores.append(0.75)
                        elif label == "negative":
                            scores.append(-0.75)

            if scores:
                return round(sum(scores) / len(scores), 4)

            # Fallback
            return _calculate_sentiment(items)

        except Exception as e:
            logger.warning(f"Reddit fetch failed for {pair}: {e}")
            return 0.0

    def run(self):
        results = {}
        for pair in PAIR_KEYWORDS:
            score = self.fetch_pair(pair)
            results[pair] = score
            logger.info(f"{pair}: {score}")
        return results


def save_cache(sentiments):
    cache = {
        pair: {
            "sentiment": score,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": "TwqHBuZZPHJxiQrTU + fallback"
        }
        for pair, score in sentiments.items()
    }
    with open(REDDIT_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)
    return cache


def main():
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Reddit sentiment (TwqHBuZZPHJxiQrTU)")

    fetcher = RedditSentimentFetcher()
    sentiments = fetcher.run()

    if sentiments:
        cache = save_cache(sentiments)
        print(json.dumps(cache, indent=2))


if __name__ == "__main__":
    main()