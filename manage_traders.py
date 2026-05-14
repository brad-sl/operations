#!/usr/bin/env python3
"""
Trader Registry Management CLI

Add/remove/list traders without restarting the bot (when using phase5_scalable.py).

Usage:
    python3 manage_traders.py list
    python3 manage_traders.py add trader_id BTC-USD,ETH-USD 1000
    python3 manage_traders.py remove trader_id
    python3 manage_traders.py show trader_id
"""

import sys
import json
from pathlib import Path
from datetime import datetime

REGISTRY_PATH = Path(__file__).parent / 'trader_registry.json'


def load_registry():
    """Load trader registry from JSON"""
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, 'r') as f:
            return json.load(f)
    return {}


def save_registry(traders):
    """Save trader registry to JSON"""
    with open(REGISTRY_PATH, 'w') as f:
        json.dump(traders, f, indent=2)
    print(f"✅ Saved {len(traders)} traders")


def cmd_list():
    """List all traders"""
    traders = load_registry()
    if not traders:
        print("❌ No traders registered")
        return
    
    print(f"\n{'Trader ID':<20} {'Pairs':<40} {'Capital':<10}")
    print("=" * 70)
    for tid, config in traders.items():
        pairs_str = ', '.join(config.get('pairs', []))[:37] + '...' if len(', '.join(config.get('pairs', []))) > 40 else ', '.join(config.get('pairs', []))
        print(f"{tid:<20} {pairs_str:<40} ${config.get('capital', 0):.2f}")
    print()


def cmd_add(trader_id, pairs_str, capital):
    """Add a new trader"""
    traders = load_registry()
    pairs = [p.strip() for p in pairs_str.split(',')]
    
    traders[trader_id] = {
        'name': f'Trader {trader_id}',
        'pairs': pairs,
        'capital': float(capital),
        'created_at': datetime.now().isoformat() + 'Z'
    }
    
    save_registry(traders)
    print(f"✅ Added trader '{trader_id}' with pairs: {pairs}")


def cmd_remove(trader_id):
    """Remove a trader"""
    traders = load_registry()
    if trader_id not in traders:
        print(f"❌ Trader '{trader_id}' not found")
        return
    
    del traders[trader_id]
    save_registry(traders)
    print(f"✅ Removed trader '{trader_id}'")


def cmd_show(trader_id):
    """Show trader details"""
    traders = load_registry()
    if trader_id not in traders:
        print(f"❌ Trader '{trader_id}' not found")
        return
    
    config = traders[trader_id]
    print(f"\nTrader: {trader_id}")
    print(f"  Name: {config.get('name')}")
    print(f"  Pairs: {', '.join(config.get('pairs', []))}")
    print(f"  Capital: ${config.get('capital', 0):.2f}")
    print(f"  Created: {config.get('created_at')}")
    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == 'list':
        cmd_list()
    elif cmd == 'add':
        if len(sys.argv) < 5:
            print("Usage: manage_traders.py add <trader_id> <pairs_csv> <capital>")
            sys.exit(1)
        cmd_add(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == 'remove':
        if len(sys.argv) < 3:
            print("Usage: manage_traders.py remove <trader_id>")
            sys.exit(1)
        cmd_remove(sys.argv[2])
    elif cmd == 'show':
        if len(sys.argv) < 3:
            print("Usage: manage_traders.py show <trader_id>")
            sys.exit(1)
        cmd_show(sys.argv[2])
    else:
        print(f"❌ Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
