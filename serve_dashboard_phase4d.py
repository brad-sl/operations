#!/usr/bin/env python3
"""Phase 4d Dashboard — reads live from phase4_trades.db"""
import http.server, socketserver, json, sqlite3
from pathlib import Path

PORT = 8501
BASE = Path(__file__).parent

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?')[0]

        if path in ('/', '/index.html'):
            self.send_response(200)
            html = '''<!DOCTYPE html><html><head><meta charset="utf-8"><title>Phase 4d Bot</title>
<style>body{font-family:monospace;background:#0e1117;color:#e0e0e0;padding:20px}
h1{color:#00d4ff}table{width:100%;border-collapse:collapse;background:#1a1d27}
th{background:#2a2d3a;padding:8px;text-align:left;font-size:11px;color:#888}
td{padding:7px 12px;border-bottom:1px solid #2a2d3a}
.pos{color:#0cce6b}.neg{color:#ff4454}.section{margin:20px 0}</style>
</head><body><h1>Phase 4d Trading Bot — LIVE</h1>
<div class="section">Market: Sideways (RSI=50) | Awaiting entry signals...</div>
<div id="trades"></div>
<script>
async function load(){
  try{const r=await fetch('/api/trades');const trades=await r.json();
  const html=trades.length?`<table>
<tr><th>Pair</th><th>Entry $</th><th>Exit $</th><th>PnL</th><th>%</th><th>Time</th></tr>
${trades.map(t=>'<tr><td>'+t.pair+'</td><td>'+t.entry_price.toFixed(2)+'</td><td>'+(t.exit_price?t.exit_price.toFixed(2):'OPEN')+'</td><td class="'+(t.pnl>=0?'pos':'neg')+'">'+t.pnl.toFixed(2)+'</td><td class="'+(t.pnl_pct>=0?'pos':'neg')+'">'+(t.pnl_pct*100).toFixed(1)+'%</td><td>'+new Date(t.created_at).toLocaleString()+'</td></tr>').join('')}
</table>`:'<p>No trades yet. Awaiting signal...</p>';
  document.getElementById('trades').innerHTML=html;}catch(e){console.log(e);}
  setTimeout(load,5000);
}
load();
</script></body></html>'''
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Content-Length', len(html))
            self.end_headers()
            self.wfile.write(html.encode())
        elif path == '/api/trades':
            try:
                conn = sqlite3.connect(str(BASE / 'phase4_trades.db'))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM trades ORDER BY created_at DESC LIMIT 50")
                trades = [dict(row) for row in cursor.fetchall()]
                conn.close()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Content-Length', str(len(json.dumps(trades))))
                self.end_headers()
                self.wfile.write(json.dumps(trades).encode())
            except Exception as e:
                self.send_error(500)
        else:
            self.send_error(404)
    def log_message(self, *args): pass

with socketserver.TCPServer(('0.0.0.0', PORT), Handler) as httpd:
    print('✅ Phase 4d Dashboard ready')
    httpd.serve_forever()
