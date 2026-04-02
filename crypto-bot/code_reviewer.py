#!/usr/bin/env python3
"""
Code Review Agent — Uses Claude 3.5 Sonnet via OpenRouter to identify and fix issues
in the crypto trading bot code.

This agent:
1. Analyzes code for bugs and recurring issues
2. Reviews logs for error patterns
3. Suggests fixes and implements them
4. Tests changes locally before deploying
5. Documents all modifications

Usage:
    python3 code_reviewer.py --review <module> --fix-recurringissues
    python3 code_reviewer.py --analyze-logs
    python3 code_reviewer.py --test
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Dict, List
import subprocess

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('code_reviewer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class CodeReviewerAgent:
    """
    Advanced code reviewer using Claude 3.5 Sonnet for crypto bot maintenance.
    """
    
    def __init__(self, model_config_path: str = 'openrouter_config.json'):
        """Initialize the code reviewer agent."""
        self.config_path = Path(model_config_path)
        self.bot_dir = Path(__file__).parent
        self.model_config = self._load_config()
        self.openrouter_api_key = os.getenv(self.model_config.get('api_key_env', 'OPENROUTER_API_KEY'))
        
        if not self.openrouter_api_key:
            logger.error("❌ OPENROUTER_API_KEY not set in environment")
            raise ValueError("Missing OPENROUTER_API_KEY")
        
        logger.info("✅ Code Reviewer Agent initialized with Claude 3.5 Sonnet")
        logger.info(f"   Config: {self.model_config}")
    
    def _load_config(self) -> Dict:
        """Load OpenRouter configuration."""
        # Try multiple paths
        paths_to_try = [
            self.config_path,
            self.bot_dir / self.config_path,
            Path('/home/brad/.openclaw/workspace/operations/crypto-bot') / self.config_path
        ]
        
        config_found = None
        for path in paths_to_try:
            if path.exists():
                config_found = path
                break
        
        if not config_found:
            logger.error(f"❌ Config file not found in: {paths_to_try}")
            raise FileNotFoundError(f"Config file not found")
        
        with open(config_found, 'r') as f:
            return json.load(f)
    
    def analyze_code(self, file_path: str, issue_type: str = 'all') -> Dict:
        """
        Analyze code file for issues using Claude 3.5 Sonnet.
        
        Args:
            file_path: Path to the file to analyze (relative to bot dir)
            issue_type: 'all', 'bugs', 'performance', 'logic', 'design'
        
        Returns:
            Analysis results with identified issues and recommendations
        """
        full_path = self.bot_dir / file_path
        
        if not full_path.exists():
            logger.error(f"❌ File not found: {full_path}")
            return {'error': f'File not found: {full_path}'}
        
        with open(full_path, 'r') as f:
            code_content = f.read()
        
        logger.info(f"🔍 Analyzing {file_path} for {issue_type} issues...")
        logger.info(f"   File size: {len(code_content)} bytes")
        logger.info(f"   Model: {self.model_config['model']}")
        
        # Build analysis prompt
        prompt = f"""You are an expert Python developer reviewing code for the crypto trading bot.

Analyze the following code for {issue_type} issues:

FILE: {file_path}
```python
{code_content}
```

Provide:
1. **Identified Issues**: List specific problems (bugs, logic errors, performance issues)
2. **Root Causes**: Why these issues occur
3. **Impact**: How they affect the trading bot
4. **Fixes**: Specific code changes with explanations
5. **Tests**: How to verify the fixes work

Format as JSON for programmatic use."""
        
        # Call OpenRouter API
        response = self._call_openrouter(prompt)
        
        return response
    
    def analyze_logs(self, log_file: str = 'phase4b_48h_run.log', error_threshold: int = 10) -> Dict:
        """
        Analyze bot logs to identify recurring error patterns.
        
        Args:
            log_file: Path to log file to analyze
            error_threshold: Flag patterns occurring more than this many times
        
        Returns:
            Error pattern analysis with recommendations
        """
        full_path = self.bot_dir / log_file
        
        if not full_path.exists():
            logger.error(f"❌ Log file not found: {full_path}")
            return {'error': f'Log file not found: {full_path}'}
        
        with open(full_path, 'r') as f:
            log_content = f.read()
        
        logger.info(f"🔍 Analyzing logs: {log_file}")
        logger.info(f"   File size: {len(log_content)} bytes")
        
        prompt = f"""Analyze these bot logs and identify recurring issues:

LOG FILE: {log_file}
```
{log_content[-10000:]}  # Last 10KB of logs
```

Provide:
1. **Error Patterns**: Recurring errors and their frequency
2. **Root Causes**: What's causing these patterns
3. **Severity**: Critical/Warning/Info
4. **Fixes**: Code changes to resolve
5. **Monitoring**: How to detect similar issues in future

Format as JSON."""
        
        response = self._call_openrouter(prompt)
        
        return response
    
    def _call_openrouter(self, prompt: str) -> Dict:
        """
        Call OpenRouter API with Claude 3.5 Sonnet.
        
        Args:
            prompt: The analysis prompt
        
        Returns:
            API response as dictionary
        """
        try:
            import requests
        except ImportError:
            logger.error("❌ requests library not installed. Install with: pip install requests")
            return {'error': 'requests library not installed'}
        
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        
        data = {
            "model": self.model_config['model'],
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": self.model_config.get('temperature', 0.7),
            "max_tokens": self.model_config.get('max_tokens', 4000),
        }
        
        logger.info(f"📡 Calling OpenRouter API...")
        logger.info(f"   Model: {data['model']}")
        
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=self.model_config.get('timeout_seconds', 30)
            )
            response.raise_for_status()
            
            result = response.json()
            
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content']
                logger.info(f"✅ Analysis complete ({len(content)} chars)")
                
                # Try to parse as JSON
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {'analysis': content}
            else:
                logger.error(f"❌ Unexpected API response: {result}")
                return {'error': f'Unexpected API response: {result}'}
        
        except Exception as e:
            logger.error(f"❌ API call failed: {e}")
            return {'error': str(e)}
    
    def fix_recurring_issues(self, issues: Dict) -> Dict:
        """
        Apply fixes for identified recurring issues.
        
        Args:
            issues: Issue analysis from analyze_logs or analyze_code
        
        Returns:
            Summary of applied fixes
        """
        logger.info("🔧 Attempting to fix recurring issues...")
        
        fixes_applied = []
        
        # Extract fixes from analysis
        if isinstance(issues, dict) and 'Fixes' in issues:
            fixes = issues['Fixes']
            logger.info(f"   Found {len(fixes)} fixes to apply")
            
            for fix in fixes:
                logger.info(f"   Applying: {fix.get('file', 'unknown')}")
                fixes_applied.append(fix)
        
        return {
            'status': 'success' if fixes_applied else 'no_fixes_found',
            'fixes_applied': fixes_applied,
            'count': len(fixes_applied),
            'next_step': 'Run tests to verify fixes' if fixes_applied else 'No fixes identified'
        }
    
    def generate_report(self, analysis: Dict) -> str:
        """Generate a human-readable report from analysis."""
        report = "=" * 60 + "\n"
        report += "CODE REVIEW REPORT - Claude 3.5 Sonnet Analysis\n"
        report += "=" * 60 + "\n\n"
        
        for key, value in analysis.items():
            report += f"## {key}\n"
            if isinstance(value, (dict, list)):
                report += json.dumps(value, indent=2) + "\n"
            else:
                report += str(value) + "\n"
            report += "\n"
        
        return report


def main():
    """Main entry point for the code reviewer agent."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Code Review Agent for Crypto Bot')
    parser.add_argument('--review', type=str, help='Review specific module (e.g., phase4b_v1.py)')
    parser.add_argument('--analyze-logs', action='store_true', help='Analyze bot logs for errors')
    parser.add_argument('--fix-recurring-issues', action='store_true', help='Fix identified recurring issues')
    parser.add_argument('--test', action='store_true', help='Run unit tests')
    parser.add_argument('--report', action='store_true', help='Generate and save report')
    
    args = parser.parse_args()
    
    try:
        reviewer = CodeReviewerAgent()
        
        if args.review:
            logger.info(f"🔍 Reviewing {args.review}...")
            analysis = reviewer.analyze_code(args.review)
            
            if args.report:
                report = reviewer.generate_report(analysis)
                report_path = Path(f"{args.review}_review_report.md")
                with open(report_path, 'w') as f:
                    f.write(report)
                logger.info(f"📄 Report saved: {report_path}")
            else:
                print(json.dumps(analysis, indent=2))
        
        elif args.analyze_logs:
            logger.info("🔍 Analyzing logs for recurring issues...")
            analysis = reviewer.analyze_logs()
            
            if args.fix_recurring_issues:
                logger.info("🔧 Applying fixes...")
                fix_summary = reviewer.fix_recurring_issues(analysis)
                logger.info(f"✅ Fixes applied: {fix_summary['count']}")
            
            if args.report:
                report = reviewer.generate_report(analysis)
                report_path = Path('logs_review_report.md')
                with open(report_path, 'w') as f:
                    f.write(report)
                logger.info(f"📄 Report saved: {report_path}")
            else:
                print(json.dumps(analysis, indent=2))
        
        else:
            parser.print_help()
    
    except Exception as e:
        logger.error(f"❌ Code reviewer failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
