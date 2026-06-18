#!/usr/bin/env python3
from dotenv import load_dotenv
load_dotenv()

from phase5_v3_robust import Phase5V3Robust

print('Testing Phase 5 v3 initialization...')
try:
    bot = Phase5V3Robust(sandbox=True)
    print('✅ Phase 5 v3 initialized successfully')
    print(f'   Pairs: {bot.pairs}')
    print(f'   Capital: ${bot.total_capital}')
    print(f'   SL%: {bot.sl_pct*100}%')
    print(f'   State manager ready: {bot.state_manager is not None}')
    print('\n✅ Ready for sandbox validation')
except Exception as e:
    print(f'❌ Init failed: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
