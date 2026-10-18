#!/usr/bin/env python3
"""
§5 SL width would-arm shadow (MEASURE_ONLY).

Implements policy sketch from config/sl_width_arming_policy.json:
- W1 default 8%
- W2 3% only on dead unproven shells (≤~$30, not core, weak MFE, held≥4h)
- W3 never tighten after green (MFE≥2% / trail proof / dwell graduated)

Logs would_arm_3pct vs would_arm_8pct.
When policy.live_apply + W2 rule match, resolve_live_sl_pct may return 3% for
dead unproven shells only. Core/green/graduated always stay on NEEDLE-04 8% band.
No global stop_loss_pct rewrite.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from phase6.core.paths import CONFIG_DIR, PROJECT_ROOT, STATE_DIR

logger = logging.getLogger(__name__)

SCHEMA = "sl_width_would_arm_shadow_v1"
CONFIG_PATH = CONFIG_DIR / "sl_width_arming_policy.json"
LATEST = STATE_DIR / "sl_width_would_arm_latest.json"
HISTORY = STATE_DIR / "sl_width_would_arm_history.jsonl"
PPD = STATE_DIR / "post_proof_dwell.json"
KILL = STATE_DIR / "sl_width_arming_KILL"

DEFAULTS = {
    "shell_notional_lte_usd": 30.0,
    "min_hours_held": 4.0,
    "mfe_green_pct": 0.02,
    "core_pairs": ["BTC-USD", "ETH-USD"],
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> Any:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("load %s: %s", path, e)
        return {}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def _norm(pair: str) -> str:
    p = str(pair or "").strip().upper().replace("_", "-")
    if p and "-" not in p:
        p = f"{p}-USD"
    return p


def load_policy() -> Dict[str, Any]:
    raw = _load(CONFIG_PATH)
    if not isinstance(raw, dict):
        raw = {}
    out = {
        "status": raw.get("status") or "MEASURE_ONLY",
        "live_apply": bool(raw.get("live_apply", False)),
        "live_default": raw.get("live_default") or {"stop_loss_pct": 0.08},
        "arming_rules_shadow": raw.get("arming_rules_shadow") or [],
        "do_not": raw.get("do_not") or [],
    }
    # W2 rule knobs (from shadow rule or defaults)
    w2 = None
    for rule in out["arming_rules_shadow"] or []:
        if isinstance(rule, dict) and str(rule.get("id") or "").startswith("W2"):
            w2 = rule
            break
    if isinstance(w2, dict):
        out["w2_sl_pct"] = _f(w2.get("sl_base_pct"), 0.03)
        out["w2_sl_min"] = _f(w2.get("sl_min_pct"), 0.03)
        out["w2_sl_max"] = _f(w2.get("sl_max_pct"), 0.05)
        # honor per-rule live_apply if present
        if "live_apply" in w2:
            out["w2_live_apply"] = bool(w2.get("live_apply"))
        else:
            out["w2_live_apply"] = bool(out["live_apply"])
    else:
        out["w2_sl_pct"] = 0.03
        out["w2_sl_min"] = 0.03
        out["w2_sl_max"] = 0.05
        out["w2_live_apply"] = bool(out["live_apply"])
    out.update(DEFAULTS)
    return out


def effective_w2_live(policy: Optional[Dict[str, Any]] = None) -> bool:
    """W2 shell fuse live only when policy + W2 rule arm and no kill."""
    if KILL.is_file():
        return False
    p = policy or load_policy()
    if not bool(p.get("live_apply")):
        return False
    return bool(p.get("w2_live_apply", True))


def resolve_live_sl_pct(
    *,
    pair: str,
    held_usd: float = 0.0,
    role: str = "",
    has_tryout_lot: bool = False,
    mfe_pct: float = 0.0,
    hours_held: float = 0.0,
    graduated: Optional[bool] = None,
    default_pct: float = 0.08,
    policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Attach-time width resolver.
    Returns {sl_pct, rule_id, live_override, would_arm_3pct, reasons}.
    Only overrides default when W2 live + dead unproven shell.
    Never global 8→3. Never tightens after green (W3).
    """
    p = policy or load_policy()
    live = effective_w2_live(p)
    if graduated is None:
        ppd = _load(PPD)
        graduated = _graduated(pair, ppd if isinstance(ppd, dict) else {})
    cls = classify_would_arm(
        pair=pair,
        held_usd=held_usd,
        role=role,
        has_tryout_lot=has_tryout_lot,
        mfe_pct=mfe_pct,
        hours_held=hours_held,
        graduated=bool(graduated),
        policy=p,
    )
    base = _f((p.get("live_default") or {}).get("stop_loss_pct"), default_pct) or _f(
        default_pct, 0.08
    )
    out: Dict[str, Any] = {
        "pair": _norm(pair),
        "sl_pct": base,
        "rule_id": cls.get("rule_id"),
        "live_override": False,
        "would_arm_3pct": bool(cls.get("would_arm_3pct")),
        "live_apply": live,
        "reasons": list(cls.get("reasons") or []),
        "arm": cls.get("arm"),
    }
    if live and cls.get("would_arm_3pct") and cls.get("rule_id") == "W2_tight_unproven_shell":
        pct = _f(p.get("w2_sl_pct"), 0.03)
        # clamp to W2 band
        pct = max(_f(p.get("w2_sl_min"), 0.03), min(_f(p.get("w2_sl_max"), 0.05), pct))
        out["sl_pct"] = pct
        out["live_override"] = True
        out["reasons"].append("w2_live_fuse_applied")
    return out


def _graduated(pair: str, ppd: Dict[str, Any]) -> bool:
    pairs_raw = ppd.get("pairs") if isinstance(ppd, dict) else None
    pairs = pairs_raw if isinstance(pairs_raw, dict) else {}
    st = pairs.get(pair) or pairs.get(_norm(pair)) or {}
    if not isinstance(st, dict):
        return False
    return str(st.get("status") or "") in ("graduated_hold", "graduated", "dwell_graduated")


def _mfe_pct(pair: str, live: Dict[str, Any], row: Dict[str, Any]) -> float:
    # Prefer explicit path peak if present
    for blob_key in ("path_mfe", "pair_mfe", "mfe_while_held"):
        blob = live.get(blob_key)
        if isinstance(blob, dict):
            v = blob.get(pair) or blob.get(_norm(pair))
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, dict) and v.get("mfe_pct") is not None:
                return _f(v.get("mfe_pct"))
    # open_upnl as weak proxy when green
    held = _f(row.get("held_usd"))
    upnl = row.get("open_upnl_usd")
    if held > 0 and upnl is not None:
        return max(0.0, _f(upnl) / held)
    return 0.0


def _hours_held(pair: str, live: Dict[str, Any], row: Dict[str, Any]) -> float:
    lots = live.get("tryout_open_lots") or live.get("open_lots") or {}
    if isinstance(lots, dict):
        lot = lots.get(pair) or lots.get(_norm(pair))
        if isinstance(lot, dict):
            for k in ("entry_ts", "opened_at", "buy_ts", "timestamp"):
                ts = lot.get(k)
                if not ts:
                    continue
                try:
                    t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    return max(0.0, (datetime.now(timezone.utc) - t).total_seconds() / 3600.0)
                except Exception:
                    pass
    # matrix may not have hold hours
    return _f(row.get("hold_hours"), 0.0)


def classify_would_arm(
    *,
    pair: str,
    held_usd: float,
    role: str,
    has_tryout_lot: bool,
    mfe_pct: float,
    hours_held: float,
    graduated: bool,
    policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    p = policy or load_policy()
    pn = _norm(pair)
    core = {_norm(x) for x in (p.get("core_pairs") or DEFAULTS["core_pairs"])}
    shell_cap = _f(p.get("shell_notional_lte_usd"), 30.0)
    min_h = _f(p.get("min_hours_held"), 4.0)
    mfe_green = _f(p.get("mfe_green_pct"), 0.02)

    out: Dict[str, Any] = {
        "pair": pn,
        "held_usd": round(held_usd, 2),
        "role": role,
        "has_tryout_lot": bool(has_tryout_lot),
        "mfe_pct": round(mfe_pct, 4),
        "hours_held": round(hours_held, 2),
        "graduated": bool(graduated),
        "would_arm_3pct": False,
        "would_arm_8pct": True,
        "arm": "8pct_band",
        "rule_id": "W1_default_wide",
        "reasons": [],
        "live_apply": False,
        "shadow": True,
    }

    # W3 never tighten after green
    if mfe_pct >= mfe_green or graduated:
        out["reasons"].append("W3_never_tighten_after_green")
        out["arm"] = "keep_8pct"
        out["rule_id"] = "W3_never_tighten_after_green"
        out["would_arm_3pct"] = False
        out["would_arm_8pct"] = True
        return out

    if pn in core or role in ("ballast_core", "sticky_core"):
        out["reasons"].append("core_or_ballast")
        out["rule_id"] = "W1_default_wide"
        return out

    if held_usd > shell_cap and not has_tryout_lot:
        out["reasons"].append("notional_above_shell")
        return out

    # W2 tight unproven shell
    shellish = has_tryout_lot or held_usd <= shell_cap
    if (
        shellish
        and not graduated
        and pn not in core
        and mfe_pct < mfe_green
        and hours_held >= min_h
    ):
        out["would_arm_3pct"] = True
        out["would_arm_8pct"] = False
        out["arm"] = "3pct_fixed"
        out["rule_id"] = "W2_tight_unproven_shell"
        out["reasons"].append("W2_dead_unproven_shell")
        return out

    if shellish and hours_held < min_h:
        out["reasons"].append("shell_but_hours_lt_min")
    elif shellish and mfe_pct >= mfe_green:
        out["reasons"].append("shell_but_green_mfe")
    else:
        out["reasons"].append("default_wide")
    return out


def evaluate_open_shells_would_arm(
    *,
    matrix_rows: Optional[List[Dict[str, Any]]] = None,
    live: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    policy = load_policy()
    live = live if isinstance(live, dict) else _load(STATE_DIR / "phase6_live_state.json")
    if not isinstance(live, dict):
        live = {}
    ppd = _load(PPD)
    if not isinstance(ppd, dict):
        ppd = {}
    rows = matrix_rows
    if rows is None:
        mx = _load(STATE_DIR / "membership_sizing_matrix_latest.json")
        rows = mx.get("rows") if isinstance(mx, dict) else []
    if not isinstance(rows, list):
        rows = []

    evals: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        pair = _norm(str(row.get("pair") or ""))
        held = _f(row.get("held_usd"))
        if held < 5.0 and not row.get("has_tryout_lot"):
            continue  # skip dust/empty
        # Focus tryout-ish + small held + any held with lot
        role = str(row.get("role") or "")
        has_lot = bool(row.get("has_tryout_lot"))
        if role in ("ballast_core",) and held > 40:
            # still log ballast as 8% proof path
            pass
        elif held < 5.0 and not has_lot:
            continue
        mfe = _mfe_pct(pair, live, row)
        hrs = _hours_held(pair, live, row)
        grad = _graduated(pair, ppd)
        evals.append(
            classify_would_arm(
                pair=pair,
                held_usd=held,
                role=role,
                has_tryout_lot=has_lot,
                mfe_pct=mfe,
                hours_held=hrs,
                graduated=grad,
                policy=policy,
            )
        )

    n3 = sum(1 for e in evals if e.get("would_arm_3pct"))
    n8 = sum(1 for e in evals if e.get("would_arm_8pct"))
    w2_live = effective_w2_live(policy)
    out = {
        "schema": SCHEMA,
        "as_of": _utc(),
        "status": "W2_LIVE_SHELL_ONLY" if w2_live else (policy.get("status") or "MEASURE_ONLY"),
        "live_apply": w2_live,
        "kill_file": KILL.is_file(),
        "n_eval": len(evals),
        "n_would_3pct": n3,
        "n_would_8pct": n8,
        "rows": evals,
        "policy_path": str(CONFIG_PATH.relative_to(PROJECT_ROOT)),
        "note": (
            "W2 live: 3% fuse only on dead unproven shells at attach; core/green stay 8%"
            if w2_live
            else "MEASURE_ONLY — no money path; 14d shadow before any live fuse GO"
        ),
    }
    return out


def run_and_persist() -> Dict[str, Any]:
    out = evaluate_open_shells_would_arm()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(out, default=str) + "\n")
    return out


if __name__ == "__main__":
    o = run_and_persist()
    print(
        f"SL would-arm shadow · n={o.get('n_eval')} "
        f"3pct={o.get('n_would_3pct')} 8pct={o.get('n_would_8pct')} "
        f"live_apply=OFF status={o.get('status')}"
    )
    print(f"state: {LATEST}")
