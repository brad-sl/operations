#!/usr/bin/env python3
"""Membership × sizing matrix SSOT — filterable law + live room.

Joins:
  • novelty class (sticky_core / liquid_core / graduated / novelty_*)
  • role law (ballast_core / preserve / tryout_shell / liquid_held)
  • regime add_risk factors (from regime_cash_policy — not duplicated)
  • live add-room (max_add / block_max / budgets)
  • tryout scale_path when a shell is open

Measure-only. No orders. Agent Q&A and ops validate against this board first.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from phase6.core.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

SCHEMA = "membership_sizing_matrix_v1"
CONFIG_PATH = PROJECT_ROOT / "config" / "membership_sizing_matrix.json"
LATEST_PATH = PROJECT_ROOT / "data" / "state" / "membership_sizing_matrix_latest.json"
REGIME_POLICY_PATH = PROJECT_ROOT / "config" / "regime_cash_policy.json"
REGIME_STATUS_PATH = PROJECT_ROOT / "data" / "state" / "regime_cash_status.json"

# Fallback if config missing
_DEFAULT_ROLE_LAW: Dict[str, Any] = {
    "ballast_core": {
        "scale_path": "add_risk_pyramid",
        "can_eject_scale_window": False,
        "first_fill_haircut": False,
        "membership_remove": "never",
        "kindling_eligible": False,
        "pairs": ["BTC-USD", "ETH-USD"],
    },
    "preserve_ballast": {
        "scale_path": "none",
        "can_eject_scale_window": False,
        "first_fill_haircut": False,
        "membership_remove": "never",
        "kindling_eligible": False,
        "pairs": ["PAXG-USD"],
    },
    "tryout_shell": {
        "scale_path": "kindling_once",
        "can_eject_scale_window": True,
        "first_fill_haircut": True,
        "membership_remove": "dust_only",
        "kindling_eligible": True,
    },
    "liquid_held": {
        "scale_path": "add_risk_pyramid",
        "can_eject_scale_window": False,
        "first_fill_haircut": True,
        "membership_remove": "m_gate",
        "kindling_eligible": False,
    },
    "cash_like": {
        "scale_path": "none",
        "can_eject_scale_window": False,
        "first_fill_haircut": False,
        "membership_remove": "never",
        "kindling_eligible": False,
        "pairs": ["USD-USD", "USDC-USD", "USDT-USD"],
    },
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def _norm_pair(pair: str) -> str:
    p = str(pair or "").strip().upper().replace("_", "-")
    if not p:
        return ""
    if "-" not in p:
        p = f"{p}-USD"
    return p


def _load_json(path: Path, default: Any = None) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("[MSM] load %s failed: %s", path, e)
    return default if default is not None else {}


def load_config() -> Dict[str, Any]:
    raw = _load_json(CONFIG_PATH, {})
    if not isinstance(raw, dict) or not raw:
        return {
            "schema": SCHEMA,
            "enabled": True,
            "role_law": dict(_DEFAULT_ROLE_LAW),
            "class_order": [
                "sticky_core",
                "liquid_core",
                "graduated",
                "novelty_restricted",
                "novelty_blocked",
            ],
        }
    if not isinstance(raw.get("role_law"), dict):
        raw["role_law"] = dict(_DEFAULT_ROLE_LAW)
    return raw


def _role_pair_sets(role_law: Dict[str, Any]) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    for role, law in (role_law or {}).items():
        if not isinstance(law, dict):
            continue
        pairs = {_norm_pair(p) for p in (law.get("pairs") or []) if p}
        out[str(role)] = pairs
    return out


def resolve_role(
    pair: str,
    *,
    class_: str,
    held_usd: float,
    has_tryout_lot: bool,
    role_law: Dict[str, Any],
) -> str:
    """Pick membership role for a pair (law, not vibes)."""
    pn = _norm_pair(pair)
    sets = _role_pair_sets(role_law)
    if pn in sets.get("cash_like", set()) or pn.split("-")[0] in ("USD", "USDC", "USDT"):
        return "cash_like"
    if pn in sets.get("preserve_ballast", set()) or class_ == "sticky_core" and "PAXG" in pn:
        if "PAXG" in pn:
            return "preserve_ballast"
    if pn in sets.get("ballast_core", set()) or (
        class_ == "sticky_core" and pn in ("BTC-USD", "ETH-USD", "BTC-USDC", "ETH-USDC")
    ):
        return "ballast_core"
    if has_tryout_lot and held_usd >= 12.0:
        return "tryout_shell"
    if held_usd >= 15.0 and class_ in ("liquid_core", "graduated", "sticky_core"):
        if class_ == "sticky_core" and "PAXG" in pn:
            return "preserve_ballast"
        if class_ == "sticky_core":
            return "ballast_core"
        return "liquid_held"
    if has_tryout_lot:
        return "tryout_shell"
    # Flat basket seat — still liquid path for future tryout/add
    if class_ in ("liquid_core", "graduated"):
        return "liquid_held"
    if class_ in ("novelty_restricted", "novelty_blocked"):
        return "tryout_shell" if has_tryout_lot else "liquid_held"
    return "liquid_held"


def role_law_for(role: str, role_law: Dict[str, Any]) -> Dict[str, Any]:
    law = (role_law or {}).get(role) or _DEFAULT_ROLE_LAW.get(role) or {}
    return dict(law) if isinstance(law, dict) else {}


def load_regime_sheet() -> Dict[str, Any]:
    """Regime × add_risk factors — single sheet for instant lookup."""
    pol = _load_json(REGIME_POLICY_PATH, {})
    status = _load_json(REGIME_STATUS_PATH, {})
    add = pol.get("add_risk") if isinstance(pol.get("add_risk"), dict) else {}
    by = add.get("by_regime") if isinstance(add.get("by_regime"), dict) else {}
    live_reg = str(status.get("regime") or status.get("regime_layer") or "unknown")
    rows: List[Dict[str, Any]] = []
    for name in ("bull", "flat", "transition", "soft_down", "bear", "unknown"):
        r = by.get(name) if isinstance(by.get(name), dict) else {}
        rows.append(
            {
                "regime": name,
                "live": name == live_reg or (
                    name == "flat" and live_reg.startswith("flat")
                ),
                "allow_pyramid": bool(r.get("allow_pyramid", name in ("bull", "flat"))),
                "k_profit": _f(r.get("k_profit"), 0.0),
                "h_add": _f(r.get("h_add"), 0.0),
                "H_book": _f(r.get("H_book"), 0.0),
                "target_pair_weight": _f(r.get("target_pair_weight"), 0.12),
                "cash_frac": _f(r.get("cash_frac"), 0.0),
            }
        )
    entry = status.get("entry") if isinstance(status.get("entry"), dict) else {}
    return {
        "live_regime": live_reg,
        "strategy_mode": status.get("strategy_mode"),
        "allow_new_buys": status.get("allow_new_buys"),
        "target_max_util_pct": status.get("target_max_util_pct"),
        "rebalance_cap_usd": status.get("rebalance_cap_usd"),
        "min_cash_reserve_pct": status.get("min_cash_reserve_pct"),
        "entry_floors": {
            "min_sentiment": entry.get("min_sentiment"),
            "min_sentiment_new_pair": entry.get("min_sentiment_new_pair"),
            "max_rsi": entry.get("max_rsi"),
        },
        "rows": rows,
        "live_add_risk": next((x for x in rows if x.get("live")), rows[0] if rows else {}),
    }


def _class_for_pair(pair: str) -> Dict[str, Any]:
    try:
        from phase6.core.novelty_class_gate import evaluate_pair_novelty

        v = evaluate_pair_novelty(pair)
        return {
            "class": getattr(v, "class_", None) or getattr(v, "class", None) or "unknown",
            "blocked": bool(getattr(v, "blocked", False)),
            "reasons": list(getattr(v, "reasons", None) or [])[:6],
        }
    except Exception as e:
        logger.warning("[MSM] novelty class fail %s: %s", pair, e)
        # sticky fallback
        pn = _norm_pair(pair)
        if pn in ("BTC-USD", "ETH-USD", "PAXG-USD"):
            return {"class": "sticky_core", "blocked": False, "reasons": ["fallback_sticky"]}
        return {"class": "liquid_core", "blocked": False, "reasons": ["fallback_liquid", str(e)[:40]]}


def _open_tryout_lots() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    try:
        from phase6.core import tryout_seat_ledger as tsl

        path = getattr(tsl, "OPEN_LOTS_PATH", PROJECT_ROOT / "data/state/tryout_scale_up_open_lots.json")
        reg = _load_json(Path(path), {})
        lots = reg.get("lots") if isinstance(reg, dict) else None
        if isinstance(lots, dict):
            for k, lot in lots.items():
                if not isinstance(lot, dict):
                    continue
                st = str(lot.get("status") or lot.get("state") or "open").lower()
                if st in ("closed", "ejected", "done", "ghost"):
                    continue
                pn = _norm_pair(lot.get("pair") or k)
                if pn:
                    out[pn] = lot
        elif isinstance(lots, list):
            for lot in lots:
                if not isinstance(lot, dict):
                    continue
                st = str(lot.get("status") or "open").lower()
                if st in ("closed", "ejected", "done", "ghost"):
                    continue
                pn = _norm_pair(lot.get("pair") or "")
                if pn:
                    out[pn] = lot
    except Exception as e:
        logger.warning("[MSM] open lots: %s", e)
    return out


def _scale_path_for(pair: str, lot: Optional[Dict[str, Any]], held: float) -> Dict[str, Any]:
    try:
        from phase6.core.tryout_seat_ledger import classify_scale_path

        return classify_scale_path(pair=pair, lot=lot, held_usd=held)
    except Exception:
        if lot:
            return {"scale_path": "open", "scale_path_label": "open"}
        return {"scale_path": "none", "scale_path_label": "none"}


def _binding_budget(budgets: Optional[Dict[str, Any]], max_add: Any) -> str:
    if max_add is None:
        return "n/a"
    try:
        if float(max_add) > 1e-9:
            return "ok"
    except (TypeError, ValueError):
        return "n/a"
    b = budgets or {}
    # smallest positive-or-zero binding clip
    candidates = []
    for k in ("cash_slice", "profit", "heat", "book_left", "exposure_room", "rebalance_cap"):
        v = b.get(k)
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        candidates.append((fv, k))
    if not candidates:
        return str((budgets or {}).get("detail_reason") or "capped_to_zero")
    candidates.sort(key=lambda x: x[0])
    # prefer zero/near-zero as binding
    for fv, k in candidates:
        if fv <= 1e-6:
            return k
    return candidates[0][1]


def check_inconsistencies(row: Dict[str, Any]) -> List[str]:
    """Machine checks — policy drift detectors."""
    bad: List[str] = []
    role = str(row.get("role") or "")
    sp = str(row.get("scale_path_law") or "")
    class_ = str(row.get("class") or "")
    kindling_live = str(row.get("kindling_scale_path") or "none").lower()

    if role in ("ballast_core", "preserve_ballast") and sp == "kindling_once":
        bad.append("sticky_or_ballast_must_not_kindling")
    if role == "preserve_ballast" and sp not in ("none",):
        if sp == "kindling_once":
            bad.append("preserve_must_not_kindling")
    if sp == "kindling_once" and role in ("ballast_core", "preserve_ballast", "cash_like"):
        bad.append("kindling_requires_non_ballast")
    if row.get("can_eject_scale_window") and role in ("ballast_core", "preserve_ballast"):
        bad.append("scale_window_eject_false_for_ballast")
    if class_ == "sticky_core" and row.get("first_fill_haircut") is True and role != "tryout_shell":
        # sticky should be exempt unless somehow tryout (should never)
        bad.append("first_fill_exempt_matches_sticky")
    if role in ("ballast_core", "preserve_ballast") and kindling_live not in (
        "none",
        "",
        "n/a",
    ):
        if kindling_live in ("open", "pending", "live", "dead", "ghost"):
            bad.append("sticky_live_kindling_path")
    return bad


def build_matrix(
    *,
    pairs: Optional[Sequence[str]] = None,
    include_universe_classes: bool = False,
    persist: bool = True,
) -> Dict[str, Any]:
    """Compile filterable matrix. Default rows = active basket (+ held extras)."""
    cfg = load_config()
    role_law = cfg.get("role_law") or _DEFAULT_ROLE_LAW
    regime_sheet = load_regime_sheet()
    live_ar = regime_sheet.get("live_add_risk") or {}

    try:
        from phase6.core.paths import load_trading_basket

        basket = [_norm_pair(p) for p in (pairs or list(load_trading_basket()) or [])]
    except Exception:
        basket = [_norm_pair(p) for p in (pairs or [])]

    add_room: Dict[str, Any] = {}
    try:
        from phase6.core.add_risk_sizer import load_add_room_by_pair_for_dashboard

        add_room = load_add_room_by_pair_for_dashboard() or {}
    except Exception as e:
        logger.warning("[MSM] add_room: %s", e)
        add_room = {}

    by_pair_room = add_room.get("by_pair") if isinstance(add_room.get("by_pair"), dict) else {}
    open_lots = _open_tryout_lots()

    # held map from add_room positions
    held_map: Dict[str, float] = {}
    for pn, meta in by_pair_room.items():
        if isinstance(meta, dict):
            held_map[_norm_pair(pn)] = _f(meta.get("position_usd"))

    # ensure basket pairs present even if flat
    pair_set: List[str] = []
    seen: Set[str] = set()
    for p in basket + list(held_map.keys()) + list(open_lots.keys()):
        pn = _norm_pair(p)
        if pn and pn not in seen:
            seen.add(pn)
            pair_set.append(pn)

    if include_universe_classes:
        try:
            nov = _load_json(
                PROJECT_ROOT / "data/state/novelty_class_latest.json", {}
            )
            buckets = nov.get("buckets") if isinstance(nov, dict) else {}
            if isinstance(buckets, dict):
                for _bk, items in buckets.items():
                    if not isinstance(items, list):
                        continue
                    for it in items:
                        if isinstance(it, dict):
                            pn = _norm_pair(it.get("pair") or "")
                            if pn and pn not in seen:
                                seen.add(pn)
                                pair_set.append(pn)
        except Exception:
            pass

    rows: List[Dict[str, Any]] = []
    inconsistencies_all: List[Dict[str, Any]] = []

    for pn in pair_set:
        cls_info = _class_for_pair(pn)
        class_ = str(cls_info.get("class") or "unknown")
        held = _f(held_map.get(pn))
        lot = open_lots.get(pn)
        has_lot = lot is not None
        role = resolve_role(
            pn,
            class_=class_,
            held_usd=held,
            has_tryout_lot=has_lot,
            role_law=role_law,
        )
        law = role_law_for(role, role_law)
        room = by_pair_room.get(pn) if isinstance(by_pair_room.get(pn), dict) else {}
        sp_live = _scale_path_for(pn, lot, held) if has_lot else {"scale_path": "none"}
        max_add = room.get("max_add_usd")
        budgets = room.get("budgets") if isinstance(room.get("budgets"), dict) else {}
        binding = _binding_budget(budgets, max_add)
        if room.get("detail_reason") and _f(max_add) <= 0:
            # prefer sizer reason when more specific
            dr = str(room.get("detail_reason") or "")
            if dr and dr not in ("ok",):
                binding = f"{binding}|{dr}" if binding not in (dr, "ok") else dr

        target_w = _f(
            room.get("target_pair_weight"),
            _f(live_ar.get("target_pair_weight"), 0.18),
        )
        equity = _f(add_room.get("equity_usd"), 0.0)
        target_usd = round(equity * target_w, 2) if equity > 0 else None

        row: Dict[str, Any] = {
            "pair": pn,
            "in_basket": pn in basket,
            "class": class_,
            "class_blocked": bool(cls_info.get("blocked")),
            "class_reasons": cls_info.get("reasons") or [],
            "role": role,
            "scale_path_law": str(law.get("scale_path") or "none"),
            "can_eject_scale_window": bool(law.get("can_eject_scale_window")),
            "first_fill_haircut": bool(law.get("first_fill_haircut")),
            "membership_remove": str(law.get("membership_remove") or "never"),
            "kindling_eligible": bool(law.get("kindling_eligible")),
            "held_usd": round(held, 2),
            "weight_pct": room.get("weight_pct"),
            "open_upnl_usd": room.get("open_upnl_usd"),
            "regime": add_room.get("regime") or regime_sheet.get("live_regime"),
            "pyramid_allowed": bool(live_ar.get("allow_pyramid")),
            "target_pair_weight": target_w,
            "target_pair_usd": target_usd,
            "max_add_usd": max_add,
            "block_max": bool(room.get("block_max")) if room else (held >= 15.0 and True),
            "min_move_usd": room.get("min_move_usd") or add_room.get("min_move_usd"),
            "block_reason": binding if room else ("no_stack" if held < 15 else "unknown"),
            "detail_reason": room.get("detail_reason"),
            "budgets": budgets,
            "stop_gap_pct": room.get("stop_gap_pct"),
            "kindling_scale_path": sp_live.get("scale_path") or sp_live.get("scale_path_label") or "none",
            "has_tryout_lot": has_lot,
            "add_risk_enabled": bool(add_room.get("enabled", True)),
        }
        # block_max for flat names without room row
        if not room:
            row["block_max"] = False
            row["block_reason"] = "flat_no_stack"
            row["max_add_usd"] = None

        bad = check_inconsistencies(row)
        row["inconsistencies"] = bad
        if bad:
            inconsistencies_all.append({"pair": pn, "issues": bad})
        rows.append(row)

    # sort: inconsistencies first, then held desc, then pair
    rows.sort(
        key=lambda r: (
            0 if r.get("inconsistencies") else 1,
            0 if r.get("in_basket") else 1,
            -_f(r.get("held_usd")),
            str(r.get("pair") or ""),
        )
    )

    counts = {
        "n_rows": len(rows),
        "n_basket": sum(1 for r in rows if r.get("in_basket")),
        "n_block_max": sum(1 for r in rows if r.get("block_max")),
        "n_kindling": sum(1 for r in rows if r.get("scale_path_law") == "kindling_once"),
        "n_inconsistent": len(inconsistencies_all),
        "by_role": {},
        "by_class": {},
    }
    for r in rows:
        role = str(r.get("role") or "?")
        cl = str(r.get("class") or "?")
        counts["by_role"][role] = counts["by_role"].get(role, 0) + 1
        counts["by_class"][cl] = counts["by_class"].get(cl, 0) + 1

    plain = (
        f"regime={regime_sheet.get('live_regime')} · basket={counts['n_basket']} · "
        f"block-max={counts['n_block_max']} · inconsistent={counts['n_inconsistent']} · "
        f"pyramid={'on' if live_ar.get('allow_pyramid') else 'off'}"
    )

    out: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": _utc_iso(),
        "enabled": bool(cfg.get("enabled", True)),
        "brad_go": cfg.get("brad_go"),
        "plain_english": plain,
        "regime_sheet": regime_sheet,
        "add_room_meta": {
            "regime": add_room.get("regime"),
            "equity_usd": add_room.get("equity_usd"),
            "cash_usd": add_room.get("cash_usd"),
            "min_move_usd": add_room.get("min_move_usd"),
            "target_pair_weight": add_room.get("target_pair_weight"),
            "max_blocked_pairs": add_room.get("max_blocked_pairs") or [],
            "enabled": add_room.get("enabled"),
        },
        "role_law": {
            k: {
                "scale_path": v.get("scale_path"),
                "can_eject_scale_window": v.get("can_eject_scale_window"),
                "first_fill_haircut": v.get("first_fill_haircut"),
                "membership_remove": v.get("membership_remove"),
                "kindling_eligible": v.get("kindling_eligible"),
            }
            for k, v in (role_law or {}).items()
            if isinstance(v, dict)
        },
        "counts": counts,
        "inconsistencies": inconsistencies_all,
        "rows": rows,
        "filters_help": {
            "class": "sticky_core|liquid_core|graduated|novelty_restricted|novelty_blocked",
            "role": "ballast_core|preserve_ballast|tryout_shell|liquid_held|cash_like",
            "scale_path_law": "none|kindling_once|add_risk_pyramid",
            "block_max": "true|false",
            "inconsistent": "true",
        },
        "notation": {
            "scale_path_law": "What *may* grow the bag (product lane)",
            "kindling_scale_path": "Live tryout shell state if any (open|pending|live|dead|ghost|none)",
            "max_add_usd": "Live factor add-risk ceiling for existing stack; 0 = ·block-max",
            "block_reason": "Binding budget or sizer reason when max_add=0",
            "membership_remove": "never|dust_only|m_gate — who can leave the roster",
            "pyramid_allowed": "Regime allows adds into existing stacks",
        },
    }

    if persist:
        try:
            LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
            LATEST_PATH.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.warning("[MSM] persist failed: %s", e)
            out["persist_error"] = str(e)

    return out


def filter_rows(
    matrix: Dict[str, Any],
    *,
    pair: Optional[str] = None,
    class_: Optional[str] = None,
    role: Optional[str] = None,
    scale_path: Optional[str] = None,
    block_max: Optional[bool] = None,
    inconsistent_only: bool = False,
    in_basket: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    rows = list(matrix.get("rows") or [])
    if pair:
        pn = _norm_pair(pair)
        rows = [r for r in rows if r.get("pair") == pn]
    if class_:
        rows = [r for r in rows if str(r.get("class")) == class_]
    if role:
        rows = [r for r in rows if str(r.get("role")) == role]
    if scale_path:
        rows = [r for r in rows if str(r.get("scale_path_law")) == scale_path]
    if block_max is not None:
        rows = [r for r in rows if bool(r.get("block_max")) is bool(block_max)]
    if inconsistent_only:
        rows = [r for r in rows if r.get("inconsistencies")]
    if in_basket is not None:
        rows = [r for r in rows if bool(r.get("in_basket")) is bool(in_basket)]
    return rows


def pair_card(pair: str, matrix: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One-pair instant answer (agent path)."""
    m = matrix or build_matrix(persist=False)
    rows = filter_rows(m, pair=pair)
    if not rows:
        return {
            "pair": _norm_pair(pair),
            "found": False,
            "plain_english": f"{pair}: not on matrix (not basket/held)",
            "regime_sheet_live": (m.get("regime_sheet") or {}).get("live_add_risk"),
        }
    r = rows[0]
    sp = r.get("scale_path_law")
    how = {
        "none": "Does not scale via tryout or add-risk ladder.",
        "kindling_once": "Tryout timed option — one +$ step if kindling bar clears; else eject.",
        "add_risk_pyramid": "Factor add-risk into existing stack under regime budgets.",
    }.get(str(sp), str(sp))
    plain = (
        f"{r['pair']} · class={r.get('class')} · role={r.get('role')} · "
        f"scale={sp} · held=${r.get('held_usd')} · max_add=${r.get('max_add_usd')} · "
        f"block={r.get('block_reason')} · {how}"
    )
    return {
        "pair": r["pair"],
        "found": True,
        "plain_english": plain,
        "how_it_scales": how,
        "row": r,
        "regime_live": (m.get("regime_sheet") or {}).get("live_add_risk"),
        "notation": m.get("notation"),
    }


def load_latest() -> Dict[str, Any]:
    raw = _load_json(LATEST_PATH, {})
    return raw if isinstance(raw, dict) else {}
