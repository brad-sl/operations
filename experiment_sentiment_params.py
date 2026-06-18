#!/usr/bin/env python3
"""Experiment script to find parameter combo that triggers native sentiment fields"""

import os
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()
client = ApifyClient(os.getenv("APIFY_API_TOKEN"))

ACTOR_ID = "TwqHBuZZPHJxiQrTU"

def test_combo(name, run_input):
    print(f"\n=== Testing: {name} ===")
    try:
        run = client.actor(ACTOR_ID).call(run_input=run_input)
        output = getattr(run, "output", {}) or {}
        results = output.get("results", [])
        
        if not results:
            print("No results")
            return
        
        first = results[0]
        if isinstance(first, dict):
            has_sentiment = any(k.startswith("sentiment_") for k in first.keys())
            print(f"Items: {len(results)} | Has sentiment fields: {has_sentiment}")
            if has_sentiment:
                print("Keys with sentiment:", [k for k in first.keys() if k.startswith("sentiment_")])
                print("Sample sentiment_label:", first.get("sentiment_label"))
                print("Sample sentiment_score_normalized:", first.get("sentiment_score_normalized"))
        else:
            print(f"Items: {len(results)} | First item is string (no sentiment)")
    except Exception as e:
        print(f"Error: {e}")

# Test 1: Baseline (current)
test_combo("Baseline (relevance + week + sentiment)", {
    "queries": ["bitcoin"],
    "subredditName": "CryptoCurrency",
    "sort": "relevance",
    "timeframe": "week",
    "maxPosts": 10,
    "sentiment_analysis": True,
})

# Test 2: With maximize_coverage
test_combo("With maximize_coverage", {
    "queries": ["bitcoin"],
    "subredditName": "CryptoCurrency",
    "sort": "relevance",
    "timeframe": "week",
    "maxPosts": 10,
    "sentiment_analysis": True,
    "maximize_coverage": True,
})

# Test 3: scrapeComments + sentiment
test_combo("scrapeComments + sentiment", {
    "queries": ["bitcoin"],
    "subredditName": "CryptoCurrency",
    "sort": "relevance",
    "timeframe": "week",
    "maxPosts": 8,
    "scrapeComments": True,
    "maxComments": 15,
    "sentiment_analysis": True,
})

# Test 4: Higher volume
test_combo("Higher volume (maxPosts=25)", {
    "queries": ["bitcoin"],
    "subredditName": "CryptoCurrency",
    "sort": "relevance",
    "timeframe": "week",
    "maxPosts": 25,
    "sentiment_analysis": True,
})

print("\n=== Experiment complete ===")