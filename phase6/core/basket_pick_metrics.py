#!/usr/bin/env python3
"""
Basket pick metrics — track promoted membership changes and later outcomes.

Ledger: data/state/basket_pick_metrics.jsonl  (one JSON object per line)
Summary: data/state/basket_pick_metrics_latest.json

A "pick" is a promoted add (and optional remove). We snapshot baseline market
stats at promote time, then refresh marks at 1d/3d/7d/14d/30d for methodology
validation — not for auto-trading.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "data" / "state"
LEDGER_PATH = STATE_DIR / "basket_pick_metrics.jsonl"
LATEST_PATH = STATE_DIR / "basket_pick_metrics_latest.json"
SUMMARY_PATH = STATE_DIR / "basket_pick_metrics_summary.json"
GRAD_LATEST_PATH = STATE_DIR / "basket_seat_graduation_latest.json"
GRAD_REPORT_PATH = PROJECT_ROOT / "reports" / "BASKET_SEAT_GRADUATION_LATEST.md"
DECISION_CTX_PATH = STATE_DIR / "decision_context_log.jsonl"
RUN_PHASE_AUDIT_PATH = STATE_DIR / "run_phase_deploy_audit.jsonl"
TRADES_PATH = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"

UA = {"User-Agent": "phase6-basket-metrics/1.0"}
HORIZONS_HOURS = (24, 72, 168, 336, 720)  # 1d 3d 7d 14d 30d
# Graduation observation window after promote (days). After this, no-signal seats are "stale".
GRAD_WINDOW_DAYS = 30
MIN_FILL_USD = 15.0  # ignore dust / phantom buys


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    return s


def fetch_spot_and_stats(product_id: str, session: Optional[requests.Session] = None) -> Dict[str, Any]:
    sess = session or _session()
    out: Dict[str, Any] = {"product_id": product_id, "ok": False}
    try:
        t = sess.get(f"https://api.exchange.coinbase.com/products/{product_id}/ticker", timeout=20)
        st = sess.get(f"https://api.exchange.coinbase.com/products/{product_id}/stats", timeout=20)
        if t.status_code == 200:
            td = t.json()
            out["price"] = float(td.get("price") or 0.0)
            out["bid"] = float(td.get("bid") or 0.0) if td.get("bid") else None
            out["ask"] = float(td.get("ask") or 0.0) if td.get("ask") else None
        if st.status_code == 200:
            sd = st.json()
            last = float(sd.get("last") or out.get("price") or 0.0)
            open_ = float(sd.get("open") or 0.0)
            high = float(sd.get("high") or 0.0)
            low = float(sd.get("low") or 0.0)
            vol = float(sd.get("volume") or 0.0)
            out["last"] = last
            out["open_24h"] = open_
            out["high_24h"] = high
            out["low_24h"] = low
            out["volume_base_24h"] = vol
            mid = (high + low) / 2.0 if high and low else last
            out["volume_quote_24h_est"] = vol * mid if mid else None
            out["ret_24h"] = ((last - open_) / open_) if open_ else None
        out["ok"] = bool(out.get("price") or out.get("last"))
        if out.get("price") is None and out.get("last") is not None:
            out["price"] = out["last"]
    except Exception as e:
        out["error"] = str(e)[:200]
    out["ts"] = _utc_now()
    return out


@dataclass
class BasketPickRecord:
    pick_id: str
    promoted_at: str
    source: str  # discovery_pipeline | pool_cycling | manual
    add_pair: str
    remove_pair: Optional[str]
    add_score: Optional[float] = None
    remove_score: Optional[float] = None
    delta: Optional[float] = None
    reason: str = ""
    remove_held_usd_at_promote: float = 0.0
    residual_hold_allowed: bool = False
    methodology: Dict[str, Any] = field(default_factory=dict)
    baseline_add: Dict[str, Any] = field(default_factory=dict)
    baseline_remove: Dict[str, Any] = field(default_factory=dict)
    basket_before: List[str] = field(default_factory=list)
    basket_after: List[str] = field(default_factory=list)
    marks: Dict[str, Any] = field(default_factory=dict)  # horizon_key -> mark
    status: str = "open"  # open | closed | superseded
    notes: List[str] = field(default_factory=list)
    # Seat → signal → fill → outcome (filled by refresh_graduation)
    graduation: Dict[str, Any] = field(default_factory=dict)


def append_pick(record: BasketPickRecord, path: Path = LEDGER_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(asdict(record), default=str) + "\n")
    LATEST_PATH.write_text(json.dumps(asdict(record), indent=2, default=str) + "\n")
    return path


def load_ledger(path: Path = LEDGER_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def rewrite_ledger(rows: Sequence[Dict[str, Any]], path: Path = LEDGER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")


def _horizon_key(hours: int) -> str:
    if hours % 24 == 0:
        d = hours // 24
        return f"{d}d"
    return f"{hours}h"


def refresh_open_picks(path: Path = LEDGER_PATH) -> Dict[str, Any]:
    """Update mark-to-market for open picks at due horizons."""
    rows = load_ledger(path)
    sess = _session()
    now = datetime.now(timezone.utc)
    updated = 0
    for row in rows:
        if row.get("status") != "open":
            continue
        t0 = _parse_ts(row.get("promoted_at"))
        if t0 is None:
            continue
        age_h = (now - t0).total_seconds() / 3600.0
        marks = dict(row.get("marks") or {})
        add = row.get("add_pair")
        base_px = float((row.get("baseline_add") or {}).get("price") or 0.0)
        if not add or base_px <= 0:
            continue
        changed = False
        for h in HORIZONS_HOURS:
            key = _horizon_key(h)
            if key in marks:
                continue
            if age_h + 0.5 < h:  # not yet due (30m slack)
                continue
            spot = fetch_spot_and_stats(add, sess)
            px = float(spot.get("price") or 0.0)
            if px <= 0:
                continue
            ret = (px / base_px) - 1.0
            marks[key] = {
                "ts": spot.get("ts"),
                "price": px,
                "ret_vs_promote": round(ret, 6),
                "ret_pct": round(ret * 100.0, 3),
                "age_hours": round(age_h, 2),
            }
            # Optional: remove-pair counterfactual if we have baseline
            rem = row.get("remove_pair")
            br = row.get("baseline_remove") or {}
            br_px = float(br.get("price") or 0.0)
            if rem and br_px > 0:
                rspot = fetch_spot_and_stats(rem, sess)
                rpx = float(rspot.get("price") or 0.0)
                if rpx > 0:
                    rret = (rpx / br_px) - 1.0
                    marks[key]["remove_ret_pct"] = round(rret * 100.0, 3)
                    marks[key]["excess_vs_remove_pct"] = round((ret - rret) * 100.0, 3)
            changed = True
        if changed:
            row["marks"] = marks
            row["last_refresh"] = _utc_now()
            updated += 1
    if updated:
        rewrite_ledger(rows, path)
    grad = refresh_graduation(path=path)
    summary = summarize(rows if not updated else load_ledger(path))
    summary["graduation"] = grad.get("funnel") or {}
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n")
    return {
        "updated": updated,
        "open": summary.get("open_picks"),
        "summary": summary,
        "graduation": grad,
    }


def _parse_ts(ts: Any) -> Optional[datetime]:
    """Parse ts string to tz-aware UTC datetime. Handles legacy naive ISO (no tz),
    Z, +00:00 etc. Assumes UTC for naive (common in older trades logs).
    """
    if ts is None:
        return None
    try:
        s = str(ts).strip().replace("Z", "+00:00")
        if not s:
            return None
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open(errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _pair_norm(p: Any) -> str:
    return str(p or "").strip().upper()


def _scan_decision_signals(pair: str, t0: datetime) -> Dict[str, Any]:
    """First post-promote BUY / ROTATE_IN evidence from decision_context_log."""
    pair_u = _pair_norm(pair)
    first_sig = None
    max_score = None
    max_tilt_usd = None
    n_sig = 0
    for row in _iter_jsonl(DECISION_CTX_PATH):
        ts = _parse_ts(
            row.get("timestamp")
            or row.get("ts")
            or row.get("decision_id")
            or row.get("id")
        )
        # id like rebalance_20260826T160118Z_...
        if ts is None:
            rid = str(row.get("decision_id") or row.get("id") or "")
            if "T" in rid:
                try:
                    chunk = rid.split("_")[1]  # 20260826T160118Z
                    ts = datetime.strptime(chunk.replace("Z", ""), "%Y%m%dT%H%M%S").replace(
                        tzinfo=timezone.utc
                    )
                except Exception:
                    pass
        if ts is None or ts < t0:
            continue
        hit = False
        score = None
        tilt_usd = None

        # Live schema: proposals_summary=[{pair, side, score, source}, ...]
        props = row.get("proposals_summary") or row.get("proposals") or []
        for prop in props:
            if not isinstance(prop, dict):
                continue
            if _pair_norm(prop.get("pair")) != pair_u:
                continue
            act = str(
                prop.get("side") or prop.get("action") or prop.get("signal") or ""
            ).upper()
            if "ROTATE_IN" in act or act in ("BUY", "ADD", "ENTER"):
                hit = True
                try:
                    score = float(prop.get("score")) if prop.get("score") is not None else score
                except (TypeError, ValueError):
                    pass

        # Live schema: tilted_plan = { "PENGU-USD": 711.22, ... } target notionals
        plan = row.get("tilted_plan") or row.get("plan") or {}
        if isinstance(plan, dict) and plan and not any(
            k in plan for k in ("actions", "trades")
        ):
            for pk, pv in plan.items():
                if _pair_norm(pk) != pair_u:
                    continue
                try:
                    u = float(pv)
                except (TypeError, ValueError):
                    continue
                # Only count as buy signal if also ROTATE_IN / explicit, or large new target
                # while we already hit from proposals — else require proposal hit.
                if hit or u >= MIN_FILL_USD:
                    # If only tilted without ROTATE_IN, treat as signal only when
                    # pair appears with positive target and proposals said buy/hold-upgrade.
                    if hit:
                        tilt_usd = u
                    elif u >= MIN_FILL_USD and score is not None:
                        hit = True
                        tilt_usd = u
        else:
            actions = []
            if isinstance(plan, dict):
                actions = plan.get("actions") or plan.get("trades") or []
            if isinstance(plan, list):
                actions = plan
            for a in actions or []:
                if not isinstance(a, dict):
                    continue
                if _pair_norm(a.get("pair") or a.get("product_id")) != pair_u:
                    continue
                side = str(a.get("side") or a.get("action") or "").upper()
                if "BUY" in side or "ROTATE_IN" in side:
                    hit = True
                    try:
                        u = a.get("usd") or a.get("notional_usd") or a.get("quote_size")
                        if u is not None:
                            tilt_usd = float(u)
                    except (TypeError, ValueError):
                        pass

        # Also: if tilted_plan has pair USD and proposals_summary ROTATE_IN already set hit
        if isinstance(plan, dict) and hit and tilt_usd is None:
            raw = plan.get(pair) or plan.get(pair_u) or plan.get(pair_u.replace("-USD", "-USD"))
            # try common key forms
            for k, v in plan.items():
                if _pair_norm(k) == pair_u:
                    try:
                        tilt_usd = float(v)
                    except (TypeError, ValueError):
                        pass
                    break

        if not hit:
            continue
        n_sig += 1
        if first_sig is None:
            first_sig = {
                "ts": ts.isoformat(),
                "score": score,
                "tilt_usd": tilt_usd,
                "source": "decision_context",
            }
        if score is not None:
            max_score = score if max_score is None else max(max_score, score)
        if tilt_usd is not None:
            max_tilt_usd = tilt_usd if max_tilt_usd is None else max(max_tilt_usd, tilt_usd)
    return {
        "signaled": first_sig is not None,
        "first_signal": first_sig,
        "n_signal_cycles": n_sig,
        "max_signal_score": max_score,
        "max_tilt_usd": max_tilt_usd,
    }


def _scan_run_phase_blocks(pair: str, t0: datetime) -> Dict[str, Any]:
    pair_u = _pair_norm(pair)
    blocks: List[Dict[str, Any]] = []
    for row in _iter_jsonl(RUN_PHASE_AUDIT_PATH):
        ts = _parse_ts(row.get("ts"))
        if ts is None or ts < t0:
            continue
        for r in row.get("results") or []:
            if not isinstance(r, dict):
                continue
            if _pair_norm(r.get("pair")) != pair_u:
                continue
            if r.get("dropped") or r.get("blocked"):
                snap = r.get("snapshot") or {}
                blocks.append(
                    {
                        "ts": ts.isoformat(),
                        "phase_name": r.get("phase_name") or snap.get("phase_name"),
                        "original_usd": r.get("original_usd"),
                        "blocked": bool(r.get("blocked")),
                        "detail": str(snap.get("blocked_reason") or snap.get("reason") or "")[:120]
                        or (
                            f"phase={r.get('phase_name')};off_peak={snap.get('off_peak_pct')}"
                        ),
                    }
                )
    return {
        "n_run_phase_blocks": len(blocks),
        "first_block": blocks[0] if blocks else None,
        "block_reasons": sorted(
            {str(b.get("phase_name") or b.get("detail") or "?") for b in blocks}
        )[:8],
    }


def _scan_fills(pair: str, t0: datetime) -> Dict[str, Any]:
    """Live fills after promote from trades ledger."""
    pair_u = _pair_norm(pair)
    buys: List[Dict[str, Any]] = []
    sells: List[Dict[str, Any]] = []
    for row in _iter_jsonl(TRADES_PATH):
        if _pair_norm(row.get("pair") or row.get("product_id")) != pair_u:
            continue
        ts = _parse_ts(row.get("timestamp") or row.get("ts"))
        if ts is None or ts < t0:
            continue
        side = str(row.get("side") or "").upper()
        try:
            qty = float(row.get("qty") or row.get("size") or 0.0)
        except (TypeError, ValueError):
            qty = 0.0
        px = row.get("entry_price") if "BUY" in side else row.get("exit_price")
        try:
            px_f = float(px or 0.0)
        except (TypeError, ValueError):
            px_f = 0.0
        usd = qty * px_f if qty and px_f else None
        if usd is None:
            try:
                usd = float(row.get("notional_usd") or row.get("usd") or 0.0) or None
            except (TypeError, ValueError):
                usd = None
        if usd is not None and usd < MIN_FILL_USD and "BUY" in side:
            continue  # dust
        rec = {
            "ts": ts.isoformat(),
            "side": side,
            "qty": qty,
            "usd": round(usd, 2) if usd is not None else None,
            "reason": row.get("reason") or row.get("exit_reason") or row.get("signal_source"),
            "pnl": row.get("pnl"),
            "pnl_pct": row.get("pnl_pct"),
            "order_id": row.get("order_id"),
        }
        if "BUY" in side:
            buys.append(rec)
        elif "SELL" in side:
            sells.append(rec)
    buy_usd = sum(float(b["usd"] or 0) for b in buys)
    sell_pnl = 0.0
    n_pnl = 0
    for s in sells:
        if s.get("pnl") is not None:
            try:
                sell_pnl += float(s["pnl"])
                n_pnl += 1
            except (TypeError, ValueError):
                pass
    return {
        "filled": len(buys) > 0,
        "first_fill": buys[0] if buys else None,
        "n_buys": len(buys),
        "n_sells": len(sells),
        "buy_usd_sum": round(buy_usd, 2),
        "realized_pnl_sum": round(sell_pnl, 4) if n_pnl else None,
        "sells": sells[-5:],  # tail for audit
    }


def _classify_stage(g: Dict[str, Any], age_days: float) -> str:
    """
    Stages (mutually exclusive label for scoreboard):
      seated | signaled | blocked_no_fill | filled_open | filled_win | filled_loss | stale_no_signal
    """
    if g.get("filled"):
        pnl = g.get("realized_pnl_sum")
        n_sells = int(g.get("n_sells") or 0)
        if n_sells <= 0 or pnl is None:
            return "filled_open"
        return "filled_win" if float(pnl) > 0 else "filled_loss"
    if g.get("signaled"):
        if int(g.get("n_run_phase_blocks") or 0) > 0:
            return "blocked_no_fill"
        return "signaled"
    if age_days >= float(GRAD_WINDOW_DAYS):
        return "stale_no_signal"
    return "seated"


def refresh_graduation(path: Path = LEDGER_PATH) -> Dict[str, Any]:
    """
    Attach seat→signal→fill→outcome graduation to each pick.

    Does not place orders. Reads decision_context, run_phase audit, trades ledger.
    """
    rows = load_ledger(path)
    now = datetime.now(timezone.utc)
    changed = 0
    per_pick: List[Dict[str, Any]] = []
    for row in rows:
        add = row.get("add_pair")
        t0 = _parse_ts(row.get("promoted_at"))
        if not add or t0 is None:
            continue
        age_days = (now - t0).total_seconds() / 86400.0
        sig = _scan_decision_signals(add, t0)
        blk = _scan_run_phase_blocks(add, t0)
        fills = _scan_fills(add, t0)
        g: Dict[str, Any] = {
            "seated": True,
            "promoted_at": row.get("promoted_at"),
            "add_pair": add,
            "remove_pair": row.get("remove_pair"),
            "source": row.get("source"),
            "age_days": round(age_days, 2),
            **sig,
            **blk,
            **fills,
        }
        # hours to first signal / fill
        if sig.get("first_signal") and sig["first_signal"].get("ts"):
            t1 = _parse_ts(sig["first_signal"]["ts"])
            if t1:
                g["hours_to_first_signal"] = round((t1 - t0).total_seconds() / 3600.0, 2)
        if fills.get("first_fill") and fills["first_fill"].get("ts"):
            t2 = _parse_ts(fills["first_fill"]["ts"])
            if t2:
                g["hours_to_first_fill"] = round((t2 - t0).total_seconds() / 3600.0, 2)
        g["stage"] = _classify_stage(g, age_days)
        # paper MTM still useful when never filled
        marks = row.get("marks") or {}
        for hk in ("1d", "3d", "7d", "14d", "30d"):
            m = marks.get(hk)
            if isinstance(m, dict) and m.get("ret_pct") is not None:
                g[f"paper_ret_{hk}_pct"] = m.get("ret_pct")
                if m.get("excess_vs_remove_pct") is not None:
                    g[f"paper_excess_{hk}_pct"] = m.get("excess_vs_remove_pct")
        prev = row.get("graduation") or {}
        # strip heavy sell tails from equality noise
        slim_prev = {k: v for k, v in prev.items() if k != "sells"}
        slim_g = {k: v for k, v in g.items() if k != "sells"}
        if slim_prev != slim_g:
            row["graduation"] = g
            row["last_graduation_refresh"] = _utc_now()
            changed += 1
        per_pick.append(
            {
                "pick_id": row.get("pick_id"),
                "add_pair": add,
                "remove_pair": row.get("remove_pair"),
                "stage": g["stage"],
                "signaled": g.get("signaled"),
                "filled": g.get("filled"),
                "realized_pnl_sum": g.get("realized_pnl_sum"),
                "n_run_phase_blocks": g.get("n_run_phase_blocks"),
                "hours_to_first_signal": g.get("hours_to_first_signal"),
                "hours_to_first_fill": g.get("hours_to_first_fill"),
                "age_days": g.get("age_days"),
                "paper_ret_7d_pct": g.get("paper_ret_7d_pct"),
            }
        )
    if changed:
        rewrite_ledger(rows, path)

    n = len(per_pick) or 1
    stages = {s: 0 for s in (
        "seated", "signaled", "blocked_no_fill", "filled_open",
        "filled_win", "filled_loss", "stale_no_signal",
    )}
    for p in per_pick:
        stages[p["stage"]] = stages.get(p["stage"], 0) + 1
    n_seated = len(per_pick)
    n_sig = sum(1 for p in per_pick if p.get("signaled"))
    n_fill = sum(1 for p in per_pick if p.get("filled"))
    n_win = stages.get("filled_win", 0)
    n_closed = n_win + stages.get("filled_loss", 0)

    def _rate(a: int, b: int) -> Optional[float]:
        return round(a / b, 3) if b else None

    funnel = {
        "n_seated": n_seated,
        "n_signaled": n_sig,
        "n_filled": n_fill,
        "n_filled_win": n_win,
        "n_filled_loss": stages.get("filled_loss", 0),
        "n_blocked_no_fill": stages.get("blocked_no_fill", 0),
        "n_filled_open": stages.get("filled_open", 0),
        "n_stale_no_signal": stages.get("stale_no_signal", 0),
        "rate_signal_given_seat": _rate(n_sig, n_seated),
        "rate_fill_given_signal": _rate(n_fill, n_sig),
        "rate_win_given_fill_closed": _rate(n_win, n_closed),
        "rate_win_given_seat": _rate(n_win, n_seated),  # Brad's ~1/4 prior (full funnel)
        "stages": stages,
        "prior_note": (
            "Guestimate prior ~0.25 win|seat is a planning bar only. "
            "rate_win_given_seat needs closed fills; n small ⇒ noise."
        ),
    }
    out = {
        "ts": _utc_now(),
        "window_days": GRAD_WINDOW_DAYS,
        "funnel": funnel,
        "picks": per_pick,
        "updated": changed,
        "plain_english": _graduation_plain(funnel),
    }
    GRAD_LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAD_LATEST_PATH.write_text(json.dumps(out, indent=2, default=str) + "\n")
    _write_graduation_report(out)
    return out


def _graduation_plain(f: Dict[str, Any]) -> str:
    return (
        f"Seats={f.get('n_seated')} → signaled={f.get('n_signaled')} "
        f"({f.get('rate_signal_given_seat')}) → filled={f.get('n_filled')} "
        f"({f.get('rate_fill_given_signal')}|sig) → wins={f.get('n_filled_win')} "
        f"(win|seat={f.get('rate_win_given_seat')}; "
        f"blocked_no_fill={f.get('n_blocked_no_fill')})"
    )


def _write_graduation_report(out: Dict[str, Any]) -> None:
    f = out.get("funnel") or {}
    lines = [
        "# Basket seat graduation funnel",
        "",
        f"_Generated {out.get('ts')} · window {out.get('window_days')}d post-promote_",
        "",
        "## Plain English",
        "",
        str(out.get("plain_english") or ""),
        "",
        "## Rates (optimize these, not vibes)",
        "",
        "| Step | Rate | Count |",
        "|------|------|-------|",
        f"| Signal \\| seat | {f.get('rate_signal_given_seat')} | {f.get('n_signaled')}/{f.get('n_seated')} |",
        f"| Fill \\| signal | {f.get('rate_fill_given_signal')} | {f.get('n_filled')}/{f.get('n_signaled')} |",
        f"| Win \\| closed fill | {f.get('rate_win_given_fill_closed')} | {f.get('n_filled_win')}/"
        f"{(f.get('n_filled_win') or 0) + (f.get('n_filled_loss') or 0)} |",
        f"| **Win \\| seat (full funnel)** | **{f.get('rate_win_given_seat')}** | "
        f"{f.get('n_filled_win')}/{f.get('n_seated')} |",
        "",
        "Prior guestimate ~**0.25** win|seat — replace with `rate_win_given_seat` when N≥12 closed episodes.",
        "",
        "## Per pick",
        "",
        "| Pick | Add | Stage | Sig | Fill | PnL$ | Block | Age d | Paper 7d% |",
        "|------|-----|-------|-----|------|------|-------|-------|-----------|",
    ]
    for p in out.get("picks") or []:
        lines.append(
            f"| {p.get('pick_id')} | {p.get('add_pair')} | {p.get('stage')} | "
            f"{'Y' if p.get('signaled') else 'n'} | {'Y' if p.get('filled') else 'n'} | "
            f"{p.get('realized_pnl_sum')} | {p.get('n_run_phase_blocks')} | "
            f"{p.get('age_days')} | {p.get('paper_ret_7d_pct')} |"
        )
    lines += [
        "",
        "## Stage meanings",
        "",
        "- `seated` — promoted; no buy signal yet",
        "- `signaled` — ROTATE_IN/BUY plan seen; not filled (gates may still run)",
        "- `blocked_no_fill` — signal + run-phase (or similar) drop; no live buy",
        "- `filled_open` — bought; episode not fully realized",
        "- `filled_win` / `filled_loss` — sells booked with net pnl",
        "- `stale_no_signal` — past window, never signaled",
        "",
        "## Honesty",
        "",
        str(f.get("prior_note") or ""),
        "",
        "Paper MTM (marks) ≠ trade success. Optimize **fill|signal** vs **win|fill** separately.",
        "",
    ]
    GRAD_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAD_REPORT_PATH.write_text("\n".join(lines) + "\n")


def summarize(rows: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    rows = list(rows if rows is not None else load_ledger())
    open_rows = [r for r in rows if r.get("status") == "open"]
    by_h: Dict[str, List[float]] = {}
    excess: Dict[str, List[float]] = {}
    for r in rows:
        for k, m in (r.get("marks") or {}).items():
            if isinstance(m, dict) and m.get("ret_pct") is not None:
                by_h.setdefault(k, []).append(float(m["ret_pct"]))
            if isinstance(m, dict) and m.get("excess_vs_remove_pct") is not None:
                excess.setdefault(k, []).append(float(m["excess_vs_remove_pct"]))

    def _avg(xs: List[float]) -> Optional[float]:
        return round(sum(xs) / len(xs), 3) if xs else None

    return {
        "ts": _utc_now(),
        "n_picks": len(rows),
        "open_picks": len(open_rows),
        "adds": [r.get("add_pair") for r in rows],
        "avg_ret_pct_by_horizon": {k: _avg(v) for k, v in sorted(by_h.items())},
        "avg_excess_vs_remove_pct": {k: _avg(v) for k, v in sorted(excess.items())},
        "hit_rate_positive_7d": (
            round(
                sum(1 for x in by_h.get("7d", []) if x > 0) / len(by_h["7d"]),
                3,
            )
            if by_h.get("7d")
            else None
        ),
        "methodology_note": (
            "Paper success = add_pair MTM vs promote baseline; "
            "excess_vs_remove = add return minus removed pair return. "
            "Trade graduation = seat→signal→fill→win in graduation funnel "
            "(see basket_seat_graduation_latest.json)."
        ),
    }


def record_promotion(
    *,
    add_pair: str,
    remove_pair: Optional[str],
    basket_before: Sequence[str],
    basket_after: Sequence[str],
    source: str = "pool_cycling",
    add_score: Optional[float] = None,
    remove_score: Optional[float] = None,
    delta: Optional[float] = None,
    reason: str = "",
    remove_held_usd: float = 0.0,
    residual_hold_allowed: bool = False,
    methodology: Optional[Dict[str, Any]] = None,
    notes: Optional[List[str]] = None,
) -> BasketPickRecord:
    sess = _session()
    base_add = fetch_spot_and_stats(add_pair, sess)
    base_rem = fetch_spot_and_stats(remove_pair, sess) if remove_pair else {}
    rec = BasketPickRecord(
        pick_id=str(uuid.uuid4())[:12],
        promoted_at=_utc_now(),
        source=source,
        add_pair=add_pair,
        remove_pair=remove_pair,
        add_score=add_score,
        remove_score=remove_score,
        delta=delta,
        reason=reason,
        remove_held_usd_at_promote=float(remove_held_usd or 0.0),
        residual_hold_allowed=residual_hold_allowed,
        methodology=methodology or {},
        baseline_add=base_add,
        baseline_remove=base_rem,
        basket_before=list(basket_before),
        basket_after=list(basket_after),
        notes=list(notes or []),
    )
    append_pick(rec)
    summarize()  # refresh summary file
    SUMMARY_PATH.write_text(json.dumps(summarize(), indent=2) + "\n")
    return rec
