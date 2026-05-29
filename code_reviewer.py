#!/usr/bin/env python3
"""
Enhanced Code Review Agent — Uses Claude 3.5 Sonnet via OpenRouter

Improvements:
- Smart/chunked file reading (avoids dumping entire large files)
- Context length error detection and graceful fallback
- --quick mode for lighter reviews (good for monitoring code)
- Better logging and token estimation
- More robust error handling

Usage:
    python3 code_reviewer.py --review <file> --quick
    python3 code_reviewer.py --review <file> --report
    python3 code_reviewer.py --analyze-logs
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
    Robust code reviewer using Claude 3.5 Sonnet via OpenRouter.
    """

    def __init__(self, model_config_path: str = 'openrouter_config.json'):
        self.config_path = Path(model_config_path)
        self.bot_dir = Path(__file__).parent
        self.model_config = self._load_config()
        self.openrouter_api_key = os.getenv(self.model_config.get('api_key_env', 'OPENROUTER_API_KEY'))

        if not self.openrouter_api_key:
            logger.error("❌ OPENROUTER_API_KEY not set")
            raise ValueError("Missing OPENROUTER_API_KEY")

        logger.info("✅ Code Reviewer Agent initialized")
        logger.info(f"   Model: {self.model_config.get('model')}")

    def _load_config(self) -> Dict:
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
            raise FileNotFoundError(f"Config file not found in: {paths_to_try}")

        with open(config_found, 'r') as f:
            return json.load(f)

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (1 token ≈ 4 chars for English/code)."""
        return len(text) // 3

    def _read_file_smart(self, file_path: Path, max_lines: int = 150, quick: bool = False) -> str:
        with open(file_path, 'r') as f:
            lines = f.readlines()

        total_lines = len(lines)
        if total_lines <= max_lines:
            return ''.join(lines)

        if quick:
            top_n, bottom_n = 25, 15
            max_middle, grab = 10, 8
        else:
            top_n, bottom_n = 60, 40
            max_middle, grab = 40, 15

        top = lines[:top_n]
        bottom = lines[-bottom_n:]

        middle = []
        start = len(top)
        end = len(lines) - len(bottom)
        for i, line in enumerate(lines[start:end]):
            if line.strip().startswith(('def ', 'class ', 'async def ')):
                middle.extend(lines[start + i:start + i + grab])
                if len(middle) > max_middle:
                    break

        result = ''.join(top)
        if middle:
            result += "\n# [key functions]\n" + ''.join(middle[:max_middle])
        result += "\n# [truncated]\n" + ''.join(bottom)

        logger.info(f"   Smart read: {total_lines} lines -> reduced to ~{len(result.splitlines())} lines")
        return result
    def analyze_code(self, file_path: str, quick: bool = False) -> Dict:
        """Analyze code with smart reading and better error handling."""
        full_path = self.bot_dir / file_path

        if not full_path.exists():
            return {'error': f'File not found: {full_path}'}

        code_content = self._read_file_smart(full_path, max_lines=50 if quick else 120, quick=quick)

        mode = "quick" if quick else "full"
        logger.info(f"🔍 Analyzing {file_path} ({mode} mode)")
        logger.info(f"   Size: {len(code_content)} chars (~{self._estimate_tokens(code_content)} tokens)")

        prompt = f"""You are an expert Python developer reviewing code for a crypto trading bot.

Analyze the following code for issues:

FILE: {file_path}
```python
{code_content}
```

Provide:
1. Identified Issues (bugs, logic, performance, monitoring)
2. Root Causes
3. Impact on the bot
4. Specific Fixes with code snippets
5. Tests to verify

Return as clean JSON."""

        try:
            response = self._call_openrouter(prompt, max_tokens=2500 if quick else 4500)
            return response
        except Exception as e:
            logger.error(f"❌ Analysis failed: {e}")
            return {'error': str(e)}

    def analyze_logs(self, log_file: str = 'phase4b_48h_run.log') -> Dict:
        full_path = self.bot_dir / log_file
        if not full_path.exists():
            return {'error': f'Log file not found: {full_path}'}

        with open(full_path, 'r') as f:
            log_content = f.read()[-8000:]  # Last 8KB

        prompt = f"""Analyze these crypto bot logs and find recurring issues:

LOG: {log_file}
```
{log_content}
```

Return JSON with: Error Patterns, Root Causes, Severity, Fixes."""

        return self._call_openrouter(prompt, max_tokens=4000)

    def _call_openrouter(self, prompt: str, max_tokens: int = 4000) -> Dict:
        import requests

        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": self.model_config['model'],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.model_config.get('temperature', 0.7),
            "max_tokens": max_tokens,
        }

        logger.info(f"📡 Calling OpenRouter ({data['model']}, max_tokens={max_tokens})")

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=self.model_config.get('timeout_seconds', 45)
            )
            response.raise_for_status()
            result = response.json()

            if 'choices' in result and result['choices']:
                content = result['choices'][0]['message'].get('content')
                if content:
                    logger.info(f"✅ Response received ({len(content)} chars)")
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return {'analysis': content}
                else:
                    return {'analysis': result['choices'][0]['message']}
            else:
                return {'error': 'Unexpected API response', 'raw': result}

        except requests.exceptions.HTTPError as e:
            if "context_length_exceeded" in str(e) or response.status_code == 400:
                logger.warning("⚠️ Context length exceeded. Try --quick mode or smaller file.")
            logger.error(f"❌ API error: {e}")
            return {'error': str(e)}
        except Exception as e:
            logger.error(f"❌ API call failed: {e}")
            return {'error': str(e)}

    def generate_report(self, analysis: Dict) -> str:
        report = "=" * 60 + "\n"
        report += "CODE REVIEW REPORT\n"
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
    import argparse

    parser = argparse.ArgumentParser(description='Enhanced Code Review Agent')
    parser.add_argument('--review', type=str, help='Review specific file')
    parser.add_argument('--quick', action='store_true', help='Use lighter review mode')
    parser.add_argument('--analyze-logs', action='store_true')
    parser.add_argument('--report', action='store_true')
    parser.add_argument('--fix-recurring-issues', action='store_true')

    args = parser.parse_args()

    try:
        reviewer = CodeReviewerAgent()

        if args.review:
            analysis = reviewer.analyze_code(args.review, quick=args.quick)

            if args.report:
                report = reviewer.generate_report(analysis)
                report_path = Path(f"{args.review}_review.md")
                with open(report_path, 'w') as f:
                    f.write(report)
                logger.info(f"📄 Report saved: {report_path}")
            else:
                print(json.dumps(analysis, indent=2))

        elif args.analyze_logs:
            analysis = reviewer.analyze_logs()
            print(json.dumps(analysis, indent=2))

        else:
            parser.print_help()

    except Exception as e:
        logger.error(f"❌ Reviewer failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()