"""
Decision-first daily brief for Telegram (no LLM).

Brad product bar (2026-08-25): go/no-go first, plain English, clear action /
decision / direction. Not an ops metric dump.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _short_pair(p: str) -> str:
    return str(p or "").replace("-USD", "")


def _regime_mood_label(risk_on_bias: float) -> str:
    b = float(risk_on_bias)
    if b >= 0.62:
        return "risk-on"
    if b <= 0.38:
        return "risk-off"
    return "neutral"


def _promotion_plain(deploy_hint: str) -> str:
    d = (deploy_hint or "").strip()
    low = d.lower()
    if not d:
        return "No change — no weekly test board on disk."
    if "shadow-trial" in low or "candidate" in low:
        return f"Candidate for paper/shadow trial only (not live yet): {d}"
    if "hold" in low or "blocked" in low:
        return "Hold strategy as-is — no test beat live results on real overlap."
    return d


def _stance_from_regime_cash(rc: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    """Returns (stance_word, one_line)."""
    if not rc:
        return "UNKNOWN", "Market posture: unavailable this cycle."
    regime = str(rc.get("regime") or "?").lower()
    allow = bool(rc.get("allow_new_buys", True))
    mode = str(rc.get("strategy_mode") or "")
    park = mode == "usdc_park" or not allow
    util = rc.get("target_max_util_pct")
    util_s = f"{float(util):.0%}" if util is not None else "?"
    if park:
        return (
            "CASH-HEAVY",
            f"Market mode: {regime} — holding cash on purpose (new buys OFF). "
            f"Deploy target ≤{util_s}.",
        )
    return (
        "DEPLOY",
        f"Market mode: {regime} — new buys ON. Deploy target ≤{util_s}.",
    )


def _trend_plain(opt_brief: Dict[str, Any]) -> Optional[str]:
    tr = opt_brief.get("trend_repair") or {}
    if not tr:
        return None
    raw_health = tr.get("health")
    if isinstance(raw_health, dict):
        health = str(
            raw_health.get("label")
            or raw_health.get("state")
            or raw_health.get("blurb")
            or "n/a"
        )
    else:
        health = str(raw_health or "n/a")
    health = health.replace("_", " ")
    wr = tr.get("window_return_pct")
    rr = tr.get("recent_return_pct")
    parts = [f"Path: {health}"]
    if wr is not None:
        try:
            parts.append(f"window {float(wr):+.1f}%")
        except (TypeError, ValueError):
            pass
    if rr is not None:
        try:
            parts.append(f"recent {float(rr):+.1f}%")
        except (TypeError, ValueError):
            pass
    layer = tr.get("primary_layer")
    if layer:
        parts.append(f"focus={str(layer).replace('_', ' ')}")
    # Pull first T0 recommendation action if present
    recs = tr.get("recommendations") or []
    if recs:
        a0 = recs[0].get("action") or ""
        if a0:
            plain = str(a0).replace("_", " ")
            # common playbook ids → human
            plain = {
                "preserve gate integrity": "keep risk gates as-is",
                "preserve_gate_integrity": "keep risk gates as-is",
            }.get(plain, plain)
            parts.append(f"playbook: {plain}")
    return " · ".join(parts)


def _bottom_line(
    *,
    stance_word: str,
    deploy_hint: str,
    buy_pairs: Sequence[str],
    sell_pairs: Sequence[str],
    trend_line: Optional[str],
    ss_recent: int,
) -> Tuple[str, str]:
    """Returns (label, one-sentence why)."""
    if sell_pairs and not buy_pairs:
        label = "TRIM / DEFEND"
    elif buy_pairs and stance_word == "DEPLOY":
        label = "SELECTIVE BUY"
    elif stance_word == "CASH-HEAVY":
        label = "HOLD CASH"
    elif ss_recent > 0:
        label = "HOLD — WATCH STOPS"
    else:
        label = "HOLD / MONITOR"

    why_bits: List[str] = []
    if stance_word == "DEPLOY":
        why_bits.append("New buys allowed")
    elif stance_word == "CASH-HEAVY":
        why_bits.append("Cash posture on purpose")
    else:
        why_bits.append("Posture unclear")

    why_bits.append(_promotion_plain(deploy_hint).split("—")[0].strip().rstrip("."))
    if trend_line and ("down" in trend_line.lower() or "soft" in trend_line.lower()):
        why_bits.append("recent path soft — keep gates tight")
    if buy_pairs:
        why_bits.append(
            "signal interest: " + ", ".join(_short_pair(p) for p in buy_pairs[:4])
        )
    if ss_recent > 0:
        why_bits.append(f"{ss_recent} same-day buy→stop in last 3d")
    return label, ". ".join(why_bits) + "."


def format_decision_brief(
    *,
    basket: Sequence[str],
    full_count: int,
    last_rebalance: str,
    poly: Dict[str, Any],
    sl_risks: Dict[str, Any],
    signals: Sequence[Dict[str, Any]],
    opt_brief: Optional[Dict[str, Any]] = None,
    same_session: Optional[Dict[str, Any]] = None,
    same_session_3d: Optional[Dict[str, Any]] = None,
    proposals: Optional[Sequence[Dict[str, Any]]] = None,
    next_focus: str = "",
    generated_at: Optional[datetime] = None,
) -> str:
    """
    Build Telegram body.

    signals items: {pair, signal, reason, sl_level}
    """
    now = generated_at or datetime.now(timezone.utc)
    ob = dict(opt_brief or {})
    proposals = list(proposals or [])

    # --- facts ---
    ret = ob.get("production_since_go_live_return_pct")
    eq = ob.get("production_end_equity_usd")
    trades = ob.get("production_trade_count")
    rebs = ob.get("production_live_rebalances")
    deploy_hint = str(ob.get("deployment_hint") or "")
    rc = ob.get("regime_cash") or {}
    stance_word, stance_line = _stance_from_regime_cash(rc if rc else None)
    trend_line = _trend_plain(ob)
    mood = _regime_mood_label(float(poly.get("risk_on_bias", 0.5) or 0.5))

    high_sl = [
        p
        for p in basket
        if str((sl_risks or {}).get(p, {}).get("level", "")).upper()
        in ("HIGH", "CRITICAL")
    ]
    buy_pairs = [
        s["pair"]
        for s in signals
        if str(s.get("signal", "")).upper() == "BUY"
    ]
    sell_pairs = [
        s["pair"]
        for s in signals
        if str(s.get("signal", "")).upper() == "SELL"
    ]

    ss3 = same_session_3d or {}
    ss_recent = int(ss3.get("count_2h") or 0)
    ss_pairs = list(ss3.get("pairs_2h") or [])

    # Historical 30d line is context only if recent is zero
    ss_hist = same_session or {}
    ss_hist_n = int(ss_hist.get("count_2h") or 0)

    label, why = _bottom_line(
        stance_word=stance_word,
        deploy_hint=deploy_hint,
        buy_pairs=buy_pairs,
        sell_pairs=sell_pairs,
        trend_line=trend_line,
        ss_recent=ss_recent,
    )

    lines: List[str] = []
    lines.append("=== Phase 6 Daily Brief ===")
    lines.append(f"{now.date().isoformat()} · {now.strftime('%H:%M')} UTC")
    lines.append("")
    lines.append(f"BOTTOM LINE: {label}")
    lines.append(why)
    lines.append("")

    # --- Do now ---
    lines.append("=== Do now ===")
    do_now: List[str] = []
    if proposals:
        do_now.append(
            f"Your call on {len(proposals)} proposal(s) — see Needs your call below."
        )
    if buy_pairs and stance_word == "DEPLOY":
        for s in signals:
            if str(s.get("signal", "")).upper() != "BUY":
                continue
            p = s["pair"]
            sl = str(s.get("sl_level") or "?").upper()
            note = " (stop risk high — size small / wait if unsure)" if sl in (
                "HIGH",
                "CRITICAL",
            ) else ""
            reason = (s.get("reason") or "signal").strip()
            do_now.append(f"Engine may buy {_short_pair(p)}: {reason}{note}")
    if sell_pairs:
        for s in signals:
            if str(s.get("signal", "")).upper() != "SELL":
                continue
            do_now.append(
                f"Engine may sell {_short_pair(s['pair'])}: {(s.get('reason') or 'signal').strip()}"
            )
    if ss_recent > 0:
        do_now.append(
            "Same-day buy→stop still firing ("
            + ", ".join(_short_pair(p) for p in ss_pairs[:5])
            + ") — treat as a wound, not noise."
        )
    if stance_word == "CASH-HEAVY":
        do_now.append("No FOMO needed: cash is intentional under current market mode.")
    if not do_now:
        do_now.append("Nothing for you to decide. Engine on autopilot.")
    for item in do_now[:6]:
        lines.append(f"• {item}")
    lines.append("")

    # --- Book ---
    lines.append("=== Book ===")
    if ret is not None and eq is not None:
        adj = " (deposit-adjusted)" if ob.get("production_deposit_adjusted") else ""
        book = f"Equity ${float(eq):,.0f} · {float(ret):+.1f}% since go-live{adj}"
        if trades is not None:
            book += f" · {int(trades)} trades"
        if rebs is not None:
            book += f" · {int(rebs)} rebalances"
        lines.append(book)
    else:
        lines.append("Equity / return: unavailable this cycle.")
    lines.append(f"Last rebalance: {last_rebalance or '?'}")
    data_ok = full_count >= max(len(basket) - 1, 1)
    lines.append(
        f"Signal data: {full_count}/{len(basket)} pairs ready"
        + ("" if data_ok else " — thin coverage, allocator may skip pairs")
    )
    lines.append("")

    # --- Stance ---
    lines.append("=== Stance (what the system decided) ===")
    lines.append(stance_line)
    lines.append(f"Risk mood (prediction markets): {mood}")
    lines.append(f"Strategy change: {_promotion_plain(deploy_hint)}")
    # Shadow one-liner
    # Prefer facts already in opt_brief if present; else skip
    if trend_line:
        lines.append(trend_line)
    lines.append("")

    # --- Wounds ---
    lines.append("=== Wounds / watch ===")
    wounds: List[str] = []
    if high_sl:
        wounds.append(
            f"Elevated stop risk on {len(high_sl)} pair(s) "
            f"({', '.join(_short_pair(p) for p in high_sl[:6])}"
            f"{'…' if len(high_sl) > 6 else ''}) — more stop-outs if tape whipsaws."
        )
    if ss_recent > 0:
        wounds.append(
            f"Last 3 days: {ss_recent} buy→stop within 2h "
            f"({', '.join(_short_pair(p) for p in ss_pairs[:6])})."
        )
    elif ss_hist_n > 0:
        wounds.append(
            f"Older ledger still shows {ss_hist_n} same-day buy→stops (30d history) — "
            "not treated as today's crisis unless 3d count rises."
        )
    if not wounds:
        wounds.append("No fresh wounds called out.")
    for w in wounds[:4]:
        lines.append(f"• {w}")
    lines.append("")

    # --- What's next ---
    lines.append("=== What's next ===")
    focus = (next_focus or "").strip()
    if not focus:
        focus = "Keep live gates; shadow-only for any OPT winner until promotion gates pass."
    # De-jargon / replace research-speak evolution notes with operator English
    fl = focus.lower()
    if (
        "regime scorecard" in fl
        or "regime_knob" in fl
        or "shadow+drift" in fl
        or "live config promotion" in fl
    ):
        focus_plain = (
            "No live strategy flip. Keep paper-trialing OPT ideas; "
            "only promote after gates pass on real overlap."
        )
    else:
        focus_plain = (
            focus.replace("regime_knob_map", "regime playbook")
            .replace("shadow+drift", "paper trial + drift check")
            .replace("live config promotion", "live settings")
        )
    lines.append(f"• {focus_plain}")
    lines.append("• Next scheduled rebalance: morning ~09:05 PT / evening ~21:05 PT")
    if not proposals:
        lines.append("• No new strategy proposals this cycle.")
    lines.append("")

    if proposals:
        lines.append("=== Needs your call ===")
        for i, p in enumerate(proposals, 1):
            lines.append(f"{i}. {p.get('id')}: {p.get('title')} [{p.get('priority', '?')}]")
        lines.append('Reply: "proceed with 1" | "wait" | "none"')
        lines.append("")

    lines.append("— End brief —")
    return "\n".join(lines)
