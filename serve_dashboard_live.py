#!/usr/bin/env python3
# Live Dashboard for Phase 5 $1K Test - Tails phase5_live_$1k_real.log, polls DB
import os
import re
import time
import sqlite3
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread
from pathlib import Path

BOT_DIR = Path(__file__).parent
LOG_PATH = BOT_DIR / 'phase5_live_$1k_real.log'
DB_PATH = BOT_DIR / 'phase4_trades.db'

class LiveHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            html = self.generate_html()
            self.wfile.write(html.encode())
        elif self.path == '/api/live':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            data = self.get_live_data()
            self.wfile.write(json.dumps(data).encode())
        else:
            super().do_GET()

    def generate_html(self):
        return '''
<!DOCTYPE html>
<html>
<head><title>Phase 5 Live $1K Dashboard</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="p-8 bg-gray-900 text-white">
<h1 class="text-3xl font-bold mb-8">Phase 5 Live $1K Test</h1>
<div id="live-data" class="grid grid-cols-1 md:grid-cols-2 gap-4"></div>
<script>
setInterval(() => fetch('/api/live').then(r=>r.json()).then(updateUI), 30000);
function updateUI(data) {
  document.getElementById('live-data').innerHTML = `
    <div class="bg-blue-900 p-6 rounded-lg">
      <h2>Cycles</h2>
      <pre>${JSON.stringify(data.cycles.slice(-10),null,2)}</pre>
    </div>
    <div class="bg-green-900 p-6 rounded-lg">
      <h2>Trades</h2>
      <pre>${JSON.stringify(data.trades, null,2)}</pre>
    </div>
  `;
}
</script>
</body>
</html>
        '''

    def get_live_data(self):
        cycles = []
        trades = []
        try:
            with open(LOG_PATH, 'r') as f:
                lines = f.readlines()[-500:]
            for line in lines:
                m = re.search(r'Cycle (\d+).*?(\w+)-USD=\$([\d.]+).*RSI: ([\d.]+).*Sig: (\w+)', line)
                if m:
                    cycles.append({'cycle': int(m.group(1)), 'pair': m.group(2), 'price': m.group(3), 'rsi': float(m.group(4)), 'signal': m.group(5)})
                m = re.search(r'TRADE: (\w+) (\w+) @\$([\d.]+)', line)
                if m:
                    trades.append({'action': m.group(1), 'type': m.group(2), 'price': m.group(3)})
        except:
            pass
        return {'cycles': cycles, 'trades': trades}

if __name__ == '__main__':
    PORT = 8501
    with HTTPServer(('0.0.0.0', PORT), LiveHandler) as httpd:
        print(f'Dashboard live at http://192.168.0.91:{PORT}')
        httpd.serve_forever()
