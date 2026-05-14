import subprocess
import time
import os
from datetime import datetime

def monitor_bot():
    log_file = 'trading_bot.log'
    pid_file = 'phase4d.pid'
    
    while True:
        # Check if PID file exists and process is running
        if os.path.exists(pid_file):
            with open(pid_file, 'r') as f:
                pid = f.read().strip()
            if pid and subprocess.run(['ps', '-p', pid], capture_output=True).returncode == 0:
                print(f'[{datetime.now()}] Bot running (PID: {pid})')
            else:
                print(f'[{datetime.now()}] Bot down — restarting...')
                subprocess.Popen(['python3', 'phase4c_multi_pair.py'], cwd='/home/brad/.openclaw/workspace/operations/crypto-bot')
                with open(pid_file, 'w') as f:
                    f.write(str(subprocess.Popen(['python3', 'phase4c_multi_pair.py'], cwd='/home/brad/.openclaw/workspace/operations/crypto-bot').pid))
        else:
            print(f'[{datetime.now()}] No PID file — starting bot')
            p = subprocess.Popen(['python3', 'phase4c_multi_pair.py'], cwd='/home/brad/.openclaw/workspace/operations/crypto-bot')
            with open(pid_file, 'w') as f:
                f.write(str(p.pid))
        
        # Tail log
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                lines = f.readlines()
                if lines:
                    print(f'Last log: {lines[-1].strip()}')
        
        time.sleep(30)

if __name__ == '__main__':
    monitor_bot()
