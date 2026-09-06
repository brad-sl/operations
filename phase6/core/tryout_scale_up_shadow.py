"""Tryout mid-flight scale-up shadow — ride the wave (Brad GO 2026-09-05).

Product hole this fills:
  $75 tryout opens → works (green, still building) → step up size *while holding*
  → ride with real size → jump (TP/trail/dual-peak) before the break.
  NOT: tryout → tiny TP → flat → 24h lockout → \"graduated\" with no capital behind proof.

Standing rules:
  • Shadow only until Brad GO live_apply
  • One step-up per open lot (tryout → tryout+step), never pyramid
  • Pre-TP band only (green but below trail arm) — do not chase into bank zone
  • Phase ignition/trend + structure_ok (same honesty as H4 / ignition scout)
  • Volume is NOT the scale trigger (liquidity already filtered at intake)
  • Post-TP cooloff / H4 stay orthogonal (this is in-seat, pre-exit)
  • first_fill graduate_on_tp remains post-close for *next empty seat* — different job

Brad framing: catch the wave as it builds; jump before it breaks.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from phase6.core.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

SCHEMA = "tryout_scale_up_shadow_v1"
STATE_DIR = PROJECT_ROOT / "data" / "state"
REPORTS_DIR = PROJECT_ROOT / "reports"
LATEST_PATH = STATE_DIR / "tryout_scale_up_shadow_latest.json"
CRUMBS_PATH = STATE_DIR / "tryout_scale_up_shadow_crumbs.jsonl"
OPEN_LOTS_PATH = STATE_DIR / "tryout_scale_up_open_lots.json"
DECISION_PATH = STATE_DIR / "tryout_scale_up_brad_decision.json"
REPORT_PATH = REPORTS_DIR / "TRYOUT_SCALE_UP_SHADOW_LATEST.md"
LIVE_STATE = STATE_DIR / "phase6_live_state.json"
LEDGER_PATH = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"

# Defaults — conservative ride-the-wave shadow
DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "live_apply": False,  # NEVER true without Brad GO
    "tryout_max_usd": 90.0,  # open seat still "tryout-sized" if held ≤ this
    "tryout_min_usd": 40.0,
    "step_usd": 75.0,  # one add: $75 → ~$150
    "max_total_after_step_usd": 160.0,
    "min_hold_hours": 2.0,  # not scalp FOMO
    "min_unrealized_r": 0.015,  # +1.5%
    "max_unrealized_r": 0.038,  # below ~trail arm (+4%); don't scale into bank zone
    "require_phase_in": [1, 2],  # ignition, trend
    "require_structure_ok": True,
    "fee_haircut_rt": 0.0016,  # ~round-trip bps proxy for CF
    "sl_r": -0.03,
    "sticky_skip": ("BTC-USD", "BTC-USDC", "PAXG-USD", "PAXG-USDC", "USDC-USD", "USD-USD"),
    "score_horizon_hours": 168.0,  # score open paper legs up to 7d
    "cf_min_scored": 8,
    "cf_prefer_scored": 12,
    # edge bar (ATTENTION_ONLY even if green): scale path mean excess vs tryout-only ≥ +0.5pp
    "cf_min_excess_pp": 0.005,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(dt: Optional[datetime] = None) -> str:
    d = dt or _utc_now()
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.isoformat()


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return float(default)
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def _norm_pair(p: str) -> str:
    s = str(p or "").strip().upper().replace("_", "-")
    if not s:
        return ""
    if "-" not in s:
        s = f"{s}-USD"
    return s


def load_cfg(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    # optional file knobs
    for path in (
        PROJECT_ROOT / "config" / "tryout_scale_up_shadow.json",
        STATE_DIR / "tryout_scale_up_shadow_cfg.json",
    ):
        try:
            if path.exists():
                raw = json.loads(path.read_text())
                if isinstance(raw, dict):
                    cfg.update({k: v for k, v in raw.items() if v is not None})
        except Exception:
            pass
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    # normalize lists
    cfg["require_phase_in"] = [int(x) for x in (cfg.get("require_phase_in") or [1, 2])]
    cfg["sticky_skip"] = tuple(
        _norm_pair(x) for x in (cfg.get("sticky_skip") or DEFAULTS["sticky_skip"])
    )
    cfg["live_apply"] = False if not bool(cfg.get("live_apply")) else False  # hard pin shadow
    # re-read pin: only decision file can flip live later — still false here
    cfg["live_apply"] = False
    return cfg


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:
        logger.debug("load %s fail: %s", path, e)
    return default


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")


def _append_crumb(row: Dict[str, Any]) -> None:
    CRUMBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CRUMBS_PATH.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")


def load_live_positions() -> List[Dict[str, Any]]:
    d = _load_json(LIVE_STATE, {})
    if not isinstance(d, dict):
        return []
    rows = d.get("positions") or d.get("active_positions") or []
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        pair = _norm_pair(str(r.get("pair") or ""))
        if not pair:
            continue
        out.append(
            {
                "pair": pair,
                "value_usd": _f(r.get("value_usd") or r.get("notional_usd")),
                "entry_price": _f(r.get("entry_price") or r.get("avg_entry") or r.get("cost_basis")),
                "current_price": _f(r.get("current_price") or r.get("price") or r.get("mark")),
                "unrealized_pnl_pct": _f(r.get("unrealized_pnl_pct")),
                "qty": _f(r.get("qty") or r.get("amount") or r.get("quantity")),
                "sleeve": str(r.get("sleeve") or ""),
                "raw": r,
            }
        )
    return out


def _ledger_rows_for_pair(pair: str, limit: int = 40) -> List[Dict[str, Any]]:
    p = _norm_pair(pair)
    rows: List[Dict[str, Any]] = []
    if not LEDGER_PATH.exists():
        return rows
    try:
        for line in LEDGER_PATH.open():
            line = line.strip()
            if not line or p.split("-")[0] not in line:
                continue
            try:
                t = json.loads(line)
            except Exception:
                continue
            if _norm_pair(str(t.get("pair") or "")) != p:
                continue
            rows.append(t)
    except Exception:
        return rows
    return rows[-limit:]


def _parse_ts(s: Any) -> Optional[datetime]:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        try:
            return datetime.fromtimestamp(float(s), tz=timezone.utc)
        except Exception:
            return None
    text = str(s).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def infer_open_lot_entry(pair: str, pos: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort open lot: last BUY after last full flat, else position entry."""
    rows = _ledger_rows_for_pair(pair, limit=80)
    last_buy: Optional[Dict[str, Any]] = None
    # walk newest-first
    for t in reversed(rows):
        side = str(t.get("side") or "").upper()
        if side == "SELL":
            # if we hit a sell before a buy, lot may still be open if position exists —
            # keep scanning for buy under current position assumption
            if last_buy is None:
                continue
            break
        if side == "BUY":
            last_buy = t
            break
    entry_px = _f(pos.get("entry_price"))
    entry_ts = None
    reason = ""
    tryout_tag = False
    if last_buy:
        entry_ts = _parse_ts(last_buy.get("timestamp") or last_buy.get("ts"))
        bp = _f(last_buy.get("price") or last_buy.get("fill_price") or last_buy.get("entry_price"))
        if bp > 0:
            entry_px = bp
        reason = str(last_buy.get("reason") or last_buy.get("exit_reason") or "")
        rl = reason.lower()
        tryout_tag = any(
            x in rl
            for x in (
                "tryout",
                "first_fill",
                "quality_tryout",
                "e2e_rebalance",
            )
        )
    # fallback hold hours unknown
    return {
        "entry_price": entry_px,
        "entry_ts": entry_ts.isoformat() if entry_ts else None,
        "entry_reason": reason,
        "tryout_tagged_buy": tryout_tag,
    }


def _unrealized_r(pos: Dict[str, Any], entry_px: float) -> float:
    # Prefer stamped unrealized; else mark/entry
    u = pos.get("unrealized_pnl_pct")
    if u is not None and abs(_f(u)) > 0:
        # some paths store fraction, some percent
        v = _f(u)
        if abs(v) > 1.5:  # clearly percent
            return v / 100.0
        return v
    mark = _f(pos.get("current_price"))
    if entry_px > 0 and mark > 0:
        return (mark / entry_px) - 1.0
    return 0.0


def _phase_and_structure(pair: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "phase": None,
        "phase_name": None,
        "structure_ok": None,
        "error": None,
    }
    try:
        from phase6.core.run_phase_deploy import (
            classify_run_phase,
            fetch_daily_candles_public,
            load_run_phase_config,
        )
        from phase6.core.run_lifecycle import classify_structure

        candles = fetch_daily_candles_public(pair, limit=40) or []
        if len(candles) < 15:
            out["error"] = "thin_candles"
            return out
        phase_cfg = load_run_phase_config(None)
        snap = classify_run_phase(pair, candles, phase_cfg)
        out["phase"] = int(getattr(snap, "phase", 0) or 0)
        out["phase_name"] = str(getattr(snap, "phase_name", "") or getattr(snap, "name", "") or "")
        try:
            sc = classify_structure(candles, pair=pair)
            out["structure_ok"] = bool(getattr(sc, "structure_ok_for_entry", False))
        except Exception as e:
            out["structure_ok"] = None
            out["error"] = f"structure:{e}"
    except Exception as e:
        out["error"] = str(e)
    return out


@dataclass
class ScaleDecision:
    pair: str
    status: str  # skip | would_scale | blocked | not_tryout | sticky
    held_usd: float
    unrealized_r: float
    hold_hours: Optional[float]
    phase: Optional[int]
    structure_ok: Optional[bool]
    step_usd: float
    reasons: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_scale_up(
    pos: Dict[str, Any],
    cfg: Optional[Dict[str, Any]] = None,
    *,
    now: Optional[datetime] = None,
    phase_struct: Optional[Dict[str, Any]] = None,
) -> ScaleDecision:
    """Pure-ish evaluate: does this open seat earn one mid-flight step-up?"""
    c = cfg or load_cfg()
    now = now or _utc_now()
    pair = _norm_pair(pos.get("pair") or "")
    held = _f(pos.get("value_usd"))
    step = _f(c.get("step_usd"), 75.0)
    reasons: List[str] = []

    if pair in set(c.get("sticky_skip") or ()):
        return ScaleDecision(pair, "sticky", held, 0.0, None, None, None, 0.0, ["sticky_ballast"])

    sleeve = str(pos.get("sleeve") or "").lower()
    if sleeve == "preserve":
        return ScaleDecision(pair, "skip", held, 0.0, None, None, None, 0.0, ["preserve_sleeve"])

    lot = infer_open_lot_entry(pair, pos)
    entry_px = _f(lot.get("entry_price") or pos.get("entry_price"))
    r = _unrealized_r(pos, entry_px)
    hold_h = None
    ets = _parse_ts(lot.get("entry_ts"))
    if ets:
        hold_h = max(0.0, (now - ets).total_seconds() / 3600.0)

    # tryout-sized open seat?
    tmin = _f(c.get("tryout_min_usd"), 40.0)
    tmax = _f(c.get("tryout_max_usd"), 90.0)
    is_tryout_size = tmin <= held <= tmax
    if not is_tryout_size and not lot.get("tryout_tagged_buy"):
        return ScaleDecision(
            pair,
            "not_tryout",
            held,
            r,
            hold_h,
            None,
            None,
            0.0,
            [f"held_usd={held:.0f} outside tryout band {tmin}-{tmax}"],
            {"lot": lot},
        )
    if held > tmax and not lot.get("tryout_tagged_buy"):
        return ScaleDecision(
            pair,
            "skip",
            held,
            r,
            hold_h,
            None,
            None,
            0.0,
            ["already_above_tryout_size"],
            {"lot": lot},
        )

    # already stepped? check open lots registry
    open_reg = _load_json(OPEN_LOTS_PATH, {"lots": {}})
    lots = open_reg.get("lots") if isinstance(open_reg, dict) else {}
    if isinstance(lots, dict) and pair in lots and lots[pair].get("scaled"):
        return ScaleDecision(
            pair,
            "skip",
            held,
            r,
            hold_h,
            None,
            None,
            0.0,
            ["already_scaled_this_lot"],
            {"lot": lot, "reg": lots.get(pair)},
        )

    if hold_h is not None and hold_h < _f(c.get("min_hold_hours"), 2.0):
        reasons.append(f"hold_hours={hold_h:.2f}<{c.get('min_hold_hours')}")
    elif hold_h is None:
        reasons.append("hold_hours_unknown")

    rmin = _f(c.get("min_unrealized_r"), 0.015)
    rmax = _f(c.get("max_unrealized_r"), 0.038)
    if r < rmin:
        reasons.append(f"r={r:.4f}<min {rmin}")
    if r > rmax:
        reasons.append(f"r={r:.4f}>max {rmax} (bank_zone_or_extended)")

    ps = phase_struct if phase_struct is not None else _phase_and_structure(pair)
    phase = ps.get("phase")
    struct_ok = ps.get("structure_ok")
    allow_phases = {int(x) for x in (c.get("require_phase_in") or [1, 2])}
    if phase is None:
        reasons.append(f"phase_unknown:{ps.get('error')}")
    elif int(phase) not in allow_phases:
        reasons.append(f"phase={phase} not in {sorted(allow_phases)}")
    if bool(c.get("require_structure_ok", True)):
        if struct_ok is None:
            reasons.append("structure_unknown")
        elif not struct_ok:
            reasons.append("structure_not_ok")

    total_after = held + step
    if total_after > _f(c.get("max_total_after_step_usd"), 160.0) + 1e-6:
        reasons.append(f"total_after={total_after:.0f}>max")

    detail = {
        "lot": lot,
        "phase_struct": ps,
        "entry_price": entry_px,
        "mark": _f(pos.get("current_price")),
        "step_usd": step,
        "total_after_usd": round(total_after, 2),
        "ride_the_wave": True,
    }

    if reasons:
        return ScaleDecision(
            pair, "blocked", held, r, hold_h, phase if isinstance(phase, int) else None,
            struct_ok if isinstance(struct_ok, bool) else None, 0.0, reasons, detail
        )

    return ScaleDecision(
        pair,
        "would_scale",
        held,
        r,
        hold_h,
        int(phase) if phase is not None else None,
        bool(struct_ok) if struct_ok is not None else None,
        step,
        ["earned_mid_flight_step", "pre_tp_band", "early_phase_structure"],
        detail,
    )


def _mark_open_lot_scaled(pair: str, decision: ScaleDecision, now: datetime) -> None:
    reg = _load_json(OPEN_LOTS_PATH, {"schema": SCHEMA, "lots": {}})
    if not isinstance(reg, dict):
        reg = {"schema": SCHEMA, "lots": {}}
    lots = reg.setdefault("lots", {})
    lots[_norm_pair(pair)] = {
        "scaled": True,
        "scaled_at": _utc_iso(now),
        "held_usd_at_scale": decision.held_usd,
        "step_usd": decision.step_usd,
        "unrealized_r": decision.unrealized_r,
        "phase": decision.phase,
        "entry_ts": (decision.detail.get("lot") or {}).get("entry_ts"),
        "entry_price": (decision.detail.get("lot") or {}).get("entry_price")
        or decision.detail.get("entry_price"),
        "mark_at_scale": decision.detail.get("mark"),
        "status": "paper_open",
    }
    reg["updated_at"] = _utc_iso(now)
    _write_json(OPEN_LOTS_PATH, reg)


def _clear_open_lot(pair: str) -> None:
    reg = _load_json(OPEN_LOTS_PATH, {"lots": {}})
    if not isinstance(reg, dict):
        return
    lots = reg.get("lots") or {}
    if _norm_pair(pair) in lots:
        lots.pop(_norm_pair(pair), None)
        reg["lots"] = lots
        reg["updated_at"] = _utc_iso()
        _write_json(OPEN_LOTS_PATH, reg)


def _score_resolved_lots(cfg: Dict[str, Any], now: datetime) -> List[Dict[str, Any]]:
    """When a scaled paper lot's pair goes flat (SELL in ledger after scale), score CF."""
    reg = _load_json(OPEN_LOTS_PATH, {"lots": {}})
    lots = (reg.get("lots") if isinstance(reg, dict) else {}) or {}
    scored: List[Dict[str, Any]] = []
    fee = _f(cfg.get("fee_haircut_rt"), 0.0016)
    for pair, meta in list(lots.items()):
        if not isinstance(meta, dict) or not meta.get("scaled"):
            continue
        if meta.get("status") == "scored":
            continue
        scale_ts = _parse_ts(meta.get("scaled_at"))
        entry_px = _f(meta.get("entry_price"))
        mark_scale = _f(meta.get("mark_at_scale"))
        step = _f(meta.get("step_usd"), 75.0)
        held0 = _f(meta.get("held_usd_at_scale"), 75.0)
        # find first SELL after scale
        sell = None
        for t in _ledger_rows_for_pair(pair, limit=30):
            ts = _parse_ts(t.get("timestamp") or t.get("ts"))
            if not ts or not scale_ts or ts <= scale_ts:
                continue
            if str(t.get("side") or "").upper() != "SELL":
                continue
            sell = t
            break
        # still held?
        pos_map = {p["pair"]: p for p in load_live_positions()}
        still = pos_map.get(_norm_pair(pair))
        if still and _f(still.get("value_usd")) >= 20:
            # update paper mark-to-market only
            continue
        if not sell:
            # flat with no sell row — clear stale
            if not still or _f((still or {}).get("value_usd")) < 15:
                meta["status"] = "flat_no_sell_row"
                lots[pair] = meta
            continue

        exit_px = _f(sell.get("price") or sell.get("fill_price") or sell.get("exit_price"))
        if exit_px <= 0 and entry_px > 0:
            # pnl_pct path
            pnl = sell.get("pnl_pct")
            if pnl is not None:
                pv = _f(pnl)
                if abs(pv) > 1.5:
                    pv = pv / 100.0
                exit_px = entry_px * (1.0 + pv)
        if entry_px <= 0 or exit_px <= 0:
            continue

        # tryout-only path: original held through exit
        r_exit = (exit_px / entry_px) - 1.0
        tryout_net = r_exit - fee
        # scale path: original lot same r; added step from mark_at_scale → exit
        if mark_scale > 0:
            r_step = (exit_px / mark_scale) - 1.0
        else:
            r_step = r_exit
        # portfolio r on combined notional
        w0 = held0 / max(held0 + step, 1e-9)
        w1 = step / max(held0 + step, 1e-9)
        scale_net = w0 * (r_exit - fee) + w1 * (r_step - fee)
        excess = scale_net - tryout_net
        reason = str(sell.get("reason") or sell.get("exit_reason") or "")
        row = {
            "pair": pair,
            "scored_at": _utc_iso(now),
            "scale_at": meta.get("scaled_at"),
            "exit_ts": sell.get("timestamp") or sell.get("ts"),
            "exit_reason": reason,
            "entry_px": entry_px,
            "mark_at_scale": mark_scale,
            "exit_px": exit_px,
            "held0": held0,
            "step": step,
            "tryout_net_r": round(tryout_net, 6),
            "scale_net_r": round(scale_net, 6),
            "excess_r": round(excess, 6),
            "r_exit": round(r_exit, 6),
            "r_step": round(r_step, 6),
        }
        scored.append(row)
        meta["status"] = "scored"
        meta["score"] = row
        lots[pair] = meta
        _append_crumb({"kind": "score", **row})
    if isinstance(reg, dict):
        reg["lots"] = lots
        reg["updated_at"] = _utc_iso(now)
        _write_json(OPEN_LOTS_PATH, reg)
    return scored


def _load_score_history(limit: int = 200) -> List[Dict[str, Any]]:
    if not CRUMBS_PATH.exists():
        return []
    rows = []
    try:
        for line in CRUMBS_PATH.open():
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("kind") == "score":
                rows.append(o)
    except Exception:
        return []
    return rows[-limit:]


def _cf_summary(scores: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Dict[str, Any]:
    n = len(scores)
    if n == 0:
        return {
            "n": 0,
            "mean_excess_r": None,
            "mean_tryout_net_r": None,
            "mean_scale_net_r": None,
            "pct_scale_wins": None,
            "edge_class": "INSUFFICIENT_N",
            "plain": "No scored scale-up exits yet — collecting crumbs.",
        }
    ex = [_f(s.get("excess_r")) for s in scores]
    tnet = [_f(s.get("tryout_net_r")) for s in scores]
    snet = [_f(s.get("scale_net_r")) for s in scores]
    mean_ex = sum(ex) / n
    mean_t = sum(tnet) / n
    mean_s = sum(snet) / n
    win = sum(1 for x in ex if x > 0) / n
    bar = _f(cfg.get("cf_min_excess_pp"), 0.005)
    min_n = int(cfg.get("cf_min_scored") or 8)
    prefer = int(cfg.get("cf_prefer_scored") or 12)
    if n < min_n:
        edge = "INSUFFICIENT_N"
        plain = f"n={n}<{min_n} scored exits — keep shadow; no live."
    elif mean_ex >= bar and mean_s > mean_t:
        edge = "ATTENTION_ONLY_scale_helps"
        plain = (
            f"n={n} mean excess {mean_ex*100:.2f}pp ≥ {bar*100:.1f}pp bar — "
            "still ATTENTION_ONLY until Brad GO live_apply."
        )
        if n < prefer:
            plain += f" Prefer n≥{prefer}."
    else:
        edge = "NO_CLEAR_EDGE_or_hurts"
        plain = (
            f"n={n} mean excess {mean_ex*100:.2f}pp — scale-up not clearly better; "
            "do not live; redesign band/phase or drop."
        )
    return {
        "n": n,
        "mean_excess_r": round(mean_ex, 6),
        "mean_tryout_net_r": round(mean_t, 6),
        "mean_scale_net_r": round(mean_s, 6),
        "pct_scale_wins": round(win, 4),
        "edge_class": edge,
        "bar_excess_r": bar,
        "min_n": min_n,
        "plain": plain,
    }


def ensure_decision_artifact() -> Dict[str, Any]:
    if DECISION_PATH.exists():
        d = _load_json(DECISION_PATH, {})
        if isinstance(d, dict) and d.get("schema"):
            return d
    d = {
        "schema": "tryout_scale_up_brad_decision_v1",
        "as_of": _utc_iso(),
        "live_apply": False,
        "brad_go_shadow": True,
        "framing": "ride_the_wave — catch building tryout, one step-up, jump before break",
        "note": (
            "Shadow only. Mid-flight tryout scale-up is NOT post-TP graduation and NOT volume rank. "
            "Live adds require explicit Brad GO after CF bar."
        ),
        "cf_bar": {
            "min_scored": DEFAULTS["cf_min_scored"],
            "prefer_scored": DEFAULTS["cf_prefer_scored"],
            "min_mean_excess_r": DEFAULTS["cf_min_excess_pp"],
            "even_if_green": "ATTENTION_ONLY — no auto live_apply",
        },
    }
    _write_json(DECISION_PATH, d)
    return d


def write_report(payload: Dict[str, Any]) -> None:
    cf = payload.get("cf") or {}
    decs = payload.get("decisions") or []
    would = [d for d in decs if d.get("status") == "would_scale"]
    blocked = [d for d in decs if d.get("status") == "blocked"]
    lines = [
        "# Tryout scale-up shadow — ride the wave",
        "",
        f"**As of:** {payload.get('as_of')}",
        f"**Schema:** `{SCHEMA}`",
        f"**Live apply:** `{payload.get('live_apply')}` (hard false until Brad GO)",
        "",
        "## Intent",
        "",
        "Catch tryout while the wave is **building**; one mid-flight step-up; "
        "exit stack (trail/TP/dual-peak) still jumps before the break. "
        "Does **not** wait for tiny TP + lockout to “graduate.”",
        "",
        "## CF scoreboard",
        "",
        f"- n scored exits: **{cf.get('n')}**",
        f"- mean tryout-only net r: `{cf.get('mean_tryout_net_r')}`",
        f"- mean scale path net r: `{cf.get('mean_scale_net_r')}`",
        f"- mean excess (scale − tryout): `{cf.get('mean_excess_r')}`",
        f"- scale wins pct: `{cf.get('pct_scale_wins')}`",
        f"- edge class: **{cf.get('edge_class')}**",
        f"- plain: {cf.get('plain')}",
        "",
        "## This cycle",
        "",
        f"- open positions scanned: {payload.get('n_scanned')}",
        f"- would_scale: **{len(would)}**",
        f"- blocked (in band but gates): {len(blocked)}",
        "",
    ]
    if would:
        lines.append("### Would scale (paper)")
        lines.append("")
        for d in would:
            lines.append(
                f"- **{d.get('pair')}** held=${_f(d.get('held_usd')):.0f} "
                f"r={_f(d.get('unrealized_r'))*100:.2f}% step=${_f(d.get('step_usd')):.0f} "
                f"phase={d.get('phase')} struct={d.get('structure_ok')}"
            )
        lines.append("")
    if blocked:
        lines.append("### Blocked (why not yet)")
        lines.append("")
        for d in blocked[:12]:
            lines.append(
                f"- {d.get('pair')}: {', '.join(d.get('reasons') or [])}"
            )
        lines.append("")
    lines.extend(
        [
            "## Gates (shadow)",
            "",
            "- tryout-sized open seat (or tryout-tagged buy)",
            "- hold ≥ min_hold_hours",
            "- unrealized in [min_r, max_r] (pre-trail-arm band)",
            "- phase ignition/trend + structure_ok",
            "- one step only per lot",
            "- live_apply pinned false",
            "",
            "## Separations",
            "",
            "| This | Not that |",
            "|------|----------|",
            "| Mid-flight scale-up | first_fill post-close graduate_on_tp |",
            "| Pre-TP band add | post-TP 24h / H4 re-entry |",
            "| Structure×phase earn | volume/RVOL seat vote |",
            "| Shadow CF | live add |",
            "",
            f"State: `{LATEST_PATH}` · crumbs: `{CRUMBS_PATH}` · decision: `{DECISION_PATH}`",
            "",
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def run_cycle(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One shadow cycle: evaluate open tryouts, register would_scale, score exits."""
    cfg = load_cfg(overrides)
    now = _utc_now()
    decision = ensure_decision_artifact()
    positions = load_live_positions()
    decisions: List[ScaleDecision] = []

    for pos in positions:
        if _f(pos.get("value_usd")) < 15:
            continue
        d = evaluate_scale_up(pos, cfg, now=now)
        decisions.append(d)
        if d.status == "would_scale":
            _mark_open_lot_scaled(d.pair, d, now)
            _append_crumb(
                {
                    "kind": "would_scale",
                    "ts": _utc_iso(now),
                    "pair": d.pair,
                    "held_usd": d.held_usd,
                    "unrealized_r": d.unrealized_r,
                    "hold_hours": d.hold_hours,
                    "phase": d.phase,
                    "structure_ok": d.structure_ok,
                    "step_usd": d.step_usd,
                    "reasons": d.reasons,
                }
            )

    newly_scored = _score_resolved_lots(cfg, now)
    scores = _load_score_history()
    cf = _cf_summary(scores, cfg)

    payload = {
        "schema": SCHEMA,
        "as_of": _utc_iso(now),
        "live_apply": False,
        "brad_decision_live_apply": bool(decision.get("live_apply")),
        "framing": "ride_the_wave",
        "cfg": {
            k: cfg[k]
            for k in (
                "tryout_min_usd",
                "tryout_max_usd",
                "step_usd",
                "min_hold_hours",
                "min_unrealized_r",
                "max_unrealized_r",
                "require_phase_in",
                "require_structure_ok",
                "cf_min_scored",
                "cf_min_excess_pp",
            )
            if k in cfg
        },
        "n_scanned": len(decisions),
        "decisions": [d.to_dict() for d in decisions],
        "would_scale_pairs": [d.pair for d in decisions if d.status == "would_scale"],
        "newly_scored": newly_scored,
        "cf": cf,
        "open_lots_path": str(OPEN_LOTS_PATH),
        "note": (
            "Paper only. No orders. Scale-up earns capital into momentum before TP; "
            "exit automation still owns the jump before the break."
        ),
    }
    _write_json(LATEST_PATH, payload)
    write_report(payload)
    return payload


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Tryout scale-up shadow (ride the wave)")
    p.add_argument("--score-only", action="store_true", help="Only resolve/score open paper lots")
    args = p.parse_args(list(argv) if argv is not None else None)
    if args.score_only:
        cfg = load_cfg()
        now = _utc_now()
        scored = _score_resolved_lots(cfg, now)
        scores = _load_score_history()
        cf = _cf_summary(scores, cfg)
        print(json.dumps({"newly_scored": scored, "cf": cf}, indent=2, default=str))
        return 0
    out = run_cycle()
    print(
        json.dumps(
            {
                "as_of": out.get("as_of"),
                "would_scale": out.get("would_scale_pairs"),
                "cf": out.get("cf"),
                "n_scanned": out.get("n_scanned"),
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
