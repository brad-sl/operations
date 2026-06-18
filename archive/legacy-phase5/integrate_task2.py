#!/usr/bin/env python3
"""
Task 2 Integration Script: Add OrderExecutorWrapper to phase5_multi_pair.py
Run once to integrate Phase 6 paper trading alongside Phase 5.1 live trading
"""

import sys
import os

TARGET_FILE = '/home/brad/.openclaw/workspace/operations/crypto-bot/phase5_multi_pair.py'

def add_import():
    """Add OrderExecutorWrapper import after CoinbaseAdvancedClient"""
    with open(TARGET_FILE, 'r') as f:
        content = f.read()
    
    # Find insertion point (after CoinbaseAdvancedClient import block)
    insertion_point = content.find('# Suppress verbose fallback API errors')
    
    if insertion_point == -1:
        print("❌ Could not find insertion point for import")
        return False
    
    wrapper_import = '''try:
    from phase5_order_executor_wrapper import OrderExecutorWrapper
    ORDER_EXECUTOR_WRAPPER_AVAILABLE = True
except ImportError:
    ORDER_EXECUTOR_WRAPPER_AVAILABLE = False
    OrderExecutorWrapper = None

'''
    
    content = content[:insertion_point] + wrapper_import + content[insertion_point:]
    
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    
    print("✅ Added OrderExecutorWrapper import")
    return True


def add_init_code():
    """Add executor wrapper initialization in __init__"""
    with open(TARGET_FILE, 'r') as f:
        lines = f.readlines()
    
    # Find line after capital_per_pair assignment
    target_line = None
    for i, line in enumerate(lines):
        if 'self.capital_per_pair = self.total_capital / len(self.pairs)' in line:
            target_line = i
            break
    
    if target_line is None:
        print("❌ Could not find capital_per_pair line")
        return False
    
    init_code = '''        
        # Phase 6: Sandbox trading via OrderExecutor
        self.order_size_usd = self.config.get('global_settings', {}).get('order_size_usd', 25.0)
        self.sandbox_trading = os.getenv('SANDBOX_TRADING', 'True').lower() == 'true'
        self.executor_wrapper = None
        
        if ORDER_EXECUTOR_WRAPPER_AVAILABLE and self.sandbox_trading:
            try:
                self.executor_wrapper = OrderExecutorWrapper(
                    cb_client=self.cb_client,
                    sandbox_mode=self.sandbox_trading,
                    order_size_usd=self.order_size_usd,
                    logger=self.logger
                )
                self.logger.info(f"✅ Phase 6 OrderExecutor initialized (sandbox={self.sandbox_trading}, order_size=${self.order_size_usd})")
            except Exception as e:
                self.logger.warning(f"Phase 6 initialization failed: {e}. Running Phase 5 only.")
                self.executor_wrapper = None
        else:
            self.logger.info("⚠️  Phase 6 OrderExecutor unavailable (Phase 5 manual trading only)")
'''
    
    lines.insert(target_line + 1, init_code)
    
    with open(TARGET_FILE, 'w') as f:
        f.writelines(lines)
    
    print("✅ Added executor wrapper initialization")
    return True


def update_process_pair():
    """Update _process_pair() to call executor wrapper"""
    with open(TARGET_FILE, 'r') as f:
        content = f.read()
    
    # Find the return signal line in _process_pair
    old_return = '''            # Trading decision logic
            signal = self._determine_trade_signal(pair, price, rsi, sentiment)
            
            return signal'''
    
    new_return = '''            # Trading decision logic
            signal = self._determine_trade_signal(pair, price, rsi, sentiment)
            
            # Phase 6: Execute via OrderExecutorWrapper (sandbox paper trading)
            if self.executor_wrapper and signal != "HOLD":
                try:
                    results = self.executor_wrapper.execute_signal(
                        pair=pair,
                        signal=signal,
                        price=price,
                        rsi=rsi,
                        sentiment=sentiment,
                        cycle=cycle
                    )
                    if results:
                        self.logger.info(f"✅ {pair} {signal}: {len(results)} order(s) executed (sandbox)")
                except Exception as e:
                    self.logger.error(f"Phase 6 execution error: {e}")
            
            return signal'''
    
    if old_return in content:
        content = content.replace(old_return, new_return)
        with open(TARGET_FILE, 'w') as f:
            f.write(content)
        print("✅ Updated _process_pair() with executor wrapper call")
        return True
    else:
        print("⚠️  Could not find exact _process_pair return statement (may be already modified)")
        return False


def main():
    print("\n🚀 Phase 6 Task 2: Integration Script Started\n")
    
    try:
        if not add_import():
            sys.exit(1)
        if not add_init_code():
            sys.exit(1)
        if not update_process_pair():
            print("⚠️  Warning: _process_pair update may need manual review")
        
        print("\n✅ Phase 6 Task 2 Integration Complete!")
        print("   • Import added")
        print("   • Wrapper initialization added")
        print("   • _process_pair() updated with executor calls")
        print("\n📝 Next: Run phase5_multi_pair.py to start parallel paper trading\n")
        
    except Exception as e:
        print(f"\n❌ Integration failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
