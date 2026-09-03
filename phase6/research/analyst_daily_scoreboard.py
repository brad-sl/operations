#!/usr/bin/env python3
"""
Analyst daily outcome scoreboard (deterministic, no LLM).

Facts only: trades, positions, signals, sentiment/RSI, gates, Phase2, OPT,
trial pipeline, proposal freshness. Feeds Analyst Daily Review compose.

Writes:
  data/state/analyst_daily_scoreboard_latest.json
  data/state/analyst_daily_scoreboard_latest.md  (compact operator text)

Stdout: empty by default (cron quiet). Use --print for body.
Never writes config/ or live knobs.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.paths import load_project_dotenv

load_project_dotenv()

STATE = ROOT / "data" / "state"
OUT_JSON = STATE / "analyst_daily_scoreboard_latest.json"
OUT_MD = STATE / "analyst_daily_scoreboard_latest.md"
HISTORY = STATE / "analyst_daily_scoreboard_history.jsonl"
TRADES = ROOT / "trades" / "phase6_trades.jsonl"
NORTH_STAR = (
    "Maximize risk-adjusted return and minimize losses via regime-aware knobs, "
    "sizing, signals, and methodology — evidence before live change."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None or raw == "":
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    try:
        t = datetime.fromisoformat(s)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.astimezone(timezone.utc)
    except Exception:
        return None


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text() or "null")
    except Exception:
        return default


def _read_trades(lookback_days: float = 30.0) -> List[Dict[str, Any]]:
    if not TRADES.exists():
        return []
    cutoff = _now() - timedelta(days=lookback_days)
    out: List[Dict[str, Any]] = []
    try:
        with TRADES.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                ts = _parse_ts(row.get("timestamp") or row.get("entry_ts"))
                if ts is None or ts < cutoff:
                    continue
                row["_ts"] = ts
                out.append(row)
    except Exception:
        return []
    return out


def _window_stats(trades: List[Dict[str, Any]], days: float) -> Dict[str, Any]:
    cutoff = _now() - timedelta(days=days)
    rows = [t for t in trades if t.get("_ts") and t["_ts"] >= cutoff]
    buys = [t for t in rows if str(t.get("side", "")).upper() == "BUY"]
    sells = [t for t in rows if str(t.get("side", "")).upper() == "SELL"]
    pnls = []
    for t in sells:
        try:
            if t.get("pnl") is not None:
                pnls.append(float(t["pnl"]))
        except (TypeError, ValueError):
            pass
    exit_reasons = Counter(
        str(t.get("exit_reason") or t.get("reason") or "unknown") for t in sells
    )
    pairs = Counter(str(t.get("pair") or "?") for t in rows)
    green = sum(1 for p in pnls if p > 0)
    red = sum(1 for p in pnls if p < 0)
    return {
        "days": days,
        "n_trades": len(rows),
        "n_buys": len(buys),
        "n_sells": len(sells),
        "realized_pnl_usd": round(sum(pnls), 4) if pnls else 0.0,
        "n_green_exits": green,
        "n_red_exits": red,
        "exit_reasons_top": exit_reasons.most_common(8),
        "pairs_top": pairs.most_common(8),
    }


def _positions_snapshot() -> Dict[str, Any]:
    runner = _load_json(STATE / "phase6_runner_state.json", {}) or {}
    snap = runner.get("capital_position_snapshot") or {}
    positions = snap.get("positions") or {}
    nav = runner.get("capital_nav_snapshot") or {}
    open_rows = []
    total_usd = 0.0
    if isinstance(positions, dict):
        for pair, meta in positions.items():
            if not isinstance(meta, dict):
                continue
            usd = meta.get("usd") or meta.get("value_usd") or meta.get("market_value")
            try:
                usd_f = float(usd) if usd is not None else 0.0
            except (TypeError, ValueError):
                usd_f = 0.0
            qty = meta.get("qty") or meta.get("size") or meta.get("quantity")
            try:
                qty_f = float(qty) if qty is not None else 0.0
            except (TypeError, ValueError):
                qty_f = 0.0
            if qty_f <= 0 and usd_f <= 0:
                continue
            total_usd += max(usd_f, 0.0)
            open_rows.append(
                {
                    "pair": pair,
                    "usd": round(usd_f, 2),
                    "qty": qty_f,
                    "unrealized_pct": meta.get("unrealized_pct")
                    or meta.get("pnl_pct"),
                }
            )
    open_rows.sort(key=lambda r: r.get("usd") or 0, reverse=True)
    equity = None
    for k in ("equity_usd", "nav_usd", "total_equity_usd", "equity"):
        if nav.get(k) is not None:
            try:
                equity = float(nav[k])
                break
            except (TypeError, ValueError):
                pass
    return {
        "as_of": snap.get("ts") or runner.get("last_updated"),
        "n_open": len(open_rows),
        "open_usd": round(total_usd, 2),
        "equity_usd": equity,
        "top_positions": open_rows[:12],
        "last_rebalance_date": runner.get("last_rebalance_date"),
        "cash_hold_usd": runner.get("manual_liquidation_cash_hold_usd"),
    }


def _signals_sent_rsi() -> Dict[str, Any]:
    try:
        from phase6.core.sentiment_scorer import (
            load_latest_sentiment_for_basket,
            load_sentiment_scores,
        )
        from phase6.core.signal_generator import SignalGenerator
        from phase6.scripts.generate_trading_intelligence_report import load_basket
    except Exception as e:
        return {"error": f"signal_load_failed: {e}"}

    basket = load_basket()
    sent = load_sentiment_scores(universe=basket)
    latest_raw = load_latest_sentiment_for_basket(basket=basket, sentiment_scores=sent)
    latest: Dict[str, Any] = latest_raw if isinstance(latest_raw, dict) else {}
    rsi_map: Dict[str, Any] = dict(latest["rsi"]) if isinstance(latest.get("rsi"), dict) else {}
    if isinstance(latest.get("sentiment"), dict):
        sent_map: Dict[str, Any] = dict(latest["sentiment"])
    elif isinstance(sent, dict):
        sent_map = dict(sent)
    else:
        sent_map = {}
    sg = SignalGenerator()
    rows = []
    counts = Counter()
    for pair in basket:
        rsi = rsi_map.get(pair)
        s = sent_map.get(pair, 0.0)
        try:
            sig = sg.generate_signal(pair, rsi or 50.0, sentiment=s or 0.0)
            signal = sig.signal
            reason = (sig.reason or "")[:72]
        except Exception:
            signal, reason = "?", ""
        counts[str(signal).upper()] += 1
        rows.append(
            {
                "pair": pair,
                "signal": signal,
                "rsi": rsi,
                "sentiment": round(float(s or 0.0), 4),
                "reason": reason,
            }
        )
    return {
        "basket_n": len(basket),
        "signal_counts": dict(counts),
        "rows": rows,
    }


def _phase2_and_trend() -> Dict[str, Any]:
    p2 = _load_json(STATE / "phase2_stabilize_check_latest.json", {}) or {}
    try:
        from phase6.core.phase2_stabilize_check import compute_phase2_check

        p2 = compute_phase2_check() or p2
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / "phase2_stabilize_check_latest.json").write_text(
            json.dumps(p2, indent=2, default=str)
        )
    except Exception:
        pass
    tr = _load_json(STATE / "trend_repair_status.json", {}) or {}
    et = tr.get("equity_trend") or {}
    health = et.get("health") if isinstance(et, dict) else {}
    if isinstance(health, dict):
        health_label = health.get("state") or health.get("label") or ""
    else:
        health_label = str(health or "")
    return {
        "phase2_ready": p2.get("phase2_ready"),
        "phase2_verdict": p2.get("verdict"),
        "phase2_tiles": p2.get("tiles"),
        "path_health": health_label,
        "window_return_pct": (et or {}).get("window_return_pct")
        if isinstance(et, dict)
        else None,
        "recent_return_pct": (et or {}).get("recent_return_pct")
        if isinstance(et, dict)
        else None,
        "trend_operator_summary": (tr.get("operator_summary") or "")[:240],
        "diagnosis": tr.get("diagnosis"),
    }


def _opt_and_intel() -> Dict[str, Any]:
    brief = _load_json(STATE / "intel_strategic_brief.json", {}) or {}
    opt = brief.get("optimization") or {}
    weekly = _load_json(STATE / "analyst_weekly_assessment_latest.json", {}) or {}
    return {
        "opt_run_id": opt.get("run_id"),
        "opt_winner": opt.get("winner_id"),
        "deployment_hint": opt.get("deployment_hint"),
        "production_return_pct": opt.get("production_since_go_live_return_pct"),
        "production_equity_usd": opt.get("production_end_equity_usd"),
        "production_trades": opt.get("production_trade_count"),
        "risk_on_bias": brief.get("risk_on_bias"),
        "high_sl_risk_pairs": brief.get("high_sl_risk_pairs") or [],
        "weekly_assessment_keys": list(weekly.keys())[:12] if isinstance(weekly, dict) else [],
    }


def _pipeline() -> Dict[str, Any]:
    idx = _load_json(STATE / "trials" / "INDEX.json", {}) or {}
    strategy = _load_json(STATE / "trials" / "TEST_STRATEGY.json", {}) or {}
    pickup = _load_json(STATE / "trials" / "PICKUP_QUEUE.json", {}) or {}
    # Prefer live computed strategy status (includes by_status + live_regime)
    try:
        from phase6.research.analyst_test_strategy import status as strategy_status

        strategy = strategy_status() or strategy
    except Exception:
        pass
    # Fallback live regime from trend_repair if strategy still blank
    live_regime = strategy.get("live_regime")
    if not live_regime:
        tr = _load_json(STATE / "trend_repair_status.json", {}) or {}
        reg = tr.get("regime") or {}
        if isinstance(reg, dict):
            live_regime = reg.get("regime")
        elif isinstance(reg, str):
            live_regime = reg
    trials = idx.get("trials") or []
    by_status = Counter(str(t.get("status")) for t in trials if isinstance(t, dict))
    active = [
        {
            "trial_id": t.get("trial_id"),
            "status": t.get("status"),
            "family": t.get("family"),
            "master_id": t.get("master_id"),
            "final_at": t.get("final_at"),
        }
        for t in trials
        if isinstance(t, dict)
        and str(t.get("status") or "").upper()
        not in ("CLOSED", "DONE", "KILLED", "ABORTED", "DROPPED", "DECIDED")
    ]
    backlog = _load_json(STATE / "analyst_proposed_backlog.json", {}) or {}
    props = backlog.get("proposals") or []
    last_ids = []
    open_n = 0
    waiting_n = 0
    for p in props:
        if not isinstance(p, dict):
            continue
        st = str(p.get("status") or "").lower()
        if st == "open" or st in ("queued", "running", "in_progress"):
            open_n += 1
        elif st.startswith("waiting"):
            waiting_n += 1
    for p in props:
        if isinstance(p, dict) and str(p.get("status") or "").lower() in (
            "open",
            "waiting_regime_bear",
            "waiting_phase2",
            "waiting_dependency",
            "queued",
            "running",
        ):
            last_ids.append(p.get("id"))
    last_ids = last_ids[-8:]
    # Prefer explicit open_queue if present
    oq = backlog.get("open_queue") or []
    if oq:
        last_ids = [x.get("id") for x in oq if isinstance(x, dict)][:8]
    # inbox open reviews — only REVIEW_* without a matching DECIDED_* 
    inbox = ROOT / "docs" / "testing" / "inbox"
    open_reviews = []
    if inbox.exists():
        decided_names = " ".join(p.name for p in inbox.glob("DECIDED_*.md"))
        for f in sorted(inbox.glob("REVIEW_*.md")):
            stem = f.name.replace("REVIEW_", "", 1).replace(".md", "")
            # Skip if any DECIDED file covers this trial id stem
            if stem and stem in decided_names:
                continue
            if any(stem in p.name for p in inbox.glob("DECIDED_*.md")):
                continue
            open_reviews.append(f.name)
    planned = []
    running = []
    bs = strategy.get("by_status") if isinstance(strategy.get("by_status"), dict) else {}
    if bs:
        planned = list(bs.get("planned") or [])
        running = list(bs.get("running") or [])
    return {
        "trials_by_status": dict(by_status),
        "active_trials": active,
        "strategy_planned": planned,
        "strategy_running_note": running,
        "active_master_ids": strategy.get("active_master_ids") or [],
        "live_regime": live_regime,
        "pickup_ready": len(pickup.get("ready") or []),
        "pickup_running_auto": pickup.get("running_auto_count"),
        "proposal_backlog_n": len(props),
        "proposal_open_n": open_n,
        "proposal_waiting_n": waiting_n,
        "proposal_last_ids": last_ids,
        "open_review_files": open_reviews[:10],
        "north_star": strategy.get("north_star") or NORTH_STAR,
    }


def _wounds() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        from phase6.core.same_session_sl import summarize as ss

        out["same_session_30d"] = ss(persist=False, lookback_days=30.0)
        out["same_session_3d"] = ss(persist=False, lookback_days=3.0)
        out["same_session_7d"] = ss(persist=False, lookback_days=7.0)
    except Exception as e:
        out["error"] = str(e)
    return out


def _gates_regime() -> Dict[str, Any]:
    # Prefer trend_repair / intel / policy read-only
    policy = _load_json(ROOT / "config" / "regime_cash_policy.json", {}) or {}
    tr = _load_json(STATE / "trend_repair_status.json", {}) or {}
    regime = tr.get("regime") or {}
    regimes_src = policy.get("regimes") if isinstance(policy.get("regimes"), dict) else {}
    if not regimes_src and isinstance(policy, dict):
        # flat policy layout: top-level bull/flat/…
        regimes_src = {
            k: v
            for k, v in policy.items()
            if k in ("bull", "flat", "bear", "transition", "unknown") and isinstance(v, dict)
        }
    policy_regimes = {}
    for k, v in regimes_src.items():
        if not isinstance(v, dict):
            continue
        policy_regimes[k] = {
            "strategy_mode": v.get("strategy_mode"),
            "allow_new_buys": v.get("allow_new_buys"),
            "rebalance_cap_usd": v.get("rebalance_cap_usd"),
        }
    return {
        "policy_enforce": policy.get("enforce"),
        "policy_regimes": policy_regimes,
        "detected_regime": regime if isinstance(regime, dict) else {"raw": regime},
        "open_book": tr.get("open_book"),
    }


def _material_flags(board: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    p2 = board.get("path") or {}
    if p2.get("phase2_ready") is False:
        flags.append("phase2_not_ready")
    health = str(p2.get("path_health") or "").lower()
    if "declin" in health or "soft" in health:
        flags.append("path_soft_or_declining")
    w = board.get("wounds") or {}
    ss3 = w.get("same_session_3d") or {}
    if int(ss3.get("count_2h") or 0) > 0:
        flags.append("same_session_sl_3d")
    t1 = (board.get("trades") or {}).get("1d") or {}
    if float(t1.get("realized_pnl_usd") or 0) < -25:
        flags.append("1d_realized_loss")
    pipe = board.get("pipeline") or {}
    if pipe.get("active_trials"):
        flags.append("active_trials")
    if pipe.get("open_review_files"):
        flags.append("open_reviews")
    opt = board.get("opt") or {}
    hint = str(opt.get("deployment_hint") or "").lower()
    if "promote" in hint and "hold" not in hint:
        flags.append("opt_promote_hint")
    sig = board.get("signals") or {}
    sc = sig.get("signal_counts") or {}
    if int(sc.get("SELL") or 0) >= 3:
        flags.append("many_sell_signals")
    if not flags:
        flags.append("quiet_stable")
    return flags


def _goal_realization(board: Dict[str, Any]) -> Dict[str, Any]:
    """Score progress vs north star without fake guarantees."""
    opt = board.get("opt") or {}
    path = board.get("path") or {}
    ret = opt.get("production_return_pct")
    eq = opt.get("production_equity_usd")
    p2_ready = path.get("phase2_ready")
    health = str(path.get("path_health") or "")
    wounds = board.get("wounds") or {}
    ss3 = int((wounds.get("same_session_3d") or {}).get("count_2h") or 0)
    score = 50  # neutral baseline
    notes = []
    if p2_ready is True:
        score += 15
        notes.append("Phase2 exit bar met")
    elif p2_ready is False:
        score -= 15
        notes.append("Phase2 exit bar NOT met — stabilize")
    if "declin" in health.lower():
        score -= 20
        notes.append(f"path health={health}")
    elif "improv" in health.lower() or "stable" in health.lower():
        score += 10
        notes.append(f"path health={health}")
    # Prefer recent path window over all-time go-live return (which can dominate forever)
    try:
        recent = float(path.get("recent_return_pct") or 0.0)
        window = float(path.get("window_return_pct") or 0.0)
        if recent > 0 and window >= 0:
            score += 12
            notes.append(f"recent path {recent:+.2f}% window {window:+.2f}%")
        elif recent < -2 or window < -5:
            score -= 12
            notes.append(f"recent path soft recent={recent:+.2f}% window={window:+.2f}%")
        else:
            notes.append(f"recent path recent={recent:+.2f}% window={window:+.2f}%")
    except (TypeError, ValueError):
        pass
    if ret is not None:
        try:
            r = float(ret)
            # Context only — light weight so deep historical DD doesn't zero the meter
            if r >= 0:
                score += 5
                notes.append(f"deposit-adj go-live return {r:+.1f}%")
            else:
                score -= min(8, max(2, int(abs(r) / 15)))
                notes.append(f"deposit-adj go-live return {r:+.1f}% (context)")
        except (TypeError, ValueError):
            pass
    if ss3 > 0:
        score -= 10
        notes.append(f"{ss3} same-session SL (3d)")
    pipe = board.get("pipeline") or {}
    if not pipe.get("active_trials") and not pipe.get("open_review_files"):
        notes.append("test capacity free")
        score += 5
    score = max(0, min(100, score))
    if score >= 70:
        label = "ON_TRACK"
    elif score >= 45:
        label = "STABILIZE"
    else:
        label = "OFF_TRACK"
    return {
        "score_0_100": score,
        "label": label,
        "north_star": (board.get("pipeline") or {}).get("north_star") or NORTH_STAR,
        "notes": notes,
        "equity_usd": eq,
        "production_return_pct": ret,
    }


def build_scoreboard() -> Dict[str, Any]:
    trades = _read_trades(30.0)
    board: Dict[str, Any] = {
        "schema": "analyst_daily_scoreboard_v1",
        "as_of": _now().isoformat().replace("+00:00", "Z"),
        "trades": {
            "1d": _window_stats(trades, 1.0),
            "3d": _window_stats(trades, 3.0),
            "7d": _window_stats(trades, 7.0),
            "30d": _window_stats(trades, 30.0),
        },
        "positions": _positions_snapshot(),
        "signals": _signals_sent_rsi(),
        "path": _phase2_and_trend(),
        "opt": _opt_and_intel(),
        "pipeline": _pipeline(),
        "wounds": _wounds(),
        "gates": _gates_regime(),
    }
    board["goal"] = _goal_realization(board)
    board["material_flags"] = _material_flags(board)
    board["material"] = not (
        board["material_flags"] == ["quiet_stable"]
        or board["material_flags"] == []
    )
    # Always material if off-track or stabilize with wounds
    if board["goal"]["label"] != "ON_TRACK":
        board["material"] = True
    if "quiet_stable" in board["material_flags"] and len(board["material_flags"]) == 1:
        board["material"] = False
    return board


def format_scoreboard_md(board: Dict[str, Any]) -> str:
    g = board.get("goal") or {}
    lines = [
        f"=== Analyst Daily Scoreboard ===",
        f"{board.get('as_of', '')}",
        f"GOAL: {g.get('label')} ({g.get('score_0_100')}/100)",
        " · ".join(g.get("notes") or []) or "(no notes)",
        "",
        "--- Trades ---",
    ]
    for key in ("1d", "3d", "7d"):
        t = (board.get("trades") or {}).get(key) or {}
        lines.append(
            f"{key}: n={t.get('n_trades')} buys={t.get('n_buys')} sells={t.get('n_sells')} "
            f"pnl=${t.get('realized_pnl_usd')} G/R={t.get('n_green_exits')}/{t.get('n_red_exits')}"
        )
    pos = board.get("positions") or {}
    lines += [
        "",
        "--- Positions ---",
        f"open={pos.get('n_open')} ~${pos.get('open_usd')} equity={pos.get('equity_usd')} "
        f"last_reb={pos.get('last_rebalance_date')}",
    ]
    sig = board.get("signals") or {}
    lines += [
        "",
        "--- Signals ---",
        f"counts={sig.get('signal_counts')} basket={sig.get('basket_n')}",
    ]
    path = board.get("path") or {}
    lines += [
        "",
        "--- Path ---",
        f"phase2_ready={path.get('phase2_ready')} verdict={path.get('phase2_verdict')}",
        f"health={path.get('path_health')} window={path.get('window_return_pct')} "
        f"recent={path.get('recent_return_pct')}",
    ]
    opt = board.get("opt") or {}
    lines += [
        "",
        "--- OPT ---",
        f"winner={opt.get('opt_winner')} hint={opt.get('deployment_hint')}",
        f"prod_ret={opt.get('production_return_pct')} eq={opt.get('production_equity_usd')}",
    ]
    pipe = board.get("pipeline") or {}
    lines += [
        "",
        "--- Pipeline ---",
        f"active_trials={pipe.get('active_trials')}",
        f"planned={pipe.get('strategy_planned')}",
        f"open_reviews={pipe.get('open_review_files')}",
        f"pickup_ready={pipe.get('pickup_ready')} regime={pipe.get('live_regime')}",
    ]
    w = board.get("wounds") or {}
    ss3 = w.get("same_session_3d") or {}
    lines += [
        "",
        "--- Wounds ---",
        f"same_session_3d count_2h={ss3.get('count_2h')} pairs={ss3.get('pairs_2h')}",
        "",
        f"flags={board.get('material_flags')} material={board.get('material')}",
    ]
    return "\n".join(lines) + "\n"


def persist(board: Dict[str, Any], md: str) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(board, indent=2, default=str))
    OUT_MD.write_text(md)
    try:
        with HISTORY.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "as_of": board.get("as_of"),
                        "goal": board.get("goal"),
                        "material_flags": board.get("material_flags"),
                        "material": board.get("material"),
                    },
                    default=str,
                )
                + "\n"
            )
    except Exception:
        pass


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--print", action="store_true", help="Print markdown to stdout")
    ap.add_argument(
        "--print-json", action="store_true", help="Print JSON to stdout (debug)"
    )
    args = ap.parse_args(argv)
    board = build_scoreboard()
    md = format_scoreboard_md(board)
    persist(board, md)
    if args.print_json:
        print(json.dumps(board, indent=2, default=str))
    elif args.print:
        print(md, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
