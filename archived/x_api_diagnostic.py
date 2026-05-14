#!/usr/bin/env python3
"""
X API Diagnostic Script
Helps troubleshoot connection and authentication issues
"""

import os
import sys
import json
import requests
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s: %(message)s')

def debug_env_loading():
    """
    Detailed environment variable debugging
    """
    print("🔍 Debugging Environment Variable Loading:")
    print("-" * 50)
    
    # Try multiple methods of loading
    print("1. Direct os.getenv:")
    print(f"   X_BEARER_TOKEN: {os.getenv('X_BEARER_TOKEN')}")
    
    print("\n2. Explicit .env loading:")
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    print(f"   ENV File Path: {env_path}")
    print(f"   ENV File Exists: {os.path.exists(env_path)}")
    
    load_dotenv(env_path, override=True)
    
    print("\n3. After dotenv loading:")
    print(f"   X_BEARER_TOKEN: {os.getenv('X_BEARER_TOKEN')}")
    print(f"   Token Length: {len(os.getenv('X_BEARER_TOKEN', ''))}")
    
    print("\n4. Full Environment:")
    for key, value in os.environ.items():
        if 'TOKEN' in key or 'API' in key:
            print(f"   {key}: {value}")

def test_x_api_connection(bearer_token):
    """
    Comprehensive test of X API connection
    
    :param bearer_token: X API Bearer Token
    :return: Detailed connection test results
    """
    # Define test configurations
    base_url = 'https://api.twitter.com/2'
    test_queries = ['Bitcoin', 'Crypto', 'BTC-USD']
    
    # Detailed test results
    results = {
        'token_length': len(bearer_token),
        'token_prefix': bearer_token[:10],
        'tests': {}
    }
    
    # Headers for API requests
    headers = {
        'Authorization': f'Bearer {bearer_token}',
        'User-Agent': 'CryptoBot-X-API-Diagnostic/1.0'
    }
    
    # Test each query
    for query in test_queries:
        params = {
            'query': query,
            'max_results': 10,
            'tweet.fields': 'created_at,public_metrics',
            'expansions': 'author_id'
        }
        
        try:
            # Attempt to fetch tweets
            response = requests.get(f'{base_url}/tweets/search/recent', 
                                    headers=headers, 
                                    params=params, 
                                    timeout=10)
            
            # Log detailed response information
            results['tests'][query] = {
                'status_code': response.status_code,
                'success': response.status_code == 200,
                'response_headers': dict(response.headers),
                'tweet_count': 0
            }
            
            if response.status_code == 200:
                data = response.json()
                results['tests'][query]['tweet_count'] = len(data.get('data', []))
            else:
                results['tests'][query]['error_text'] = response.text
        
        except requests.exceptions.RequestException as e:
            results['tests'][query] = {
                'status_code': None,
                'success': False,
                'error': str(e)
            }
    
    return results

def main():
    # Debug environment variable loading
    debug_env_loading()
    
    # Load bearer token from .env
    bearer_token = os.getenv('X_BEARER_TOKEN')
    
    if not bearer_token:
        print("❌ No X Bearer Token found in environment variables.")
        sys.exit(1)
    
    # Run diagnostic
    diagnostic_results = test_x_api_connection(bearer_token)
    
    # Print results
    print("\n🔍 X API Connection Diagnostic")
    print("=" * 40)
    print(f"Token Length: {diagnostic_results['token_length']}")
    print(f"Token Prefix: {diagnostic_results['token_prefix']}")
    print("\nTest Results:")
    
    for query, test_result in diagnostic_results['tests'].items():
        print(f"\n{query} Query:")
        print(f"  Status Code: {test_result.get('status_code', 'N/A')}")
        print(f"  Success: {test_result.get('success', False)}")
        if not test_result.get('success', False):
            print(f"  Error: {test_result.get('error', test_result.get('error_text', 'Unknown error'))}")
        if test_result.get('tweet_count') is not None:
            print(f"  Tweet Count: {test_result['tweet_count']}")
    
    if all(test.get('success', False) for test in diagnostic_results['tests'].values()):
        print("\n✅ All X API tests passed successfully!")
    else:
        print("\n❌ Some X API tests failed. Check the details above.")

if __name__ == '__main__':
    main()