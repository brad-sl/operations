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
from typing import Any, Dict

from dotenv import load_dotenv
load_dotenv()

from phase6.core.trade_ledger import TradeLedger
from phase6.core.performance_api import (
    flush_performance_cache,
    perf_compute_lock,
    performance_cache,
    schedule_performance_recompute,
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
    # Always prefer cash+holdings when both present — refuses PAXG-only totals
    # left on disk after a cash-API wipe (header $84 / −96% class).
    try:
        cash_sum = 0.0
        for b in out.get("balances") or []:
            cur = str(b.get("currency") or "").upper()
            if cur in ("USD", "USDC"):
                cash_sum += float(b.get("balance") or b.get("available") or 0)
        if not cash_sum and out.get("cash_usd") is not None:
            cash_sum = float(out.get("cash_usd") or 0) + float(out.get("usdc") or 0)
        for row in out.get("cash_positions") or []:
            cash_sum = max(cash_sum, float(row.get("value_usd") or row.get("amount") or 0))
        hold_sum = sum(
            float(p.get("value_usd") or 0)
            for p in (out.get("trading_positions") or poss or [])
            if str(p.get("pair") or "").upper() not in ("USD", "USDC")
        )
        recomputed = cash_sum + hold_sum
        if recomputed > 0 and (
            not total_usd
            or float(total_usd or 0) <= 0
            or (cash_sum >= 50 and float(total_usd or 0) < cash_sum * 0.5)
        ):
            total_usd = recomputed
            out["total_holdings_value"] = hold_sum
            if cash_sum and out.get("cash_usd") is None:
                out["cash_usd"] = cash_sum
    except Exception:
        pass
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
    """Strength-scaled sentiment label/color (aligned with live gates, not vanity green).

    Trading-relevant floors (REGIME-CASH / SignalGenerator):
      ±0.20  → weighted signal "positive/negative sentiment" contribution
      +0.15  → bull *new-pair* min_sentiment_new_pair (empty seat)
      -0.10  → bull min_sentiment for *existing* held seats
    Values like +0.05 are mild — must NOT read as full emerald "Bullish".
    """
    try:
        v = float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        v = 0.0
    # Strong (signal-generator magnitude)
    if v >= 0.20:
        return "Strong bull", "emerald-400"
    if v <= -0.20:
        return "Strong bear", "red-400"
    # Clears typical new-pair entry floor in bull (~0.15)
    if v >= 0.15:
        return "Bull (new-ok)", "emerald-300"
    if v <= -0.15:
        return "Bear", "red-300"
    # Mild — visible but not "go" green (RAVE ~0.05 lives here)
    if v >= 0.045:
        return "Mild+", "cyan-400"
    if v <= -0.045:
        return "Mild-", "orange-400"
    if v >= 0.015:
        return "Soft+", "slate-300"
    if v <= -0.015:
        return "Soft-", "slate-300"
    return "Neutral", "slate-500"


# Trades panel: compact reason (1–2 words). Full ledger string stays on reason/exit_reason.
_TRADE_REASON_SHORT: Dict[str, str] = {
    "stop_loss_exchange": "SL",
    "stop_loss": "SL",
    "rotation_exchange": "ROT",
    "rotation": "ROT",
    "rebalance_buy": "Rebal",
    "rebalance": "Rebal",
    "take_profit_trail": "Trail TP",
    "take_profit_fixed_tp": "TP",
    "take_profit": "TP",
    "lifecycle_dual_peak": "Dual peak",
    "lifecycle_extension_partial": "Extension",
    "lifecycle_extension": "Extension",
    "lifecycle_protected_exit": "Protect",
    "dust_sweep_after_sl": "Dust",
    "dust_sweep_orphan": "Dust",
    "dust_sweep": "Dust",
    "preserve_arm_micro": "Preserve",
    "preserve_arm": "Preserve",
    "preserve_disarm": "Disarm",
    "preserve_buy": "Preserve",
    "preserve_trim": "Preserve",
}


def short_trade_reason(raw: Any) -> str:
    """Map machine exit/buy reason → short Trades-column label."""
    full = str(raw or "").strip()
    if not full:
        return ""
    head = full.split(":", 1)[0].strip().lower()
    if head in _TRADE_REASON_SHORT:
        return _TRADE_REASON_SHORT[head]
    if head.startswith("operator_trim"):
        return "Trim"
    if head.startswith("lifecycle_"):
        bits = [b for b in head.replace("lifecycle_", "", 1).split("_") if b]
        if not bits:
            return "Lifecycle"
        first = bits[0].capitalize()
        if len(bits) == 1:
            return first
        return f"{first} {bits[1]}"
    if head.startswith("dust"):
        return "Dust"
    token = head.split("_")[0] if head else full[:12]
    return token[:12].capitalize() if token else ""


def _annotate_trade_reason_short(t: Any) -> Any:
    if not isinstance(t, dict):
        return t
    out = dict(t)
    raw = out.get("reason") or out.get("exit_reason") or ""
    label = short_trade_reason(raw)
    if label:
        out["reason_label"] = label
        out["reason_short"] = label  # alias for UI
    return out


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
    # Market heat vs posture + Why idle (scale FAQ — explanation mandatory)
    try:
        from phase6.core.market_posture_explain import build_market_posture_payload

        posture = build_market_posture_payload(force_heat=False)
        payload["market_heat"] = posture.get("market_heat")
        payload["why_idle"] = posture.get("why_idle")
        payload["cream_summary"] = posture.get("cream_summary")
    except Exception as e:
        payload["market_heat"] = {"hot": None, "error": str(e)}
        payload["why_idle"] = {"headline": "posture unavailable", "reasons": [], "error": str(e)}
        payload["cream_summary"] = {}
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
            # Compact reason for Trades panel; full machine string stays in reason/exit_reason
            try:
                trades = [_annotate_trade_reason_short(t) for t in trades]
            except Exception:
                pass
            # Per-trader display TZ (storage stays UTC / Coinbase standard)
            try:
                from phase6.core.trader_account_config import (
                    resolve_runner_account_id,
                    ui_display_settings,
                )
                ui = ui_display_settings(resolve_runner_account_id(None))
            except Exception:
                ui = {
                    "display_timezone": "America/Los_Angeles",
                    "locale": "en-US",
                }
            self.send_json({
                "trades": trades,
                "mode": MODE,
                "count": len(trades),
                "source": "TradeLedger",
                "timestamp_storage": "UTC",
                "display_timezone": ui.get("display_timezone") or "America/Los_Angeles",
                "locale": ui.get("locale") or "en-US",
            })
        elif path == '/api/ui-prefs':
            try:
                from phase6.core.trader_account_config import (
                    resolve_runner_account_id,
                    ui_display_settings,
                )
                ui = ui_display_settings(resolve_runner_account_id(None))
            except Exception as e:
                ui = {
                    "display_timezone": "America/Los_Angeles",
                    "locale": "en-US",
                    "error": str(e)[:120],
                }
            self.send_json({"status": "ok", **ui, "timestamp_storage": "UTC"})
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
            # Mid-cycle teed-up preview (free/Adanos/raw X) — DISPLAY ONLY, not gates
            teed_bundle: Dict[str, Any] = {}
            teed_by: Dict[str, Any] = {}
            try:
                from phase6.core.sentiment_teed_up_preview import (
                    load_sentiment_teed_up_preview,
                )
                teed_bundle = load_sentiment_teed_up_preview(basket=basket) or {}
                teed_by = teed_bundle.get("by_pair") or {}
            except Exception:
                teed_bundle = {}
                teed_by = {}
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

            # Held seats (for new-pair vs add entry floors) — same idea as ·held in UI
            held_pairs = set()
            held_usd_map = {}
            try:
                st_live = load_live_state() or {}
                for p in (st_live.get("trading_positions") or st_live.get("positions") or []):
                    if not isinstance(p, dict):
                        continue
                    pair_h = str(p.get("pair") or p.get("product_id") or "")
                    if not pair_h or pair_h in ("USD", "USDC"):
                        continue
                    usd = p.get("value_usd")
                    if usd is None:
                        usd = p.get("usd_value")
                    if usd is None:
                        usd = p.get("market_value")
                    try:
                        usd_f = float(usd or 0)
                    except (TypeError, ValueError):
                        usd_f = 0.0
                    held_usd_map[pair_h] = usd_f
                    # Flat dust ≠ held seat for new-pair sentiment floor
                    if usd_f >= 25.0:
                        held_pairs.add(pair_h)
            except Exception:
                held_pairs = set()
                held_usd_map = {}

            # REGIME-CASH entry floors (the "under the table" gates)
            entry_snap = None
            entry_floors = {
                "min_sentiment": -0.1,
                "min_sentiment_new_pair": 0.15,
                "max_rsi": 70.0,
            }
            try:
                from phase6.core.regime_cash_policy import resolve_regime_cash, evaluate_buy_entry
                entry_snap = resolve_regime_cash()
                if getattr(entry_snap, "entry", None):
                    entry_floors = {
                        "min_sentiment": float((entry_snap.entry or {}).get("min_sentiment", -0.1)),
                        "min_sentiment_new_pair": float(
                            (entry_snap.entry or {}).get("min_sentiment_new_pair", 0.15)
                        ),
                        "max_rsi": float((entry_snap.entry or {}).get("max_rsi", 70.0)),
                    }
            except Exception:
                entry_snap = None
                evaluate_buy_entry = None  # type: ignore

            # ADD-RISK room (held stacks) — ·block-max when max_add < min_move
            add_room_by: Dict[str, Any] = {}
            max_blocked_pairs: list = []
            add_room_meta: Dict[str, Any] = {}
            try:
                from phase6.core.add_risk_sizer import load_add_room_by_pair_for_dashboard
                _ar = load_add_room_by_pair_for_dashboard() or {}
                add_room_by = _ar.get("by_pair") or {}
                max_blocked_pairs = list(_ar.get("max_blocked_pairs") or [])
                add_room_meta = {
                    "min_move_usd": _ar.get("min_move_usd"),
                    "target_pair_weight": _ar.get("target_pair_weight"),
                    "regime": _ar.get("regime"),
                    "enabled": _ar.get("enabled"),
                }
            except Exception:
                add_room_by = {}
                max_blocked_pairs = []
                add_room_meta = {}

            # Recovery / quality_tryout telegraph (visible mode, not hover-only)
            recovery_summary: Dict[str, Any] = {}
            try:
                from phase6.core.dashboard_serve_helpers import (
                    recovery_policy_dashboard_summary,
                    short_gate_label,
                )
                recovery_summary = recovery_policy_dashboard_summary() or {}
            except Exception:
                recovery_summary = {}
                try:
                    from phase6.core.dashboard_serve_helpers import short_gate_label
                except Exception:
                    short_gate_label = None  # type: ignore

            # Preserve config basket order (not A→Z cache union).
            pairs = list(basket)
            rows = []
            blocked_pairs = []
            gated_pairs = []
            for pair in pairs:
                r = rsi_map.get(pair) or {}
                s = sent_map.get(pair) or {}
                rsi_v = r.get("rsi")
                if rsi_v is None:
                    rsi_v = 50.0
                sent_v = s.get("sentiment")
                if sent_v is None:
                    sent_v = 0.0
                # Always recompute sentiment label/color here (strength scale) —
                # do not trust cache labels that painted mild +0.05 as full Bullish.
                sent_label, sent_color = get_sentiment_label(sent_v)
                rsi_label, rsi_color = get_rsi_label(rsi_v)
                status, st_color, conf, reason = get_combined_status(rsi_v, sent_v, pair=pair)
                blk = buy_blocks.get(pair) or buy_blocks.get(str(pair).upper()) or {}
                buy_blocked = bool(blk.get("blocked"))
                if buy_blocked:
                    blocked_pairs.append(pair)
                    # Signal formula can still say BUY — block is a separate deploy gate.
                    if status == "BUY":
                        reason = (reason or "") + " · auto-BUY blocked until cooldown expires"

                is_new_seat = pair not in held_pairs
                sent_floor = (
                    entry_floors["min_sentiment_new_pair"]
                    if is_new_seat
                    else entry_floors["min_sentiment"]
                )
                entry_allowed = True
                entry_reasons = []
                if entry_snap is not None and evaluate_buy_entry is not None:
                    try:
                        dec = evaluate_buy_entry(
                            pair,
                            entry_snap,
                            sentiment=float(sent_v),
                            rsi=float(rsi_v),
                            lockout_pairs=set(blocked_pairs) | {
                                p for p, b in buy_blocks.items() if (b or {}).get("blocked")
                            },
                            is_new_pair=is_new_seat,
                        )
                        entry_allowed = bool(dec.allowed)
                        entry_reasons = list(dec.reasons or [])
                    except Exception as _eg:
                        entry_allowed = True
                        entry_reasons = [f"entry_check_error:{_eg}"]

                # BUY signal that cannot clear deploy entry gates → telegraph weak/gated
                entry_gated = bool(status == "BUY" and not entry_allowed)
                if entry_gated:
                    gated_pairs.append(pair)
                    why = "; ".join(entry_reasons) if entry_reasons else "entry_gate"
                    seat = "new seat" if is_new_seat else "add"
                    reason = (
                        (reason or "BUY")
                        + f" · gated ({seat}: need sent≥{sent_floor:.2f}; {why})"
                    )
                    # Dim the status green — not a clean deploy light
                    st_color = "amber-400"

                # ADD-RISK: held stack with no meaningful add room
                ar = add_room_by.get(pair) or add_room_by.get(str(pair).upper()) or {}
                block_max = bool(ar.get("block_max"))
                max_add_usd = ar.get("max_add_usd")
                held_weight_pct = ar.get("weight_pct")
                over_target = bool(ar.get("over_target"))
                add_block_reason = ar.get("detail_reason") if block_max else None
                if block_max and status == "BUY":
                    why_ar = str(add_block_reason or "add_risk")
                    wtxt = f" wt {held_weight_pct:.0f}%" if held_weight_pct is not None else ""
                    mad = f" max_add=${float(max_add_usd):.0f}" if max_add_usd is not None else ""
                    reason = (reason or "BUY") + f" · block-max ({why_ar}{wtxt}{mad})"
                    # Keep Status BUY (signal) — flag carries the gate; dim slightly if not already gated
                    if not entry_gated and st_color == "emerald-400":
                        st_color = "amber-400"

                deploy_ready = bool(
                    status == "BUY" and entry_allowed and not buy_blocked
                    and bool(getattr(entry_snap, "allow_new_buys", True) if entry_snap else True)
                    and not block_max
                )

                gate_label = None
                # Surface deploy gates even when Status ≠ BUY (HOLD/SELL still blocked from new seats).
                show_gate = (not entry_allowed) or buy_blocked or block_max
                if short_gate_label is not None and show_gate:
                    try:
                        gate_label = short_gate_label(
                            entry_reasons if not entry_allowed else [],
                            buy_blocked=buy_blocked,
                            block_max=block_max,
                            add_block_reason=add_block_reason,
                            block_reason=blk.get("reason") if buy_blocked else None,
                        )
                    except Exception:
                        gate_label = None

                # seat_closed: empty seat that policy will not open (tryout/allowlist/floors)
                seat_closed = bool(is_new_seat and not entry_allowed)

                tee = teed_by.get(pair) or teed_by.get(str(pair).upper()) or {}
                teed_v = tee.get("teed")
                teed_src = tee.get("teed_source")
                teed_label = None
                teed_color = None
                if teed_v is not None:
                    try:
                        teed_label, teed_color = get_sentiment_label(float(teed_v))
                    except Exception:
                        teed_label, teed_color = None, None

                aged_out = bool(tee.get("live_aged_out"))
                # Preview signal from tee (RSI + free/Adanos/x_raw) — DISPLAY ONLY
                status_preview = None
                status_preview_color = None
                status_preview_conf = None
                status_preview_reason = None
                if teed_v is not None and aged_out:
                    try:
                        sp, spc, spconf, spreason = get_combined_status(
                            rsi_v, float(teed_v), pair=pair
                        )
                        status_preview = sp
                        status_preview_color = spc
                        status_preview_conf = spconf
                        status_preview_reason = spreason
                    except Exception:
                        status_preview = None

                # What the operator should *read* as the score mid-cycle
                if aged_out and teed_v is not None:
                    sent_show = round(float(teed_v), 4)
                    sent_show_label = teed_label or sent_label
                    sent_show_color = teed_color or sent_color
                    sent_show_is_preview = True
                    sent_show_source = teed_src or "preview"
                else:
                    sent_show = round(float(sent_v), 4)
                    sent_show_label = sent_label
                    sent_show_color = sent_color
                    sent_show_is_preview = False
                    sent_show_source = "live"

                # Status the eye should read: preview when live aged-out, else live
                if (
                    aged_out
                    and status_preview
                    and status_preview != status
                ):
                    status_show = status_preview
                    status_show_color = (
                        "amber-400"
                        if status_preview == "BUY"
                        else (
                            "orange-400"
                            if status_preview == "SELL"
                            else (status_preview_color or st_color)
                        )
                    )
                    status_show_is_preview = True
                else:
                    status_show = status
                    status_show_color = st_color
                    status_show_is_preview = False

                rows.append({
                    "pair": pair,
                    "rsi": round(float(rsi_v), 2),
                    "rsi_label": rsi_label,
                    "rsi_color": rsi_color,
                    # Live gate scorer (may be 0 when aged) — still authoritative for deploy
                    "sentiment": round(float(sent_v), 4),
                    "sentiment_label": sent_label,
                    "sentiment_color": sent_color,
                    # Operator-facing score (tee when live aged-out)
                    "sentiment_show": sent_show,
                    "sentiment_show_label": sent_show_label,
                    "sentiment_show_color": sent_show_color,
                    "sentiment_show_is_preview": sent_show_is_preview,
                    "sentiment_show_source": sent_show_source,
                    "sentiment_live_raw": tee.get("live_raw"),
                    "sentiment_aged_out": aged_out,
                    "sentiment_age_min": tee.get("age_min"),
                    "sentiment_decay": tee.get("decay_factor"),
                    "teed_sentiment": None if teed_v is None else round(float(teed_v), 4),
                    "teed_source": teed_src,
                    "teed_label": teed_label,
                    "teed_color": teed_color,
                    "teed_drives_gates": False,
                    "teed_free": tee.get("free"),
                    "teed_adanos": tee.get("adanos"),
                    "teed_x_raw": tee.get("x_raw"),
                    "teed_reddit": tee.get("reddit"),
                    # Live status (runner/gates path)
                    "status": status,
                    "status_color": st_color,
                    "confidence": conf,
                    "reason": reason,
                    # Preview status from tee mid-cycle (not deploy)
                    "status_preview": status_preview,
                    "status_preview_color": status_preview_color,
                    "status_preview_confidence": status_preview_conf,
                    "status_preview_reason": status_preview_reason,
                    "status_show": status_show,
                    "status_show_color": status_show_color,
                    "status_show_is_preview": status_show_is_preview,
                    # back-compat for older UI tooltip
                    "weighted": conf,
                    "in_active_basket": True,
                    "held_usd": round(float(held_usd_map.get(pair) or 0.0), 2),
                    "is_new_seat": is_new_seat,
                    "seat_closed": seat_closed,
                    "buy_blocked": buy_blocked,
                    "block_reason": blk.get("reason") if buy_blocked else None,
                    "block_source": blk.get("source") if buy_blocked else None,
                    "block_expires_at": blk.get("expires_at") if buy_blocked else None,
                    "block_hours_remaining": blk.get("hours_remaining") if buy_blocked else None,
                    "block_hours": blk.get("block_hours") if buy_blocked else block_hours,
                    # Deploy telegraph (REGIME-CASH) — separate from signal Status
                    "entry_allowed": entry_allowed,
                    "entry_gated": entry_gated,
                    "entry_reasons": entry_reasons,
                    "entry_sent_floor": sent_floor,
                    "deploy_ready": deploy_ready,
                    # Plain-English gate (visible; full machine string stays in entry_reasons)
                    "gate_label": gate_label,
                    # ADD-RISK size telegraph — held stack maxed / no add budget
                    "block_max": block_max,
                    "max_add_usd": max_add_usd,
                    "held_weight_pct": held_weight_pct,
                    "over_target": over_target,
                    "add_block_reason": add_block_reason,
                    "target_pair_weight": (add_room_meta or {}).get("target_pair_weight"),
                    "min_move_usd": (add_room_meta or {}).get("min_move_usd"),
                })
            ok = bool(rows)
            regime_label = None
            try:
                if entry_snap is not None:
                    regime_label = f"{entry_snap.regime}/{entry_snap.strategy_mode}"
            except Exception:
                regime_label = None
            formula = (
                "Signal Status = SignalGenerator weighted (RSI±0.4 @30/70, sent±0.3 @±0.2; "
                "BUY if score>0.25). Deploy is separate: REGIME-CASH entry — "
                f"held min_sent≥{entry_floors['min_sentiment']}, "
                f"new seat min_sent≥{entry_floors['min_sentiment_new_pair']}, "
                f"max_rsi≤{entry_floors['max_rsi']}. "
                "·gated = BUY signal but fails entry (reason in gate_label). "
                "·blocked = post-SL/manual rebuy cooldown. "
                "·block-max = held stack add-risk budget $0 / below min_move "
                "(over target weight, zero risk budget, or gap). "
                "·ready requires entry clear + not cooldown + not block-max. "
                "When X is aged-out, Sent. and Status *show* free/Adanos preview "
                "(sentiment_show / status_show) with ·prev — live gates still use aged X. "
                "Preview BUY is amber, never ·ready. "
                "Sent. colors scale by strength (mild ≠ full green)."
            )
            if recovery_summary.get("active") and recovery_summary.get("label"):
                formula += f" Recovery: {recovery_summary.get('label')}."
            self.send_json({
                "status": "ok" if ok else "no_data",
                "rows": rows,
                "count": len(rows),
                "basket": pairs,
                "basket_scope": "active_trading",
                "buy_blocked_pairs": blocked_pairs,
                "buy_block_hours": block_hours,
                "entry_gated_pairs": gated_pairs,
                "max_blocked_pairs": max_blocked_pairs,
                "add_room": add_room_meta,
                "entry_floors": entry_floors,
                "recovery": recovery_summary,
                "regime": regime_label,
                "rsi_source": rsi_src,
                "sentiment_source": (sent_meta or {}).get("source"),
                "sentiment_mode": (sent_meta or {}).get("mode"),
                "sentiment_teed": {
                    "drives_gates": False,
                    "label": teed_bundle.get("label"),
                    "next_x_refresh": teed_bundle.get("next_x_refresh"),
                    "non_zero_live": teed_bundle.get("non_zero_live"),
                    "non_zero_raw": teed_bundle.get("non_zero_raw"),
                    "sources": teed_bundle.get("sources"),
                    "note": teed_bundle.get("note"),
                },
                "formula": formula,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            })
            return

        elif path == '/api/performance':
            st = load_live_state() or {}
            perf = st.get("performance_metrics") or {}
            total = float(st.get("total_usd") or st.get("total_balance") or 0)
            # Refuse cash-API-zero cliffs as period end NAV (2026-08-28: $84 PAXG-only → −96%)
            try:
                from phase6.core.live_state_nav_guard import sanitize_current_total_for_kpis
                from phase6.core.dashboard_serve_helpers import _total_usd_at_ts, _nearest_ts
                import sqlite3 as _sqlite3

                if DB_PATH.exists() and total > 0:
                    _conn = _sqlite3.connect(
                        f"file:{DB_PATH}?mode=ro", uri=True, timeout=1.0
                    )
                    try:
                        _mx = _conn.execute("SELECT MAX(ts) FROM account_balances").fetchone()
                        _last_ts = _mx[0] if _mx else None
                        _last_nav = float(_total_usd_at_ts(_conn, _last_ts)) if _last_ts else 0.0
                    finally:
                        _conn.close()
                    total_safe, s_meta = sanitize_current_total_for_kpis(
                        total, _last_nav, external_flow_usd=0.0
                    )
                    if s_meta.get("sanitized"):
                        total = total_safe
            except Exception:
                pass
            trading = st.get("trading_positions") or st.get("positions") or []

            # Short TTL cache: mobile refresh was hammering large DB → N/A tiles + starved balances.
            # Key is stable (not per-cent NAV) so TTL actually hits across polls.
            cache_key = "api_performance_v2"
            cached_payload = performance_cache.get(cache_key)

            closed_win = win_ratio_from_positions(trading)
            trades = LEDGER.get_recent_trades(limit=100)
            DUST_OR_NOISE = {
                "dust_sweep_after_sl",
                "dust_sweep_orphan",
                "dust_sweep",
                "preserve_disarm",
            }

            def _exit_reason(t):
                return str(t.get("reason") or t.get("exit_reason") or "")

            closed_all = [t for t in trades if t.get("pnl") is not None and float(t.get("pnl") or 0) != 0]
            closed = [t for t in closed_all if _exit_reason(t) not in DUST_OR_NOISE]
            win_ratio_exits = None
            win_ratio_exits_raw = None
            if closed_all:
                raw_wins = sum(1 for t in closed_all if (t.get("pnl") or 0) > 0)
                win_ratio_exits_raw = {
                    "wins": raw_wins,
                    "total": len(closed_all),
                    "basis": "ledger_nonzero_pnl_including_dust",
                }
            if closed:
                win_wins = sum(1 for t in closed if (t.get("pnl") or 0) > 0)
                win_ratio = win_wins / len(closed)
                # mix breakdown for operator
                from collections import Counter
                by = Counter(_exit_reason(t) or "unknown" for t in closed)
                win_ratio_exits = {
                    "wins": win_wins,
                    "total": len(closed),
                    "basis": "ledger_nonzero_pnl_strategy",
                    "excluded_dust_noise": len(closed_all) - len(closed),
                    "by_reason": dict(by),
                }
            else:
                win_ratio = closed_win if trading else float(perf.get("win_rate", 0.0) or 0.0)
                if trading and closed_win:
                    win_ratio_exits = {"basis": "open_book_unrealized", "total": len(trading)}

            def _overlay_fresh_wr(base: dict, cache_tag: str) -> dict:
                out = dict(base)
                out["win_ratio"] = round(float(win_ratio), 3)
                out["win_ratio_exits"] = win_ratio_exits
                if win_ratio_exits_raw is not None:
                    out["win_ratio_exits_raw"] = win_ratio_exits_raw
                out["total_trades"] = len(trades) or perf.get("total_trades", 0)
                out["last_updated"] = datetime.now(timezone.utc).isoformat()
                out["cache"] = cache_tag
                return out

            def _payload_populated(p: dict) -> bool:
                if any(p.get(k) is not None for k in ("today", "h24", "d7", "d14", "d30")):
                    return True
                eq = p.get("equity_trend") or {}
                return eq.get("status") == "ok" and len(eq.get("points") or []) >= 2

            def _compute_and_store():
                as_of = datetime.now(timezone.utc)
                try:
                    periods = compute_period_performance(
                        total, DB_PATH, timeout=3.5, as_of=as_of
                    )
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
                        as_of=as_of,
                    )
                except Exception:
                    equity_trend = {"status": "timeout", "points": []}

                # SSOT: Window/Recent on Account health must equal 30D/7D tiles exactly.
                # compute_equity_trend already uses the tile formula; still overwrite so a
                # future path drift cannot reintroduce dual numbers on one payload.
                if isinstance(equity_trend, dict) and equity_trend.get("status") == "ok":
                    d30 = periods.get("d30")
                    d7 = periods.get("d7")
                    if d30 is not None:
                        equity_trend["window_return_pct"] = d30
                    if d7 is not None:
                        equity_trend["recent_return_pct"] = d7
                    wr = equity_trend.get("window_return_pct")
                    if d30 is not None and wr is not None:
                        equity_trend["window_matches_period_tiles"] = abs(float(wr) - float(d30)) < 0.005
                    else:
                        equity_trend["window_matches_period_tiles"] = d30 is None or wr is None

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
                populated = _payload_populated(payload)
                if populated:
                    performance_cache.set(cache_key, payload, ttl=60.0)
                else:
                    # Don't clobber last_good with empties; briefly re-arm stale if present.
                    stale = performance_cache.get_last_good(cache_key)
                    if stale and _payload_populated(stale):
                        performance_cache.set(cache_key, stale, ttl=15.0)
                    else:
                        performance_cache.set(cache_key, payload, ttl=8.0)
                return payload

            if cached_payload and isinstance(cached_payload, dict):
                # Prefer fresh populated cache; if TTL left only empty timeout junk,
                # fall through to last-good below when present.
                if _payload_populated(cached_payload) or not performance_cache.get_last_good(cache_key):
                    self.send_json(_overlay_fresh_wr(cached_payload, "hit"))
                    return

            # Stale-while-revalidate: if we already have numbers, return them immediately
            # and refresh in a background thread (never block the UI poll on DB).
            stale = performance_cache.get_last_good(cache_key)
            if stale and isinstance(stale, dict) and _payload_populated(stale):
                schedule_performance_recompute(_compute_and_store)
                out = _overlay_fresh_wr(stale, "stale")
                out["source"] = (stale.get("source") or "portfolio_snapshots_db") + " (stale-while-revalidate)"
                self.send_json(out)
                return

            # First paint / no last_good: single-flight blocking compute.
            acquired = perf_compute_lock.acquire(blocking=False)
            if not acquired:
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
                cached_payload = performance_cache.get(cache_key)
                if cached_payload and isinstance(cached_payload, dict) and _payload_populated(cached_payload):
                    self.send_json(_overlay_fresh_wr(cached_payload, "hit"))
                    return
                payload = _compute_and_store()
                self.send_json(_overlay_fresh_wr(payload, payload.get("cache") or "miss"))
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
            # SSOT = live buy blocks (post-SL / post-TP / capital controls).
            # Do NOT trust stale recovery_state.json alone (was empty since 2026-07-03
            # while UNI/LINK/RAVE were blocked — Recovery tile lied "None").
            try:
                from phase6.core.runner_capital_events import load_buy_block_status

                blocks = load_buy_block_status() or {}
                pairs = sorted(
                    [
                        p
                        for p, b in blocks.items()
                        if isinstance(b, dict) and b.get("blocked")
                    ]
                )
                details = []
                for p in pairs:
                    b = blocks[p]
                    details.append(
                        {
                            "pair": p,
                            "reason": b.get("reason"),
                            "source": b.get("source"),
                            "hours_remaining": b.get("hours_remaining"),
                            "block_hours": b.get("block_hours"),
                            "expires_at": b.get("expires_at"),
                        }
                    )
                # Mode: normal unless we are thin on positions (legacy field)
                mode = "normal"
                try:
                    rec_path = Path("data/state/recovery_state.json")
                    if rec_path.exists():
                        legacy = json.loads(rec_path.read_text())
                        if legacy.get("mode") in ("emergency", "normal", "recovery"):
                            mode = legacy.get("mode") or mode
                except Exception:
                    pass
                if not pairs and mode == "emergency":
                    # thin book without blocks still recovery-ish
                    pass
                self.send_json(
                    {
                        "mode": mode,
                        "cooldown_pairs": pairs,
                        "cooldown_details": details,
                        "last_update": datetime.now(timezone.utc).isoformat(),
                        "source": "load_buy_block_status",
                        "display_timezone": (
                            __import__(
                                "phase6.core.trader_account_config",
                                fromlist=["ui_display_settings"],
                            ).ui_display_settings(None).get("display_timezone")
                            or "America/Los_Angeles"
                        ),
                    }
                )
            except Exception as e:
                # Fallback to file if block loader fails
                try:
                    rec_path = Path("data/state/recovery_state.json")
                    if rec_path.exists():
                        self.send_json(json.loads(rec_path.read_text()))
                    else:
                        self.send_json(
                            {
                                "mode": "normal",
                                "cooldown_pairs": [],
                                "last_update": datetime.now(timezone.utc).isoformat(),
                                "error": str(e)[:160],
                            }
                        )
                except Exception as e2:
                    self.send_json({"error": str(e2), "cooldown_pairs": []})
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
