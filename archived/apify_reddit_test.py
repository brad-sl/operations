#!/usr/bin/env python3
"""
Advanced Reddit Sentiment Data Retrieval and Analysis
Comprehensive Multi-Pair Sentiment Processing
"""

import os
import sys
import json
import logging
import traceback
import requests
import time
from datetime import datetime, UTC
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional
import pandas as pd
from textblob import TextBlob

class ApifyRedditSentimentAnalyzer:
    """
    Advanced Reddit Scraping and Sentiment Analysis Tool
    """
    
    def __init__(self, 
                 log_path: str = '/home/brad/.openclaw/workspace/operations/crypto-bot/logs/reddit_sentiment.log'):
        """
        Initialize comprehensive Reddit sentiment analyzer
        
        Args:
            log_path (str): Path to log file
        """
        # Configure logging
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s: %(message)s',
            handlers=[
                logging.FileHandler(log_path),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Load environment variables
        load_dotenv()
        
        # Apify configuration
        self.api_token = os.getenv('APIFY_API_TOKEN')
        self.base_url = 'https://api.apify.com/v2'
        
        # Trading pairs configuration
        self.trading_pairs = [
            'Bitcoin', 
            'Ethereum', 
            'Ripple', 
            'Cardano'
        ]
    
    def retrieve_dataset(self, dataset_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve dataset from Apify with execution time tracking
        """
        start_time = time.time()
        try:
            # Full URL for dataset items
            url = f"{self.base_url}/datasets/{dataset_id}/items"
            
            # Prepare request parameters
            params = {
                'token': self.api_token,
                'format': 'json'
            }
            
            # Make request
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            # Parse response
            response_data = response.json()
            
            # Log the raw response for debugging
            self.logger.debug(f"Raw Dataset Response: {json.dumps(response_data, indent=2)}")
            
            # Handle different possible response structures
            if isinstance(response_data, dict):
                # If response is a dict with 'data', extract items
                items = response_data.get('data', [])
            elif isinstance(response_data, list):
                # If response is directly a list of items
                items = response_data
            else:
                # Unexpected response format
                self.logger.warning(f"Unexpected response format: {type(response_data)}")
                items = []
            
            # Log items structure
            if items:
                self.logger.debug(f"First Item Structure: {json.dumps(items[0] if items else {}, indent=2)}")
            
            # Calculate retrieval time
            retrieval_time = time.time() - start_time
            
            self.logger.info(f"Dataset Retrieved: {len(items)} items in {retrieval_time:.2f} seconds")
            
            return items
        
        except requests.RequestException as e:
            self.logger.error(f"Dataset Retrieval Failed: {e}")
            return []

    def analyze_sentiment(self, items: List[Dict[str, Any]], pairs: List[str]) -> Dict[str, Any]:
        """
        Perform comprehensive sentiment analysis with pair-specific breakdown
        """
        # Log input items for diagnostic purposes
        self.logger.debug(f"Total Input Items: {len(items)}")
        
        # Flexible text extraction
        def extract_text(item: Dict[str, Any]) -> str:
            """
            Flexibly extract text from various possible item structures
            """
            possible_text_keys = ['title', 'text', 'comments', 'content', 'body']
            
            for key in possible_text_keys:
                if key in item and isinstance(item[key], str):
                    return item[key]
            
            # If no text found, convert entire item to string
            return str(item)
        
        # Create a list of text contents
        all_texts = [extract_text(item) for item in items]
        
        start_time = time.time()
        
        # Sentiment scoring function
        def get_sentiment_score(text: str) -> float:
            """
            Calculate sentiment using TextBlob
            """
            try:
                return TextBlob(text).sentiment.polarity
            except Exception:
                return 0.0
        
        # Compute sentiment scores
        sentiment_scores = [get_sentiment_score(text) for text in all_texts]
        
        # Overall sentiment analysis
        sentiment_analysis = {
            'total_items': len(items),
            'total_sentiment_samples': len(sentiment_scores),
            'avg_sentiment': sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0,
            'execution_time_seconds': time.time() - start_time,
            'sentiment_distribution': {
                'very_negative': sum(1 for s in sentiment_scores if s <= -0.6),
                'negative': sum(1 for s in sentiment_scores if -0.6 < s <= -0.2),
                'neutral': sum(1 for s in sentiment_scores if abs(s) <= 0.2),
                'positive': sum(1 for s in sentiment_scores if 0.2 < s <= 0.6),
                'very_positive': sum(1 for s in sentiment_scores if s > 0.6)
            }
        }
        
        # Save detailed results
        output_path = '/home/brad/.openclaw/workspace/operations/crypto-bot/logs/reddit_sentiment_analysis.json'
        with open(output_path, 'w') as f:
            json.dump(sentiment_analysis, f, indent=2)
        
        self.logger.info(f"Sentiment Analysis Complete. Results saved to {output_path}")
        
        return sentiment_analysis

    def execute_scrape(self, 
                       pairs: Optional[List[str]] = None,
                       search_terms: Optional[List[List[str]]] = None) -> Dict[str, Any]:
        """
        Execute comprehensive Reddit scraping for trading pairs
        """
        # Use default pairs if not provided
        pairs = pairs or self.trading_pairs
        
        # Prepare search terms if not provided
        if not search_terms:
            search_terms = []
            for pair in pairs:
                pair_terms = [
                    f"{pair.lower()} crypto trading", 
                    f"{pair.lower()} market analysis", 
                    f"{pair.lower()} investment discussion"
                ]
                search_terms.append(pair_terms)

        start_time = time.time()
        
        # Prepare input payload with refined parameters
        input_payload = {
            "startUrls": [
                {"url": "https://www.reddit.com/r/CryptoCurrency/top/"},
                {"url": "https://www.reddit.com/r/Bitcoin/top/"},
                {"url": "https://www.reddit.com/r/ethtrader/top/"},
                {"url": "https://www.reddit.com/r/CryptoTechnology/top/"}
            ],
            "searchQueries": [term for sublist in search_terms for term in sublist],
            "mode": "posts",
            "maxRequestsPerCrawl": 200,
            "maxCrawlingDepth": 3,
            "proxyConfiguration": {
                "useApifyProxy": True
            },
            "timeFilter": "week"
        }
        
        # Prepare API request
        request_params = {
            'token': self.api_token
        }
        
        try:
            # Execute scrape request
            self.logger.info(f"Initiating Reddit sentiment scrape for pairs: {pairs}")
            response = requests.post(
                f"{self.base_url}/acts/trudax~reddit-scraper-lite/runs", 
                json=input_payload, 
                params=request_params
            )
            
            # Check response
            response.raise_for_status()
            
            # Parse response
            scrape_result = response.json()
            
            # Extract run details
            run_id = scrape_result.get('data', {}).get('id')
            dataset_id = scrape_result.get('data', {}).get('defaultDatasetId')
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Construct comprehensive output
            output = {
                'status': 'success',
                'run_id': run_id,
                'dataset_id': dataset_id,
                'timestamp': datetime.now(UTC).isoformat(),
                'pairs': pairs,
                'search_terms': [term for sublist in search_terms for term in sublist],
                'execution_time_seconds': execution_time
            }
            
            self.logger.info(f"Scrape Initiated: {json.dumps(output, indent=2)}")
            
            return output
        
        except requests.RequestException as e:
            error_details = {
                'status': 'error',
                'error_type': type(e).__name__,
                'error_message': str(e),
                'traceback': traceback.format_exc(),
                'timestamp': datetime.now(UTC).isoformat(),
                'execution_time_seconds': time.time() - start_time
            }
            
            self.logger.error(f"Scrape Failed: {json.dumps(error_details, indent=2)}")
            return error_details
    
    def comprehensive_reddit_sentiment(self) -> Dict[str, Any]:
        """
        End-to-end Reddit sentiment retrieval and analysis
        """
        start_time = time.time()
        
        try:
            # Execute scrape
            scrape_result = self.execute_scrape()
            
            # Check for successful scrape
            if scrape_result.get('status') != 'success':
                return scrape_result
            
            # Retrieve dataset
            dataset_items = self.retrieve_dataset(scrape_result['dataset_id'])
            
            # Perform sentiment analysis
            sentiment_results = self.analyze_sentiment(dataset_items, self.trading_pairs)
            
            # Calculate total execution time
            total_execution_time = time.time() - start_time
            
            # Combine scrape and sentiment results
            final_results = {
                **scrape_result,
                'sentiment_analysis': sentiment_results,
                'total_execution_time_seconds': total_execution_time
            }
            
            return final_results
        
        except Exception as e:
            error_details = {
                'status': 'error',
                'error_type': type(e).__name__,
                'error_message': str(e),
                'traceback': traceback.format_exc(),
                'timestamp': datetime.now(UTC).isoformat(),
                'total_execution_time_seconds': time.time() - start_time
            }
            
            self.logger.error(f"Comprehensive Analysis Failed: {json.dumps(error_details, indent=2)}")
            return error_details

def main():
    """
    Execute comprehensive Reddit sentiment analysis
    """
    # Initialize sentiment analyzer
    analyzer = ApifyRedditSentimentAnalyzer()
    
    # Execute full sentiment workflow
    results = analyzer.comprehensive_reddit_sentiment()
    
    # Print results with clear formatting
    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()