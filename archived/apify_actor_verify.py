#!/usr/bin/env python3
"""
Verify Apify Actor Configuration
"""

import os
import sys
import json
import logging
import requests
from dotenv import load_dotenv
from typing import Dict, Any

class ApifyActorVerifier:
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Apify configuration
        self.api_token = os.getenv('APIFY_API_TOKEN')
        self.base_url = 'https://api.apify.com/v2'
    
    def verify_actor_details(self, actor_id: str) -> Dict[str, Any]:
        """
        Verify details of a specific Apify actor
        """
        try:
            # URL to fetch actor details
            url = f"{self.base_url}/actors/{actor_id}"
            
            # Prepare request parameters
            params = {
                'token': self.api_token
            }
            
            # Make request
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            # Parse response
            actor_details = response.json()
            
            # Print detailed information
            print("Actor Details:")
            print(json.dumps(actor_details, indent=2))
            
            return actor_details
        
        except requests.RequestException as e:
            print(f"Error fetching actor details: {e}")
            return {'error': str(e)}
    
    def test_actor_run(self, actor_id: str, input_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Test running the actor with a specific configuration
        """
        try:
            # URL to start actor run
            url = f"{self.base_url}/acts/{actor_id}/runs"
            
            # Prepare request parameters
            params = {
                'token': self.api_token
            }
            
            # Make request to start run
            response = requests.post(url, json=input_config, params=params)
            response.raise_for_status()
            
            # Parse response
            run_details = response.json()
            
            # Print run details
            print("\nActor Run Details:")
            print(json.dumps(run_details, indent=2))
            
            return run_details
        
        except requests.RequestException as e:
            print(f"Error starting actor run: {e}")
            return {'error': str(e)}

def main():
    # Actor ID from the console URL
    actor_id = 'oAuCIx3ItNrs2okjQ'
    
    # Initialize verifier
    verifier = ApifyActorVerifier()
    
    # Verify actor details
    verifier.verify_actor_details(actor_id)
    
    # Example input configuration (adjust based on actor's readme)
    input_config = {
        "startUrls": [
            {"url": "https://www.reddit.com/r/CryptoCurrency/top/"},
            {"url": "https://www.reddit.com/r/Bitcoin/top/"}
        ],
        "searchQueries": ["bitcoin", "crypto trading"],
        "mode": "posts",
        "maxRequestsPerCrawl": 10
    }
    
    # Test actor run
    verifier.test_actor_run(actor_id, input_config)

if __name__ == '__main__':
    main()