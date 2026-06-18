#!/usr/bin/env python3
"""Phase 6 Dashboard Server — DB-first architecture.

Live data is now served from database views, with a fallback to cache.
"""

import http.server
import socketserver
import os
import urllib.parse
import json
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from phase6.core.trade_ledger import TradeLedger
from phase6.core.performance_api import flush_performance_cache
from phase6.core.rebalance_logger import get_recent_rebalances

PORT = 8502
BASE = Path(__file__).parent
MODE = 'paper'
LEDGER = TradeLedger()

CACHE_PATH = Path("/home/brad/projects/crypto-trading-bot/data/state/phase6_live_state.json")
DB_PATH = Path("/home/brad/projects/crypto-trading-bot/data/phase6.db")

def load_live_state():
    """Read the latest state written by the runner or collector."""
    if not CACHE_PATH.exists():
        return None
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return None

def fetch_from_db():
    """Query DB views for live data. Returns dict or None if not available."""
    if not DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(str(DB_PATH))
        # Query v_phase6_dashboard for core state
        row = conn.execute("SELECT cash_usd, usdc, total_holdings_value, total_usd, active_positions, positions_json, last_updated FROM v_phase6_dashboard").fetchone()
        conn.close()
        
        if not row or row[0] is None:
            return None
            
        cash, usdc, holdings_val, total, active, pos_json, last_upd = row
        positions = []
        if pos_json:
            try:
                positions = json.loads(pos_json)
            except:
                positions = []
                
        return {
            "balances": [{"currency": "USD", "balance": cash or 0, "available": cash or 0, "hold": 0}],
            "total_usd": total or 0,
            "active_positions": active or 0,
            "positions": positions,
            "source": "Live (DB view)",
            "last_updated": last_upd or datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        print(f"DB fetch error: {e}")
        return None

def fetch_balances():
    """Serve balances from DB views (preferred) or cache fallback."""
    if MODE == 'live':
        db_data = fetch_from_db()
        if db_data:
            db_data["mode"] = "live"
            db_data["bought_indicators"] = []
            db_data["sold_indicators"] = []
            return db_data
            
        state = load_live_state()
        if state and 'balances' in state:
            state["source"] = "Live (cached JSON fallback)"
            return state
            
        return {
            "balances": [{"currency": "USD", "balance": 0, "available": 0, "hold": 0}],
            "total_usd": 0,
            "mode": "live",
            "source": "Live (cache miss)",
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    else:
        return {
            "balances": [{"currency": "USD", "balance": 967.76, "available": 967.76, "hold": 0}],
            "total_usd": 967.76,
            "mode": "paper",
            "source": "Paper Mode"
        }

def fetch_live_positions():
    """Serve positions from DB views (preferred) or cache."""
    if MODE == 'live':
        db_data = fetch_from_db()
        if db_data and db_data.get('positions'):
            return {
                "positions": db_data.get('positions', []),
                "total_balance": db_data.get('total_usd', 0),
                "active_positions": db_data.get('active_positions', 0),
                "bought_indicators": [],
                "sold_indicators": [],
                "mode": "live",
                "source": db_data.get('source', 'Live (DB view)'),
                "last_updated": db_data.get('last_updated', datetime.now(timezone.utc).isoformat())
            }
            
    state = load_live_state()
    if state and 'positions' in state:
        state["source"] = "Live (cached JSON fallback)"
        return state

    return {
        "positions": [],
        "total_balance": 0,
        "mode": "live",
        "source": "Live (cache miss)",
        "last_updated": datetime.now(timezone.utc).isoformat()
    }

def fetch_paper_positions():
    return {
        "positions": [],
        "total_balance": 0,
        "mode": "paper",
        "source": "Paper (not implemented)"
    }

def fetch_positions():
    if MODE == "live":
        return fetch_live_positions()
    return fetch_paper_positions()

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/' or path == '/index.html':
            self.serve_file('/home/brad/projects/crypto-trading-bot/phase6_dashboard.html', 'text/html')
        elif path == '/api/balances':
            self.send_json(fetch_balances())
        elif path == '/api/positions':
            self.send_json(fetch_positions())
        elif path == '/api/trades':
            trades = LEDGER.get_recent_trades(limit=20)
            self.send_json({"trades": trades or [], "mode": MODE, "count": len(trades or []), "source": "TradeLedger"})
        elif path == '/api/sentiment':
            # Prefer DB (populated by RSI/Sentiment refresh pipelines for dynamic values)
            # Falls back to canonical cache
            try:
                import sqlite3
                conn = sqlite3.connect(str(DB_PATH))
                rows = conn.execute("""
                    SELECT pair, score, source, ts 
                    FROM sentiment_scores 
                    WHERE ts = (SELECT MAX(ts) FROM sentiment_scores s2 WHERE s2.pair = sentiment_scores.pair)
                    ORDER BY pair
                """).fetchall()
                if rows:
                    data = {}
                    for pair, score, source, ts in rows:
                        data[pair] = {"sentiment": float(score) if score is not None else 0.0, "source": source or "db", "ts": ts}
                    conn.close()
                    self.send_json({"status": "ok", "data": data, "source": "phase6_db.sentiment_scores (dynamic)", "last_updated": datetime.now(timezone.utc).isoformat()})
                    return
                conn.close()
            except Exception as e:
                pass  # fall through to cache
            sentiment_file = Path.home() / ".trading-bot" / "sentiment_cache.json"
            if sentiment_file.exists():
                try:
                    with open(sentiment_file) as f:
                        raw = json.load(f)
                        scores = raw.get("sentiment", raw)
                        normalized = {pair: {"sentiment": val.get("sentiment_score", val) if isinstance(val, dict) else val} for pair, val in scores.items()}
                        self.send_json({"status": "ok", "data": normalized, "source": "canonical cache", "last_updated": datetime.now(timezone.utc).isoformat()})
                        return
                except Exception as e:
                    self.send_json({"status": "error", "message": str(e)})
                    return
            self.send_json({"status": "no_data", "message": "No sentiment data found"})
        elif path == '/api/rsi':
            # Most recent per-pair RSI from DB (populated by 15m refresher dual-write) or fallback to rsi_cache.json
            # Text notation ready for dashboard: value + (Neutral/Oversold/Overbought)
            try:
                import sqlite3
                conn = sqlite3.connect(str(DB_PATH))
                rows = conn.execute("""
                    SELECT pair, value, source, ts 
                    FROM rsi_values 
                    WHERE ts = (SELECT MAX(ts) FROM rsi_values s2 WHERE s2.pair = rsi_values.pair)
                    ORDER BY pair
                """).fetchall()
                if rows:
                    data = {}
                    for pair, value, source, ts in rows:
                        data[pair] = {"rsi": float(value) if value is not None else 50.0, "source": source or "db", "ts": ts}
                    conn.close()
                    self.send_json({"status": "ok", "data": data, "source": "phase6_db.rsi_values (15m refresher, most recent)", "last_updated": datetime.now(timezone.utc).isoformat()})
                    return
                conn.close()
            except Exception:
                pass
            # Fallback to JSON cache from refresher
            rsi_file = Path("data/state/rsi_cache.json")
            if rsi_file.exists():
                try:
                    with open(rsi_file) as f:
                        raw = json.load(f)
                        rsi_block = raw.get("rsi", {})
                        normalized = {pair: {"rsi": info.get("rsi", 50.0), "source": info.get("source", "cache"), "ts": info.get("timestamp")} for pair, info in rsi_block.items()}
                        self.send_json({"status": "ok", "data": normalized, "source": "rsi_cache.json (15m)", "last_updated": datetime.now(timezone.utc).isoformat()})
                        return
                except Exception as e:
                    self.send_json({"status": "error", "message": str(e)})
                    return
            self.send_json({"status": "no_data", "message": "No RSI data found"})

        elif path == '/api/performance':
            trades = LEDGER.get_recent_trades(limit=100)
            closed = [t for t in trades if t.get('pnl') is not None]
            win_ratio = sum(1 for t in closed if t.get('pnl', 0) > 0) / len(closed) if closed else 0.0
            self.send_json({
                "status": "ok",
                "win_ratio": round(win_ratio, 3),
                "total_trades": len(closed),
                "today": 0.0, "h24": 0.0, "d7": 0.0, "d30": 0.0,
                "source": "TradeLedger",
                "last_updated": datetime.now(timezone.utc).isoformat()
            })
        elif path == '/api/performance/flush':
            flush_performance_cache()
            self.send_json({"status": "cache_flushed", "timestamp": datetime.now(timezone.utc).isoformat()})
        elif path == '/api/rebalances':
            rebalances = get_recent_rebalances(limit=20)
            self.send_json({"rebalances": rebalances or [], "count": len(rebalances or []), "source": "rebalance_history.jsonl", "last_updated": datetime.now(timezone.utc).isoformat()})
        elif path == '/api/recovery':
            try:
                rec_path = Path("data/state/recovery_state.json")
                if rec_path.exists():
                    self.send_json(json.loads(rec_path.read_text()))
                else:
                    self.send_json({"mode": "normal", "cooldown_pairs": [], "last_update": datetime.now(timezone.utc).isoformat()})
            except Exception as e:
                self.send_json({"error": str(e)})
        else:
            self.send_error(404)

    def send_json(self, data):
        resp = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def serve_file(self, path, ct):
        try:
            p = Path(path)
            data = p.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', ct + '; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(404)

    def log_message(self, *args):
        pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['paper', 'live'], default='paper')
    parser.add_argument('--port', type=int, default=8502)
    args = parser.parse_args()
    MODE = args.mode
    print(f"Phase 6 Dashboard ({MODE} mode, DB-first) at http://0.0.0.0:{args.port}")
    with socketserver.TCPServer(('0.0.0.0', args.port), Handler) as httpd:
        httpd.serve_forever()
