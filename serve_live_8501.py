#!/usr/bin/env python3
"""Phase 6 Live Dashboard Server (8501) - Real data endpoints"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json
import sys
sys.path.insert(0, "/home/brad/projects/crypto-trading-bot")

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.trade_ledger import TradeLedger
# Canonical single source sentiment
from phase6.core.sentiment_scorer import load_sentiment_scores

PORT = 8501
HTML_PATH = Path("/home/brad/projects/crypto-trading-bot/phase6_dashboard.html")
LEDGER = TradeLedger()
LIVE_STATE_PATH = Path("/home/brad/projects/crypto-trading-bot/data/state/phase6_live_state.json")
RECOVERY_STATE_PATH = Path("/home/brad/projects/crypto-trading-bot/data/state/recovery_state.json")


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PATH.read_bytes())

        elif self.path == "/api/balances":
            try:
                if LIVE_STATE_PATH.exists():
                    state = json.loads(LIVE_STATE_PATH.read_text())
                    data = {
                        "balances": [{"currency": "USD", "balance": state.get("cash_usd", 0), "available": state.get("cash_usd", 0), "hold": 0}],
                        "total_usd": state.get("total_usd", 0),
                        "mode": "live",
                        "source": "phase6_live_state.json"
                    }
                else:
                    client = CoinbaseExchangeClient(mode="live")
                    usd = client.get_account_balance("USD")
                    data = {"balances": [{"currency": "USD", "balance": usd}], "total_usd": usd, "mode": "live", "source": "Coinbase"}
            except Exception as e:
                data = {"error": str(e), "total_usd": 0, "mode": "live"}
            self.send_json(data)

        elif self.path == "/api/positions":
            try:
                if LIVE_STATE_PATH.exists():
                    state = json.loads(LIVE_STATE_PATH.read_text())
                    data = {
                        "positions": state.get("positions", []),
                        "active_positions": state.get("active_positions", 0),
                        "bought_indicators": state.get("bought_indicators", []),
                        "sold_indicators": state.get("sold_indicators", []),
                        "total_holdings_value": state.get("total_holdings_value", 0),
                        "cash_usd": state.get("cash_usd", 0),
                        "mode": "live",
                        "source": "phase6_live_state.json"
                    }
                else:
                    data = {"positions": [], "active_positions": 0, "mode": "live"}
            except Exception as e:
                data = {"error": str(e), "positions": []}
            self.send_json(data)

        elif self.path == "/api/trades":
            trades = LEDGER.get_recent_trades(limit=20)
            self.send_json({"trades": trades or [], "mode": "live", "count": len(trades or [])})

        elif self.path == "/api/sentiment":
            try:
                scores = load_sentiment_scores()  # single canonical source
                ts = None
                try:
                    from phase6.core.sentiment_scorer import get_sentiment_timestamp
                    ts = get_sentiment_timestamp()
                except Exception:
                    pass
                self.send_json({"data": scores, "status": "ok", "source": "canonical", "timestamp": ts})
            except Exception as e:
                self.send_json({"data": {}, "status": "error", "error": str(e)})

        elif self.path == "/api/recovery":
            try:
                if RECOVERY_STATE_PATH.exists():
                    data = json.loads(RECOVERY_STATE_PATH.read_text())
                else:
                    data = {"mode": "normal", "cooldown_pairs": []}
                self.send_json(data)
            except Exception as e:
                self.send_json({"mode": "normal", "cooldown_pairs": [], "error": str(e)})

        else:
            self.send_error(404)

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


if __name__ == "__main__":
    httpd = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Phase 6 Live Dashboard (real data) on http://0.0.0.0:{PORT}")
    httpd.serve_forever()