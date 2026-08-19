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
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from phase6.core.trade_ledger import TradeLedger
from phase6.core.performance_api import (
    flush_performance_cache,
    perf_compute_lock,
    performance_cache,
)
from phase6.core.rebalance_logger import get_recent_rebalances
from phase6.core.dashboard_serve_helpers import (
    compute_period_performance,
    compute_equity_trend,
    win_ratio_from_positions,
    fast_observability_metrics,
)

PORT = 8502
BASE = Path(__file__).parent
MODE = 'paper'
LEDGER = TradeLedger()

CACHE_PATH = BASE / "data/state/phase6_live_state.json"
DB_PATH = BASE / "data/phase6.db"
DB_READ_TIMEOUT = 0.35  # never block the HTTP server on runner WAL writes


def enrich_live_state(state: dict | None) -> dict | None:
    """Add server-side splits the HTML expects (pure consumer)."""
    if not state:
        return state
    out = dict(state)
    poss = out.get("positions") or []
    if not out.get("cash_positions") and not out.get("trading_positions"):
        out["cash_positions"] = [p for p in poss if p.get("pair") in ("USD", "USDC")]
        out["trading_positions"] = [p for p in poss if p.get("pair") not in ("USD", "USDC")]
    elif not out.get("trading_positions"):
        out["trading_positions"] = [p for p in poss if p.get("pair") not in ("USD", "USDC")]
    from phase6.core.display_dust import DEFAULT_DUST_HIDE_USD, split_dust_positions
    from phase6.core.position_cost_basis import recompute_trading_positions_pnl
    from phase6.core.paths import PRICE_HISTORY
    from phase6.core.price_freshness import DEFAULT_MAX_QUOTE_AGE_SEC

    # Ensure Preserve sleeve (PAXG) is visible even if runner cache lagged basket-only prices
    try:
        from phase6.core.preserve_hold import load_state as _ph_load_state

        _pst = _ph_load_state()
        if _pst.get("armed"):
            pax_pair = str(_pst.get("asset") or "PAXG-USD")
            have = any(
                (p.get("pair") or "").upper() == pax_pair.upper()
                for p in (out.get("trading_positions") or out.get("positions") or [])
            )
            if not have:
                amt = float(_pst.get("arm_qty") or 0)
                px = float(_pst.get("arm_vwap") or 0)
                # prefer live status file if present
                try:
                    from pathlib import Path as _P
                    import json as _j

                    sp = _P("data/state/preserve_hold_status.json")
                    if sp.exists():
                        ss = _j.loads(sp.read_text())
                        if ss.get("preserve_usd"):
                            # reconstruct qty from status if possible
                            pass
                        if ss.get("arm_vwap"):
                            px = float(ss.get("arm_vwap") or px)
                        if ss.get("preserve_usd") and px > 0 and amt <= 0:
                            amt = float(ss["preserve_usd"]) / px
                        elif ss.get("preserve_usd") and amt > 0:
                            px = float(ss.get("preserve_usd")) / amt if amt else px
                except Exception:
                    pass
                if amt > 0:
                    val = round(amt * px, 4) if px else 0.0
                    row = {
                        "pair": pax_pair,
                        "amount": amt,
                        "current_price": px,
                        "value_usd": val,
                        "entry_price": float(_pst.get("arm_vwap") or px or 0),
                        "unrealized_pnl_pct": 0.0,
                        "side": "long",
                        "sleeve": "preserve",
                        "note": "preserve_hold_sleeve",
                    }
                    tpos = list(out.get("trading_positions") or [])
                    tpos.append(row)
                    out["trading_positions"] = tpos
                    poss = list(out.get("positions") or [])
                    if not any((p.get("pair") or "").upper() == pax_pair.upper() for p in poss):
                        poss.append(row)
                    out["positions"] = poss
                    # fix totals if clearly missing sleeve
                    try:
                        th = float(out.get("total_holdings_value") or 0)
                        if th < val * 0.5:
                            out["total_holdings_value"] = th + val
                            out["total_usd"] = float(out.get("total_usd") or 0) + val
                            out["total_balance"] = out["total_usd"]
                    except Exception:
                        pass
    except Exception:
        pass

    price_quote_ts: dict = {}
    if PRICE_HISTORY.exists():
        try:
            ph = json.loads(PRICE_HISTORY.read_text())
            price_quote_ts = ph.get("last_updated") or {}
        except Exception:
            price_quote_ts = {}

    from phase6.core.price_staleness import resolve_position_price_stale

    state_as_of = out.get("last_updated") or out.get("data_as_of") or ""

    trading_raw = list(out.get("trading_positions") or [p for p in poss if p.get("pair") not in ("USD", "USDC")])
    if trading_raw:
        for p in trading_raw:
            pair = p.get("pair")
            if not pair:
                continue
            pair_ts = price_quote_ts.get(pair)
            stale = resolve_position_price_stale(
                p,
                pair_quote_ts=pair_ts,
                state_as_of=state_as_of or None,
            )
            p["price_stale"] = stale
            if not p.get("price_as_of"):
                p["price_as_of"] = pair_ts or state_as_of or None
        trading_raw = recompute_trading_positions_pnl(trading_raw, LEDGER)
        out["trading_positions"] = trading_raw
        # Keep combined positions list in sync for legacy consumers
        cash_part = [p for p in poss if p.get("pair") in ("USD", "USDC")]
        out["positions"] = cash_part + trading_raw
    trading_show, dust_hidden = split_dust_positions(trading_raw, DEFAULT_DUST_HIDE_USD)
    out["trading_positions"] = trading_show
    out["dust_positions_hidden"] = dust_hidden
    out["dust_hide_threshold_usd"] = DEFAULT_DUST_HIDE_USD
    cash_rows = list(out.get("cash_positions") or [])
    if not cash_rows:
        for b in out.get("balances") or []:
            cur = (b.get("currency") or "").upper()
            if cur in ("USD", "USDC"):
                bal = float(b.get("balance") or b.get("available") or 0)
                if bal >= 0.01:
                    cash_rows.append(
                        {
                            "pair": cur,
                            "amount": bal,
                            "available": bal,
                            "hold": 0.0,
                            "value_usd": bal,
                            "unrealized_pnl_pct": 0,
                        }
                    )
        out["cash_positions"] = cash_rows
    total_usd = out.get("total_usd") or out.get("total_balance")
    if not total_usd:
        cash_sum = 0.0
        for b in out.get("balances") or []:
            cash_sum += float(b.get("balance") or b.get("available") or 0)
        if not cash_sum and out.get("cash_usd") is not None:
            cash_sum = float(out.get("cash_usd") or 0) + float(out.get("usdc") or 0)
        hold_sum = sum(float(p.get("value_usd") or 0) for p in (out.get("trading_positions") or poss))
        total_usd = cash_sum + hold_sum
    out["total_usd"] = float(total_usd or 0)
    out["total_balance"] = out["total_usd"]
    if not out.get("active_positions"):
        out["active_positions"] = len(out.get("trading_positions") or [])
    from datetime import datetime, timezone

    out["data_as_of"] = out.get("last_updated") or ""
    out["pnl_computed_at"] = datetime.now(timezone.utc).isoformat()
    out["pnl_basis_note"] = (
        "Unrealized P&L vs average cost for current size. "
        "Prices and balances are from the latest runner refresh (data_as_of); "
        "avg cost merges ledger + verified Coinbase fills each time you load this view."
    )
    return out


def open_db(timeout: float = DB_READ_TIMEOUT, readonly: bool = True):
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
    if v > 0.03:
        return "Bullish", "emerald-400"
    elif v < -0.03:
        return "Bearish", "red-400"
    elif v > 0.01:
        return "Mild Bullish", "emerald-300"
    elif v < -0.01:
        return "Mild Bearish", "red-300"
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
    elif v < 45:
        return "Weak", "emerald-300"
    elif v > 55:
        return "Strong", "amber-300"
    return "Neutral", "slate-400"


def get_combined_status(rsi, sentiment, pair: str = ""):
    """
    Same Status as the daily brief / runner: phase6.core.signal_generator
    (weighted mode). Returns (status, color, score_or_conf, reason).
    """
    try:
        r = float(rsi) if rsi is not None else 50.0
    except (ValueError, TypeError):
        r = 50.0
    try:
        s = float(sentiment) if sentiment is not None else 0.0
    except (ValueError, TypeError):
        s = 0.0
    try:
        from phase6.core.signal_generator import SignalGenerator

        sig = SignalGenerator().generate_signal(
            pair or "PAIR", r, atr=None, sentiment=s, mode="weighted"
        )
        st = (sig.signal or "HOLD").upper()
        conf = float(sig.confidence or 0.0)
        reason = sig.reason or ""
    except Exception:
        # Fallback mirrors SignalGenerator._weighted_signal
        score = 0.0
        reasons = []
        if r < 30:
            score += 0.4
            reasons.append("RSI oversold")
        elif r > 70:
            score -= 0.4
            reasons.append("RSI overbought")
        if s > 0.2:
            score += 0.3
            reasons.append("Positive sentiment")
        elif s < -0.2:
            score -= 0.3
            reasons.append("Negative sentiment")
        if score > 0.25:
            st, conf, reason = "BUY", min(score, 1.0), " | ".join(reasons)
        elif score < -0.25:
            st, conf, reason = "SELL", min(abs(score), 1.0), " | ".join(reasons)
        else:
            st, conf, reason = "HOLD", 0.5, "No strong signal"
    color = {"BUY": "emerald-400", "SELL": "red-400"}.get(st, "slate-300")
    return st, color, round(conf, 3), reason


def _load_rsi_map():
    """pair -> {rsi, label, color, source} or empty."""
    rsi_file = Path("data/state/rsi_cache.json")
    if rsi_file.exists():
        try:
            with open(rsi_file) as f:
                raw = json.load(f)
            rsi_block = raw.get("rsi", {})
            out = {}
            for pair, info in rsi_block.items():
                rsi = info.get("rsi", 50.0) if isinstance(info, dict) else info
                try:
                    rsi = float(rsi)
                except Exception:
                    rsi = 50.0
                label, color = get_rsi_label(rsi)
                out[pair] = {"rsi": rsi, "label": label, "color": color, "source": "rsi_cache.json"}
            if out:
                return out, "data/state/rsi_cache.json"
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
                    data[pair] = {
                        "rsi": rsi,
                        "label": label,
                        "color": color,
                        "source": source or "db",
                        "ts": ts,
                    }
                return data, "phase6_db.rsi_values"
    except Exception:
        pass
    return {}, None


def _load_sentiment_map():
    """pair -> {sentiment, label, color, source} + meta dict."""
    meta = {}
    try:
        from phase6.core.sentiment_scorer import (
            load_sentiment_scores_detailed,
            get_sentiment_timestamp,
        )
        detail = load_sentiment_scores_detailed()
        ts = get_sentiment_timestamp()
        normalized = {}
        for pair, entry in (detail.get("scores") or {}).items():
            if isinstance(entry, dict):
                sent = float(entry.get("sentiment", 0.0) or 0.0)
                src = entry.get("source") or detail.get("mode") or "scorer"
            else:
                sent = float(entry or 0.0)
                src = detail.get("mode") or "scorer"
            label, color = get_sentiment_label(sent)
            normalized[pair] = {
                "sentiment": sent,
                "label": label,
                "color": color,
                "source": src,
            }
        mode = detail.get("mode") or "unknown"
        meta = {
            "mode": mode,
            "x_usable": detail.get("x_usable"),
            "non_zero": detail.get("non_zero"),
            "free_meta": detail.get("free_meta") or {},
            "timestamp": ts,
            "source": f"phase6.core.sentiment_scorer mode={mode}",
        }
        if normalized:
            return normalized, meta
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
                if isinstance(val, dict):
                    sent = float(
                        val.get("sentiment_score", val.get("sentiment", val.get("score", 0.0)))
                        or 0.0
                    )
                    src = val.get("source") or "sentiment_cache.json"
                else:
                    sent = float(val) if val is not None else 0.0
                    src = "sentiment_cache.json"
                label, color = get_sentiment_label(sent)
                normalized[pair] = {
                    "sentiment": sent,
                    "label": label,
                    "color": color,
                    "source": src,
                }
            if normalized:
                return normalized, {"source": "data/state/sentiment_cache.json"}
        except Exception:
            pass
    return {}, {"source": None}

def load_live_state():
    """Read the latest state written by the runner or collector."""
    if not CACHE_PATH.exists():
        return None
    try:
        with open(CACHE_PATH) as f:
            return enrich_live_state(json.load(f))
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
        if trading_positions:
            from phase6.core.position_cost_basis import recompute_trading_positions_pnl

            trading_positions = recompute_trading_positions_pnl(trading_positions, LEDGER)
            positions = cash_positions + trading_positions
        from datetime import datetime, timezone

        pnl_meta = {
            "data_as_of": last_upd or datetime.now(timezone.utc).isoformat(),
            "pnl_computed_at": datetime.now(timezone.utc).isoformat(),
            "pnl_basis_note": (
                "Unrealized P&L vs average cost for current size. "
                "DB prices/qty as of data_as_of; avg cost recomputed on each dashboard poll."
            ),
        }
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
            "brief_consumed": brief_con or 0,
            **pnl_meta,
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
            data = enrich_live_state(dict(state))
            data["mode"] = "live"
            data["source"] = data.get("source") or "Live (runner state)"
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
            data = enrich_live_state(dict(state))
            data["mode"] = "live"
            data["source"] = data.get("source") or "Live (runner state)"
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

def _query_v_dashboard_metrics():
    """Heavy DB view — run only inside a worker thread with an outer timeout."""
    conn = open_db(timeout=DB_READ_TIMEOUT, readonly=True)
    if not conn:
        return None
    try:
        conn.execute("PRAGMA busy_timeout=350")
        row = conn.execute("SELECT * FROM v_dashboard_metrics LIMIT 1").fetchone()
        if not row:
            return None
        cur = conn.execute("SELECT * FROM v_dashboard_metrics LIMIT 1")
        cols = [d[0] for d in (cur.description or [])]
        return dict(zip(cols, row)) if cols else None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _metrics_from_live_state(reason: str = "", message: str = "", db_metrics: dict | None = None):
    """Cache-first observability payload; optional DB overlay when fast.

    KPI truth: utilization and SL OK always prefer live holdings/protective-stop
    computation. Never let a stale DB 0% overwrite real attach rate.
    """
    st = load_live_state() or {}
    arch4 = st.get("arch4") or {}
    perf = st.get("performance_metrics") or {}
    total = float(st.get("total_usd") or st.get("total_balance") or 0)
    holdings = float(st.get("total_holdings_value") or 0)
    active = int(st.get("active_positions") or len(st.get("trading_positions") or []) or 0)
    # Primary holdings/total (match fast_observability)
    utilization = None
    if total > 0 and holdings >= 0:
        utilization = round(holdings / total, 4) if total > 0 else None
    if utilization is None:
        utilization = arch4.get("last_exposure")

    # Live SL OK from open trading positions (protective stop est / attach)
    trading = [
        p
        for p in (st.get("trading_positions") or st.get("positions") or [])
        if (p.get("pair") or "") not in ("USD", "USDC")
        and float(p.get("value_usd") or 0) >= 0.01
    ]
    live_sl = None
    if trading:
        protected = sum(
            1
            for p in trading
            if p.get("sl_stop_price_est") is not None
            or p.get("sl_attached") is True
            or p.get("stop_loss")
        )
        live_sl = round(protected / len(trading), 4)

    metrics = {
        "utilization": utilization,
        "proposal_acceptance": None,
        "sl_success_rate": live_sl if live_sl is not None else st.get("sl_success_rate"),
        "churn": arch4.get("last_rotations"),
        "rebalance_count": None,
        "recovery_attempts": st.get("recovery_attempts"),
        "replay_match_rate": st.get("replay_match_rate"),
        "total_trades": perf.get("total_trades"),
        "win_rate": perf.get("win_rate"),
    }
    if db_metrics:
        for key in (
            "proposal_acceptance",
            "churn",
            "rebalance_count",
            "recovery_attempts",
            "replay_match_rate",
            "win_rate",
            "total_trades",
        ):
            if db_metrics.get(key) is not None:
                metrics[key] = db_metrics[key]
        # utilization: keep live holdings/total; only fill if missing
        if metrics.get("utilization") is None and db_metrics.get("utilization") is not None:
            metrics["utilization"] = db_metrics["utilization"]
        # sl: prefer live attach rate; never replace with DB 0.0
        db_sl = db_metrics.get("sl_success_rate")
        if metrics.get("sl_success_rate") is None and db_sl is not None and float(db_sl) > 0:
            metrics["sl_success_rate"] = db_sl
        elif metrics.get("sl_success_rate") is None and db_sl is not None:
            metrics["sl_success_rate"] = None  # unknown → UI shows --

    status = "ok" if (db_metrics or utilization is not None) else "degraded"
    source = (
        "fast_observability + live holdings/SL"
        if reason == "cache_first_live"
        else ("v_dashboard_metrics overlay" if db_metrics else "phase6_live_state.json (cache-first)")
    )
    payload = {
        "status": status,
        "metrics": metrics,
        "source": source,
        "last_updated": st.get("last_updated") or datetime.now(timezone.utc).isoformat(),
    }
    if reason and status == "degraded":
        payload["reason"] = reason
    if message:
        payload["message"] = message
    # REGIME-CASH (RC-03) — cache file first, else resolve
    try:
        rc_path = Path("data/state/regime_cash_status.json")
        if rc_path.exists():
            payload["regime_cash"] = json.loads(rc_path.read_text(encoding="utf-8"))
        else:
            from phase6.core.regime_cash_policy import resolve_regime_cash, persist_status

            snap = resolve_regime_cash()
            persist_status(snap)
            payload["regime_cash"] = snap.to_dict()
    except Exception as e:
        payload["regime_cash"] = {"error": str(e), "regime": "unknown"}
    # Preserve Hold badge (status file; never claims risk-free)
    try:
        from phase6.core.paths import PROJECT_ROOT as _PR

        ph_path = _PR / "data/state/preserve_hold_status.json"
        if ph_path.exists():
            payload["preserve_mode"] = json.loads(ph_path.read_text(encoding="utf-8"))
        else:
            from phase6.core.preserve_hold import persist_status

            payload["preserve_mode"] = persist_status()
        # Always recompute badge from live state when file is stale OFF
        pm = payload.get("preserve_mode") or {}
        if pm.get("badge") == "OFF" or not pm.get("state_armed"):
            try:
                from phase6.core.preserve_hold import status_snapshot

                live_pm = status_snapshot()
                if live_pm.get("state_armed") or live_pm.get("badge") not in (None, "OFF"):
                    payload["preserve_mode"] = live_pm
            except Exception:
                pass
    except Exception as e:
        payload["preserve_mode"] = {"badge": "OFF", "error": str(e), "detail": "status unavailable"}
    return payload


def fetch_dashboard_metrics():
    """Cache-first metrics. Live mode never blocks on v_dashboard_metrics (heavy view)."""
    if MODE == "live":
        st = load_live_state() or {}
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            fut = pool.submit(fast_observability_metrics, DB_PATH, st, 0.8)
            fast = fut.result(timeout=1.2)
        except Exception:
            fast = None
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        # Prefer fast_observability (already util + SL from positions); merge keeps live SL/util truth
        return _metrics_from_live_state("cache_first_live", db_metrics=fast)

    if not DB_PATH.exists():
        return _metrics_from_live_state("no_db")

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(_query_v_dashboard_metrics)
        db_metrics = fut.result(timeout=0.45)
    except concurrent.futures.TimeoutError:
        print("metrics fetch: v_dashboard_metrics timed out (>0.45s)")
        return _metrics_from_live_state("view_timeout")
    except Exception as e:
        print(f"metrics fetch error: {e}")
        return _metrics_from_live_state("error", str(e))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    if db_metrics:
        return _metrics_from_live_state(db_metrics=db_metrics)
    return _metrics_from_live_state("no_data")

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
            # newest-first (ledger sorts; keep explicit for API contract)
            trades = sorted(
                trades or [],
                key=lambda t: str(t.get("timestamp") or t.get("ts") or ""),
                reverse=True,
            )
            self.send_json({"trades": trades, "mode": MODE, "count": len(trades), "source": "TradeLedger"})
        elif path == '/api/sentiment':
            # Scorer first (includes free_fallback when X empty/spend-cap)
            try:
                from phase6.core.sentiment_scorer import (
                    load_sentiment_scores_detailed,
                    get_sentiment_timestamp,
                )
                detail = load_sentiment_scores_detailed()
                ts = get_sentiment_timestamp()
                normalized = {}
                for pair, entry in (detail.get("scores") or {}).items():
                    if isinstance(entry, dict):
                        sent = float(entry.get("sentiment", 0.0) or 0.0)
                        src = entry.get("source") or detail.get("mode") or "scorer"
                    else:
                        sent = float(entry or 0.0)
                        src = detail.get("mode") or "scorer"
                    label, color = get_sentiment_label(sent)
                    normalized[pair] = {
                        "sentiment": sent,
                        "label": label,
                        "color": color,
                        "source": src,
                    }
                mode = detail.get("mode") or "unknown"
                self.send_json({
                    "status": "ok",
                    "data": normalized,
                    "source": f"phase6.core.sentiment_scorer mode={mode}",
                    "mode": mode,
                    "x_usable": detail.get("x_usable"),
                    "non_zero": detail.get("non_zero"),
                    "free_meta": detail.get("free_meta") or {},
                    "timestamp": ts,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                })
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
                            if isinstance(val, dict):
                                sent = float(
                                    val.get("sentiment_score", val.get("sentiment", val.get("score", 0.0)))
                                    or 0.0
                                )
                                src = val.get("source") or "sentiment_cache.json"
                            else:
                                sent = float(val) if val is not None else 0.0
                                src = "sentiment_cache.json"
                            label, color = get_sentiment_label(sent)
                            normalized[pair] = {
                                "sentiment": sent,
                                "label": label,
                                "color": color,
                                "source": src,
                            }
                        self.send_json({
                            "status": "ok",
                            "data": normalized,
                            "source": "data/state/sentiment_cache.json",
                            "last_updated": datetime.now(timezone.utc).isoformat(),
                        })
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
                            data[pair] = {
                                "sentiment": sent,
                                "label": label,
                                "color": color,
                                "source": source or "db",
                                "ts": ts,
                            }
                        self.send_json({
                            "status": "ok",
                            "data": data,
                            "source": "phase6_db.sentiment_scores (dynamic)",
                            "last_updated": datetime.now(timezone.utc).isoformat(),
                        })
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
            self.send_json({"status": "no_data", "message": "No RSI data found"})

        elif path == '/api/pair-signals':
            # Active trading basket only (runner/rebalancer eligible).
            # Shadow discovery / opportunity_pool contenders are intentionally excluded —
            # those may get a separate pane later.
            try:
                from phase6.core.paths import load_trading_basket
                basket = [str(p) for p in (load_trading_basket() or []) if p]
            except Exception:
                basket = []
            if not basket:
                # Last-resort: config file direct (same SSOT path as load_trading_basket)
                try:
                    cfg = json.loads((BASE / "config/trading_config_phase6.json").read_text())
                    basket = [str(p) for p in (cfg.get("global_settings") or {}).get("pairs") or [] if p]
                except Exception:
                    basket = []

            rsi_map, rsi_src = _load_rsi_map()
            sent_map, sent_meta = _load_sentiment_map()
            # Post-SL / manual rebuy blocks (same sources as runner deploy gate)
            buy_blocks = {}
            block_hours = 72.0
            try:
                from phase6.core.runner_capital_events import load_buy_block_status
                buy_blocks = load_buy_block_status() or {}
                if buy_blocks:
                    block_hours = float(next(iter(buy_blocks.values())).get("block_hours") or 72.0)
                else:
                    from phase6.core.runner_capital_events import _default_stop_block_hours
                    block_hours = float(_default_stop_block_hours())
            except Exception:
                buy_blocks = {}
            # Preserve config basket order (not A→Z cache union).
            pairs = list(basket)
            rows = []
            blocked_pairs = []
            for pair in pairs:
                r = rsi_map.get(pair) or {}
                s = sent_map.get(pair) or {}
                rsi_v = r.get("rsi")
                if rsi_v is None:
                    rsi_v = 50.0
                sent_v = s.get("sentiment")
                if sent_v is None:
                    sent_v = 0.0
                status, st_color, conf, reason = get_combined_status(rsi_v, sent_v, pair=pair)
                blk = buy_blocks.get(pair) or buy_blocks.get(str(pair).upper()) or {}
                buy_blocked = bool(blk.get("blocked"))
                if buy_blocked:
                    blocked_pairs.append(pair)
                    # Signal formula can still say BUY — block is a separate deploy gate.
                    if status == "BUY":
                        reason = (reason or "") + " · auto-BUY blocked until cooldown expires"
                rows.append({
                    "pair": pair,
                    "rsi": round(float(rsi_v), 2),
                    "rsi_label": r.get("label") or get_rsi_label(rsi_v)[0],
                    "rsi_color": r.get("color") or get_rsi_label(rsi_v)[1],
                    "sentiment": round(float(sent_v), 4),
                    "sentiment_label": s.get("label") or get_sentiment_label(sent_v)[0],
                    "sentiment_color": s.get("color") or get_sentiment_label(sent_v)[1],
                    "status": status,
                    "status_color": st_color,
                    "confidence": conf,
                    "reason": reason,
                    # back-compat for older UI tooltip
                    "weighted": conf,
                    "in_active_basket": True,
                    "buy_blocked": buy_blocked,
                    "block_reason": blk.get("reason") if buy_blocked else None,
                    "block_source": blk.get("source") if buy_blocked else None,
                    "block_expires_at": blk.get("expires_at") if buy_blocked else None,
                    "block_hours_remaining": blk.get("hours_remaining") if buy_blocked else None,
                    "block_hours": blk.get("block_hours") if buy_blocked else block_hours,
                })
            ok = bool(rows)
            self.send_json({
                "status": "ok" if ok else "no_data",
                "rows": rows,
                "count": len(rows),
                "basket": pairs,
                "basket_scope": "active_trading",
                "buy_blocked_pairs": blocked_pairs,
                "buy_block_hours": block_hours,
                "rsi_source": rsi_src,
                "sentiment_source": (sent_meta or {}).get("source"),
                "sentiment_mode": (sent_meta or {}).get("mode"),
                "formula": "SignalGenerator weighted (same as daily brief): RSI±0.4 at 30/70, sent±0.3 at ±0.2; BUY if score>0.25, SELL if <-0.25, else HOLD. Rows = global_settings.pairs only. ·blocked = post-SL/manual rebuy cooldown (no auto-BUY until expiry).",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            })
            return

        elif path == '/api/performance':
            st = load_live_state() or {}
            perf = st.get("performance_metrics") or {}
            total = float(st.get("total_usd") or st.get("total_balance") or 0)
            trading = st.get("trading_positions") or st.get("positions") or []

            # Short TTL cache: mobile refresh was hammering large DB → N/A tiles + starved balances.
            # Key is stable (not per-cent NAV) so TTL actually hits across polls.
            cache_key = "api_performance_v2"
            cached_payload = performance_cache.get(cache_key)

            closed_win = win_ratio_from_positions(trading)
            trades = LEDGER.get_recent_trades(limit=100)
            closed = [t for t in trades if t.get("pnl") is not None and float(t.get("pnl") or 0) != 0]
            win_ratio_exits = None
            if closed:
                win_wins = sum(1 for t in closed if (t.get("pnl") or 0) > 0)
                win_ratio = win_wins / len(closed)
                win_ratio_exits = {
                    "wins": win_wins,
                    "total": len(closed),
                    "basis": "ledger_nonzero_pnl",
                }
            else:
                win_ratio = closed_win if trading else float(perf.get("win_rate", 0.0) or 0.0)
                if trading and closed_win:
                    win_ratio_exits = {"basis": "open_book_unrealized", "total": len(trading)}

            if cached_payload and isinstance(cached_payload, dict):
                out = dict(cached_payload)
                out["win_ratio"] = round(float(win_ratio), 3)
                out["win_ratio_exits"] = win_ratio_exits
                out["total_trades"] = len(trades) or perf.get("total_trades", 0)
                out["last_updated"] = datetime.now(timezone.utc).isoformat()
                out["cache"] = "hit"
                self.send_json(out)
                return

            # Single-flight cold compute: concurrent UI polls must not N× stampede SQLite.
            # Sequential periods-then-equity with tight timeouts (parallel dual-read thrash).
            acquired = perf_compute_lock.acquire(blocking=False)
            if not acquired:
                # Another thread computing — serve explicit short timeout, never fake 0 tiles.
                self.send_json({
                    "status": "ok",
                    "win_ratio": round(float(win_ratio), 3),
                    "win_ratio_exits": win_ratio_exits,
                    "total_trades": len(trades) or perf.get("total_trades", 0),
                    "today": None,
                    "h24": None,
                    "d7": None,
                    "d14": None,
                    "d30": None,
                    "external_flows_usd": {},
                    "deposit_adjusted": False,
                    "equity_trend": {"status": "timeout", "points": []},
                    "source": "portfolio_snapshots_db + positions (inflight)",
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "cache": "inflight",
                })
                return
            try:
                # Re-check cache after acquiring (winner may have just filled it).
                cached_payload = performance_cache.get(cache_key)
                if cached_payload and isinstance(cached_payload, dict):
                    out = dict(cached_payload)
                    out["win_ratio"] = round(float(win_ratio), 3)
                    out["win_ratio_exits"] = win_ratio_exits
                    out["total_trades"] = len(trades) or perf.get("total_trades", 0)
                    out["last_updated"] = datetime.now(timezone.utc).isoformat()
                    out["cache"] = "hit"
                    self.send_json(out)
                    return

                try:
                    periods = compute_period_performance(total, DB_PATH, timeout=3.5)
                except Exception:
                    periods = {
                        "today": None,
                        "h24": None,
                        "d7": None,
                        "d14": None,
                        "d30": None,
                        "source": "timeout",
                        "external_flows_usd": {},
                    }
                try:
                    equity_trend = compute_equity_trend(
                        total,
                        DB_PATH,
                        days=30,
                        max_points=36,
                        timeout=3.5,
                    )
                except Exception:
                    equity_trend = {"status": "timeout", "points": []}

                payload = {
                    "status": "ok",
                    "win_ratio": round(float(win_ratio), 3),
                    "win_ratio_exits": win_ratio_exits,
                    "total_trades": len(trades) or perf.get("total_trades", 0),
                    "today": periods.get("today"),
                    "h24": periods.get("h24"),
                    "d7": periods.get("d7"),
                    "d14": periods.get("d14"),
                    "d30": periods.get("d30"),
                    "external_flows_usd": periods.get("external_flows_usd") or {},
                    "deposit_adjusted": str(periods.get("source", "")).endswith("_adjusted"),
                    "equity_trend": equity_trend,
                    "source": f"portfolio_snapshots_db + positions ({periods.get('source', '')})",
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "cache": "miss",
                }
                populated = any(
                    periods.get(k) is not None for k in ("today", "h24", "d7", "d14", "d30")
                )
                # Always cache: populated → 60s; empty/timeout → 15s anti-stampede (not forever N/A).
                performance_cache.set(cache_key, payload, ttl=60.0 if populated else 15.0)
                self.send_json(payload)
            finally:
                perf_compute_lock.release()
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
        elif path == '/api/capital/controls':
            try:
                qs = urllib.parse.parse_qs(parsed.query or "")
                aid = (qs.get("account_id") or [None])[0]
                from phase6.core.capital_controls_api import get_capital_controls_status

                self.send_json({"status": "ok", **get_capital_controls_status(aid)})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)})
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}

        try:
            if path == "/api/capital/clear-cash-hold":
                from phase6.core.capital_controls_api import api_clear_cash_hold

                aid = body.get("account_id")
                source = str(body.get("source") or "dashboard")
                result = api_clear_cash_hold(aid, source=source)
                self.send_json({"status": "ok", **result})
            elif path == "/api/capital/clear-cooldown":
                from phase6.core.capital_controls_api import api_clear_cooldown

                aid = body.get("account_id")
                source = str(body.get("source") or "dashboard")
                clear_all = bool(body.get("all"))
                pairs = body.get("pairs")
                if isinstance(pairs, str):
                    pairs = [pairs]
                result = api_clear_cooldown(
                    aid,
                    pairs=list(pairs) if pairs else None,
                    clear_all=clear_all,
                    source=source,
                )
                self.send_json({"status": "ok", **result})
            elif path == "/api/capital/request-clear-cash-hold":
                from phase6.core.capital_controls_api import api_request_clear_cash_hold

                self.send_json(
                    {"status": "ok", **api_request_clear_cash_hold(body.get("account_id"))}
                )
            else:
                self.send_error(404)
        except Exception as e:
            self.send_json({"status": "error", "message": str(e)})

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

    class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        daemon_threads = True

    print(f"Phase 6 Dashboard ({MODE} mode, DB-first) at http://0.0.0.0:{args.port}")
    with ThreadingHTTPServer(('0.0.0.0', args.port), Handler) as httpd:
        httpd.serve_forever()
