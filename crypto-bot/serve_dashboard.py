#!/usr/bin/env python3
"""Minimal HTTP server for the crypto bot dashboard. No numpy/pandas/plotly."""
import http.server, socketserver, os, urllib.parse
from pathlib import Path

PORT = 8501
BASE = Path(__file__).parent

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == '/' or path == '/index.html':
            self.serve_file(BASE / 'dashboard.html', 'text/html')
        elif path == '/log':
            env = params.get('env', ['prod'])[0]
            if env == 'test':
                log = BASE / 'PHASE4B_SMOKE_TEST.log'
            else:
                log = BASE / 'phase4b_24h_run.txt'
                if not log.exists():
                    log = BASE / 'PHASE4B_SMOKE_TEST.log'
            self.serve_file(log, 'text/plain')
        elif path == '/loglist':
            # Returns available log files as JSON
            files = []
            for f in ['phase4b_24h_run.txt', 'PHASE4B_SMOKE_TEST.log']:
                p = BASE / f
                if p.exists():
                    files.append({'name': f, 'size': p.stat().st_size, 'mtime': p.stat().st_mtime})
            import json
            data = json.dumps(files).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(data))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)

    def serve_file(self, path, ct):
        try:
            data = path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', ct + '; charset=utf-8')
            self.send_header('Content-Length', len(data))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_error(404)

    def log_message(self, *args): pass

with socketserver.TCPServer(('0.0.0.0', PORT), Handler) as httpd:
    print(f'Dashboard at http://0.0.0.0:{PORT}')
    httpd.serve_forever()
