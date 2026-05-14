#!/usr/bin/env python3
"""
Comprehensive Apify Reddit Scraper Diagnostic Tool
"""

import os
import sys
import json
import logging
import requests
import traceback
from datetime import datetime, timezone
from dotenv import load_dotenv
from typing import Dict, Any, List

class ApifyScraperDiagnostics:
    """
    Advanced Diagnostics for Apify Reddit Scraper
    """
    
    def __init__(self, log_path: str = '/home/brad/.openclaw/workspace/operations/crypto-bot/logs/apify_diagnostics.log'):
        """
        Initialize diagnostics with comprehensive logging
        """
        # Ensure log directory exists
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        
        # Configure logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s: %(message)s',
            handlers=[
                logging.FileHandler(log_path, mode='w'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Load environment variables
        load_dotenv()
        
        # Apify configuration
        self.api_token = os.getenv('APIFY_API_TOKEN')
        self.base_url = 'https://api.apify.com/v2'
    
    def verify_api_credentials(self) -> Dict[str, Any]:
        """
        Verify Apify API credentials and account status
        """
        try:
            # Attempt to get account info
            url = f"{self.base_url}/users/me"
            headers = {
                'Authorization': f'Bearer {self.api_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            account_info = response.json()
            
            self.logger.info("API Credentials Verified Successfully")
            return {
                'status': 'success',
                'account_id': account_info.get('id'),
                'username': account_info.get('username'),
                'plan': account_info.get('plan')
            }
        
        except requests.RequestException as e:
            self.logger.error(f"API Credential Verification Failed: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def list_available_actors(self) -> Dict[str, Any]:
        """
        List available actors, with special focus on Reddit scrapers
        """
        try:
            url = f"{self.base_url}/actors"
            params = {
                'token': self.api_token,
                'limit': 100  # Increase to see more actors
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            actors = response.json().get('data', {}).get('items', [])
            
            # Filter and log Reddit-related actors
            reddit_actors = [
                actor for actor in actors 
                if 'reddit' in actor.get('name', '').lower()
            ]
            
            self.logger.info(f"Total Actors: {len(actors)}")
            self.logger.info(f"Reddit-related Actors: {len(reddit_actors)}")
            
            # Detailed logging of Reddit actors
            for actor in reddit_actors:
                self.logger.info(f"Actor: {actor.get('name')}")
                self.logger.info(f"  Description: {actor.get('description', 'N/A')}")
                self.logger.info(f"  Public/Private: {'Public' if actor.get('isPublic') else 'Private'}")
            
            return {
                'status': 'success',
                'total_actors': len(actors),
                'reddit_actors': [actor.get('name') for actor in reddit_actors]
            }
        
        except requests.RequestException as e:
            self.logger.error(f"Actor Listing Failed: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def validate_reddit_scraper_configuration(self) -> Dict[str, Any]:
        """
        Validate the specific Reddit scraper configuration
        """
        try:
            # Payload to test configuration
            input_payload = {
                "startUrls": [
                    {"url": "https://www.reddit.com/r/CryptoCurrency/top/"},
                    {"url": "https://www.reddit.com/r/Bitcoin/top/"}
                ],
                "searchQueries": ["bitcoin", "crypto trading"],
                "mode": "posts",
                "maxRequestsPerCrawl": 10,
                "maxCrawlingDepth": 2,
                "proxyConfiguration": {
                    "useApifyProxy": True
                },
                "timeFilter": "week"
            }
            
            # Attempt to start the actor run
            url = f"{self.base_url}/acts/trudax~reddit-scraper-lite/runs"
            params = {
                'token': self.api_token
            }
            
            response = requests.post(url, json=input_payload, params=params)
            response.raise_for_status()
            
            run_result = response.json()
            
            # Extract and log run details
            run_id = run_result.get('data', {}).get('id')
            dataset_id = run_result.get('data', {}).get('defaultDatasetId')
            
            self.logger.info(f"Scraper Run Initiated: {run_id}")
            self.logger.info(f"Dataset ID: {dataset_id}")
            
            return {
                'status': 'success',
                'run_id': run_id,
                'dataset_id': dataset_id
            }
        
        except requests.RequestException as e:
            self.logger.error(f"Scraper Configuration Validation Failed: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def run_comprehensive_diagnostics(self) -> Dict[str, Any]:
        """
        Run full suite of diagnostics
        """
        diagnostics_results = {
            'credentials_check': self.verify_api_credentials(),
            'available_actors': self.list_available_actors(),
            'scraper_configuration': self.validate_reddit_scraper_configuration()
        }
        
        # Log comprehensive results
        self.logger.info("Comprehensive Diagnostics Completed")
        self.logger.info(json.dumps(diagnostics_results, indent=2))
        
        return diagnostics_results

def main():
    """
    Execute comprehensive Apify scraper diagnostics
    """
    # Initialize diagnostics
    diagnostics = ApifyScraperDiagnostics()
    
    # Run full diagnostic suite
    results = diagnostics.run_comprehensive_diagnostics()
    
    # Print results with formatting
    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()