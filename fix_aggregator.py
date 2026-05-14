#!/usr/bin/env python3
import json

with open('/home/brad/.openclaw/workspace/operations/crypto-bot/sentiment_aggregator.py', 'r') as f:
    content = f.read()

# Replace the fetch function with a working version
old_fetch = '''def fetch_x_sentiment_batch_optimized() -> Dict[str, Any]:
    """
    Fetch X sentiment using optimized batch queries.
    Calls fetch_x_sentiment.py which handles:
    - Single OR query instead of 6 separate calls
    - Keyword distribution across pairs
    - Batch chunking if needed
    """
    try:
        result = subprocess.run(
            [
                '/home/brad/.openclaw/workspace/operations/crypto-bot/venv/bin/python3',
                '/home/brad/.openclaw/workspace/operations/crypto-bot/fetch_x_sentiment.py'
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd='/home/brad/.openclaw/workspace/operations/crypto-bot'
        )
        
        if result.returncode == 0:
            # Parse JSON from output (last valid JSON block)
            lines = result.stdout.split('\n')
            for line in reversed(lines):
                if line.strip().startswith('{'):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        pass
        
        print(f"⚠️ X sentiment fetch failed: {result.stderr}")
        return {}
    
    except Exception as e:
        print(f"❌ Error fetching X sentiment: {e}")
        return {}'''

new_fetch = '''def fetch_x_sentiment_batch_optimized() -> Dict[str, Any]:
    """
    Fetch X sentiment using optimized batch queries.
    Calls fetch_x_sentiment.py which handles:
    - Single OR query instead of 6 separate calls
    - Keyword distribution across pairs
    - Batch chunking if needed
    """
    try:
        result = subprocess.run(
            [
                '/home/brad/.openclaw/workspace/operations/crypto-bot/venv/bin/python3',
                '/home/brad/.openclaw/workspace/operations/crypto-bot/fetch_x_sentiment.py'
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd='/home/brad/.openclaw/workspace/operations/crypto-bot'
        )
        
        if result.returncode == 0:
            # Extract JSON from stdout (look for sentiment cache block with BTC-USD key)
            try:
                lines = result.stdout.split('\n')
                for i, line in enumerate(lines):
                    if 'BTC-USD' in line and '{' in line:
                        # Found start of sentiment cache, collect until }
                        json_str = ''.join(lines[max(0, i-1):])
                        parsed = json.loads(json_str[:json_str.find('}')+1])
                        if 'BTC-USD' in parsed:
                            return parsed
            except:
                pass
            
            # Fallback: try parsing last complete JSON object
            try:
                idx = result.stdout.rfind('{')
                if idx >= 0:
                    return json.loads(result.stdout[idx:result.stdout.rfind('}')+1])
            except:
                pass
        
        return {}
    
    except Exception as e:
        print(f"❌ Error fetching X sentiment: {e}")
        return {}'''

content = content.replace(old_fetch, new_fetch)

with open('/home/brad/.openclaw/workspace/operations/crypto-bot/sentiment_aggregator.py', 'w') as f:
    f.write(content)

print("✅ Fixed sentiment_aggregator.py")
