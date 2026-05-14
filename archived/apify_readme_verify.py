#!/usr/bin/env python3
"""
Verify Apify Actor README and Configuration
"""

import os
import requests
from dotenv import load_dotenv

def verify_apify_actor_details():
    # Load environment variables
    load_dotenv()
    
    # Apify API token
    api_token = os.getenv('APIFY_API_TOKEN')
    
    # Actor ID
    actor_id = 'oAuCIx3ItNrs2okjQ'
    
    # API endpoint
    base_url = 'https://api.apify.com/v2'
    
    try:
        # Fetch actor input schema
        input_schema_url = f'{base_url}/actors/{actor_id}/input-schema'
        headers = {
            'Authorization': f'Bearer {api_token}'
        }
        
        response = requests.get(input_schema_url, headers=headers)
        response.raise_for_status()
        
        # Parse and print input schema
        input_schema = response.json()
        print("Input Schema:")
        import json
        print(json.dumps(input_schema, indent=2))
    
    except requests.RequestException as e:
        print(f"Error fetching actor details: {e}")

if __name__ == '__main__':
    verify_apify_actor_details()