#!/usr/bin/env python3
"""
Cryptocurrency Sentiment Analysis Test Harness

Comprehensive validation of sentiment retrieval with advanced diagnostic capabilities
"""

import os
import sys
import json
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, Optional

# Ensure the current directory is in the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import dependencies with explicit error handling
try:
    from dotenv import load_dotenv
    import requests
except ImportError as e:
    print(f"Critical Import Error: {e}")
    sys.exit(1)

class DiagnosticSentimentTestHarness:
    """
    Advanced Sentiment Analysis Test Framework with Comprehensive Diagnostics
    """
    
    def __init__(self, 
                 log_path: str = '/home/brad/.openclaw/workspace/operations/crypto-bot/logs/sentiment_diagnostic.log'):
        """
        Initialize test harness with advanced logging and diagnostic capabilities
        
        Args:
            log_path (str): Detailed diagnostic log file path
        """
        # Ensure log directory exists
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        
        # Configure multilevel logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_path, mode='w'),  # Overwrite log on each run
                logging.StreamHandler(sys.stdout)  # Console output
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Environment variable loading with explicit tracking
        self.logger.info("Initializing Sentiment Test Harness")
        self._load_environment_variables()
    
    def _load_environment_variables(self):
        """
        Load and validate environment variables with comprehensive logging
        """
        try:
            # Load .env file
            load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
            
            # Track loaded environment variables (masking sensitive parts)
            env_vars = [
                'APIFY_USER_ID', 
                'X_API_TOKEN', 
                'NEWS_API_KEY'
            ]
            
            for var in env_vars:
                value = os.getenv(var)
                # Log presence without revealing full value
                self.logger.info(f"ENV: {var} - {'PRESENT' if value else 'MISSING'}")
        
        except Exception as e:
            self.logger.error(f"Environment Variable Loading Error: {e}")
            self.logger.error(traceback.format_exc())
    
    def run_comprehensive_diagnostic(self) -> Dict[str, Any]:
        """
        Execute comprehensive diagnostic test with multiple validation stages
        
        Returns:
            Detailed diagnostic report
        """
        diagnostic_report = {
            'timestamp': datetime.utcnow().isoformat(),
            'stages': {}
        }
        
        try:
            # Stage 1: Environment Validation
            diagnostic_report['stages']['environment'] = self._validate_environment()
            
            # Stage 2: Import Validation
            diagnostic_report['stages']['imports'] = self._validate_imports()
            
            # Stage 3: Credential Check
            diagnostic_report['stages']['credentials'] = self._validate_credentials()
            
        except Exception as e:
            self.logger.critical(f"Diagnostic Run Failed: {e}")
            diagnostic_report['error'] = {
                'type': type(e).__name__,
                'message': str(e),
                'traceback': traceback.format_exc()
            }
        
        # Log and return diagnostic report
        self.logger.info(f"Diagnostic Report: {json.dumps(diagnostic_report, indent=2)}")
        return diagnostic_report
    
    def _validate_environment(self) -> Dict[str, Any]:
        """
        Validate Python environment and current working context
        
        Returns:
            Environment validation details
        """
        return {
            'python_version': sys.version,
            'python_executable': sys.executable,
            'current_directory': os.getcwd(),
            'script_directory': os.path.dirname(os.path.abspath(__file__))
        }
    
    def _validate_imports(self) -> Dict[str, bool]:
        """
        Check critical module imports
        
        Returns:
            Import validation status
        """
        modules_to_check = {
            'dotenv': False,
            'requests': False,
            'apify_client': False
        }
        
        for module in modules_to_check:
            try:
                __import__(module)
                modules_to_check[module] = True
                self.logger.info(f"Module Import Success: {module}")
            except ImportError:
                self.logger.warning(f"Module Import Failed: {module}")
        
        return modules_to_check
    
    def _validate_credentials(self) -> Dict[str, bool]:
        """
        Check if critical API credentials are present
        
        Returns:
            Credential presence validation
        """
        credentials = {
            'APIFY_USER_ID': bool(os.getenv('APIFY_USER_ID')),
            'APIFY_API_TOKEN': bool(os.getenv('APIFY_API_TOKEN')),
            'X_API_TOKEN': bool(os.getenv('X_API_TOKEN')),
            'NEWS_API_KEY': bool(os.getenv('NEWS_API_KEY'))
        }
        
        # Log credential status
        for cred, status in credentials.items():
            self.logger.info(f"Credential Check - {cred}: {'PRESENT' if status else 'MISSING'}")
        
        return credentials

def main():
    """
    Execute diagnostic test harness
    """
    harness = DiagnosticSentimentTestHarness()
    diagnostic_results = harness.run_comprehensive_diagnostic()
    
    # Print results with clear formatting
    print(json.dumps(diagnostic_results, indent=2))

if __name__ == '__main__':
    main()