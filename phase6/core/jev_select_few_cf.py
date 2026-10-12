#!/usr/bin/env python3
"""Jev select-few counterfactual paper book — measure-only.

OHLCV + aged eng sentiment (via decision_packet) → Jev judgment on
production tryout-eligible doors (cap top-K) → paper notional seats only.
Tracks potential returns. Never places live orders. would_order always false.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from zoneinfo import ZoneInfo

    PT = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    PT = timezone.utc

from phase6.core.jev_lab_calibration import (
    HORIZONS_H,
    forward_return,
    load_ohlcv_candles,
    refresh_ohlcv_1h,
)
from phase6.core.jev_lab_shadow import LabConfig, run_lab
from phase6.core.paths import PROJECT_ROOT, STATE_DIR
from phase6.core.rsi_event_x_tryout_shadow import production_tryout_eligible_sources
from phase6.domain.services.decision_packet import confidence_gate_paper

SCHEMA = "jev_select_few_cf_v1"
DEFAULT_NOTIONAL = 25.0
DEFAULT_MAX_PAIRS = 5  # was 3 — held names were eating all judgment slots
DEFAULT_MAX_OPEN = 6
DEFAULT_MAX_CALLS = 24  # was 12 — more doors/day for collection
MIN_N_CLAIM = 20
# Collection-mode paper gate (still would_order=false). Live lab defaults stay stricter.
# Crumbs: 14× action=buy but paper_would_buy_tag 0× under lab floors (st≥0.65 conf_act≥0.85).
# Jev buy labels cluster should_trade ~0.34–0.45 — collection must sit under that mass.
CF_SHOULD_TRADE_MIN = 0.30
CF_FAKEOUT_MAX = 0.65
CF_ACTION_CONF_MIN = 0.35
CF_CONF_ACT = 0.50  # route "act" once conf ≥ this (was 0.85)
CF_CONF_ESCALATE = 0.30
# Soft open: action=buy is enough if st/fk not toxic (measure collection, not live floors)
CF_SOFT_SHOULD_TRADE_MIN = 0.28
CF_SOFT_ACTION_CONF_MIN = 0.30

STATE_PATH = STATE_DIR / "jev_select_few_cf_latest.json"
BOOK_PATH = STATE_DIR / "jev_select_few_cf_book.json"
CRUMBS_PATH = STATE_DIR / "jev_select_few_cf_crumbs.jsonl"
BUDGET_PATH = STATE_DIR / "jev_select_few_cf_budget.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "JEV_SELECT_FEW_CF_LATEST.md"
WEEKLY_STATE_PATH = STATE_DIR / "jev_select_few_cf_weekly_latest.json"
WEEKLY_REPORT_PATH = PROJECT_ROOT / "reports" / "JEV_SELECT_FEW_CF_WEEKLY_LATEST.md"


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
    # Prefer eligible doors for *new* CF seats; held is context only (not first slots)
    include_held: bool = True
    prefer_eligible_over_held: bool = True
    close_horizon_h: int = 24
    write: bool = True
    # Collection paper gate (measure-only). Not live buy floors.
    should_trade_min: float = CF_SHOULD_TRADE_MIN
    fakeout_max: float = CF_FAKEOUT_MAX
    action_conf_min: float = CF_ACTION_CONF_MIN
    conf_act: float = CF_CONF_ACT
    conf_escalate: float = CF_CONF_ESCALATE
    soft_should_trade_min: float = CF_SOFT_SHOULD_TRADE_MIN
    soft_action_conf_min: float = CF_SOFT_ACTION_CONF_MIN
    # Also open paper seat on action=buy + soft floors (even if conf_route != act)
    allow_soft_buy_open: bool = True


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
    # Collection fix: eligible doors first so we actually judge *new* seat candidates.
    # Old order put held first → max_pairs=3 was often TIA/SOL/BTC forever, no new CF opens.
    ordered: List[str] = []
    if cfg.prefer_eligible_over_held:
        primary, secondary = universe, held
    else:
        primary, secondary = held, universe
    for p in primary + secondary:
        pu = str(p).upper().replace("_", "-")
        if pu and pu not in ordered:
            ordered.append(pu)
    capped = ordered[: max(1, int(cfg.max_pairs))]
    meta_out = dict(meta)
    meta_out["held_included"] = held
    meta_out["selected"] = capped
    meta_out["max_pairs"] = cfg.max_pairs
    meta_out["prefer_eligible_over_held"] = bool(cfg.prefer_eligible_over_held)
    meta_out["selection_note"] = (
        "eligible_first_collection_v1"
        if cfg.prefer_eligible_over_held
        else "held_first_legacy"
    )
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


def load_book(path: Optional[Path] = None) -> Dict[str, Any]:
    # Resolve BOOK_PATH at call time so tests can patch the module attribute.
    path = path if path is not None else BOOK_PATH
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


def save_book(book: Dict[str, Any], path: Optional[Path] = None) -> None:
    path = path if path is not None else BOOK_PATH
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
        # Close when full horizon return exists (calibration-ready).
        # exit_ts = entry + horizon (not "now") so weekly windows count historical closes honestly.
        age_h = (now_ts - entry_ts) / 3600.0
        if r_close is not None and age_h >= close_horizon_h * 0.9:
            pnl = _f(marks.get(f"pnl_{close_horizon_h}h_usd"))
            exit_ts_f = entry_ts + float(close_horizon_h) * 3600.0
            seat["exit_ts"] = datetime.fromtimestamp(exit_ts_f, tz=timezone.utc).isoformat()
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


def _apply_cf_paper_gate(
    judgment_row: Dict[str, Any],
    cfg: SelectFewConfig,
) -> Dict[str, Any]:
    """Re-score paper tag with collection-mode floors (lab default gate is too strict to ever open)."""
    answers = judgment_row.get("answers") or {}
    lab_paper = judgment_row.get("paper")
    paper = confidence_gate_paper(
        answers,
        should_trade_min=float(cfg.should_trade_min),
        fakeout_max=float(cfg.fakeout_max),
        action_conf_min=float(cfg.action_conf_min),
        conf_act=float(cfg.conf_act),
        conf_escalate=float(cfg.conf_escalate),
    )
    # Soft path: action=buy + soft st floor + not high fakeout.
    # Collection goal = open paper seats when model says buy so CF can mark/close.
    if cfg.allow_soft_buy_open and not paper.get("paper_would_buy_tag"):
        act = (answers.get("action") or {}).get("choice")
        st = None
        try:
            raw_st = (answers.get("should_trade_name_now") or {}).get("noul")
            if raw_st is not None:
                st = float(raw_st)
        except Exception:
            st = None
        fk_f = None
        try:
            fk = (answers.get("is_fakeout_or_stop_run") or {}).get("noul")
            if fk is not None:
                fk_f = float(fk)
        except Exception:
            fk_f = None
        ac_f = None
        try:
            ac = (answers.get("action") or {}).get("confidence")
            if ac is not None:
                ac_f = float(ac)
        except Exception:
            ac_f = None
        soft_st = float(cfg.soft_should_trade_min)
        soft_ac = float(cfg.soft_action_conf_min)
        if (
            act == "buy"
            and st is not None
            and st >= soft_st
            and (fk_f is None or fk_f < float(cfg.fakeout_max))
            and (ac_f is None or ac_f >= soft_ac)
        ):
            paper = dict(paper)
            paper["paper_would_buy_tag"] = True
            paper["confidence_route"] = str(paper.get("confidence_route") or "soft_cf")
            paper["reasons"] = list(paper.get("reasons") or []) + [
                "soft_cf_buy_collection_v1"
            ]
            paper["would_order"] = False
            paper["soft_thresholds"] = {
                "soft_should_trade_min": soft_st,
                "soft_action_conf_min": soft_ac,
                "fakeout_max": float(cfg.fakeout_max),
            }
    out = dict(judgment_row)
    out["paper_lab_default"] = lab_paper
    out["paper"] = paper
    return out


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


def backfill_paper_seats_from_crumbs(
    *,
    book: Optional[Dict[str, Any]] = None,
    crumbs_path: Optional[Path] = None,
    book_path: Optional[Path] = None,
    cfg: Optional[SelectFewConfig] = None,
    write: bool = True,
    mark_close: bool = True,
) -> Dict[str, Any]:
    """Replay historical crumbs under collection gate → paper seats (measure-only).

    Does not place orders. Skips crumb rows that are tick summaries (no answers).
    One open seat per pair (first qualifying crumb wins).
    """
    cfg = cfg or SelectFewConfig()
    crumbs_path = crumbs_path if crumbs_path is not None else CRUMBS_PATH
    book_path = book_path if book_path is not None else BOOK_PATH
    book = book if book is not None else load_book(book_path)
    opened: List[Dict[str, Any]] = []
    scanned = 0
    buyish = 0
    if not crumbs_path.is_file():
        return {"scanned": 0, "opened": [], "book": book}
    lines = crumbs_path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or not row.get("answers"):
            continue
        if not row.get("ok", True):
            continue
        scanned += 1
        pair = str(row.get("pair") or "")
        if not pair:
            continue
        gated = _apply_cf_paper_gate(row, cfg)
        if not (gated.get("paper") or {}).get("paper_would_buy_tag"):
            continue
        buyish += 1
        seat = _open_paper_seat(
            book,
            pair=pair,
            entry_ts=str(row.get("ts") or _utc_now().isoformat()),
            notional=float(cfg.notional_usd),
            judgment_row=gated,
            max_open=int(cfg.max_open_seats),
        )
        if seat:
            opened.append({"pair": pair, "entry_ts": seat.get("entry_ts")})
    mark_info: Dict[str, Any] = {}
    if mark_close:
        mark_info = _mark_open_seats(
            book,
            now_ts=_utc_now().timestamp(),
            close_horizon_h=int(cfg.close_horizon_h),
        )
    if write:
        save_book(book, book_path)
    return {
        "scanned": scanned,
        "n_gate_pass": buyish,
        "opened_now": opened,
        "n_opened_now": len(opened),
        "mark": mark_info,
        "book_banks": book.get("banks"),
        "n_open": len(book.get("open") or []),
        "n_closed": len(book.get("closed") or []),
    }


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
    skip_reasons: Dict[str, int] = {}
    n_gate_pass = 0
    for row in lab.get("results") or []:
        if not row.get("ok"):
            skip_reasons["lab_not_ok"] = skip_reasons.get("lab_not_ok", 0) + 1
            continue
        pair = str(row.get("pair") or "")
        gated = _apply_cf_paper_gate(row, cfg)
        paper = gated.get("paper") or {}
        if paper.get("paper_would_buy_tag"):
            n_gate_pass += 1
        else:
            for rsn in paper.get("reasons") or ["no_paper_tag"]:
                key = str(rsn).split(":")[0][:48]
                skip_reasons[key] = skip_reasons.get(key, 0) + 1
        seat = _open_paper_seat(
            book,
            pair=pair,
            entry_ts=str(row.get("ts") or now.isoformat()),
            notional=float(cfg.notional_usd),
            judgment_row=gated,
            max_open=int(cfg.max_open_seats),
        )
        if seat:
            opened.append({"pair": pair, "notional_usd": cfg.notional_usd})
        elif paper.get("paper_would_buy_tag"):
            skip_reasons["open_blocked_already_open_or_cap"] = (
                skip_reasons.get("open_blocked_already_open_or_cap", 0) + 1
            )

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
        "funnel": {
            "n_judged_ok": lab.get("n_ok"),
            "n_cf_gate_pass": n_gate_pass,
            "n_opened": len(opened),
            "skip_reasons": skip_reasons,
            "gate": {
                "should_trade_min": cfg.should_trade_min,
                "fakeout_max": cfg.fakeout_max,
                "action_conf_min": cfg.action_conf_min,
                "conf_act": cfg.conf_act,
                "soft_buy_open": cfg.allow_soft_buy_open,
                "mode": "collection_v1",
            },
        },
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
                "paper_buy": (_apply_cf_paper_gate(r, cfg).get("paper") or {}).get(
                    "paper_would_buy_tag"
                )
                if r.get("ok")
                else False,
                "action": ((r.get("answers") or {}).get("action") or {}).get("choice"),
                "should_trade": ((r.get("answers") or {}).get("should_trade_name_now") or {}).get(
                    "noul"
                ),
                "fakeout": ((r.get("answers") or {}).get("is_fakeout_or_stop_run") or {}).get(
                    "noul"
                ),
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
    funnel = payload.get("funnel") or {}
    lines = [
        "🧪 Jev select-few CF (measure-only)",
        f"Claim: {payload.get('claim_class')}",
        f"Doors: {', '.join(payload.get('pairs_judged') or []) or '—'}",
        f"Lab: ok={lab.get('n_ok')}/{lab.get('n_pairs')} · "
        f"cf_gate_pass={funnel.get('n_cf_gate_pass')} · opened={funnel.get('n_opened')}",
        f"Paper book: open={b.get('n_open')} {b.get('open_pairs')} · "
        f"${b.get('notional_per_seat')}/seat",
        f"Realized CF: ${b.get('realized_pnl_usd')} (n_closed={b.get('n_closed_total')}) · "
        f"unreal≈${b.get('unrealized_pnl_usd_approx')}",
    ]
    opened = payload.get("opened_this_tick") or []
    if opened:
        lines.append(f"Opened this tick: {opened}")
    skips = funnel.get("skip_reasons") or {}
    if skips and not opened:
        top = sorted(skips.items(), key=lambda kv: -kv[1])[:3]
        lines.append("Skip top: " + ", ".join(f"{k}×{v}" for k, v in top))
    lines.append("No orders · no knobs · full: reports/JEV_SELECT_FEW_CF_LATEST.md")
    return "\n".join(lines)


def _pt_now(now: Optional[datetime] = None) -> datetime:
    now = now or _utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(PT)


def _seat_ts(seat: Dict[str, Any], key: str = "exit_ts") -> Optional[float]:
    return _parse_ts(seat.get(key) or seat.get("entry_ts"))


def build_weekly_rollup(
    *,
    lookback_days: int = 7,
    now: Optional[datetime] = None,
    write: bool = True,
    book_path: Path = BOOK_PATH,
) -> Dict[str, Any]:
    """Sunday (or on-demand) measure-only CF week card. No Jev calls, no orders."""
    now = now or _utc_now()
    now_pt = _pt_now(now)
    window_start = now - timedelta(days=max(1, int(lookback_days)))
    window_ts = window_start.timestamp()
    book = load_book(book_path)
    banks = book.get("banks") or {}

    closed_all = [s for s in (book.get("closed") or []) if isinstance(s, dict)]
    closed_week = []
    for s in closed_all:
        ts = _seat_ts(s, "exit_ts")
        if ts is not None and ts >= window_ts:
            closed_week.append(s)

    opened_week = 0
    for s in list(book.get("open") or []) + closed_all:
        if not isinstance(s, dict):
            continue
        ts = _seat_ts(s, "entry_ts")
        if ts is not None and ts >= window_ts:
            opened_week += 1

    week_pnl = 0.0
    wins = 0
    losses = 0
    by_pair: Dict[str, float] = {}
    for s in closed_week:
        pnl = _f(s.get("realized_pnl_usd"))
        week_pnl += pnl
        pair = str(s.get("pair") or "?")
        by_pair[pair] = round(by_pair.get(pair, 0.0) + pnl, 4)
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1

    n_closed_w = len(closed_week)
    n_closed_all = int(banks.get("n_closed") or 0)
    claim = "N_INSUFFICIENT_no_edge_claim"
    if n_closed_all >= MIN_N_CLAIM:
        claim = "SAMPLE_OK_still_no_live_edge_claim"

    # Unrealized approx on open (longest mark)
    unreal = 0.0
    open_pairs: List[str] = []
    for s in book.get("open") or []:
        if not isinstance(s, dict):
            continue
        open_pairs.append(str(s.get("pair") or ""))
        m = s.get("marks") or {}
        for h in reversed(HORIZONS_H):
            k = f"pnl_{h}h_usd"
            if m.get(k) is not None:
                unreal += _f(m[k])
                break

    # Crumb activity this window + judgment funnel (not only empty book)
    n_ticks = 0
    n_action_buy = 0
    n_action_hold = 0
    n_ok_crumbs = 0
    if CRUMBS_PATH.is_file():
        try:
            for line in CRUMBS_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = _parse_ts(row.get("ts"))
                if ts is None or ts < window_ts:
                    continue
                n_ticks += 1
                if not row.get("answers"):
                    continue
                if row.get("ok"):
                    n_ok_crumbs += 1
                act = ((row.get("answers") or {}).get("action") or {}).get("choice")
                if act == "buy":
                    n_action_buy += 1
                elif act == "hold":
                    n_action_hold += 1
        except OSError:
            pass

    # Why empty book? Diagnose for TG
    empty_reason = None
    if n_closed_all == 0 and int(banks.get("n_opened") or 0) == 0:
        if n_action_buy == 0 and n_ok_crumbs > 0:
            empty_reason = "model_mostly_hold_no_buy_labels"
        elif n_action_buy > 0:
            empty_reason = (
                "buys_existed_but_paper_gate_blocked_pre_collection_fix"
                if n_closed_w == 0
                else None
            )
        elif n_ticks > 0:
            empty_reason = "ticks_but_no_judgment_answers_in_window"
        else:
            empty_reason = "no_ticks_in_window"

    budget = {}
    if BUDGET_PATH.is_file():
        try:
            budget = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
        except Exception:
            budget = {}

    payload: Dict[str, Any] = {
        "schema": "jev_select_few_cf_weekly_v1",
        "as_of": now.isoformat(),
        "as_of_pt": now_pt.isoformat(),
        "lookback_days": int(lookback_days),
        "window_start": window_start.isoformat(),
        "measure_only": True,
        "would_order_always_false": True,
        "no_knobs": True,
        "claim_class": claim,
        "min_n_claim": MIN_N_CLAIM,
        "week": {
            "n_closed": n_closed_w,
            "n_opened": opened_week,
            "realized_pnl_usd": round(week_pnl, 4),
            "wins": wins,
            "losses": losses,
            "by_pair": by_pair,
            "n_ticks": n_ticks,
            "n_ok_judgment_crumbs": n_ok_crumbs,
            "n_action_buy": n_action_buy,
            "n_action_hold": n_action_hold,
        },
        "lifetime": {
            "n_closed": n_closed_all,
            "n_opened": int(banks.get("n_opened") or 0),
            "realized_pnl_usd": banks.get("realized_pnl_usd"),
            "n_paper_buy_tags": banks.get("n_paper_buy_tags"),
        },
        "open": {
            "n": len(open_pairs),
            "pairs": open_pairs,
            "unrealized_pnl_usd_approx": round(unreal, 4),
        },
        "funnel_diagnosis": empty_reason,
        "collection_gate": {
            "should_trade_min": CF_SHOULD_TRADE_MIN,
            "conf_act": CF_CONF_ACT,
            "mode": "collection_v1",
        },
        "budget_today": budget,
        "notional_per_seat": DEFAULT_NOTIONAL,
    }
    payload["plain"] = weekly_telegram_card(payload)

    if write:
        WEEKLY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        WEEKLY_STATE_PATH.write_text(
            json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
        )
        WEEKLY_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        WEEKLY_REPORT_PATH.write_text(weekly_markdown(payload), encoding="utf-8")
    return payload


def weekly_telegram_card(payload: Dict[str, Any]) -> str:
    w = payload.get("week") or {}
    life = payload.get("lifetime") or {}
    op = payload.get("open") or {}
    by_pair = w.get("by_pair") or {}
    pair_bits = ", ".join(f"{k} ${v}" for k, v in sorted(by_pair.items())) or "—"
    lines = [
        "🧪 Jev CF — weekly (measure-only)",
        f"Window: last {payload.get('lookback_days')}d · claim {payload.get('claim_class')}",
        f"Week closed: {w.get('n_closed')} · opened {w.get('n_opened')} · "
        f"W/L {w.get('wins')}/{w.get('losses')}",
        f"Week CF $: {w.get('realized_pnl_usd')} · by pair: {pair_bits}",
        f"Judgments: buy×{w.get('n_action_buy')} hold×{w.get('n_action_hold')} · "
        f"ok_crumbs={w.get('n_ok_judgment_crumbs')} ticks={w.get('n_ticks')}",
        f"Open now: {op.get('n')} {op.get('pairs')} · unreal≈${op.get('unrealized_pnl_usd_approx')}",
        f"Lifetime: closed={life.get('n_closed')} opened={life.get('n_opened')} · "
        f"CF ${life.get('realized_pnl_usd')} · need ≥{payload.get('min_n_claim')} closed",
    ]
    diag = payload.get("funnel_diagnosis")
    if diag:
        lines.append(f"Empty-book why: {diag}")
    gate = payload.get("collection_gate") or {}
    if gate:
        lines.append(
            f"Gate: collection_v1 st≥{gate.get('should_trade_min')} conf_act≥{gate.get('conf_act')}"
        )
    lines.append("Paper only · no orders · no knobs · reports/JEV_SELECT_FEW_CF_WEEKLY_LATEST.md")
    return "\n".join(lines)


def weekly_markdown(payload: Dict[str, Any]) -> str:
    w = payload.get("week") or {}
    life = payload.get("lifetime") or {}
    op = payload.get("open") or {}
    return "\n".join(
        [
            "# Jev select-few CF — weekly rollup",
            "",
            f"**As of (PT):** `{payload.get('as_of_pt')}`",
            f"**Window:** last {payload.get('lookback_days')}d from `{payload.get('window_start')}`",
            f"**Claim:** `{payload.get('claim_class')}`",
            "",
            "> Measure-only paper book. `would_order` always false.",
            "",
            "## This window",
            "",
            f"- Closed: **{w.get('n_closed')}** · opened: **{w.get('n_opened')}** · W/L **{w.get('wins')}/{w.get('losses')}**",
            f"- Realized CF $: **{w.get('realized_pnl_usd')}**",
            f"- By pair: `{w.get('by_pair')}`",
            f"- Ticks (crumbs): {w.get('n_ticks')} · ok judgments: {w.get('n_ok_judgment_crumbs')}",
            f"- Action labels: buy×{w.get('n_action_buy')} · hold×{w.get('n_action_hold')}",
            f"- Funnel diagnosis: `{payload.get('funnel_diagnosis')}`",
            f"- Collection gate: `{payload.get('collection_gate')}`",
            "",
            "## Open / lifetime",
            "",
            f"- Open: {op.get('n')} `{op.get('pairs')}` · unreal≈${op.get('unrealized_pnl_usd_approx')}",
            f"- Lifetime closed={life.get('n_closed')} · opened={life.get('n_opened')} · "
            f"CF ${life.get('realized_pnl_usd')} · tags={life.get('n_paper_buy_tags')}",
            "",
            "```json",
            json.dumps(payload, indent=2, default=str)[:4000],
            "```",
            "",
        ]
    )
