"""First-fill probation — no-history adds get a small tryout seat.

After discovery/dud screens and miss-fire probation, *new* names still have no
realized path. This layer does not block them; it:
  • haircuts BUY notional (tryout size)
  • caps concurrent first-fill open seats
  • tags actions for ledger/dash
  • graduates after enough clean contact (or miss-fire blocks re-entry)

Does not place orders itself. No auto-promote.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from phase6.core.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

SCHEMA = "first_fill_probation_v1"
LATEST_PATH = PROJECT_ROOT / "data/state/first_fill_probation_latest.json"
LIVE_STATE = PROJECT_ROOT / "data/state/phase6_live_state.json"

# Defaults — scout-class tryout, not full seat
DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "size_mult": 0.40,  # fraction of proposed BUY
    "equity_frac_cap": 0.08,  # max tryout ≤ 8% equity
    "abs_cap_usd": 150.0,  # hard ceiling on first fill
    "min_move_usd": 40.0,  # below this → drop (dust)
    "max_open_first_fill_seats": 2,
    "min_holding_usd": 15.0,  # already held above this → not first fill
    # graduation (off this filter once earned)
    "graduate_min_rt": 2,  # ≥2 closed RTs and not miss-fire blocked
    "graduate_on_tp": True,  # or ≥1 TP/rotation green
    "sticky_exempt": ("BTC-USD", "ETH-USD", "PAXG-USD"),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
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


def _load_cfg(config_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg: Dict[str, Any] = dict(DEFAULTS)
    # trading config risk_management.first_fill_probation
    try:
        path = PROJECT_ROOT / "config/trading_config_phase6.json"
        raw: Any = json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        raw = {}
    block: Dict[str, Any] = {}
    if isinstance(raw, dict):
        rm = raw.get("risk_management")
        if isinstance(rm, dict):
            ff = rm.get("first_fill_probation")
            if isinstance(ff, dict):
                block.update(ff)
    if isinstance(config_dict, dict):
        rm2 = config_dict.get("risk_management")
        if isinstance(rm2, dict):
            ff2 = rm2.get("first_fill_probation")
            if isinstance(ff2, dict):
                block.update(ff2)
        top = config_dict.get("first_fill_probation")
        if isinstance(top, dict):
            block.update(top)
    for k, v in block.items():
        if v is not None:
            cfg[k] = v
    return cfg


@dataclass
class FirstFillDecision:
    pair: str
    status: str  # pass | haircut | drop | skip_not_first | skip_disabled | skip_sticky | seat_cap
    proposed_usd: float
    final_usd: float
    reasons: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _pair_stats_map():
    try:
        from phase6.core.missfire_probation import compute_pair_stats

        return compute_pair_stats()
    except Exception:
        return {}


def is_first_fill_candidate(
    pair: str,
    *,
    position_usd: float = 0.0,
    stats_map: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """True when pair has no graduated history and is not sticky / already seated."""
    c = cfg or DEFAULTS
    p = _norm_pair(pair)
    reasons: List[str] = []
    detail: Dict[str, Any] = {}
    sticky = {_norm_pair(x) for x in (c.get("sticky_exempt") or DEFAULTS["sticky_exempt"])}
    if p in sticky:
        return False, ["sticky_exempt"], detail

    min_h = _f(c.get("min_holding_usd"), 15.0)
    if _f(position_usd) >= min_h:
        return False, ["already_seated"], {"position_usd": _f(position_usd)}

    smap = stats_map if stats_map is not None else _pair_stats_map()
    st = smap.get(p) if isinstance(smap, dict) else None
    # miss-fire blocked pairs should not get a tryout via this path (buy gate handles)
    try:
        from phase6.core.missfire_probation import evaluate_pair_missfire

        mf = evaluate_pair_missfire(p, stats_map=smap if smap else None, enforce=True)
        detail["missfire"] = mf.to_dict()
        if mf.blocked:
            return False, ["missfire_blocked"], detail
    except Exception:
        pass

    if st is None or getattr(st, "n_rt", 0) <= 0:
        reasons.append("no_ledger_history")
        return True, reasons, detail

    n_rt = int(getattr(st, "n_rt", 0) or 0)
    n_tp = int(getattr(st, "n_tp_or_rot", 0) or 0)
    detail["n_rt"] = n_rt
    detail["n_tp"] = n_tp
    detail["net"] = getattr(st, "net_pnl", None)

    # graduated?
    if bool(c.get("graduate_on_tp", True)) and n_tp >= 1:
        return False, ["graduated_tp"], detail
    if n_rt >= int(c.get("graduate_min_rt") or 2):
        return False, ["graduated_rt"], detail

    # has history but not graduated — still tryout-sized on *new* empty seat
    reasons.append("ungraduated_history")
    return True, reasons, detail


def size_first_fill(
    *,
    pair: str,
    proposed_usd: float,
    equity_usd: float,
    cfg: Optional[Dict[str, Any]] = None,
    why: Optional[Sequence[str]] = None,
) -> FirstFillDecision:
    c = cfg or DEFAULTS
    p = _norm_pair(pair)
    prop = max(0.0, _f(proposed_usd))
    if not bool(c.get("enabled", True)):
        return FirstFillDecision(p, "skip_disabled", prop, prop, ["disabled"])

    mult = max(0.05, min(1.0, _f(c.get("size_mult"), 0.40)))
    eq_cap = max(0.0, _f(equity_usd) * _f(c.get("equity_frac_cap"), 0.08))
    abs_cap = max(0.0, _f(c.get("abs_cap_usd"), 150.0))
    min_move = max(0.0, _f(c.get("min_move_usd"), 40.0))

    raw = prop * mult
    final = min(raw, eq_cap if eq_cap > 0 else raw, abs_cap if abs_cap > 0 else raw)
    reasons = list(why or ["first_fill"])
    reasons.append(f"size_mult×{mult:.2f}")
    detail = {
        "raw_haircut": round(raw, 2),
        "equity_cap": round(eq_cap, 2),
        "abs_cap": abs_cap,
        "equity": round(_f(equity_usd), 2),
    }
    if final + 1e-9 < min_move:
        reasons.append(f"below_min_move ${min_move:.0f}")
        return FirstFillDecision(p, "drop", prop, 0.0, reasons, detail)
    if final + 1e-6 < prop:
        reasons.append(f"haircut ${prop:.0f}→${final:.0f}")
        return FirstFillDecision(p, "haircut", prop, round(final, 2), reasons, detail)
    return FirstFillDecision(p, "pass", prop, prop, reasons + ["no_clip_needed"], detail)


def _positions_and_equity(runner: Any = None) -> Tuple[Dict[str, float], float]:
    positions: Dict[str, float] = {}
    equity = 0.0
    if runner is not None:
        try:
            for pair, meta in (getattr(runner, "positions", None) or {}).items():
                if isinstance(meta, dict):
                    positions[_norm_pair(pair)] = _f(meta.get("value") or meta.get("value_usd"))
                else:
                    positions[_norm_pair(pair)] = _f(meta)
            equity = _f(getattr(runner, "equity_usd", None) or getattr(runner, "total_usd", None))
        except Exception:
            pass
    if equity <= 0 or not positions:
        try:
            if LIVE_STATE.exists():
                live = json.loads(LIVE_STATE.read_text())
                equity = _f(live.get("total_usd") or live.get("equity_usd"), equity)
                for row in live.get("positions") or []:
                    if not isinstance(row, dict):
                        continue
                    pair = _norm_pair(str(row.get("pair") or ""))
                    if pair:
                        positions[pair] = _f(row.get("value_usd") or row.get("value"))
        except Exception:
            pass
    return positions, equity


def count_open_first_fill_seats(
    positions: Dict[str, float],
    *,
    stats_map: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> List[str]:
    c = cfg or DEFAULTS
    min_h = _f(c.get("min_holding_usd"), 15.0)
    smap = stats_map if stats_map is not None else _pair_stats_map()
    open_ff: List[str] = []
    for pair, usd in positions.items():
        if _f(usd) < min_h:
            continue
        # seated with no graduation yet counts as first-fill seat
        is_ff, why, _ = is_first_fill_candidate(
            pair, position_usd=0.0, stats_map=smap, cfg=c
        )
        # already seated — check graduation only
        p = _norm_pair(pair)
        sticky = {_norm_pair(x) for x in (c.get("sticky_exempt") or ())}
        if p in sticky:
            continue
        st = smap.get(p) if isinstance(smap, dict) else None
        if st is None or getattr(st, "n_rt", 0) <= 0:
            open_ff.append(p)
            continue
        n_rt = int(getattr(st, "n_rt", 0) or 0)
        n_tp = int(getattr(st, "n_tp_or_rot", 0) or 0)
        if bool(c.get("graduate_on_tp", True)) and n_tp >= 1:
            continue
        if n_rt >= int(c.get("graduate_min_rt") or 2):
            continue
        open_ff.append(p)
    return open_ff


def filter_trade_plan_first_fill(runner: Any, plan: Any) -> Any:
    """Haircut/drop BUY first fills; enforce max concurrent tryout seats."""
    if plan is None or not getattr(plan, "actions", None):
        return plan
    cfg = _load_cfg(getattr(runner, "config_dict", None))
    if not bool(cfg.get("enabled", True)):
        return plan

    positions, equity = _positions_and_equity(runner)
    smap = _pair_stats_map()
    open_ff = count_open_first_fill_seats(positions, stats_map=smap, cfg=cfg)
    max_seats = int(cfg.get("max_open_first_fill_seats") or 2)
    seats_left = max(0, max_seats - len(open_ff))

    decisions: List[FirstFillDecision] = []
    new_actions: List[Dict[str, Any]] = []
    new_first_fills_this_plan = 0

    for a in list(plan.actions):
        action = str(a.get("action") or a.get("side") or "").upper()
        pair = a.get("pair")
        if action != "BUY" or not pair:
            new_actions.append(a)
            continue

        p = _norm_pair(str(pair))
        pos = _f(positions.get(p))
        is_ff, why, detail = is_first_fill_candidate(
            p, position_usd=pos, stats_map=smap, cfg=cfg
        )
        if not is_ff:
            proposed0 = _f(a.get("usd") if a.get("usd") is not None else a.get("usd_amount"))
            # Defense-in-depth: miss-fire blocked names must not ride through this filter
            if any("missfire" in str(w) for w in why):
                dec = FirstFillDecision(
                    p, "drop", proposed0, 0.0, why + ["first_fill_drop_missfire"], detail
                )
                decisions.append(dec)
                logger.info("[FIRST-FILL] drop missfire %s reasons=%s", p, why)
                continue
            dec = FirstFillDecision(
                p, "skip_not_first", proposed0, proposed0, why, detail
            )
            decisions.append(dec)
            new_actions.append(a)
            continue

        proposed = _f(a.get("usd") if a.get("usd") is not None else a.get("usd_amount"))
        # seat cap: only counts when opening a brand-new bag (pos ~ 0)
        if pos < _f(cfg.get("min_holding_usd"), 15.0):
            if seats_left - new_first_fills_this_plan <= 0:
                dec = FirstFillDecision(
                    p,
                    "seat_cap",
                    proposed,
                    0.0,
                    why + [f"max_open_first_fill_seats={max_seats}", f"open={open_ff}"],
                    detail,
                )
                decisions.append(dec)
                logger.info("[FIRST-FILL] seat_cap drop %s open=%s", p, open_ff)
                continue

        dec = size_first_fill(
            pair=p, proposed_usd=proposed, equity_usd=equity, cfg=cfg, why=why
        )
        dec.detail.update(detail)
        decisions.append(dec)

        if dec.status == "drop" or dec.final_usd <= 0:
            logger.info("[FIRST-FILL] drop %s proposed=$%.2f reasons=%s", p, proposed, dec.reasons)
            continue

        a = dict(a)
        a["usd"] = dec.final_usd
        if "usd_amount" in a:
            a["usd_amount"] = dec.final_usd
        a["first_fill_probation"] = True
        a["first_fill_from"] = proposed
        a["first_fill_status"] = dec.status
        a["reason"] = (str(a.get("reason") or "") + "|first_fill_tryout").strip("|")
        if dec.status == "haircut":
            logger.info(
                "[FIRST-FILL] haircut %s $%.2f → $%.2f reasons=%s",
                p,
                proposed,
                dec.final_usd,
                dec.reasons,
            )
        if pos < _f(cfg.get("min_holding_usd"), 15.0):
            new_first_fills_this_plan += 1
        new_actions.append(a)

    plan.actions = new_actions
    try:
        plan.first_fill_decisions = [d.to_dict() for d in decisions]  # type: ignore[attr-defined]
    except Exception:
        pass

    # persist board
    try:
        board = {
            "schema": SCHEMA,
            "as_of": _utc_now().isoformat(),
            "enabled": True,
            "open_first_fill_seats": open_ff,
            "max_open": max_seats,
            "seats_left_before_plan": seats_left,
            "equity_usd": equity,
            "cfg": {k: cfg[k] for k in (
                "size_mult", "equity_frac_cap", "abs_cap_usd", "min_move_usd",
                "max_open_first_fill_seats", "graduate_min_rt", "graduate_on_tp",
            ) if k in cfg},
            "decisions": [d.to_dict() for d in decisions],
        }
        LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        LATEST_PATH.write_text(json.dumps(board, indent=2) + "\n")
    except Exception:
        pass
    return plan


def tag_promote_add(add_pair: str) -> Dict[str, Any]:
    """For promote script: annotate whether ADD starts under first-fill probation."""
    smap = _pair_stats_map()
    is_ff, why, detail = is_first_fill_candidate(add_pair, position_usd=0.0, stats_map=smap)
    return {
        "pair": _norm_pair(add_pair),
        "first_fill_probation": bool(is_ff),
        "reasons": why,
        "detail": detail,
        "note": (
            "Promote is membership only; first live BUY will be tryout-sized "
            "via filter_trade_plan_first_fill."
            if is_ff
            else "ADD not under first-fill (sticky/graduated/missfire)."
        ),
    }


def main() -> int:
    cfg = _load_cfg()
    positions, equity = _positions_and_equity(None)
    smap = _pair_stats_map()
    open_ff = count_open_first_fill_seats(positions, stats_map=smap, cfg=cfg)
    print("first_fill cfg", {k: cfg[k] for k in ("size_mult", "equity_frac_cap", "abs_cap_usd", "max_open_first_fill_seats")})
    print("equity", equity, "open_first_fill_seats", open_ff)
    for p in ("SKR-USD", "TRUMP-USD", "PUMP-USD", "RAVE-USD", "BTC-USD", "PENGU-USD", "SOL-USD"):
        is_ff, why, det = is_first_fill_candidate(p, position_usd=positions.get(p, 0.0), stats_map=smap, cfg=cfg)
        dec = size_first_fill(pair=p, proposed_usd=400.0, equity_usd=equity or 2300.0, cfg=cfg, why=why)
        print(f"{p:12} first_fill={is_ff} why={why[:2]} size={dec.status} $400→${dec.final_usd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
