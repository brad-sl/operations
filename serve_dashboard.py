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

CACHE_PATH = BASE / "data/state/phase6_live_state.json"
DB_PATH = BASE / "data/phase6.db"


def open_db(timeout: float = 3.0, readonly: bool = True):
    """Short-timeout SQLite connect; read-only avoids blocking on writer locks."""
    if not DB_PATH.exists():
        return None
    try:
        if readonly:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=timeout)
        else:
            conn = sqlite3.connect(str(DB_PATH), timeout=timeout)
        conn.execute("PRAGMA busy_timeout=3000")
        return conn
    except Exception as e:
        print(f"DB open error: {e}")
        return None


def get_sentiment_label(val):
    """Pre-compute label for pure consumer dashboard (no client ifs)."""
    try:
        v = float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        v = 0.0
    if v > 0.1:
        return "Bullish", "emerald-400"
    elif v < -0.1:
        return "Bearish", "red-400"
    return "Neutral", "slate-400"

def get_rsi_label(val):
    """Pre-compute RSI label for pure consumer (no client ifs)."""
    try:
        v = float(val) if val is not None else 50.0
    except (ValueError, TypeError):
        v = 50.0
    if v < 30:
        return "Oversold", "emerald-400"
    elif v > 70:
        return "Overbought", "red-400"
    return "Neutral", "slate-400"

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
    conn = open_db(timeout=3.0, readonly=True)
    if not conn:
        return None
    try:
        scalars = conn.execute("SELECT cash_usd, usdc, total_usd, active_positions, recovery_attempts, recovery_rate, sl_success_rate, replay_match_rate, brief_consumed, last_updated FROM v_phase6_dashboard").fetchone()
        pos_rows = conn.execute("SELECT pair, amount, current_price, value_usd, entry_price, unrealized_pnl_pct, side FROM v_enriched_positions").fetchall()
        if not scalars:
            return None
        cash, usdc, total, active, rec_att, rec_rate, sl_rate, rep_rate, brief_con, last_upd = scalars
        if total is None and not pos_rows:
            return None
        positions = []
        cash_positions = []
        trading_positions = []
        for p in pos_rows:
            pair, amt, cprice, val, entry, pnl, side = p
            pos = {"pair": pair, "amount": amt, "current_price": cprice, "value_usd": val, "entry_price": entry or 0.0, "unrealized_pnl_pct": pnl or 0.0, "side": side or "long"}
            positions.append(pos)
            if pair in ("USD", "USDC"):
                cash_positions.append(pos)
            else:
                trading_positions.append(pos)
        return {
            "balances": [{"currency": "USD", "balance": cash or 0, "available": cash or 0, "hold": 0}],
            "total_usd": total or 0,
            "total_balance": total or 0,
            "active_positions": active or 0,
            "positions": positions,
            "cash_positions": cash_positions,
            "trading_positions": trading_positions,
            "source": "Live (DB view)",
            "last_updated": last_upd or datetime.now(timezone.utc).isoformat(),
            # P1 metrics from v_phase6_dashboard (DB authoritative)
            "recovery_attempts": rec_att or 0,
            "recovery_rate": rec_rate or 0.0,
            "sl_success_rate": sl_rate or 0.0,
            "replay_match_rate": rep_rate or 0.0,
            "brief_consumed": brief_con or 0
        }
    except Exception as e:
        print(f"DB fetch error: {e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass

def fetch_balances():
    """Serve balances from DB views (preferred) or cache fallback."""
    if MODE == 'live':
        # Prefer runner live_state.json for accurate current holdings (matches exchange)
        state = load_live_state()
        if state and ('balances' in state or 'positions' in state):
            data = dict(state)
            data["mode"] = "live"
            data["source"] = "Live (runner state)"
            # P1 overlay from DB is best-effort only — never block live JSON on SQLite
            if "bought_indicators" not in data:
                data["bought_indicators"] = []
            if "sold_indicators" not in data:
                data["sold_indicators"] = []
            return data

        # DB fallback only if cache unavailable
        db_data = fetch_from_db()
        if db_data:
            db_data["mode"] = "live"
            db_data["source"] = db_data.get("source", "Live (DB view)")
            return db_data
            
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
    """Serve positions from DB views (preferred) or cache. Merged bought/sold from live_state. Pre-split for pure consumer JS (no client filter)."""
    if MODE == "live":
        # Prefer runner live_state for current positions (ground truth)
        state = load_live_state()
        if state and "positions" in state:
            data = dict(state)
            data["mode"] = "live"
            data["source"] = "Live (runner state)"
            # merge bought/sold if missing
            if "bought_indicators" not in data:
                data["bought_indicators"] = state.get("bought_indicators", [])
            if "sold_indicators" not in data:
                data["sold_indicators"] = state.get("sold_indicators", [])
            return data

        # DB fallback
        db_data = fetch_from_db()
        if db_data and db_data.get("positions"):
            bought = []
            sold = []
            try:
                st = load_live_state() or {}
                bought = st.get("bought_indicators", []) or []
                sold = st.get("sold_indicators", []) or []
            except:
                pass
            return {
                "positions": db_data.get("positions", []),
                "cash_positions": db_data.get("cash_positions", []),
                "trading_positions": db_data.get("trading_positions", []),
                "total_usd": db_data.get("total_usd", 0),
                "total_balance": db_data.get("total_usd", 0),
                "active_positions": db_data.get("active_positions", 0),
                "bought_indicators": bought,
                "sold_indicators": sold,
                "mode": "live",
                "source": db_data.get("source", "Live (DB view)"),
                "last_updated": db_data.get("last_updated", datetime.now(timezone.utc).isoformat())
            }
            
    state = load_live_state()
    if state and "positions" in state:
        state["source"] = "Live (cached JSON fallback)"
        # ensure splits if missing in old cache
        if "cash_positions" not in state:
            poss = state.get("positions", [])
            state["cash_positions"] = [p for p in poss if p.get("pair") in ("USD", "USDC")]
            state["trading_positions"] = [p for p in poss if p.get("pair") not in ("USD", "USDC")]
        return state

    return {
        "positions": [],
        "cash_positions": [],
        "trading_positions": [],
        "total_usd": 0,
        "total_balance": 0,
        "mode": "live",
        "source": "Live (cache miss)",
        "last_updated": datetime.now(timezone.utc).isoformat()
    }

def fetch_paper_positions():
    return {
        "positions": [],
        "cash_positions": [],
        "trading_positions": [],
        "total_usd": 0,
        "total_balance": 0,
        "mode": "paper",
        "source": "Paper (not implemented)"
    }

def fetch_positions():
    if MODE == "live":
        return fetch_live_positions()
    return fetch_paper_positions()

def fetch_dashboard_metrics():
    """Return pre-computed observability metrics from v_dashboard_metrics (P1: proposals accepted, utilization, SL success rate, churn) + strategic brief artifact."""
    if not DB_PATH.exists():
        return {"status": "no_db"}
    conn = None
    try:
        conn = open_db(timeout=3.0, readonly=True)
        if not conn:
            return {"status": "no_db"}
        row = conn.execute("SELECT * FROM v_dashboard_metrics LIMIT 1").fetchone()
        desc = conn.execute("SELECT * FROM v_dashboard_metrics").description
        cols = [d[0] for d in desc] if desc else []
        if row and cols:
            metrics = dict(zip(cols, row))
            return {
                "status": "ok",
                "metrics": metrics,
                "source": "v_dashboard_metrics (DB view)",
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
        return {"status": "no_data"}
    except Exception as e:
        print(f"metrics fetch error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        try:
            conn.close()
        except Exception:
            pass

def fetch_strategic_brief():
    """Return the lightweight strategic brief artifact (P1)."""
    try:
        from phase6.core.paths import INTEL_BRIEF
        if INTEL_BRIEF.exists():
            import json
            brief = json.loads(INTEL_BRIEF.read_text())
            return {"status": "ok", "brief": brief, "source": "intel_strategic_brief.json", "last_updated": datetime.now(timezone.utc).isoformat()}
        return {"status": "no_brief"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/' or path == '/index.html':
            self.serve_file(str(BASE / 'phase6_dashboard.html'), 'text/html')
        elif path == '/api/balances':
            self.send_json(fetch_balances())
        elif path == '/api/positions':
            self.send_json(fetch_positions())
        elif path == '/api/trades':
            trades = LEDGER.get_recent_trades(limit=20)
            self.send_json({"trades": trades or [], "mode": MODE, "count": len(trades or []), "source": "TradeLedger"})
        elif path == '/api/sentiment':
            # Cache/scorer first — avoid blocking single-thread server on huge sentiment_scores table
            try:
                from phase6.core.sentiment_scorer import load_sentiment_scores, get_sentiment_timestamp
                scores = load_sentiment_scores()
                ts = get_sentiment_timestamp()
                normalized = {}
                for pair, val in scores.items():
                    sent = float(val) if val is not None else 0.0
                    label, color = get_sentiment_label(sent)
                    normalized[pair] = {"sentiment": sent, "label": label, "color": color, "source": "canonical_scorer"}
                self.send_json({"status": "ok", "data": normalized, "source": "phase6.core.sentiment_scorer (X primary + real reddit gate)", "timestamp": ts, "last_updated": datetime.now(timezone.utc).isoformat()})
                return
            except Exception:
                pass
            sentiment_file = Path("data/state/sentiment_cache.json")
            if sentiment_file.exists():
                try:
                    with open(sentiment_file) as f:
                        raw = json.load(f)
                        scores = raw.get("sentiment", raw)
                        normalized = {}
                        for pair, val in scores.items():
                            sent = float(val) if val is not None else 0.0
                            label, color = get_sentiment_label(sent)
                            normalized[pair] = {"sentiment": sent, "label": label, "color": color, "source": "sentiment_cache.json"}
                        self.send_json({"status": "ok", "data": normalized, "source": "data/state/sentiment_cache.json", "last_updated": datetime.now(timezone.utc).isoformat()})
                        return
                except Exception:
                    pass
            try:
                conn = open_db(timeout=2.0, readonly=True)
                if conn:
                    rows = conn.execute("""
                        SELECT s.pair, s.score, s.source, s.ts
                        FROM sentiment_scores s
                        INNER JOIN (
                            SELECT pair, MAX(ts) AS max_ts FROM sentiment_scores GROUP BY pair
                        ) latest ON s.pair = latest.pair AND s.ts = latest.max_ts
                        ORDER BY s.pair
                    """).fetchall()
                    conn.close()
                    if rows:
                        data = {}
                        for pair, score, source, ts in rows:
                            sent = float(score) if score is not None else 0.0
                            label, color = get_sentiment_label(sent)
                            data[pair] = {"sentiment": sent, "label": label, "color": color, "source": source or "db", "ts": ts}
                        self.send_json({"status": "ok", "data": data, "source": "phase6_db.sentiment_scores (dynamic)", "last_updated": datetime.now(timezone.utc).isoformat()})
                        return
            except Exception:
                pass
            self.send_json({"status": "error", "data": {}, "message": "no sentiment source"})
            return
        elif path == '/api/rsi':
            rsi_file = Path("data/state/rsi_cache.json")
            if rsi_file.exists():
                try:
                    with open(rsi_file) as f:
                        raw = json.load(f)
                        rsi_block = raw.get("rsi", {})
                        normalized = {}
                        for pair, info in rsi_block.items():
                            rsi = info.get("rsi", 50.0) if isinstance(info, dict) else info
                            try:
                                rsi = float(rsi)
                            except Exception:
                                rsi = 50.0
                            label, color = get_rsi_label(rsi)
                            normalized[pair] = {"rsi": rsi, "label": label, "color": color, "source": "rsi_cache.json"}
                        self.send_json({"status": "ok", "data": normalized, "source": "data/state/rsi_cache.json", "last_updated": datetime.now(timezone.utc).isoformat()})
                        return
                except Exception:
                    pass
            try:
                conn = open_db(timeout=2.0, readonly=True)
                if conn:
                    rows = conn.execute("""
                        SELECT s.pair, s.value, s.source, s.ts
                        FROM rsi_values s
                        INNER JOIN (
                            SELECT pair, MAX(ts) AS max_ts FROM rsi_values GROUP BY pair
                        ) latest ON s.pair = latest.pair AND s.ts = latest.max_ts
                        ORDER BY s.pair
                    """).fetchall()
                    conn.close()
                    if rows:
                        data = {}
                        for pair, value, source, ts in rows:
                            rsi = float(value) if value is not None else 50.0
                            label, color = get_rsi_label(rsi)
                            data[pair] = {"rsi": rsi, "label": label, "color": color, "source": source or "db", "ts": ts}
                        self.send_json({"status": "ok", "data": data, "source": "phase6_db.rsi_values (15m refresher, most recent)", "last_updated": datetime.now(timezone.utc).isoformat()})
                        return
            except Exception:
                pass
            # Fallback to JSON cache from refresher
            rsi_file = Path("data/state/rsi_cache.json")
            if rsi_file.exists():
                try:
                    with open(rsi_file) as f:
                        raw = json.load(f)
                        rsi_block = raw.get("rsi", {})
                        normalized = {}
                        for pair, info in rsi_block.items():
                            rsi = info.get("rsi", 50.0)
                            try:
                                rsi = float(rsi)
                            except:
                                rsi = 50.0
                            label, color = get_rsi_label(rsi)
                            normalized[pair] = {"rsi": rsi, "label": label, "color": color, "source": info.get("source", "cache"), "ts": info.get("timestamp")}
                        
                        self.send_json({"status": "ok", "data": normalized, "source": "rsi_cache.json (15m)", "last_updated": datetime.now(timezone.utc).isoformat()})
                        return
                except Exception as e:
                    self.send_json({"status": "error", "message": str(e)})
                    return
            self.send_json({"status": "no_data", "message": "No RSI data found"})

        elif path == '/api/performance':
            # Prefer live_state performance_metrics (populated by runner with real calcs + entry/pnl data)
            perf = {}
            try:
                cache = json.loads(CACHE_PATH.read_text())
                perf = cache.get("performance_metrics", {})
            except Exception:
                pass

            trades = LEDGER.get_recent_trades(limit=100)
            closed = [t for t in trades if t.get('pnl') is not None]
            win_ratio = sum(1 for t in closed if (t.get('pnl') or 0) > 0) / len(closed) if closed else perf.get("win_rate", 0.0)

            # Use values from runner state / live_state.
            # No more fake multiplication (today*7 / *30). Longer periods now come from
            # actual data (or explicit negative for known portfolio value drop).
            today = float(perf.get("today", perf.get("daily_pnl_est", 0.0)) or 0.0)
            h24 = float(perf.get("h24", today) or today)
            d7 = float(perf.get("d7", 0.0) or 0.0)
            d30 = float(perf.get("d30", 0.0) or 0.0)

            self.send_json({
                "status": "ok",
                "win_ratio": round(win_ratio, 3),
                "total_trades": len(closed) or perf.get("total_trades", 0),
                "today": round(float(today), 2),
                "h24": round(float(h24), 2),
                "d7": round(float(d7), 2),
                "d30": round(float(d30), 2),
                "source": "live_state + TradeLedger (data first per spec)",
                "last_updated": datetime.now(timezone.utc).isoformat()
            })
        elif path == '/api/performance/flush':
            flush_performance_cache()
            self.send_json({"status": "cache_flushed", "timestamp": datetime.now(timezone.utc).isoformat()})
        elif path == '/api/rebalances':
            rebalances = get_recent_rebalances(limit=20) or []
            executed_rebalances = [r for r in rebalances if (r.get("executed") or 0) > 0]
            self.send_json({"rebalances": executed_rebalances, "count": len(executed_rebalances), "source": "rebalance_history.jsonl (executed only)", "last_updated": datetime.now(timezone.utc).isoformat()})
        elif path == '/api/recovery':
            try:
                rec_path = Path("data/state/recovery_state.json")
                if rec_path.exists():
                    self.send_json(json.loads(rec_path.read_text()))
                else:
                    self.send_json({"mode": "normal", "cooldown_pairs": [], "last_update": datetime.now(timezone.utc).isoformat()})
            except Exception as e:
                self.send_json({"error": str(e)})
        elif path == '/api/metrics':
            self.send_json(fetch_dashboard_metrics())
        elif path == '/api/brief':
            self.send_json(fetch_strategic_brief())
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

    # Allow quick restart after kills/crashes (prevents "Address already in use")
    socketserver.TCPServer.allow_reuse_address = True

    print(f"Phase 6 Dashboard ({MODE} mode, DB-first) at http://0.0.0.0:{args.port}")
    with socketserver.TCPServer(('0.0.0.0', args.port), Handler) as httpd:
        httpd.serve_forever()
