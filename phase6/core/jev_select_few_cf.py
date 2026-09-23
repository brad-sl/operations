#!/usr/bin/env python3
"""Jev select-few counterfactual paper book — measure-only.

OHLCV + aged eng sentiment (via decision_packet) → Jev judgment on
production tryout-eligible doors (cap top-K) → paper notional seats only.
Tracks potential returns. Never places live orders. would_order always false.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.core.jev_lab_calibration import (
    HORIZONS_H,
    forward_return,
    load_ohlcv_candles,
    refresh_ohlcv_1h,
)
from phase6.core.jev_lab_shadow import LabConfig, run_lab
from phase6.core.paths import PROJECT_ROOT, STATE_DIR
from phase6.core.rsi_event_x_tryout_shadow import production_tryout_eligible_sources

SCHEMA = "jev_select_few_cf_v1"
DEFAULT_NOTIONAL = 25.0
DEFAULT_MAX_PAIRS = 3
DEFAULT_MAX_OPEN = 4
DEFAULT_MAX_CALLS = 12  # separate from main lab 24/day — share budget file optional
MIN_N_CLAIM = 20

STATE_PATH = STATE_DIR / "jev_select_few_cf_latest.json"
BOOK_PATH = STATE_DIR / "jev_select_few_cf_book.json"
CRUMBS_PATH = STATE_DIR / "jev_select_few_cf_crumbs.jsonl"
BUDGET_PATH = STATE_DIR / "jev_select_few_cf_budget.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "JEV_SELECT_FEW_CF_LATEST.md"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        v = float(raw)
        if v > 1e12:
            return v / 1000.0
        return v
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


@dataclass
class SelectFewConfig:
    max_pairs: int = DEFAULT_MAX_PAIRS
    max_open_seats: int = DEFAULT_MAX_OPEN
    notional_usd: float = DEFAULT_NOTIONAL
    max_calls_per_day: int = DEFAULT_MAX_CALLS
    model: str = "~typesafe/jev-latest"
    dry_run: bool = False
    refresh_ohlcv: bool = True
    pairs_override: List[str] = field(default_factory=list)
    # Always consider held tryout names even if not in eligible (already risk-on)
    include_held: bool = True
    close_horizon_h: int = 24
    write: bool = True


def _held_pairs() -> List[str]:
    live = {}
    p = STATE_DIR / "phase6_live_state.json"
    if p.exists():
        try:
            live = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            live = {}
    out: List[str] = []
    pos = live.get("trading_positions") or live.get("positions") or []
    if not isinstance(pos, list):
        return out
    stables = {"USD", "USDC", "USDT", "PAXG"}
    for row in pos:
        if not isinstance(row, dict):
            continue
        pair = str(row.get("pair") or row.get("product_id") or "").upper().replace("_", "-")
        if not pair or "-" not in pair:
            continue
        base = pair.split("-")[0]
        if base in stables:
            continue
        mv = row.get("market_value") or row.get("value")
        if mv is None:
            mv = _f(row.get("quantity") or row.get("qty") or row.get("size")) * _f(
                row.get("price") or row.get("mark") or row.get("current_price")
            )
        if _f(mv) >= 5.0 and pair not in out:
            out.append(pair)
    return out


def resolve_select_universe(cfg: SelectFewConfig) -> Tuple[List[str], Dict[str, Any]]:
    if cfg.pairs_override:
        u = [str(p).upper().replace("_", "-") for p in cfg.pairs_override]
        return u[: cfg.max_pairs], {
            "universe": u[: cfg.max_pairs],
            "source": "pairs_override",
            "parity_ok": None,
            "note": "operator override",
        }
    meta = production_tryout_eligible_sources()
    universe = list(meta.get("universe") or [])
    held = _held_pairs() if cfg.include_held else []
    # Prefer held first (already in risk), then eligible doors
    ordered: List[str] = []
    for p in held + universe:
        if p not in ordered:
            ordered.append(p)
    capped = ordered[: max(1, int(cfg.max_pairs))]
    meta_out = dict(meta)
    meta_out["held_included"] = held
    meta_out["selected"] = capped
    meta_out["max_pairs"] = cfg.max_pairs
    return capped, meta_out


def _empty_book() -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "open": [],  # list of paper seats
        "closed": [],  # recent closed (cap 200)
        "banks": {
            "realized_pnl_usd": 0.0,
            "n_closed": 0,
            "n_opened": 0,
            "n_paper_buy_tags": 0,
        },
        "measure_only": True,
        "would_order_always_false": True,
    }


def load_book(path: Path = BOOK_PATH) -> Dict[str, Any]:
    if not path.exists():
        return _empty_book()
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            return _empty_book()
        d.setdefault("open", [])
        d.setdefault("closed", [])
        d.setdefault("banks", _empty_book()["banks"])
        d["would_order_always_false"] = True
        d["measure_only"] = True
        return d
    except Exception:
        return _empty_book()


def save_book(book: Dict[str, Any], path: Path = BOOK_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(book, indent=2, default=str) + "\n", encoding="utf-8")


def _mark_open_seats(
    book: Dict[str, Any],
    *,
    now_ts: float,
    close_horizon_h: int,
    ohlcv_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Update mtm + close seats that have enough forward tape."""
    still_open: List[Dict[str, Any]] = []
    closed_now: List[Dict[str, Any]] = []
    for seat in list(book.get("open") or []):
        if not isinstance(seat, dict):
            continue
        pair = str(seat.get("pair") or "")
        entry_ts = _parse_ts(seat.get("entry_ts"))
        notional = _f(seat.get("notional_usd"), DEFAULT_NOTIONAL)
        if not pair or entry_ts is None:
            continue
        candles = load_ohlcv_candles(pair)
        marks: Dict[str, Any] = {}
        for h in HORIZONS_H:
            r = forward_return(candles, entry_ts, h) if candles else None
            marks[f"r_{h}h"] = None if r is None else round(r, 6)
            if r is not None:
                marks[f"pnl_{h}h_usd"] = round(notional * r, 4)
        seat["marks"] = marks
        seat["marked_at"] = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()

        r_close = marks.get(f"r_{close_horizon_h}h")
        # Close when full horizon return exists (calibration-ready)
        age_h = (now_ts - entry_ts) / 3600.0
        if r_close is not None and age_h >= close_horizon_h * 0.9:
            pnl = _f(marks.get(f"pnl_{close_horizon_h}h_usd"))
            seat["exit_ts"] = seat["marked_at"]
            seat["exit_horizon_h"] = close_horizon_h
            seat["realized_pnl_usd"] = pnl
            seat["realized_r"] = r_close
            seat["status"] = "closed_cf"
            closed_now.append(seat)
            banks = book.setdefault("banks", {})
            banks["realized_pnl_usd"] = round(_f(banks.get("realized_pnl_usd")) + pnl, 4)
            banks["n_closed"] = int(banks.get("n_closed") or 0) + 1
        else:
            seat["status"] = "open_cf"
            still_open.append(seat)

    book["open"] = still_open
    if closed_now:
        closed = list(book.get("closed") or []) + closed_now
        book["closed"] = closed[-200:]
    return {"n_closed_now": len(closed_now), "n_still_open": len(still_open)}


def _open_paper_seat(
    book: Dict[str, Any],
    *,
    pair: str,
    entry_ts: str,
    notional: float,
    judgment_row: Dict[str, Any],
    max_open: int,
) -> Optional[Dict[str, Any]]:
    open_seats = list(book.get("open") or [])
    # one open seat per pair
    for s in open_seats:
        if str(s.get("pair")) == pair:
            return None
    if len(open_seats) >= max_open:
        return None
    paper = judgment_row.get("paper") or {}
    if not paper.get("paper_would_buy_tag"):
        return None
    seat = {
        "pair": pair,
        "entry_ts": entry_ts,
        "notional_usd": notional,
        "status": "open_cf",
        "model": judgment_row.get("model"),
        "state_compact": judgment_row.get("state_compact"),
        "answers_snip": {
            "action": (judgment_row.get("answers") or {}).get("action"),
            "should_trade": (judgment_row.get("answers") or {}).get("should_trade_name_now"),
            "fakeout": (judgment_row.get("answers") or {}).get("is_fakeout_or_stop_run"),
        },
        "paper": paper,
        "would_order": False,
        "source": "jev_select_few_cf",
    }
    open_seats.append(seat)
    book["open"] = open_seats
    banks = book.setdefault("banks", {})
    banks["n_opened"] = int(banks.get("n_opened") or 0) + 1
    banks["n_paper_buy_tags"] = int(banks.get("n_paper_buy_tags") or 0) + 1
    return seat


def run_select_few_cf(
    *,
    cfg: Optional[SelectFewConfig] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    cfg = cfg or SelectFewConfig()
    now = now or _utc_now()
    now_ts = now.timestamp()

    pairs, uni_meta = resolve_select_universe(cfg)
    book = load_book()

    ohlcv_report: Dict[str, Any] = {}
    if cfg.refresh_ohlcv and pairs and not cfg.dry_run:
        try:
            ohlcv_report = refresh_ohlcv_1h(pairs, force=False)
        except Exception as e:
            ohlcv_report = {"error": f"{type(e).__name__}:{e}"}

    # Mark / close existing paper seats first (uses tape, no Jev spend)
    mark_info = _mark_open_seats(book, now_ts=now_ts, close_horizon_h=int(cfg.close_horizon_h))

    lab_cfg = LabConfig(
        pairs=list(pairs) or ["BTC-USD"],
        max_calls_per_day=int(cfg.max_calls_per_day),
        model=cfg.model,
        dry_run=bool(cfg.dry_run),
        write_crumbs=bool(cfg.write),
        budget_path=BUDGET_PATH,
        crumbs_path=CRUMBS_PATH,
        latest_path=STATE_DIR / "jev_select_few_cf_lab_tick.json",
    )
    lab = run_lab(cfg=lab_cfg, pairs=pairs if pairs else [])

    opened: List[Dict[str, Any]] = []
    for row in lab.get("results") or []:
        if not row.get("ok"):
            continue
        pair = str(row.get("pair") or "")
        seat = _open_paper_seat(
            book,
            pair=pair,
            entry_ts=str(row.get("ts") or now.isoformat()),
            notional=float(cfg.notional_usd),
            judgment_row=row,
            max_open=int(cfg.max_open_seats),
        )
        if seat:
            opened.append({"pair": pair, "notional_usd": cfg.notional_usd})

    # Re-mark after opens (entry marks may be null until tape moves)
    _mark_open_seats(book, now_ts=now_ts, close_horizon_h=int(cfg.close_horizon_h))

    # Unrealized on open
    unreal = 0.0
    for s in book.get("open") or []:
        m = s.get("marks") or {}
        # prefer longest available mark
        for h in reversed(HORIZONS_H):
            k = f"pnl_{h}h_usd"
            if m.get(k) is not None:
                unreal += _f(m[k])
                break

    banks = book.get("banks") or {}
    n_closed = int(banks.get("n_closed") or 0)
    claim = "N_INSUFFICIENT_no_edge_claim"
    if n_closed >= MIN_N_CLAIM:
        claim = "SAMPLE_OK_still_no_live_edge_claim"  # still measure-only

    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": now.isoformat(),
        "measure_only": True,
        "would_order_always_false": True,
        "no_knobs": True,
        "universe": uni_meta,
        "pairs_judged": pairs,
        "lab": {
            "n_ok": lab.get("n_ok"),
            "n_pairs": lab.get("n_pairs"),
            "paper_buy_tags": lab.get("paper_buy_tags"),
            "blocked_budget": lab.get("blocked_budget"),
            "budget": lab.get("budget"),
            "dry_run": lab.get("dry_run"),
            "model": lab.get("model"),
            "plain": lab.get("plain"),
        },
        "ohlcv_refresh": ohlcv_report,
        "mark": mark_info,
        "opened_this_tick": opened,
        "book": {
            "n_open": len(book.get("open") or []),
            "n_closed_total": n_closed,
            "realized_pnl_usd": banks.get("realized_pnl_usd"),
            "unrealized_pnl_usd_approx": round(unreal, 4),
            "n_opened_total": banks.get("n_opened"),
            "open_pairs": [s.get("pair") for s in (book.get("open") or [])],
            "notional_per_seat": cfg.notional_usd,
            "max_open": cfg.max_open_seats,
        },
        "claim_class": claim,
        "min_n_claim": MIN_N_CLAIM,
        "results_snip": [
            {
                "pair": r.get("pair"),
                "ok": r.get("ok"),
                "paper_buy": (r.get("paper") or {}).get("paper_would_buy_tag"),
                "action": ((r.get("answers") or {}).get("action") or {}).get("choice"),
                "should_trade": ((r.get("answers") or {}).get("should_trade_name_now") or {}).get("noul"),
                "fakeout": ((r.get("answers") or {}).get("is_fakeout_or_stop_run") or {}).get("noul"),
                "lat_ms": r.get("latency_ms"),
            }
            for r in (lab.get("results") or [])
        ],
    }

    if cfg.write:
        save_book(book)
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(render_markdown(payload, book), encoding="utf-8")
        # append tick crumb
        CRUMBS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CRUMBS_PATH.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": now.isoformat(),
                        "opened": opened,
                        "n_open": payload["book"]["n_open"],
                        "realized": banks.get("realized_pnl_usd"),
                        "claim": claim,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )

    payload["plain"] = telegram_card(payload)
    return payload


def render_markdown(payload: Dict[str, Any], book: Optional[Dict[str, Any]] = None) -> str:
    b = payload.get("book") or {}
    lab = payload.get("lab") or {}
    uni = payload.get("universe") or {}
    lines = [
        "# Jev select-few CF (measure-only)",
        "",
        f"**As of:** `{payload.get('as_of')}`",
        f"**Claim:** `{payload.get('claim_class')}` (need n_closed≥{payload.get('min_n_claim')} for sample bar; still no live edge)",
        "",
        "> Paper notional only. `would_order` always false. No knobs.",
        "",
        "## Universe",
        "",
        f"- Source: `{uni.get('source')}` · parity_ok=`{uni.get('parity_ok')}`",
        f"- Selected: `{payload.get('pairs_judged')}`",
        f"- Held included: `{uni.get('held_included')}`",
        "",
        "## Paper book",
        "",
        f"- Open seats: **{b.get('n_open')}** · pairs `{b.get('open_pairs')}`",
        f"- Notional/seat: ${b.get('notional_per_seat')} · max_open={b.get('max_open')}",
        f"- Realized CF PnL: **${b.get('realized_pnl_usd')}** · n_closed={b.get('n_closed_total')}",
        f"- Unrealized (approx longest mark): **${b.get('unrealized_pnl_usd_approx')}**",
        f"- Opened this tick: `{payload.get('opened_this_tick')}`",
        "",
        "## Lab tick",
        "",
        f"- ok={lab.get('n_ok')}/{lab.get('n_pairs')} · paper_buy_tags={lab.get('paper_buy_tags')} · budget={lab.get('budget')}",
        f"- dry_run={lab.get('dry_run')} · model=`{lab.get('model')}`",
        "",
        "```json",
        json.dumps(payload.get("results_snip") or [], indent=2),
        "```",
        "",
        f"State: `data/state/jev_select_few_cf_latest.json` · Book: `data/state/jev_select_few_cf_book.json`",
        "",
    ]
    return "\n".join(lines)


def telegram_card(payload: Dict[str, Any]) -> str:
    b = payload.get("book") or {}
    lab = payload.get("lab") or {}
    lines = [
        "🧪 Jev select-few CF (measure-only)",
        f"Claim: {payload.get('claim_class')}",
        f"Doors: {', '.join(payload.get('pairs_judged') or []) or '—'}",
        f"Lab: ok={lab.get('n_ok')}/{lab.get('n_pairs')} paper_buy={lab.get('paper_buy_tags')}",
        f"Paper book: open={b.get('n_open')} {b.get('open_pairs')} · "
        f"${b.get('notional_per_seat')}/seat",
        f"Realized CF: ${b.get('realized_pnl_usd')} (n_closed={b.get('n_closed_total')}) · "
        f"unreal≈${b.get('unrealized_pnl_usd_approx')}",
    ]
    opened = payload.get("opened_this_tick") or []
    if opened:
        lines.append(f"Opened this tick: {opened}")
    lines.append("No orders · no knobs · full: reports/JEV_SELECT_FEW_CF_LATEST.md")
    return "\n".join(lines)
