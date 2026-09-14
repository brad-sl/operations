"""Platform metrics spine — full pair lifecycle + runner ops (measure-only).

Joins existing SSOT boards into one operator page:
  select → shortlist → advance → promote → signal → fill → trade → DQ/remove

Never writes config, pairs, knobs, or live_membership_swaps.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from phase6.core.paths import PROJECT_ROOT

SCHEMA = "platform_metrics_spine_v1"
STATE_DIR = PROJECT_ROOT / "data" / "state"
REPORT_DIR = PROJECT_ROOT / "reports"
SPINE_PATH = STATE_DIR / "platform_metrics_spine_latest.json"
SPINE_REPORT = REPORT_DIR / "PLATFORM_METRICS_SPINE_LATEST.md"

# Default feed map (path relative to PROJECT_ROOT unless absolute)
DEFAULT_FEEDS: Dict[str, str] = {
    "runner_state": "data/state/phase6_runner_state.json",
    "live_state": "data/state/phase6_live_state.json",
    "runner_pid": "data/state/phase6_runner.pid",
    "regime_cash": "data/state/regime_cash_status.json",
    "tryout_readiness": "data/state/tryout_readiness_latest.json",
    "brad_decision": "data/state/basket_swap_brad_decision.json",
    "confidence_board": "data/state/basket_swap_confidence_board_latest.json",
    "l2": "data/state/l2_deployability_latest.json",
    "pick_summary": "data/state/basket_pick_metrics_summary.json",
    "graduation": "data/state/basket_seat_graduation_latest.json",
    "seat_idle": "data/state/basket_seat_idle_latest.json",
    "attribution": "data/state/attribution_rt_weekly_latest.json",
    "exit_stack": "data/state/exit_stack_proof_latest.json",
    "limit_first": "data/state/limit_first_evidence_latest.json",
    "regime_arm": "data/state/regime_arm_switch_latest.json",
    "missfire": "data/state/missfire_probation_latest.json",
    "novelty": "data/state/novelty_class_latest.json",
    "protective_registry": "data/state/protective_orders_registry.jsonl",
}

# Lifecycle stage order (full pair lifecycle)
LIFECYCLE_ORDER = (
    "select",
    "shortlist",
    "advance",
    "promote",
    "signal",
    "fill",
    "trade_success",
    "disqualify_remove",
)

PROMOTE_TALK_MIN_FILLED = 8
EDGE_CLAIM_MIN_RT = 20
FEED_STALE_HOURS = 36.0
RUNNER_STALE_HOURS = 2.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _utc_now()).isoformat()


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        # epoch seconds
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _age_hours(ts: Any, now: Optional[datetime] = None) -> Optional[float]:
    dt = _parse_ts(ts)
    if dt is None:
        return None
    now = now or _utc_now()
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _resolve(path_str: str, root: Path = PROJECT_ROOT) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else (root / p)


def load_feeds(
    feed_map: Optional[Mapping[str, str]] = None,
    *,
    root: Path = PROJECT_ROOT,
    overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Load feed JSON blobs. overrides[name]=dict short-circuits disk for tests."""
    fmap = dict(DEFAULT_FEEDS)
    if feed_map:
        fmap.update(dict(feed_map))
    out: Dict[str, Any] = {}
    ov = dict(overrides or {})
    for name, rel in fmap.items():
        if name in ov:
            out[name] = ov[name]
            continue
        path = _resolve(rel, root)
        if name == "protective_registry":
            out[name] = {"_path": str(path), "_lines": _tail_jsonl(path, 800)}
        elif name == "runner_pid":
            out[name] = _read_pid(path)
        else:
            blob = _read_json(path)
            blob = dict(blob)
            blob["_path"] = str(path)
            blob["_exists"] = path.exists()
            out[name] = blob
    return out


def _read_pid(path: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {"_path": str(path), "_exists": path.exists(), "pid": None, "alive": False}
    if not path.exists():
        return out
    try:
        raw = path.read_text(encoding="utf-8").strip()
        pid = int(raw.split()[0])
        out["pid"] = pid
        out["alive"] = _pid_alive(pid)
    except (OSError, ValueError, IndexError) as e:
        out["error"] = str(e)[:120]
    return out


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours
    except OSError:
        return False


def _tail_jsonl(path: Path, n: int = 800) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: List[Dict[str, Any]] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _feed_inventory(feeds: Mapping[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or _utc_now()
    inv: Dict[str, Any] = {}
    for name, blob in feeds.items():
        if not isinstance(blob, dict):
            inv[name] = {"ok": False, "note": "non_dict"}
            continue
        if name == "protective_registry":
            inv[name] = {
                "ok": bool(blob.get("_lines") is not None),
                "n_rows_tailed": len(blob.get("_lines") or []),
                "path": blob.get("_path"),
            }
            continue
        if name == "runner_pid":
            inv[name] = {
                "ok": bool(blob.get("alive")),
                "pid": blob.get("pid"),
                "alive": blob.get("alive"),
                "path": blob.get("_path"),
            }
            continue
        ts = (
            blob.get("as_of")
            or blob.get("as_of_utc")
            or blob.get("ts")
            or blob.get("last_updated")
            or blob.get("asof")
            or blob.get("generated_at")
        )
        age = _age_hours(ts, now)
        exists = blob.get("_exists", True)
        inv[name] = {
            "ok": bool(exists and (blob.keys() - {"_path", "_exists"})),
            "exists": exists,
            "as_of": ts,
            "age_hours": round(age, 2) if age is not None else None,
            "stale": bool(age is not None and age > FEED_STALE_HOURS),
            "path": blob.get("_path"),
        }
    return inv


# ---------------------------------------------------------------------------
# Runner ops (P1)
# ---------------------------------------------------------------------------


def build_runner_ops(feeds: Mapping[str, Any], *, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or _utc_now()
    rs = feeds.get("runner_state") or {}
    ls = feeds.get("live_state") or {}
    pid = feeds.get("runner_pid") or {}
    rc = feeds.get("regime_cash") or {}
    tr = feeds.get("tryout_readiness") or {}
    exit_stack = feeds.get("exit_stack") or {}
    prot_lines = (feeds.get("protective_registry") or {}).get("_lines") or []

    last_updated = rs.get("last_updated") or ls.get("last_updated")
    age = _age_hours(last_updated, now)
    slots = list(rs.get("rebalance_slots_completed") or [])
    today = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
    # slots stored as local-ish date|HH:MM — count today's
    slots_today = [s for s in slots if str(s).startswith(today) or str(s).startswith(now.strftime("%Y-%m-%d"))]
    # also accept America/Los_Angeles calendar date if present in runner
    last_rebal_date = str(rs.get("last_rebalance_date") or "")
    rebal_today = last_rebal_date == today or last_rebal_date == now.date().isoformat() or bool(slots_today)

    # Prefer list of position dicts. active_positions is often a COUNT int — never iterate it.
    trading_raw = (
        ls.get("trading_positions")
        if isinstance(ls.get("trading_positions"), (list, dict))
        else None
    )
    if trading_raw is None and isinstance(ls.get("positions"), (list, dict)):
        trading_raw = ls.get("positions")
    if trading_raw is None and isinstance(ls.get("open_positions"), (list, dict)):
        trading_raw = ls.get("open_positions")
    if isinstance(trading_raw, dict):
        trading = list(trading_raw.values())
    elif isinstance(trading_raw, list):
        trading = trading_raw
    else:
        trading = []
    open_bags = []
    for p in trading:
        if not isinstance(p, dict):
            continue
        pair = str(p.get("pair") or p.get("product_id") or "").upper()
        if not pair or pair in ("USD-USD", "USDC-USD", "USDT-USD"):
            continue
        sleeve = str(p.get("sleeve") or "").lower()
        val = float(p.get("value_usd") or p.get("notional") or p.get("market_value") or 0.0)
        qty = float(p.get("qty") or p.get("amount") or p.get("quantity") or 0.0)
        if qty <= 0 and val < 5:
            continue
        open_bags.append(
            {
                "pair": pair,
                "value_usd": round(val, 2),
                "sleeve": sleeve or None,
                "unrealized_pnl_pct": p.get("unrealized_pnl_pct"),
            }
        )

    # Open protectives from registry tail (status open/active)
    open_prot_pairs: Dict[str, int] = {}
    for row in prot_lines:
        st = str(row.get("status") or "").lower()
        if st not in ("open", "active", "resting", "live"):
            continue
        pair = str(row.get("pair") or "").upper()
        if not pair:
            continue
        open_prot_pairs[pair] = open_prot_pairs.get(pair, 0) + 1

    # SL coverage: non-preserve bags should have ≥1 open protective when value >= $15
    need_sl = [b for b in open_bags if (b.get("sleeve") or "") != "preserve" and (b.get("value_usd") or 0) >= 15]
    covered = [b for b in need_sl if open_prot_pairs.get(b["pair"], 0) > 0]
    naked = [b for b in need_sl if open_prot_pairs.get(b["pair"], 0) == 0]
    sl_coverage = (len(covered) / len(need_sl)) if need_sl else 1.0  # vacuously OK if no trade bags

    can_buy = bool(tr.get("can_buy_before_next_rebalance"))
    allow_new = rc.get("allow_new_buys")
    if allow_new is None:
        allow_new = True
    strategy_mode = rc.get("strategy_mode") or tr.get("regime") or "—"

    pid_alive = bool(pid.get("alive"))
    heartbeat_ok = bool(pid_alive and age is not None and age <= RUNNER_STALE_HOURS)
    if pid_alive and age is None:
        heartbeat_ok = True  # pid live, missing ts → soft OK
    if not pid_alive:
        heartbeat_ok = False

    # Ops integrity (not PnL)
    reasons: List[str] = []
    if not pid_alive:
        reasons.append("runner_pid_dead")
    if age is not None and age > RUNNER_STALE_HOURS:
        reasons.append(f"runner_state_stale_{age:.1f}h")
    if naked:
        reasons.append(f"naked_bags:{','.join(b['pair'] for b in naked)}")
    if need_sl and sl_coverage < 0.99:
        reasons.append(f"sl_coverage={sl_coverage:.0%}")

    ops_ok = len(reasons) == 0
    # Idle-correct: armor on, no buy door — not a failure
    idle_correct = (not can_buy) and bool(allow_new is False or not can_buy)

    return {
        "schema": "runner_ops_v1",
        "ops_ok": ops_ok,
        "ops_reasons": reasons,
        "heartbeat_ok": heartbeat_ok,
        "pid": pid.get("pid"),
        "pid_alive": pid_alive,
        "state_age_hours": round(age, 2) if age is not None else None,
        "last_updated": last_updated,
        "last_rebalance_date": last_rebal_date or None,
        "rebal_slots_today": slots_today[-4:],
        "rebal_ran_today": rebal_today,
        "n_open_trade_bags": len(need_sl),
        "n_open_all_bags": len(open_bags),
        "open_bags": open_bags,
        "sl_coverage": round(sl_coverage, 4),
        "naked_bags": naked,
        "n_open_protectives": sum(open_prot_pairs.values()),
        "open_protective_pairs": sorted(open_prot_pairs.keys()),
        "can_buy_before_next_rebalance": can_buy,
        "allow_new_buys": bool(allow_new),
        "strategy_mode": strategy_mode,
        "regime": rc.get("regime") or tr.get("regime"),
        "idle_correct_likely": bool(not can_buy),
        "cash_hold_usd": float(rs.get("manual_liquidation_cash_hold_usd") or 0.0),
        "exit_stack_go": (exit_stack.get("go_nogo") or {}).get("overall")
        if isinstance(exit_stack.get("go_nogo"), dict)
        else exit_stack.get("go_nogo"),
        "plain_english": _runner_ops_plain(
            ops_ok=ops_ok,
            pid_alive=pid_alive,
            can_buy=can_buy,
            rebal_today=rebal_today,
            naked=naked,
            sl_coverage=sl_coverage,
            n_bags=len(need_sl),
        ),
    }


def _runner_ops_plain(
    *,
    ops_ok: bool,
    pid_alive: bool,
    can_buy: bool,
    rebal_today: bool,
    naked: Sequence[Mapping[str, Any]],
    sl_coverage: float,
    n_bags: int,
) -> str:
    bits = []
    bits.append("Runner alive." if pid_alive else "Runner PID not alive.")
    bits.append("Rebal marked today." if rebal_today else "No rebal slot marked for today yet.")
    if n_bags == 0:
        bits.append("No non-preserve trade bags — SL coverage N/A (vacuous OK).")
    else:
        bits.append(f"SL coverage {sl_coverage:.0%} on {n_bags} trade bag(s).")
        if naked:
            bits.append(f"NAKED: {', '.join(b['pair'] for b in naked)}.")
    bits.append("Buy door open." if can_buy else "Buy door closed (idle may be correct under armor).")
    bits.append("OPS_OK." if ops_ok else "OPS_ATTENTION.")
    return " ".join(bits)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def build_lifecycle(feeds: Mapping[str, Any], *, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or _utc_now()
    hc = feeds.get("confidence_board") or {}
    brad = feeds.get("brad_decision") or {}
    l2 = feeds.get("l2") or {}
    tr = feeds.get("tryout_readiness") or {}
    pick = feeds.get("pick_summary") or {}
    grad = feeds.get("graduation") or {}
    idle = feeds.get("seat_idle") or {}
    attr = feeds.get("attribution") or {}
    nov = feeds.get("novelty") or {}
    mf = feeds.get("missfire") or {}
    regime_arm = feeds.get("regime_arm") or {}
    lf = feeds.get("limit_first") or {}

    preferred = brad.get("preferred_arm") or regime_arm.get("preferred_arm") or "—"
    live_swaps = bool(brad.get("live_membership_swaps"))
    arms = hc.get("arms") or []
    pref_row = next((a for a in arms if a.get("arm") == preferred), None) or {}
    hc_pref = bool(pref_row.get("high_confidence"))

    # L2 summary
    l2_sum = l2.get("summary") or {}
    l2_pass = l2_sum.get("n_pass")
    l2_total = l2_sum.get("n_rows") or l2_sum.get("n") or len(l2.get("rows") or [])
    if l2_pass is None and l2.get("rows"):
        l2_pass = sum(1 for r in l2["rows"] if r.get("l2_allowed"))
        l2_total = len(l2["rows"])

    funnel = grad.get("funnel") or pick.get("graduation") or {}
    n_seated = int(funnel.get("n_seated") or pick.get("n_picks") or 0)
    n_signaled = int(funnel.get("n_signaled") or 0)
    n_filled = int(funnel.get("n_filled") or 0)
    n_win = int(funnel.get("n_filled_win") or 0)
    n_loss = int(funnel.get("n_filled_loss") or 0)
    n_blocked = int(funnel.get("n_blocked_no_fill") or 0)

    # novelty counts
    nov_counts = nov.get("counts") or {}
    if not nov_counts and isinstance(nov.get("buckets"), dict):
        nov_counts = {k: len(v) if isinstance(v, list) else v for k, v in nov["buckets"].items()}

    blocked_mf = mf.get("blocked_pairs") or []
    if isinstance(blocked_mf, dict):
        blocked_mf = list(blocked_mf.keys())

    idle_flagged = idle.get("idle_flagged_pairs") or []
    n_idle = int(idle.get("n_idle_flagged") or len(idle_flagged) or 0)

    attr_sum = attr.get("summary") or {}
    n_rt = int(attr_sum.get("n_rt_primary") or 0)
    tax = attr_sum.get("process_tax_bank") or {}
    non_tax = attr_sum.get("non_tax_bank") or {}
    edge_allowed = bool(attr_sum.get("edge_claim_allowed"))

    tryout_pairs = tr.get("eligible_tryout_pairs") or [
        p.get("pair") for p in (tr.get("pairs") or []) if isinstance(p, dict) and p.get("eligible")
    ]
    can_buy = bool(tr.get("can_buy_before_next_rebalance"))
    allowed_tryout = [
        p.get("pair")
        for p in (tr.get("pairs") or [])
        if isinstance(p, dict) and p.get("allowed")
    ]

    # Promote paper MTM
    hit7 = pick.get("hit_rate_positive_7d")
    avg7 = (pick.get("avg_ret_pct_by_horizon") or {}).get("7d")
    excess7 = (pick.get("avg_excess_vs_remove_pct") or {}).get("7d")

    lf_agg = lf.get("aggregate") or lf
    lf_attempts = lf_agg.get("attempts") or lf_agg.get("n_attempts")
    lf_filled = lf_agg.get("filled") or lf_agg.get("n_filled")
    lf_promote = lf_agg.get("promote_talk_ok")
    if lf_promote is None:
        lf_promote = lf.get("promote_talk_ok")

    stages = [
        {
            "id": "select",
            "label": "Paper pair selection (L1 CF arms)",
            "metric": "preferred_arm_ex7_hc",
            "preferred_arm": preferred,
            "ex7": pref_row.get("ex7"),
            "hit7": pref_row.get("hit7"),
            "n7": pref_row.get("n7"),
            "high_confidence": hc_pref,
            "board_status": hc.get("status"),
            "success_local": hc_pref and (pref_row.get("ex7") or 0) > 0,
            "note": "L1 only — not fills or book PnL",
        },
        {
            "id": "shortlist",
            "label": "Shortlist filters (novelty + missfire)",
            "novelty_counts": nov_counts,
            "missfire_blocked_n": len(blocked_mf),
            "missfire_blocked": list(blocked_mf)[:12],
            "success_local": True,  # filter working is success; empty blocked OK
            "note": "M5 novelty + missfire — shortlist only; live swaps unchanged",
        },
        {
            "id": "advance",
            "label": "Advance (tryout door + paper-primary)",
            "tryout_eligible": list(tryout_pairs or [])[:12],
            "tryout_allowed_now": allowed_tryout[:12],
            "can_buy": can_buy,
            "live_membership_swaps": live_swaps,
            "l2_pass": l2_pass,
            "l2_total": l2_total,
            "l2_pass_rate": (
                (float(l2_pass) / float(l2_total))
                if (l2_total and l2_pass is not None)
                else None
            ),
            "success_local": bool(tryout_pairs) and not live_swaps,  # door exists; auto still off is correct
            "note": "Advance ≠ seat. Auto membership OFF until Brad GO.",
        },
        {
            "id": "promote",
            "label": "Basket promote (Brad GO seats)",
            "n_picks": pick.get("n_picks") or n_seated,
            "open_picks": pick.get("open_picks"),
            "adds": (pick.get("adds") or [])[:12],
            "hit_rate_7d": hit7,
            "avg_ret_7d_pct": avg7,
            "excess_vs_remove_7d_pct": excess7,
            "success_local": bool(hit7 is not None and hit7 >= 0.45 and (avg7 or 0) > 0),
            "note": "Paper MTM on seated adds — still not book alpha alone",
        },
        {
            "id": "signal",
            "label": "Signal given seat",
            "n_seated": n_seated,
            "n_signaled": n_signaled,
            "rate_signal_given_seat": funnel.get("rate_signal_given_seat"),
            "success_local": (funnel.get("rate_signal_given_seat") or 0) >= 0.5 if n_seated else None,
            "note": "BUY/decision context after promote",
        },
        {
            "id": "fill",
            "label": "Fill given signal",
            "n_filled": n_filled,
            "n_blocked_no_fill": n_blocked,
            "rate_fill_given_signal": funnel.get("rate_fill_given_signal"),
            "limit_first_attempts": lf_attempts,
            "limit_first_filled": lf_filled,
            "limit_first_promote_talk_ok": lf_promote,
            "success_local": (funnel.get("rate_fill_given_signal") or 0) >= 0.35 if n_signaled else None,
            "note": "Deploy choke — high signal low fill = gates/size/fees path",
        },
        {
            "id": "trade_success",
            "label": "Closed fill wins + stamped RTs",
            "n_filled_win": n_win,
            "n_filled_loss": n_loss,
            "rate_win_given_fill_closed": funnel.get("rate_win_given_fill_closed"),
            "rate_win_given_seat": funnel.get("rate_win_given_seat"),
            "n_rt_primary": n_rt,
            "process_tax_pnl_sum": tax.get("pnl_sum"),
            "non_tax_pnl_sum": non_tax.get("pnl_sum"),
            "edge_claim_allowed": edge_allowed,
            "success_local": bool(n_win > n_loss and n_filled >= 5),
            "promote_talk_ok": bool(n_filled >= PROMOTE_TALK_MIN_FILLED and n_win > n_loss),
            "note": "WR secondary; need N before edge claims",
        },
        {
            "id": "disqualify_remove",
            "label": "DQ / idle / removal candidates",
            "n_idle_flagged": n_idle,
            "idle_flagged_pairs": list(idle_flagged)[:12],
            "hard_eject": bool(idle.get("hard_eject")),
            "mode": idle.get("mode") or "observe_only",
            "missfire_blocked_n": len(blocked_mf),
            "success_local": idle.get("mode") in (None, "observe_only") or n_idle >= 0,
            "note": "Observe-only idle flags — no auto-eject from spine. Removal still Brad GO.",
        },
    ]

    # Choke point: first failing stage with enough N
    choke = _infer_choke(stages, funnel, can_buy, live_swaps)

    return {
        "schema": "pair_lifecycle_v1",
        "preferred_arm": preferred,
        "live_membership_swaps": live_swaps,
        "stages": stages,
        "funnel": {
            "n_seated": n_seated,
            "n_signaled": n_signaled,
            "n_filled": n_filled,
            "n_filled_win": n_win,
            "n_filled_loss": n_loss,
            "n_blocked_no_fill": n_blocked,
            "rate_signal_given_seat": funnel.get("rate_signal_given_seat"),
            "rate_fill_given_signal": funnel.get("rate_fill_given_signal"),
            "rate_win_given_fill_closed": funnel.get("rate_win_given_fill_closed"),
            "rate_win_given_seat": funnel.get("rate_win_given_seat"),
        },
        "choke_point": choke,
        "automation_readiness": {
            "auto_select_paper": True,  # arms + regime switch already run
            "auto_advance_tryout": bool(tryout_pairs),
            "auto_promote_live": False,  # hard no until GO + gates
            "auto_swap_live": live_swaps,
            "auto_disqualify_eject": bool(idle.get("hard_eject")),
            "note": (
                "Full lifecycle automation is measure→justify→Brad GO. "
                "Spine never flips live_membership_swaps or hard_eject."
            ),
        },
        "plain_english": _lifecycle_plain(choke, funnel, preferred, live_swaps, can_buy, n_win, n_filled),
    }


def _infer_choke(
    stages: Sequence[Mapping[str, Any]],
    funnel: Mapping[str, Any],
    can_buy: bool,
    live_swaps: bool,
) -> Dict[str, Any]:
    n_seated = int(funnel.get("n_seated") or 0)
    n_sig = int(funnel.get("n_signaled") or 0)
    n_fill = int(funnel.get("n_filled") or 0)
    n_win = int(funnel.get("n_filled_win") or 0)
    n_loss = int(funnel.get("n_filled_loss") or 0)

    if live_swaps:
        return {
            "id": "auto_swap_live_on",
            "severity": "high",
            "why": "live_membership_swaps ON — spine still measure-only; verify Brad GO",
        }
    if n_seated >= 3 and n_fill == 0:
        return {
            "id": "fill",
            "severity": "high",
            "why": f"{n_seated} seats / {n_sig} signals / 0 fills — deploy choke",
        }
    if n_fill >= 2 and n_win == 0 and n_loss >= 2:
        return {
            "id": "trade_success",
            "severity": "high",
            "why": f"filled={n_fill} wins=0 losses={n_loss} — exit/entry quality, not more scouts",
        }
    if n_seated >= 3 and (funnel.get("rate_fill_given_signal") or 0) < 0.3 and n_sig >= 3:
        return {
            "id": "fill",
            "severity": "high",
            "why": "fill|signal weak — gates/size/liquidity",
        }
    if not can_buy and n_fill < 3:
        return {
            "id": "advance",
            "severity": "medium",
            "why": "tryout buy door closed — sensor/armor; idle may be correct",
        }
    # promote paper red
    promote = next((s for s in stages if s.get("id") == "promote"), {})
    if promote and promote.get("success_local") is False and n_seated >= 5:
        return {
            "id": "promote",
            "severity": "medium",
            "why": "seated adds weak on 7d paper MTM — selection/promote quality",
        }
    select = next((s for s in stages if s.get("id") == "select"), {})
    if select and select.get("success_local") is False:
        return {
            "id": "select",
            "severity": "low",
            "why": "preferred arm not HC-green — paper attention only",
        }
    return {
        "id": "none_clear",
        "severity": "low",
        "why": "no single choke with enough N — keep collecting",
    }


def _lifecycle_plain(
    choke: Mapping[str, Any],
    funnel: Mapping[str, Any],
    preferred: str,
    live_swaps: bool,
    can_buy: bool,
    n_win: int,
    n_filled: int,
) -> str:
    return (
        f"Lifecycle: seat {funnel.get('n_seated')} → sig {funnel.get('n_signaled')} → "
        f"fill {funnel.get('n_filled')} → win {n_win}. "
        f"Paper-primary={preferred}; live_swaps={'ON' if live_swaps else 'OFF'}; "
        f"can_buy={can_buy}. Choke={choke.get('id')} ({choke.get('why')}). "
        f"Auto full-lifecycle: NOT ready (measure-only)."
    )


# ---------------------------------------------------------------------------
# Go / no-go strip
# ---------------------------------------------------------------------------


def build_go_nogo(runner: Mapping[str, Any], life: Mapping[str, Any], feeds_inv: Mapping[str, Any]) -> Dict[str, Any]:
    ops_ok = bool(runner.get("ops_ok"))
    funnel = life.get("funnel") or {}
    auto = life.get("automation_readiness") or {}
    choke = life.get("choke_point") or {}
    edge = False
    for s in life.get("stages") or []:
        if s.get("id") == "trade_success":
            edge = bool(s.get("edge_claim_allowed"))
            promote_talk = bool(s.get("promote_talk_ok"))
            break
    else:
        promote_talk = False

    stale_feeds = [k for k, v in feeds_inv.items() if isinstance(v, dict) and v.get("stale")]
    critical_missing = [
        k
        for k in ("runner_state", "graduation", "brad_decision", "tryout_readiness")
        if not (feeds_inv.get(k) or {}).get("ok", True)
    ]

    money_path = "NO_GO"
    n_fill = int(funnel.get("n_filled") or 0)
    n_win = int(funnel.get("n_filled_win") or 0)
    if n_fill >= PROMOTE_TALK_MIN_FILLED and n_win > int(funnel.get("n_filled_loss") or 0) and edge:
        money_path = "GO_SCALE_TALK"
    elif n_fill >= 3 and n_win > 0:
        money_path = "ATTENTION"
    else:
        money_path = "NO_GO_SCALE"

    auto_membership = "NO_GO"
    if auto.get("auto_swap_live"):
        auto_membership = "LIVE_ON_VERIFY"
    elif promote_talk and (life.get("stages") or [{}])[0].get("high_confidence"):
        auto_membership = "STILL_NO_AUTO"  # never auto from spine

    ops_verdict = "GO" if ops_ok else "ATTENTION"
    if critical_missing or (not runner.get("pid_alive")):
        ops_verdict = "NO_GO"

    return {
        "ops": ops_verdict,
        "money_path": money_path,
        "auto_membership": auto_membership,
        "edge_claim_allowed": edge,
        "promote_talk_ok": promote_talk,
        "choke_point": choke.get("id"),
        "choke_why": choke.get("why"),
        "stale_feeds": stale_feeds,
        "critical_missing_feeds": critical_missing,
        "live_membership_swaps": bool(life.get("live_membership_swaps")),
        "plain_english": (
            f"ops={ops_verdict} money_path={money_path} auto_membership={auto_membership} "
            f"edge_claim={edge} choke={choke.get('id')}. "
            "Spine never auto-promotes or auto-ejects."
        ),
    }


# ---------------------------------------------------------------------------
# Assemble + report
# ---------------------------------------------------------------------------


def build_spine(
    *,
    feeds: Optional[Mapping[str, Any]] = None,
    root: Path = PROJECT_ROOT,
    overrides: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
    write: bool = False,
) -> Dict[str, Any]:
    now = now or _utc_now()
    feeds = dict(feeds) if feeds is not None else load_feeds(root=root, overrides=overrides)
    inv = _feed_inventory(feeds, now=now)
    runner = build_runner_ops(feeds, now=now)
    life = build_lifecycle(feeds, now=now)
    go = build_go_nogo(runner, life, inv)

    # Book snapshot (from runner capital nav if present)
    rs = feeds.get("runner_state") or {}
    nav = rs.get("capital_nav_snapshot") or {}
    book = {
        "cash_usd": nav.get("cash_usd"),
        "holdings_usd": nav.get("holdings_usd"),
        "total_usd": nav.get("total_usd"),
        "nav_ts": nav.get("ts"),
        "note": "Deposit-adj period % stay on dashboard /api/performance — spine does not recompute NAV math here.",
    }

    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": _iso(now),
        "measure_only": True,
        "no_live_writes": True,
        "north_star": "~5%/mo deposit-adjusted take-home; process tax = manufactured SL leakage",
        "goal": "Full pair lifecycle metrics: select→advance→promote→trade→DQ/remove (justify + optimize; no auto live)",
        "go_nogo": go,
        "runner_ops": runner,
        "lifecycle": life,
        "book": book,
        "feeds": inv,
        "actions_taken": [],
        "links": {
            "plan": "docs/plans/2026-09-14-platform-metrics-spine.md",
            "graduation": "data/state/basket_seat_graduation_latest.json",
            "pick_summary": "data/state/basket_pick_metrics_summary.json",
            "tryout": "data/state/tryout_readiness_latest.json",
            "hc_board": "data/state/basket_swap_confidence_board_latest.json",
            "promote_chart": "data/state/promote_graduation_chart_latest.json",
            "promote_chart_md": "reports/PROMOTE_GRADUATION_CHART_LATEST.md",
        },
    }

    # P2 promote chart summary (read-only join when present)
    try:
        pc_path = root / "data" / "state" / "promote_graduation_chart_latest.json"
        if pc_path.exists():
            pc = json.loads(pc_path.read_text())
            if isinstance(pc, dict) and pc.get("schema"):
                payload["promote_graduation"] = {
                    "as_of": pc.get("as_of"),
                    "funnel": pc.get("funnel"),
                    "paper": {
                        k: (pc.get("paper") or {}).get(k)
                        for k in (
                            "n_picks",
                            "hit_rate_positive_7d",
                            "avg_ret_7d_pct",
                            "avg_excess_7d_pct",
                            "claim_allowed",
                        )
                    },
                    "choke_point": pc.get("choke_point"),
                    "go_nogo": pc.get("go_nogo"),
                    "charts": pc.get("charts"),
                    "dashboard_ready": (pc.get("dashboard") or {}).get("ready_for_pane"),
                    "series_n": (pc.get("series") or {}).get("n_points"),
                }
    except Exception:
        pass

    # P3 regime arm switch metrics join
    try:
        ra_path = root / "data" / "state" / "regime_arm_switch_metrics_latest.json"
        if ra_path.exists():
            ra = json.loads(ra_path.read_text())
            if isinstance(ra, dict) and ra.get("schema"):
                payload["regime_arm_switch"] = {
                    "as_of": ra.get("as_of"),
                    "current": ra.get("current"),
                    "summary": ra.get("summary"),
                    "hc_compare": {
                        k: (ra.get("hc_compare") or {}).get(k)
                        for k in ("ex7_leader", "preferred_is_hc", "alt_is_hc")
                    },
                    "go_nogo": ra.get("go_nogo"),
                    "charts": ra.get("charts"),
                    "dashboard_ready": (ra.get("dashboard") or {}).get("ready_for_pane"),
                }
    except Exception:
        pass

    if write:
        _write_artifacts(payload, root=root)
        payload["actions_taken"] = [
            f"wrote {SPINE_PATH.relative_to(PROJECT_ROOT)}",
            f"wrote {SPINE_REPORT.relative_to(PROJECT_ROOT)}",
        ]
    return payload


def _write_artifacts(payload: Mapping[str, Any], *, root: Path = PROJECT_ROOT) -> None:
    state_path = root / "data" / "state" / "platform_metrics_spine_latest.json"
    report_path = root / "reports" / "PLATFORM_METRICS_SPINE_LATEST.md"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    report_path.write_text(render_markdown(payload), encoding="utf-8")


def render_markdown(payload: Mapping[str, Any]) -> str:
    go = payload.get("go_nogo") or {}
    runner = payload.get("runner_ops") or {}
    life = payload.get("lifecycle") or {}
    funnel = life.get("funnel") or {}
    choke = life.get("choke_point") or {}
    auto = life.get("automation_readiness") or {}
    book = payload.get("book") or {}
    lines = [
        "# Platform metrics spine",
        "",
        f"**as_of:** `{payload.get('as_of')}`  ",
        f"**measure_only:** `{payload.get('measure_only')}` · **no_live_writes:** `{payload.get('no_live_writes')}`",
        "",
        "## Go / no-go",
        "",
        f"| Gate | Verdict |",
        f"|------|---------|",
        f"| Ops integrity | **{go.get('ops')}** |",
        f"| Money path / scale | **{go.get('money_path')}** |",
        f"| Auto membership | **{go.get('auto_membership')}** |",
        f"| Edge claim allowed | `{go.get('edge_claim_allowed')}` |",
        f"| Promote talk OK | `{go.get('promote_talk_ok')}` |",
        f"| Choke | `{go.get('choke_point')}` — {go.get('choke_why')} |",
        f"| Live swaps | `{go.get('live_membership_swaps')}` |",
        "",
        f"_{go.get('plain_english')}_",
        "",
        "## Runner / rebalance ops",
        "",
        f"- **ops_ok:** `{runner.get('ops_ok')}` reasons={runner.get('ops_reasons')}",
        f"- pid `{runner.get('pid')}` alive=`{runner.get('pid_alive')}` age_h=`{runner.get('state_age_hours')}`",
        f"- rebal_today=`{runner.get('rebal_ran_today')}` last_date=`{runner.get('last_rebalance_date')}`",
        f"- SL coverage=`{runner.get('sl_coverage')}` naked=`{runner.get('naked_bags')}`",
        f"- can_buy=`{runner.get('can_buy_before_next_rebalance')}` mode=`{runner.get('strategy_mode')}` regime=`{runner.get('regime')}`",
        f"- {runner.get('plain_english')}",
        "",
        f"Book snapshot: cash=`{book.get('cash_usd')}` holdings=`{book.get('holdings_usd')}` total=`{book.get('total_usd')}`",
        "",
        "## Pair lifecycle funnel",
        "",
        f"seat **{funnel.get('n_seated')}** → signal **{funnel.get('n_signaled')}** "
        f"({funnel.get('rate_signal_given_seat')}) → fill **{funnel.get('n_filled')}** "
        f"({funnel.get('rate_fill_given_signal')}|sig) → win **{funnel.get('n_filled_win')}** "
        f"/ loss **{funnel.get('n_filled_loss')}** (win|seat={funnel.get('rate_win_given_seat')})",
        "",
        f"**Choke:** `{choke.get('id')}` — {choke.get('why')}",
        "",
        "| Stage | Success local | Key |",
        "|-------|---------------|-----|",
    ]
    for s in life.get("stages") or []:
        key = s.get("id")
        if key == "select":
            detail = f"arm={s.get('preferred_arm')} ex7={_fmt(s.get('ex7'))} HC={s.get('high_confidence')}"
        elif key == "shortlist":
            detail = f"novelty={s.get('novelty_counts')} missfire_n={s.get('missfire_blocked_n')}"
        elif key == "advance":
            detail = (
                f"tryout={s.get('tryout_eligible')} can_buy={s.get('can_buy')} "
                f"L2={s.get('l2_pass')}/{s.get('l2_total')} swaps={s.get('live_membership_swaps')}"
            )
        elif key == "promote":
            detail = (
                f"n={s.get('n_picks')} hit7={_fmt(s.get('hit_rate_7d'))} "
                f"avg7={_fmt(s.get('avg_ret_7d_pct'))}% excess7={_fmt(s.get('excess_vs_remove_7d_pct'))}"
            )
        elif key == "signal":
            detail = f"sig|seat={s.get('rate_signal_given_seat')}"
        elif key == "fill":
            detail = f"fill|sig={s.get('rate_fill_given_signal')} blocked={s.get('n_blocked_no_fill')}"
        elif key == "trade_success":
            detail = (
                f"win={s.get('n_filled_win')} loss={s.get('n_filled_loss')} "
                f"tax$={s.get('process_tax_pnl_sum')} edge={s.get('edge_claim_allowed')}"
            )
        elif key == "disqualify_remove":
            detail = f"idle_n={s.get('n_idle_flagged')} mode={s.get('mode')} hard_eject={s.get('hard_eject')}"
        else:
            detail = s.get("note") or ""
        lines.append(f"| `{key}` | `{s.get('success_local')}` | {detail} |")

    lines += [
        "",
        "## Automation readiness (honest)",
        "",
        f"| Capability | Ready |",
        f"|------------|-------|",
        f"| Auto select (paper arms) | `{auto.get('auto_select_paper')}` |",
        f"| Auto advance tryout door | `{auto.get('auto_advance_tryout')}` |",
        f"| Auto promote to live basket | `{auto.get('auto_promote_live')}` |",
        f"| Auto live membership swaps | `{auto.get('auto_swap_live')}` |",
        f"| Auto DQ hard eject | `{auto.get('auto_disqualify_eject')}` |",
        "",
        f"_{auto.get('note')}_",
        "",
        f"_{life.get('plain_english')}_",
        "",
        "## Optimize hint",
        "",
        _optimize_hint(choke, funnel, runner),
        "",
        "---",
        f"Feeds inventory: see JSON `feeds` key. Plan: `{payload.get('links', {}).get('plan')}`.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3g}"
    return str(v)


def _optimize_hint(choke: Mapping[str, Any], funnel: Mapping[str, Any], runner: Mapping[str, Any]) -> str:
    cid = choke.get("id")
    if not runner.get("ops_ok"):
        return "Fix **ops integrity** first (runner/SL naked) before selection research."
    if cid == "fill":
        return "Optimize **deploy path** (gates, size, limit-first, sent clock) — not more scout names."
    if cid == "trade_success":
        return "Optimize **entry quality + exit/process tax** — win|fill is the bottleneck."
    if cid == "advance":
        return "Optimize **tryout sensor/armor clock** or accept idle; do not force weak fills."
    if cid == "promote":
        return "Tighten **promote criteria** (L2 + novelty + graduation) before new seats."
    if cid == "select":
        return "Paper arm attention only — keep dual-collect; no live swaps."
    return "Keep collecting stamped RTs; no scale claim yet."


def build_live(*, write: bool = True) -> Dict[str, Any]:
    """Convenience: load disk feeds and optionally write artifacts."""
    return build_spine(write=write)
