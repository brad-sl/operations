#!/usr/bin/env python3
"""
Analyst Daily Review composer (deterministic primary path).

Sections Brad required:
  GOAL REALIZATION / WORKING / NOT WORKING / NEEDS CHANGE /
  PIPELINE / CHANGE RESULTS / BLOCKERS / NEEDS YOUR CALL

Reads analyst_daily_scoreboard_latest.json (runs scoreboard if missing/stale).
Writes:
  data/state/analyst_daily_review_latest.json
  data/state/analyst_daily_review_latest.txt

Telegram rules:
  - stdout = TG body when --deliver or material
  - empty stdout when quiet and not --force (no filler spam)
  - never writes live config / knobs / orders

Novelty proposals: evidence-backed templates keyed by flags; skip if title
already in backlog (ENG-S7-01 style).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.paths import load_project_dotenv

load_project_dotenv()

STATE = ROOT / "data" / "state"
SCOREBOARD_JSON = STATE / "analyst_daily_scoreboard_latest.json"
OUT_JSON = STATE / "analyst_daily_review_latest.json"
OUT_TXT = STATE / "analyst_daily_review_latest.txt"
PREV_HASH = STATE / "analyst_daily_review_content_hash.txt"
BACKLOG = STATE / "analyst_proposed_backlog.json"
HISTORY = STATE / "analyst_daily_review_history.jsonl"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text() or "null")
    except Exception:
        return default


def _ensure_scoreboard(max_age_hours: float = 6.0, force_rebuild: bool = False) -> Dict[str, Any]:
    board = _load_json(SCOREBOARD_JSON, None)
    stale = True
    if isinstance(board, dict) and board.get("as_of") and not force_rebuild:
        try:
            ts = datetime.fromisoformat(str(board["as_of"]).replace("Z", "+00:00"))
            age_h = (_now() - ts.astimezone(timezone.utc)).total_seconds() / 3600.0
            stale = age_h > max_age_hours
        except Exception:
            stale = True
    if force_rebuild:
        stale = True
    if stale or not isinstance(board, dict):
        from phase6.research.analyst_daily_scoreboard import build_scoreboard, format_scoreboard_md, persist

        board = build_scoreboard()
        persist(board, format_scoreboard_md(board))
    return board


def _norm_title(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip().lower())


def _known_titles() -> set:
    known = set()
    backlog = _load_json(BACKLOG, {}) or {}
    for t in backlog.get("dedupe_titles") or []:
        if t:
            known.add(_norm_title(str(t)))
    for p in backlog.get("proposals") or []:
        if isinstance(p, dict) and p.get("title"):
            known.add(_norm_title(p["title"]))
    strat = _load_json(STATE / "analyst_strategic_proposals.json", {}) or {}
    for p in strat.get("proposals") or []:
        if isinstance(p, dict) and p.get("title"):
            known.add(_norm_title(p["title"]))
    return known


def _proposal_id(seq: int) -> str:
    d = _now().strftime("%Y%m%d")
    return f"ANALYST-{d}-{seq:03d}"


def _build_proposals(board: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Evidence-backed candidates only; max 3; skip known titles."""
    known = _known_titles()
    flags = set(board.get("material_flags") or [])
    path = board.get("path") or {}
    wounds = board.get("wounds") or {}
    ss3 = wounds.get("same_session_3d") or {}
    trades_7d = (board.get("trades") or {}).get("7d") or {}
    pipe = board.get("pipeline") or {}
    opt = board.get("opt") or {}
    candidates: List[Dict[str, Any]] = []

    def offer(title: str, why: str, priority: str = "Medium", category: str = "Analyst") -> None:
        if _norm_title(title) in known:
            return
        if any(_norm_title(c["title"]) == _norm_title(title) for c in candidates):
            return
        candidates.append(
            {
                "title": title,
                "why": why,
                "priority": priority,
                "category": category,
                "status": "proposed",
                "source": "analyst_daily_review_v1",
            }
        )

    if "phase2_not_ready" in flags or path.get("phase2_ready") is False:
        offer(
            "Hold earn/scale until Phase 2 stabilize bars clear (scoreboard-gated)",
            f"phase2_ready={path.get('phase2_ready')} verdict={path.get('phase2_verdict')}",
            "High",
            "Recovery",
        )

    if "same_session_sl_3d" in flags or int(ss3.get("count_2h") or 0) > 0:
        pairs = ss3.get("pairs_2h") or []
        offer(
            "Dig same-session buy→stop wounds (3d) before reopening aggressive alts",
            f"count_2h={ss3.get('count_2h')} pairs={pairs}",
            "High",
            "Exits / Risk",
        )

    if "path_soft_or_declining" in flags:
        offer(
            "Run trend-repair tier review on deposit-adjusted slope (observe-only)",
            f"health={path.get('path_health')} window={path.get('window_return_pct')} recent={path.get('recent_return_pct')}",
            "High",
            "Path health",
        )

    exit_top = trades_7d.get("exit_reasons_top") or []
    if exit_top:
        top_reason, top_n = exit_top[0][0], exit_top[0][1]
        if top_n >= 3 and "sl" in str(top_reason).lower():
            offer(
                f"Counterfactual on dominant 7d exit reason: {top_reason}",
                f"7d exit_reasons top={exit_top[:3]} pnl=${trades_7d.get('realized_pnl_usd')}",
                "Medium",
                "Exits",
            )

    if "opt_promote_hint" not in flags and "hold" in str(opt.get("deployment_hint") or "").lower():
        # only propose OPT refresh if production still deep red AND no active trial
        ret = opt.get("production_return_pct")
        try:
            deep = ret is not None and float(ret) < -20
        except (TypeError, ValueError):
            deep = False
        if deep and not (pipe.get("active_trials") or []):
            offer(
                "Refresh OPT pack + re-entry stress on current OHLCV (shadow only)",
                f"deployment_hint={opt.get('deployment_hint')} prod_ret={ret}",
                "Medium",
                "OPT",
            )

    planned = pipe.get("strategy_planned") or []
    if planned and not (pipe.get("active_trials") or []):
        offer(
            "Emit next ungated TEST_STRATEGY plan when capacity free (no live writes)",
            f"planned={planned[:3]} live_regime={pipe.get('live_regime')}",
            "Low",
            "Test strategy",
        )

    # Assign IDs
    out = []
    seq = 1
    existing_ids = set()
    for p in (_load_json(BACKLOG, {}) or {}).get("proposals") or []:
        if isinstance(p, dict) and p.get("id"):
            existing_ids.add(p["id"])
    for c in candidates[:3]:
        pid = _proposal_id(seq)
        while pid in existing_ids:
            seq += 1
            pid = _proposal_id(seq)
        c["id"] = pid
        existing_ids.add(pid)
        out.append(c)
        seq += 1
    return out


def _fmt_usd(x: Any) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "n/a"
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.2f}"


def _fmt_pct(x: Any, signed: bool = True) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "n/a"
    if signed:
        return f"{v:+.1f}%"
    return f"{v:.1f}%"


def _human_exit_reason(code: Any) -> str:
    s = str(code or "").strip()
    if not s:
        return "unknown"
    low = s.lower()
    table = {
        "stop_loss_exchange": "stop-loss",
        "stop_loss": "stop-loss",
        "dust_sweep_after_sl": "dust cleanup after stop",
        "dust_sweep_orphan": "orphan dust sweep",
        "rotation_exchange": "rotation exit",
        "take_profit": "take-profit",
        "fixed_tp": "fixed take-profit",
        "trail": "trail take-profit",
        "lifecycle": "lifecycle exit",
        "operator_unwind": "operator unwind",
    }
    for k, label in table.items():
        if k in low:
            # keep Brad GO tag readable if present
            if "brad_go" in low or "op_missfire" in low:
                return "operator unwind (prior missfire cleanup)"
            return label
    # strip ugly tuple leftovers
    s = s.replace("_", " ")
    if len(s) > 48:
        s = s[:45] + "…"
    return s


def _human_exit_mix(top: Any, limit: int = 3) -> str:
    """Turn [('stop_loss_exchange', 3), ...] into plain English."""
    if not top:
        return ""
    parts = []
    rows = top
    if isinstance(top, dict):
        rows = list(top.items())
    for row in list(rows)[:limit]:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            reason, n = row[0], row[1]
        elif isinstance(row, dict):
            reason, n = row.get("reason") or row.get("k"), row.get("n") or row.get("count")
        else:
            continue
        try:
            n_i = int(n)
        except (TypeError, ValueError):
            n_i = n
        label = _human_exit_reason(reason)
        parts.append(f"{n_i}× {label}" if n_i != 1 else f"1× {label}")
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _signal_blend(sc: Dict[str, Any]) -> str:
    if not sc:
        return "no live engine signals"
    bits = []
    for k in ("BUY", "HOLD", "SELL"):
        n = int(sc.get(k) or 0)
        if n:
            bits.append(f"{n} {k}")
    return ", ".join(bits) if bits else "flat book of signals"


def _pretty_plan(name: Any) -> str:
    s = str(name or "")
    # PLAN-BEAR-PARK-001:- → bear-park plan
    s = s.split(":")[0]
    s = s.replace("PLAN-", "").replace("_", "-")
    return s.lower() if s else "unnamed plan"


def _working(board: Dict[str, Any]) -> List[str]:
    items = []
    sig = board.get("signals") or {}
    sc = sig.get("signal_counts") or {}
    n = int(sig.get("basket_n") or 0)
    if not sig.get("error") and n >= 8:
        items.append(
            f"Coverage is healthy: sentiment, RSI, and engine signals are live across "
            f"{n} basket pairs ({_signal_blend(sc)})."
        )
    elif sc:
        items.append(f"Engine signals are posting ({_signal_blend(sc)}).")
    pos = board.get("positions") or {}
    if pos.get("last_rebalance_date"):
        items.append(
            f"Rebalance machinery ran as scheduled — last book date on disk is "
            f"{pos.get('last_rebalance_date')}."
        )
    pipe = board.get("pipeline") or {}
    if not pipe.get("active_trials"):
        items.append(
            "Offline test capacity is open — nothing is stuck in a RUNNING auto trial."
        )
    opt = board.get("opt") or {}
    hint = str(opt.get("deployment_hint") or "")
    if hint:
        if "hold" in hint.lower():
            items.append(
                "Promotion discipline is intact: weekly OPT still says hold — "
                "no scenario beat production on real overlap."
            )
        else:
            items.append(f"OPT surface: {hint}.")
    # Brad GO sticky
    sticky = ROOT / "data" / "state" / "brad_go_hold_earn_scale_until_phase2.json"
    if sticky.exists():
        try:
            st = json.loads(sticky.read_text() or "{}")
            if st.get("status") == "active" and st.get("decision") == "accept":
                items.append(
                    "Operator lock is active: hold earn/scale until Phase 2 bars clear "
                    "and you give a fresh GO (book left as-is)."
                )
        except Exception:
            pass
    if not items:
        items.append("Core data paths answered this cycle — no silent pipeline death.")
    return items[:6]


def _not_working(board: Dict[str, Any]) -> List[str]:
    items = []
    path = board.get("path") or {}
    if path.get("phase2_ready") is False:
        items.append(
            "We are still short of the Phase 2 stabilize exit bar, so the path stays "
            "in stabilize — not earn, not scale."
        )
    health = str(path.get("path_health") or "")
    if health:
        wr = path.get("window_return_pct")
        rr = path.get("recent_return_pct")
        tone = "softening" if "declin" in health.lower() else health
        items.append(
            f"Deposit-adjusted equity path looks {tone}: about {_fmt_pct(rr)} over the "
            f"recent stretch and {_fmt_pct(wr)} over the full repair window."
        )
    opt = board.get("opt") or {}
    ret = opt.get("production_return_pct")
    eq = opt.get("production_equity_usd")
    if ret is not None:
        try:
            if float(ret) < 0:
                items.append(
                    f"Since go-live (deposit-adjusted context), the book is still underwater "
                    f"at roughly {_fmt_pct(ret)} with equity near {_fmt_usd(eq)}. "
                    f"That is backdrop, not today's sole scorecard."
                )
        except (TypeError, ValueError):
            pass
    w = board.get("wounds") or {}
    ss3 = w.get("same_session_3d") or {}
    n_ss = int(ss3.get("count_2h") or 0)
    if n_ss > 0:
        pairs = ss3.get("pairs_2h") or []
        pair_bit = ""
        if isinstance(pairs, list) and pairs:
            pair_bit = " on " + ", ".join(str(p) for p in pairs[:4])
        items.append(
            f"Same-session wound check still lights up: {n_ss} buy→stop within ~2h "
            f"in the last 3 days{pair_bit}."
        )
    t1 = (board.get("trades") or {}).get("1d") or {}
    pnl1 = t1.get("realized_pnl_usd")
    try:
        pnl1_f = float(pnl1) if pnl1 is not None else None
    except (TypeError, ValueError):
        pnl1_f = None
    if pnl1_f is not None and pnl1_f < 0:
        mix = _human_exit_mix(t1.get("exit_reasons_top"))
        sells = int(t1.get("n_sells") or 0)
        bit = f" — mostly {mix}" if mix else ""
        items.append(
            f"Last 24h realized about {_fmt_usd(pnl1_f)} across {sells} sell"
            f"{'' if sells == 1 else 's'}{bit}."
        )
    t7 = (board.get("trades") or {}).get("7d") or {}
    mix7 = _human_exit_mix(t7.get("exit_reasons_top"), limit=4)
    if mix7:
        items.append(f"Over seven days the exit mix is {mix7}.")
    if not items:
        items.append(
            "No hard system failures — we are simply not ON_TRACK until the goal score rises."
        )
    return items[:8]


def _needs_change(board: Dict[str, Any], proposals: List[Dict[str, Any]]) -> List[str]:
    items = []
    goal = board.get("goal") or {}
    label = goal.get("label")
    score = goal.get("score_0_100")
    if label != "ON_TRACK":
        items.append(
            f"Main job remains moving us from {label} ({score}/100) toward ON_TRACK "
            f"without live FOMO or late pile-ons."
        )
    path = board.get("path") or {}
    if path.get("phase2_ready") is False:
        items.append(
            "Keep Phase 3 earn and Phase 4 scale closed until Phase 2 bars clear and you reopen."
        )
    for p in proposals:
        items.append(
            f"On the table: {p.get('id')} — {p.get('title')} "
            f"({p.get('priority') or 'n/a'} priority)."
        )
    if not proposals and label == "ON_TRACK":
        items.append("No forced change this cycle — hold course and keep observing.")
    return items[:6]


def _pipeline_lines(board: Dict[str, Any]) -> List[str]:
    pipe = board.get("pipeline") or {}
    items = []
    active = pipe.get("active_trials") or []
    if active:
        for t in active[:4]:
            items.append(
                f"In flight: {t.get('trial_id')} is {t.get('status')} "
                f"({t.get('family') or 'unspecified family'})."
            )
    else:
        items.append("No trials are running right now.")
    planned = pipe.get("strategy_planned") or []
    if planned:
        pretty = ", ".join(_pretty_plan(x) for x in planned[:4])
        items.append(f"Strategy queue still holds parked plans: {pretty}.")
    regime = pipe.get("live_regime") or "unknown"
    ready = pipe.get("pickup_ready")
    run_a = pipe.get("pickup_running_auto")
    items.append(
        f"Live regime reads as {regime}. Test pickup shows "
        f"{ready if ready is not None else 0} ready and "
        f"{run_a if run_a is not None else 0} auto-running."
    )
    n_back = pipe.get("proposal_backlog_n")
    if n_back is not None:
        items.append(
            f"Proposal backlog sits at {n_back} items (older templates still deduped)."
        )
    items.append(
        "On the calendar: stoch 30-day reeval 2026-09-03, weekly OPT Sunday, "
        "strategy emit Monday."
    )
    return items[:8]


def _change_results(board: Dict[str, Any]) -> List[str]:
    """Recent closed work / shadows — human labels, not raw filenames only."""
    items = []
    # Brad GO accept
    sticky = ROOT / "data" / "state" / "brad_go_hold_earn_scale_until_phase2.json"
    if sticky.exists():
        try:
            st = json.loads(sticky.read_text() or "{}")
            if st.get("status") == "active":
                items.append(
                    "Accepted ANALYST-20260902-001: hold earn/scale until Phase 2 clears "
                    "(your GO today)."
                )
        except Exception:
            pass
    inbox = ROOT / "docs" / "testing" / "inbox"
    if inbox.exists():
        decided = sorted(
            inbox.glob("DECIDED_*.md"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        for f in decided[:3]:
            name = f.name.replace("DECIDED_", "").replace(".md", "")
            # drop trailing _YYYYMMDD if present
            name = re.sub(r"_\d{8}$", "", name)
            name = name.replace("_", " ").replace("-", " ")
            if len(name) > 64:
                name = name[:61] + "…"
            items.append(f"Recently closed on the trial board: {name}.")
    opt = board.get("opt") or {}
    if opt.get("opt_run_id"):
        items.append(
            f"Latest OPT run {opt.get('opt_run_id')} crowned "
            f"{opt.get('opt_winner') or 'n/a'}; deployment stance remains "
            f"{opt.get('deployment_hint') or 'unspecified'}."
        )
    pipe = board.get("pipeline") or {}
    if not pipe.get("active_trials"):
        items.append("Offline capacity is free after the prior closes.")
    if not items:
        items.append("No fresh change artifacts on disk this cycle.")
    return items[:6]


def _blockers(board: Dict[str, Any]) -> List[str]:
    items = []
    path = board.get("path") or {}
    if path.get("phase2_ready") is False:
        items.append(
            "Phase 2 exit bar is the binding gate — it keeps earn/scale closed."
        )
    # sticky reinforce
    sticky = ROOT / "data" / "state" / "brad_go_hold_earn_scale_until_phase2.json"
    if sticky.exists():
        try:
            st = json.loads(sticky.read_text() or "{}")
            if st.get("status") == "active":
                items.append(
                    "Your hold-earn/scale lock stays in force until bars clear and a new GO."
                )
        except Exception:
            pass
    pipe = board.get("pipeline") or {}
    for t in pipe.get("active_trials") or []:
        items.append(
            f"Watch item: trial {t.get('trial_id')} is still marked {t.get('status')}."
        )
    for name in pipe.get("open_review_files") or []:
        short = str(name).replace("REVIEW_", "").replace(".md", "").replace("-", " ")
        items.append(f"An open review still needs a call: {short}.")
    regime = pipe.get("live_regime")
    if regime and str(regime).lower() in ("transition", "bear", "unknown"):
        items.append(
            f"Regime is {regime}, so bull-only parked plans stay on the shelf."
        )
    w = board.get("wounds") or {}
    ss3 = w.get("same_session_3d") or {}
    if int(ss3.get("count_2h") or 0) > 0:
        items.append("Same-session stop wound is still an active risk flag (3-day window).")
    if not items:
        items.append("No hard blockers — promote still wants evidence, not vibes.")
    return items[:8]


def compose_review(board: Dict[str, Any]) -> Dict[str, Any]:
    proposals = _build_proposals(board)
    goal = board.get("goal") or {}
    review = {
        "schema": "analyst_daily_review_v2",
        "as_of": _now().isoformat().replace("+00:00", "Z"),
        "scoreboard_as_of": board.get("as_of"),
        "goal": goal,
        "working": _working(board),
        "not_working": _not_working(board),
        "needs_change": _needs_change(board, proposals),
        "pipeline": _pipeline_lines(board),
        "change_results": _change_results(board),
        "blockers": _blockers(board),
        "proposals": proposals,
        "material_flags": board.get("material_flags"),
        "material": bool(board.get("material")) or bool(proposals) or goal.get("label") != "ON_TRACK",
        "voice": "management_report_v1",
    }
    body = format_review_text(review)
    content_hash = hashlib.sha256(body.encode()).hexdigest()[:16]
    review["content_hash"] = content_hash
    prev = PREV_HASH.read_text().strip() if PREV_HASH.exists() else ""
    review["unchanged_vs_prior"] = bool(prev and prev == content_hash)
    if review["unchanged_vs_prior"] and not proposals and goal.get("label") == "ON_TRACK":
        review["material"] = False
    return review


def format_review_text(review: Dict[str, Any]) -> str:
    """Management-report voice: short prose paragraphs, not dumpster tuples."""
    g = review.get("goal") or {}
    as_of = review.get("as_of") or ""
    when = as_of
    if "T" in as_of:
        when = as_of.replace("+00:00", "Z").replace("T", " ").replace("Z", " UTC")[:22] + " UTC"

    label = g.get("label") or "UNKNOWN"
    score = g.get("score_0_100")
    north = g.get("north_star") or ""
    notes = g.get("notes") or []

    lines: List[str] = [
        "Analyst Daily Review",
        when,
        "",
        f"Goal realization: {label} ({score}/100).",
    ]
    if north:
        lines.append(north if north.endswith(".") else north + ".")
    # fold notes into one readable sentence where possible
    if notes:
        clean = []
        for n in notes:
            s = str(n).strip().rstrip(".")
            sl = s.lower()
            if sl.startswith("phase2") or "phase 2 exit bar" in sl or "phase2 exit" in sl:
                s = "Phase 2 exit bar still not met — stay in stabilize"
            elif "path health" in sl or sl.startswith("path health"):
                s = "equity path is still declining"
            elif "recent path soft" in sl or "recent path" in sl:
                # pull numbers if present
                m = re.search(
                    r"recent[=:\s]*([+\-]?\d+(?:\.\d+)?).*window[=:\s]*([+\-]?\d+(?:\.\d+)?)",
                    s,
                    re.I,
                )
                if m:
                    s = f"recent path about {float(m.group(1)):+.1f}%, window about {float(m.group(2)):+.1f}%"
                else:
                    s = "recent repair path is still soft"
            elif "deposit-adj" in sl or "go-live return" in sl:
                m = re.search(r"([+\-]?\d+(?:\.\d+)?)\s*%", s)
                if m:
                    s = f"go-live context roughly {float(m.group(1)):+.1f}% (backdrop only)"
                else:
                    s = "go-live context still underwater (backdrop only)"
            elif "test capacity free" in sl:
                s = "offline test capacity is free"
            clean.append(s)
        # de-dupe while preserving order
        seen = set()
        uniq = []
        for c in clean:
            k = c.lower()
            if k in seen:
                continue
            seen.add(k)
            uniq.append(c)
        lines.append("In plain terms: " + "; ".join(uniq[:4]) + ".")
    lines.append("")

    def sec(title: str, items: List[str]) -> None:
        lines.append(title)
        body_items = items or ["Nothing material to report here."]
        if len(body_items) == 1:
            lines.append(body_items[0])
        else:
            for it in body_items:
                # light bullets still ok for scanability, but sentences not dumps
                lines.append(f"• {it}")
        lines.append("")

    sec("What's working", review.get("working") or [])
    sec("What's not", review.get("not_working") or [])
    sec("What needs to change", review.get("needs_change") or [])
    sec("Pipeline", review.get("pipeline") or [])
    sec("Results of recent changes", review.get("change_results") or [])
    sec("Blockers", review.get("blockers") or [])

    props = review.get("proposals") or []
    lines.append("Needs your call")
    if not props:
        lines.append("Nothing new that clears the evidence bar this cycle.")
    else:
        for i, p in enumerate(props, 1):
            why = str(p.get("why") or "").strip()
            # humanize raw why fragments
            why = why.replace("phase2_ready=False", "Phase 2 not ready")
            why = re.sub(r"verdict=NO-GO[^\]]*", "stabilize bar unmet", why)
            why = re.sub(r"health=declining\s*", "path declining; ", why)
            why = re.sub(r"window=([-\d.]+)\s*recent=([-\d.]+)", r"window \1%, recent \2%", why)
            why = re.sub(r"deployment_hint=([^ ]+)", r"OPT says \1", why)
            why = re.sub(r"prod_ret=([-\d.]+)", r"go-live context \1%", why)
            why = re.sub(r"planned=\[[^\]]+\]\s*", "parked plans in queue; ", why)
            why = re.sub(r"live_regime=(\w+)", r"regime \1", why)
            title = p.get("title") or "Untitled"
            pr = p.get("priority") or ""
            pr_bit = f" ({pr})" if pr else ""
            lines.append(f"{i}. {title}{pr_bit}")
            if why:
                lines.append(f"   Why it matters: {why}.")
            pid = p.get("id")
            if pid:
                lines.append(f"   Ref: {pid}")
        lines.append("")
        lines.append('Reply "proceed with 1" (or 2/3), "wait", or "none".')
    lines.append("")
    lines.append("— End of report —")
    lines.append("")
    return "\n".join(lines)


def _append_backlog(proposals: List[Dict[str, Any]]) -> int:
    if not proposals:
        return 0
    data = _load_json(BACKLOG, {"proposals": []}) or {"proposals": []}
    existing_ids = {p.get("id") for p in data.get("proposals") or [] if isinstance(p, dict)}
    existing_titles = {
        _norm_title(p.get("title"))
        for p in data.get("proposals") or []
        if isinstance(p, dict)
    }
    for t in data.get("dedupe_titles") or []:
        existing_titles.add(_norm_title(str(t)))
    added = 0
    for p in proposals:
        if p.get("id") in existing_ids:
            continue
        if _norm_title(p.get("title") or "") in existing_titles:
            continue
        row = dict(p)
        row.setdefault("status", "open")
        if row.get("status") == "proposed":
            row["status"] = "open"
        row["created_at"] = _now().isoformat().replace("+00:00", "Z")
        row.setdefault("open_reason", "Minted by Analyst Daily Review.")
        data.setdefault("proposals", []).append(row)
        existing_titles.add(_norm_title(row.get("title") or ""))
        added += 1
    if added:
        # Refresh open_queue + dedupe_titles
        titles = set(str(t) for t in (data.get("dedupe_titles") or []) if t)
        oq = []
        for p in data.get("proposals") or []:
            if not isinstance(p, dict):
                continue
            if p.get("title"):
                titles.add(str(p["title"]))
            st = str(p.get("status") or "").lower()
            if st == "open" or st.startswith("waiting") or st in ("queued", "running"):
                oq.append(
                    {
                        "id": p.get("id"),
                        "status": p.get("status"),
                        "title": p.get("title"),
                        "reason": p.get("open_reason") or p.get("why") or "",
                    }
                )
        data["dedupe_titles"] = sorted(titles)
        data["open_queue"] = oq
        data["schema"] = "analyst_proposed_backlog_v2"
        BACKLOG.write_text(json.dumps(data, indent=2, default=str) + "\n")
    return added


def persist_review(review: Dict[str, Any], body: str) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(review, indent=2, default=str))
    OUT_TXT.write_text(body)
    PREV_HASH.write_text(review.get("content_hash") or "")
    try:
        with HISTORY.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "as_of": review.get("as_of"),
                        "goal": (review.get("goal") or {}).get("label"),
                        "material": review.get("material"),
                        "n_proposals": len(review.get("proposals") or []),
                        "content_hash": review.get("content_hash"),
                    },
                    default=str,
                )
                + "\n"
            )
    except Exception:
        pass


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--force",
        action="store_true",
        help="Always print body even if quiet/unmaterial",
    )
    ap.add_argument(
        "--deliver",
        action="store_true",
        help="Cron mode: print body only when material (or --force)",
    )
    ap.add_argument("--print", action="store_true", help="Always print (alias of --force)")
    ap.add_argument("--no-backlog", action="store_true", help="Do not append proposals to backlog")
    args = ap.parse_args(argv)

    # --force / --print / cron --deliver always rebuild so TG isn't stale cache
    board = _ensure_scoreboard(force_rebuild=bool(args.force or args.print or args.deliver))
    review = compose_review(board)
    body = format_review_text(review)
    if not args.no_backlog:
        _append_backlog(review.get("proposals") or [])
    persist_review(review, body)

    should_print = bool(args.force or args.print)
    if args.deliver and not should_print:
        should_print = bool(review.get("material"))
    if not args.deliver and not should_print:
        # default CLI: print for human runs
        should_print = True

    if should_print:
        print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
