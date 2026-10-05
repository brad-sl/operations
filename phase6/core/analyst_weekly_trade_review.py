"""
Analyst weekly 7d trade review — fact pack SSOT (measure-only).

Builds a grounded pack from ledger + attribution RT + scoreboard + live path,
so the Sunday analyst agent can suggest return improvements without inventing fills.

Never writes config / knobs / orders.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT

SCHEMA = "analyst_weekly_trade_review_v1"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "analyst_weekly_trade_review_latest.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "ANALYST_WEEKLY_TRADE_REVIEW_LATEST.md"
LEDGER_PATH = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
DEFAULT_LOOKBACK_DAYS = 7
STABLE_TOKENS = ("USDT", "USDC", "USD-USD", "DAI")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _norm_pair(p: str) -> str:
    return str(p or "").strip().upper().replace("_", "-")


def _is_stable_pair(pair: str) -> bool:
    p = _norm_pair(pair)
    if not p or p in ("USD-USD",):
        return True
    base = p.split("-")[0] if "-" in p else p
    return base in ("USDT", "USDC", "DAI", "USD")


def _pnl(row: Mapping[str, Any]) -> Optional[float]:
    for k in ("pnl", "realized_pnl", "pnl_usd"):
        if row.get(k) is not None:
            try:
                return float(row[k])  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
    return None


def _side(row: Mapping[str, Any]) -> str:
    return str(row.get("side") or "").strip().upper()


def _exit_reason(row: Mapping[str, Any]) -> str:
    r = str(row.get("exit_reason") or row.get("reason") or row.get("done_reason") or "").strip()
    return r or "unknown"


def _read_ledger(path: Path, since: datetime, until: datetime) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            ts = _parse_ts(row.get("timestamp") or row.get("ts") or row.get("entry_ts"))
            if ts is None or ts < since or ts > until:
                continue
            row = dict(row)
            row["_ts"] = ts
            row["_pair"] = _norm_pair(str(row.get("pair") or row.get("product_id") or ""))
            out.append(row)
    except OSError:
        return []
    return out


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8") or "null")
    except (OSError, json.JSONDecodeError):
        return None


def _rel_or_abs(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except (ValueError, OSError):
        return str(path)


def _classify_exit_bucket(row: Mapping[str, Any]) -> str:
    try:
        from phase6.core.tryout_exit_taxonomy import classify_exit_reason_attr

        return str(classify_exit_reason_attr(row) or "other")
    except Exception:
        r = _exit_reason(row).lower()
        if "scale_window" in r or "tryout_scale" in r:
            return "scale_window_eject"
        if "stop" in r or "sl_" in r:
            return "sl_exchange"
        if "trail" in r or "take_profit" in r or "tp_" in r:
            return "tp_profit"
        if "dust" in r:
            return "dust_sweep"
        if "rotation" in r:
            return "rotation"
        return "other"


def _is_process_tax(bucket: str, reason: str) -> bool:
    b = (bucket or "").lower()
    r = (reason or "").lower()
    if b in ("sl_exchange", "dust_sweep", "dust"):
        return True
    if "dust" in r or "stop_loss" in r or "exchange_stop" in r:
        return True
    return False


def summarize_legs(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    buys = [r for r in rows if _side(r) == "BUY"]
    sells = [r for r in rows if _side(r) == "SELL"]
    primary_buys = [r for r in buys if not _is_stable_pair(str(r.get("_pair") or r.get("pair") or ""))]
    primary_sells = [r for r in sells if not _is_stable_pair(str(r.get("_pair") or r.get("pair") or ""))]

    pnls: List[float] = []
    green = red = flat = 0
    tax_n = 0
    tax_sum = 0.0
    non_tax_n = 0
    non_tax_sum = 0.0
    by_bucket: Counter = Counter()
    by_reason: Counter = Counter()
    by_pair_pnl: Dict[str, float] = defaultdict(float)
    by_pair_n: Counter = Counter()
    sell_rows_out: List[Dict[str, Any]] = []

    for s in primary_sells:
        pair = _norm_pair(str(s.get("_pair") or s.get("pair") or "?"))
        reason = _exit_reason(s)
        bucket = _classify_exit_bucket(s)
        p = _pnl(s)
        by_bucket[bucket] += 1
        by_reason[reason] += 1
        by_pair_n[pair] += 1
        tax = _is_process_tax(bucket, reason)
        if p is not None:
            pnls.append(p)
            by_pair_pnl[pair] += p
            if p > 0:
                green += 1
            elif p < 0:
                red += 1
            else:
                flat += 1
            if tax:
                tax_n += 1
                tax_sum += p
            else:
                non_tax_n += 1
                non_tax_sum += p
        ts_raw = s.get("_ts")
        if isinstance(ts_raw, datetime):
            ts_s = ts_raw.isoformat()
        else:
            ts_s = str(s.get("timestamp") or "")
        sell_rows_out.append(
            {
                "pair": pair,
                "ts": ts_s,
                "side": "SELL",
                "reason": reason,
                "bucket": bucket,
                "process_tax": tax,
                "pnl": round(p, 4) if p is not None else None,
            }
        )

    # same-day buy→sell loops (tryout churn signal)
    same_day_loops = 0
    buys_by_pair_day: Dict[Tuple[str, str], int] = defaultdict(int)
    sells_by_pair_day: Dict[Tuple[str, str], int] = defaultdict(int)
    for r in primary_buys + primary_sells:
        ts = r.get("_ts")
        if not isinstance(ts, datetime):
            continue
        day = ts.astimezone(timezone.utc).date().isoformat()
        pair = _norm_pair(str(r.get("_pair") or r.get("pair") or ""))
        key = (pair, day)
        if _side(r) == "BUY":
            buys_by_pair_day[key] += 1
        else:
            sells_by_pair_day[key] += 1
    for key, n_b in buys_by_pair_day.items():
        n_s = sells_by_pair_day.get(key, 0)
        if n_b >= 1 and n_s >= 1:
            same_day_loops += 1

    n_exits_with_pnl = green + red + flat
    wr = (green / n_exits_with_pnl) if n_exits_with_pnl else None
    pair_pnl_sorted = sorted(
        ({"pair": p, "pnl_usd": round(v, 4), "n_sells": int(by_pair_n.get(p, 0))} for p, v in by_pair_pnl.items()),
        key=lambda x: x["pnl_usd"],
    )

    return {
        "n_legs": len(rows),
        "n_buys": len(buys),
        "n_sells": len(sells),
        "n_primary_buys": len(primary_buys),
        "n_primary_sells": len(primary_sells),
        "n_stable_legs": len(rows) - len(primary_buys) - len(primary_sells),
        "realized_pnl_usd": round(sum(pnls), 4) if pnls else 0.0,
        "n_green_exits": green,
        "n_red_exits": red,
        "n_flat_exits": flat,
        "exit_wr": round(wr, 4) if wr is not None else None,
        "process_tax_n": tax_n,
        "process_tax_usd": round(tax_sum, 4),
        "non_tax_n": non_tax_n,
        "non_tax_usd": round(non_tax_sum, 4),
        "exit_buckets": dict(by_bucket.most_common(12)),
        "exit_reasons_top": by_reason.most_common(12),
        "pairs_by_activity": by_pair_n.most_common(12),
        "pairs_pnl_worst": pair_pnl_sorted[:8],
        "pairs_pnl_best": list(reversed(pair_pnl_sorted[-8:])) if pair_pnl_sorted else [],
        "same_day_buy_sell_pair_days": same_day_loops,
        "sells_detail": sorted(sell_rows_out, key=lambda r: str(r.get("ts") or ""), reverse=True)[:40],
    }


def _seed_hypotheses(summary: Mapping[str, Any], context: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Deterministic seed ideas for the agent — not final recommendations."""
    seeds: List[Dict[str, Any]] = []
    buckets = summary.get("exit_buckets") or {}
    tax = float(summary.get("process_tax_usd") or 0.0)
    non_tax = float(summary.get("non_tax_usd") or 0.0)
    wr = summary.get("exit_wr")
    same_day = int(summary.get("same_day_buy_sell_pair_days") or 0)
    eject_n = int(buckets.get("scale_window_eject") or buckets.get("tryout_eject") or 0)
    # also count reason-tagged ejects
    for k, v in (summary.get("exit_reasons_top") or []):
        if "scale_window" in str(k).lower() or "tryout_scale" in str(k).lower():
            eject_n = max(eject_n, int(v))

    if tax < -1.0 and abs(tax) > abs(non_tax):
        seeds.append(
            {
                "id": "seed_cut_process_tax",
                "theme": "process_tax",
                "hint": (
                    f"Process-tax exits sum ${tax:.2f} vs non-tax ${non_tax:.2f} — "
                    "rank SL leakage / dust / mis-tags before seeking new alpha."
                ),
                "priority": "P1",
            }
        )
    if eject_n >= 3:
        seeds.append(
            {
                "id": "seed_tryout_intake_quality",
                "theme": "tryout_funnel",
                "hint": (
                    f"~{eject_n} scale-window/tryout ejects in window — intake (discipline/knife/RSI door) "
                    "or kindling bar may be admitting shells that never clear scale."
                ),
                "priority": "P1",
            }
        )
    if same_day >= 2:
        seeds.append(
            {
                "id": "seed_same_day_churn",
                "theme": "tryout_churn",
                "hint": (
                    f"{same_day} pair-days with same-day buy+sell — dead-kindling loop is working but "
                    "fee+cooloff tax may dominate; check seat quality vs eject bar."
                ),
                "priority": "P2",
            }
        )
    if wr is not None and float(wr) < 0.45 and int(summary.get("n_primary_sells") or 0) >= 5:
        seeds.append(
            {
                "id": "seed_exit_wr",
                "theme": "exit_quality",
                "hint": (
                    f"Primary exit WR ~{float(wr)*100:.0f}% on n={summary.get('n_primary_sells')} — "
                    "split green meat exits vs tax/eject; do not chase size until WR path is honest."
                ),
                "priority": "P1",
            }
        )
    worst = (summary.get("pairs_pnl_worst") or [])[:3]
    if worst and float(worst[0].get("pnl_usd") or 0) < -2.0:
        names = ", ".join(f"{w.get('pair')} ${w.get('pnl_usd')}" for w in worst)
        seeds.append(
            {
                "id": "seed_pair_leak",
                "theme": "pair_leak",
                "hint": f"Worst pair PnL this week: {names}. Check membership career + cooloff stack.",
                "priority": "P2",
            }
        )
    util = context.get("util_pct")
    regime = str(context.get("regime") or "")
    if util is not None and float(util) < 25 and "flat" in regime.lower():
        seeds.append(
            {
                "id": "seed_underdeploy_flat",
                "theme": "growth_util",
                "hint": (
                    f"Util ~{float(util):.0f}% in {regime or 'flat'} — growth is starved by cash reserve / "
                    "add-risk caps / door floors, not missing trade count alone. Matrix max_add before new digs."
                ),
                "priority": "P1",
            }
        )
    msm_raw = context.get("membership_sizing_matrix") if isinstance(context, dict) else None
    msm: Dict[str, Any] = msm_raw if isinstance(msm_raw, dict) else {}
    block_n = len(msm.get("block_max_held") or (context.get("matrix_block_max_held") if isinstance(context, dict) else None) or [])
    inc_n = int(msm.get("n_inconsistent") or 0)
    if block_n >= 2:
        seeds.append(
            {
                "id": "seed_matrix_block_max",
                "theme": "matrix_room",
                "hint": (
                    f"Matrix: {block_n} held bags with max_add=$0 — review binding budgets + role_law vs "
                    "flat add-risk knobs; matrix is rulebook not stone (optimize w/ Brad GO)."
                ),
                "priority": "P1",
            }
        )
    if inc_n > 0:
        seeds.append(
            {
                "id": "seed_matrix_inconsistent",
                "theme": "matrix_policy_drift",
                "hint": f"Matrix inconsistencies n={inc_n} — fix policy drift before adding new digs.",
                "priority": "P0",
            }
        )
    # E-EJECT-COHORT-CARD (measure): % shells that ever cleared live kindling.
    eject_raw = context.get("eject_cohort_card") if isinstance(context, dict) else None
    eject: Dict[str, Any] = eject_raw if isinstance(eject_raw, dict) else {}
    try:
        n_ej = int(eject.get("n_ejects") or 0)
    except (TypeError, ValueError):
        n_ej = 0
    pct = eject.get("pct_cleared_live_kindling")
    if n_ej >= 3 and pct is not None:
        try:
            pct_f = float(pct)
        except (TypeError, ValueError):
            pct_f = None
        if pct_f is not None and pct_f <= 0.05:
            seeds.append(
                {
                    "id": "seed_eject_cohort_zero_kindling",
                    "theme": "tryout_funnel",
                    "hint": (
                        f"E-EJECT-COHORT-CARD: {n_ej} scale-window ejects, "
                        f"{pct_f * 100:.0f}% ever cleared live kindling — funnel is seat→eject, "
                        "not seat→prove→add. Review hold/phase/structure/block (measure; no knobs)."
                    ),
                    "priority": "P1",
                }
            )
    if not seeds:
        seeds.append(
            {
                "id": "seed_baseline_growth",
                "theme": "growth",
                "hint": (
                    "Book is treading water: map binding growth gate (door / kindling / add-risk / membership) "
                    "from membership sizing matrix + 7d fills — one lever, not five."
                ),
                "priority": "P2",
            }
        )
    return seeds


def _matrix_snapshot_for_review() -> Dict[str, Any]:
    """Fresh membership sizing matrix slice for weekly analyst (rulebook + live room)."""
    out: Dict[str, Any] = {
        "product_note": (
            "Membership sizing matrix is the live rulebook for class/role/scale-path/regime room — "
            "not stone. Weekly analyst must review rules + live room and may suggest optimizations "
            "(measure-only; Brad GO before knobs)."
        ),
        "paths": {
            "config": "config/membership_sizing_matrix.json",
            "state": "data/state/membership_sizing_matrix_latest.json",
            "docs": "docs/features/MEMBERSHIP_SIZING_MATRIX.md",
            "cli": "python scripts/phase6/run_membership_sizing_matrix.py --filter block_max",
        },
    }
    try:
        from phase6.core.membership_sizing_matrix import build_matrix, load_config, load_regime_sheet

        matrix = build_matrix(persist=True)
        cfg = load_config()
        regime_sheet = load_regime_sheet()
        rows = [r for r in (matrix.get("rows") or []) if isinstance(r, dict)]
        by_role: Dict[str, int] = Counter(str(r.get("role") or "unknown") for r in rows)
        by_scale: Dict[str, int] = Counter(
            str(r.get("scale_path_live") or r.get("scale_path") or r.get("scale_path_law") or "none")
            for r in rows
        )
        by_class: Dict[str, int] = Counter(str(r.get("class") or "unknown") for r in rows)
        block_max = []
        kindling = []
        ballast = []
        for r in rows:
            held = float(r.get("held_usd") or 0)
            max_add = float(r.get("max_add_usd") or 0)
            slim = {
                "pair": r.get("pair"),
                "class": r.get("class"),
                "role": r.get("role"),
                "scale_path_law": r.get("scale_path_law"),
                "scale_path_live": r.get("scale_path_live") or r.get("scale_path"),
                "held_usd": r.get("held_usd"),
                "max_add_usd": r.get("max_add_usd"),
                "block_reason": r.get("block_reason") or r.get("binding_budget"),
                "pyramid_allowed": r.get("pyramid_allowed"),
                "target_pair_weight": r.get("target_pair_weight"),
                "target_pair_usd": r.get("target_pair_usd"),
                "can_eject_scale_window": r.get("can_eject_scale_window"),
                "membership_remove": r.get("membership_remove"),
                "kindling_eligible": r.get("kindling_eligible"),
                "inconsistencies": r.get("inconsistencies") or [],
            }
            if held > 5 and max_add <= 0:
                block_max.append(slim)
            if str(slim.get("scale_path_law") or "") == "kindling_once" or slim.get("kindling_eligible"):
                if held > 0 or slim.get("scale_path_live") not in (None, "none"):
                    kindling.append(slim)
            if str(slim.get("role") or "").startswith(("ballast", "preserve")) or slim.get("role") in (
                "ballast_core",
                "preserve_ballast",
            ):
                if held > 0:
                    ballast.append(slim)
        inconsistencies = matrix.get("inconsistencies") or []
        if not inconsistencies:
            inconsistencies = []
            for r in rows:
                for inc in r.get("inconsistencies") or []:
                    inconsistencies.append({"pair": r.get("pair"), "issue": inc})
        live_ar = regime_sheet.get("live_add_risk") or {}
        out.update(
            {
                "as_of": matrix.get("as_of") or matrix.get("generated_at"),
                "regime": matrix.get("regime") or regime_sheet.get("live_regime"),
                "n_rows": len(rows),
                "counts_by_role": dict(by_role),
                "counts_by_class": dict(by_class),
                "counts_by_scale_path": dict(by_scale),
                "role_law": cfg.get("role_law") or {},
                "regime_live_add_risk": {
                    "allow_pyramid": live_ar.get("allow_pyramid"),
                    "k_profit": live_ar.get("k_profit"),
                    "h_add": live_ar.get("h_add"),
                    "H_book": live_ar.get("H_book"),
                    "target_pair_weight": live_ar.get("target_pair_weight"),
                    "rebalance_cap_usd": live_ar.get("rebalance_cap_usd"),
                },
                "regime_sheet_keys": sorted(
                    [k for k in (regime_sheet.get("by_regime") or regime_sheet.get("regimes") or {})]
                )[:12]
                if isinstance(regime_sheet.get("by_regime") or regime_sheet.get("regimes"), dict)
                else list((regime_sheet or {}).keys())[:12],
                "block_max_held": block_max[:16],
                "kindling_rows": kindling[:12],
                "ballast_held": ballast[:12],
                "inconsistencies": inconsistencies[:20],
                "n_inconsistent": len(inconsistencies),
                "held_rows": [
                    {
                        "pair": r.get("pair"),
                        "role": r.get("role"),
                        "class": r.get("class"),
                        "held_usd": r.get("held_usd"),
                        "max_add_usd": r.get("max_add_usd"),
                        "scale_path_law": r.get("scale_path_law"),
                        "block_reason": r.get("block_reason") or r.get("binding_budget"),
                    }
                    for r in rows
                    if float(r.get("held_usd") or 0) > 1
                ][:20],
            }
        )
    except Exception as e:
        stale = _load_json(PROJECT_ROOT / "data" / "state" / "membership_sizing_matrix_latest.json")
        out["error"] = str(e)[:240]
        if isinstance(stale, dict):
            out["stale_as_of"] = stale.get("as_of")
            out["n_rows_stale"] = len(stale.get("rows") or [])
    return out


def _live_context() -> Dict[str, Any]:
    ctx: Dict[str, Any] = {}
    try:
        from phase6.research.analyst_daily_scoreboard import build_scoreboard

        board = build_scoreboard()
        goal = board.get("goal") or {}
        path = board.get("path") or {}
        pipe = board.get("pipeline") or {}
        mp = board.get("month_path") or {}
        t7 = (board.get("trades") or {}).get("7d") or {}
        ctx["scoreboard"] = {
            "goal_label": goal.get("label"),
            "goal_score": goal.get("score_0_100"),
            "path_health": path.get("path_health"),
            "recent_return_pct": path.get("recent_return_pct"),
            "window_return_pct": path.get("window_return_pct"),
            "regime": pipe.get("live_regime"),
            "mtd_return_pct": mp.get("current_mtd_return_pct"),
            "mtd_process_tax_usd": mp.get("current_mtd_process_tax_usd"),
            "trades_7d_realized": t7.get("realized_pnl_usd"),
            "trades_7d_n": t7.get("n_trades"),
            "material_flags": board.get("material_flags") or [],
        }
        ctx["regime"] = pipe.get("live_regime")
    except Exception as e:
        ctx["scoreboard_error"] = str(e)[:200]

    runner = _load_json(PROJECT_ROOT / "data" / "state" / "phase6_runner_state.json") or {}
    if isinstance(runner, dict):
        nav = runner.get("capital_nav_snapshot") or {}
        try:
            equity = float(nav.get("equity") or nav.get("nav") or 0) or None
        except (TypeError, ValueError):
            equity = None
        try:
            open_usd = float(nav.get("open_positions_usd") or nav.get("invested_usd") or 0) or None
        except (TypeError, ValueError):
            open_usd = None
        util = None
        if equity and equity > 0 and open_usd is not None:
            util = round(100.0 * open_usd / equity, 2)
        ctx["nav"] = {
            "equity": equity,
            "open_usd": open_usd,
            "util_pct": util,
            "as_of": nav.get("as_of") or runner.get("updated_at"),
        }
        ctx["util_pct"] = util

    # Membership sizing matrix is in weekly analyst scope (rulebook, not stone).
    msm = _matrix_snapshot_for_review()
    if isinstance(msm, dict) and msm:
        ctx["membership_sizing_matrix"] = msm
        if msm.get("regime"):
            ctx["regime"] = msm.get("regime")
        ctx["matrix_block_max_held"] = msm.get("block_max_held") or []
        ctx["matrix_regime"] = msm.get("regime")

    # E-EJECT-COHORT-CARD: hold/phase/structure/kindling/% cleared (measure-only).
    try:
        from phase6.core.tryout_eject_cohort_card import run_card, snapshot_for_analyst

        eject_payload = run_card(lookback_days=14.0, write=True)
        eject_snap = snapshot_for_analyst(eject_payload)
        if isinstance(eject_snap, dict) and eject_snap:
            ctx["eject_cohort_card"] = eject_snap
    except Exception as e:
        stale = _load_json(PROJECT_ROOT / "data" / "state" / "tryout_eject_cohort_weekly.json")
        if isinstance(stale, dict) and stale:
            try:
                from phase6.core.tryout_eject_cohort_card import snapshot_for_analyst

                ctx["eject_cohort_card"] = snapshot_for_analyst(stale)
            except Exception:
                ctx["eject_cohort_card"] = {
                    "error": str(e)[:200],
                    "stale_as_of": stale.get("as_of"),
                    "n_ejects": (stale.get("scoreboard") or {}).get("n_ejects"),
                }
        else:
            ctx["eject_cohort_card"] = {"error": str(e)[:200]}

    attr = _load_json(PROJECT_ROOT / "data" / "state" / "attribution_rt_weekly_latest.json")
    if isinstance(attr, dict):
        ctx["attribution_rt"] = {
            "as_of": attr.get("as_of"),
            "summary": attr.get("summary"),
            "coverage_audit": attr.get("coverage_audit"),
        }

    money = _load_json(PROJECT_ROOT / "data" / "state" / "tryout_money_arms_monitor_latest.json")
    if isinstance(money, dict):
        ctx["money_arms_monitor"] = {
            "as_of": money.get("as_of") or money.get("updated"),
            "n_anomalies": money.get("n_anomalies") or money.get("anomaly_count"),
            "plain": money.get("plain_english") or money.get("telegram_summary"),
        }

    mm = _load_json(PROJECT_ROOT / "data" / "state" / "membership_manager_latest.json")
    if isinstance(mm, dict):
        ctx["membership_manager"] = {
            "as_of": mm.get("as_of") or mm.get("updated"),
            "plain_english": mm.get("plain_english"),
            "last_action": mm.get("last_action") or mm.get("action"),
        }
    return ctx


def build_fact_pack(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ledger_path: Path = LEDGER_PATH,
    now: Optional[datetime] = None,
    write: bool = True,
    refresh_attribution: bool = True,
) -> Dict[str, Any]:
    now = now or _utc_now()
    since = now - timedelta(days=int(lookback_days))

    if refresh_attribution:
        try:
            from phase6.core.attribution_rt_weekly import build_attribution_rt_weekly

            build_attribution_rt_weekly(write=True, lookback_days=int(lookback_days), now=now)
        except Exception:
            pass

    rows = _read_ledger(ledger_path, since=since, until=now)
    summary = summarize_legs(rows)
    context = _live_context()
    seeds = _seed_hypotheses(summary, context)

    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": now.isoformat(),
        "lookback_days": int(lookback_days),
        "window_start": since.isoformat(),
        "window_end": now.isoformat(),
        "measure_only": True,
        "no_knobs": True,
        "summary": summary,
        "context": context,
        "seed_hypotheses": seeds,
        "agent_brief": {
            "mission": (
                "Review prior 7d trades + Membership Sizing Matrix rulebook + free quest outside history; "
                "propose concrete ways to improve deposit-adj take-home (~5%/mo north star). Prefer less "
                "process tax and higher quality scale/membership over new digs. Matrix is the current "
                "regime rulebook — not stone; suggest optimizations with evidence."
            ),
            "rules": [
                "Ground every claim in fact pack numbers or cited state files.",
                "No live config/knob/order writes — suggestions + backlog IDs only.",
                "Honesty over cosmetics; paper MTM ≠ filled PnL.",
                "If N is thin, say so — no edge theater.",
                "Separate process tax vs true alpha miss.",
                "MUST review membership_sizing_matrix in context (role_law, regime add-risk, block_max, inconsistencies, kindling vs ballast).",
                "MUST cite eject_cohort_card when scale-window ejects >0: % cleared live kindling, top kindling_block, fee-aware net (E-EJECT-COHORT-CARD is shipped measure SSOT — not a new experiment idea).",
                "Quest OK: matrix CLI/API, eject cohort card, scale-window board, money-arms monitor, regime/add-risk, OPT leaderboard, dwell, prior week continuity/notepad.",
                "Use job notepad + continuity for week-over-week memory (open suggestions, GO status).",
                "Brad 2026-10-04: Telegram MUST open with Plain English section 0 before any shorthand scorecard — no second-pass decode required.",
            ],
            "output_contract": [
                "0) PLAIN ENGLISH FIRST (mandatory) — 6–10 short lines Brad can read without a glossary: week $ + win-rate honest/fee-aware; what made vs burned money; growing vs treading water vs leaking + why; what is blocked in plain words; what needs Brad GO vs already self-running; one bottom-line stay/fix/don't-touch. Decode any later shorthand here (WR util MTD gap-to-5% eject kindling ballast block_max min_move cash_slice STABILIZE flat-B CF TP RT-fees).",
                "1) Week scorecard (PnL, WR, tax, util, regime) — 5 lines max",
                "2) What worked / what hurt — bullets with $ or counts",
                "3) Matrix rulebook review — what binds growth; any policy drift; 1–3 matrix optimization ideas",
                "4) Eject cohort card (E-EJECT-COHORT-CARD) — n ejects, % cleared kindling, top blocks, fee net; plain one-liner",
                "5) Top 3–7 suggestions ranked P0/P1/P2 with: lever, expected effect, evidence, risk, GO needed?",
                "6) Explicit non-suggestions (do not touch)",
                "7) Optional: 1 NEW measurement experiment only if gap remains (do not re-propose E-EJECT-COHORT-CARD — it is live)",
                "8) Update notepad keys: last_scorecard, open_suggestions, matrix_notes, eject_cohort (short)",
            ],
        },
        "paths": {
            "state": _rel_or_abs(STATE_PATH),
            "report": _rel_or_abs(REPORT_PATH),
            "ledger": _rel_or_abs(ledger_path),
        },
    }
    if write:
        write_artifacts(payload)
    return payload


def render_markdown(payload: Mapping[str, Any]) -> str:
    s = payload.get("summary") or {}
    ctx = payload.get("context") or {}
    sb = ctx.get("scoreboard") or {}
    nav = ctx.get("nav") or {}
    lines = [
        "# Analyst weekly 7d trade review (fact pack)",
        "",
        f"**As of:** {payload.get('as_of')}",
        f"**Window:** {payload.get('window_start')} → {payload.get('window_end')} ({payload.get('lookback_days')}d)",
        f"**Schema:** `{payload.get('schema')}`",
        "",
        "## Scorecard",
        "",
        f"- Primary buys/sells: **{s.get('n_primary_buys')}** / **{s.get('n_primary_sells')}** (stable legs {s.get('n_stable_legs')})",
        f"- Realized PnL (primary exits w/ pnl): **${s.get('realized_pnl_usd')}**",
        f"- Exit WR: **{s.get('exit_wr')}** (green {s.get('n_green_exits')} / red {s.get('n_red_exits')} / flat {s.get('n_flat_exits')})",
        f"- Process tax: n={s.get('process_tax_n')} sum=**${s.get('process_tax_usd')}** · non-tax n={s.get('non_tax_n')} sum=**${s.get('non_tax_usd')}**",
        f"- Same-day buy+sell pair-days: **{s.get('same_day_buy_sell_pair_days')}**",
        f"- Goal/path (scoreboard): **{sb.get('goal_label')}** / **{sb.get('path_health')}** · recent {sb.get('recent_return_pct')}%",
        f"- Regime: **{ctx.get('regime') or sb.get('regime') or '—'}** · util **{nav.get('util_pct')}%** · equity ~${nav.get('equity')}",
        "",
        "## Exit buckets",
        "",
        f"```{json.dumps(s.get('exit_buckets') or {}, indent=2)}```",
        "",
        "## Exit reasons (top)",
        "",
    ]
    for reason, n in s.get("exit_reasons_top") or []:
        lines.append(f"- `{reason}` × {n}")
    lines.extend(["", "## Pair PnL (worst → best head)", ""])
    for row in s.get("pairs_pnl_worst") or []:
        lines.append(f"- {row.get('pair')}: ${row.get('pnl_usd')} (sells={row.get('n_sells')})")
    best = s.get("pairs_pnl_best") or []
    if best:
        lines.append("")
        lines.append("Best:")
        for row in best[:5]:
            lines.append(f"- {row.get('pair')}: ${row.get('pnl_usd')} (sells={row.get('n_sells')})")
    lines.extend(["", "## Seed hypotheses (agent starting points)", ""])
    for h in payload.get("seed_hypotheses") or []:
        lines.append(f"- **{h.get('priority')}** `{h.get('id')}` ({h.get('theme')}): {h.get('hint')}")
    eject = (ctx.get("eject_cohort_card") or {}) if isinstance(ctx, dict) else {}
    if eject and not eject.get("error"):
        lines.extend(
            [
                "",
                "## E-EJECT-COHORT-CARD (measure SSOT)",
                "",
                f"- {eject.get('plain') or '—'}",
                f"- n_ejects=**{eject.get('n_ejects')}** · % cleared live kindling=**{eject.get('pct_cleared_live_kindling')}** "
                f"· paper_not_live=**{eject.get('n_paper_scaled_not_live')}**",
                f"- structure false/unknown: **{eject.get('n_structure_false')}** / **{eject.get('n_structure_unknown')}**",
                f"- hold_h mean/median: **{eject.get('hold_h_mean')}** / **{eject.get('hold_h_median')}**",
                f"- fee-aware net **${eject.get('pnl_net_usd')}** · RT fees **${eject.get('rt_fee_usd')}** · "
                f"fee-green **{eject.get('n_fee_aware_green')}** · wipe **{eject.get('n_gross_green_net_red')}**",
                f"- top blocks: `{json.dumps(eject.get('kindling_block_top') or [])}`",
                f"- paths: state `{eject.get('state_path')}` · report `{eject.get('report_path')}`",
                "",
            ]
        )
    elif eject.get("error"):
        lines.extend(["", f"## E-EJECT-COHORT-CARD error: {eject.get('error')}", ""])
    msm = (ctx.get("membership_sizing_matrix") or {}) if isinstance(ctx, dict) else {}
    if msm:
        lines.extend(
            [
                "",
                "## Membership sizing matrix (rulebook — not stone)",
                "",
                str(msm.get("product_note") or ""),
                "",
                f"- Regime: **{msm.get('regime')}** · rows **{msm.get('n_rows')}** · inconsistent **{msm.get('n_inconsistent')}**",
                f"- Role counts: `{json.dumps(msm.get('counts_by_role') or {})}`",
                f"- Scale-path counts: `{json.dumps(msm.get('counts_by_scale_path') or {})}`",
                f"- Live add-risk: `{json.dumps(msm.get('regime_live_add_risk') or {})}`",
                "",
                "### Held bags",
                "",
            ]
        )
        for r in msm.get("held_rows") or []:
            lines.append(
                f"- {r.get('pair')}: role={r.get('role')} held=${r.get('held_usd')} "
                f"max_add=${r.get('max_add_usd')} path={r.get('scale_path_law')} "
                f"block={r.get('block_reason')}"
            )
        lines.extend(["", "### Block-max held (max_add=$0)", ""])
        for r in msm.get("block_max_held") or []:
            lines.append(
                f"- {r.get('pair')}: {r.get('role')} held=${r.get('held_usd')} · {r.get('block_reason')}"
            )
        if msm.get("inconsistencies"):
            lines.extend(["", "### Inconsistencies", ""])
            for inc in msm.get("inconsistencies") or []:
                if isinstance(inc, dict):
                    lines.append(f"- {inc.get('pair')}: {inc.get('issue')}")
                else:
                    lines.append(f"- {inc}")
        lines.extend(
            [
                "",
                f"CLI: `{((msm.get('paths') or {}).get('cli'))}`",
                f"Docs: `{((msm.get('paths') or {}).get('docs'))}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Agent brief",
            "",
            str((payload.get("agent_brief") or {}).get("mission") or ""),
            "",
            "Rules:",
        ]
    )
    for r in (payload.get("agent_brief") or {}).get("rules") or []:
        lines.append(f"- {r}")
    lines.extend(["", "Output contract:"])
    for r in (payload.get("agent_brief") or {}).get("output_contract") or []:
        lines.append(f"- {r}")
    lines.extend(
        [
            "",
            "## Recent primary sells (detail head)",
            "",
            "| pair | ts | bucket | tax | pnl | reason |",
            "|------|----|--------|-----|-----|--------|",
        ]
    )
    for r in (s.get("sells_detail") or [])[:25]:
        lines.append(
            "| {pair} | {ts} | {bucket} | {tax} | {pnl} | {reason} |".format(
                pair=r.get("pair"),
                ts=str(r.get("ts") or "")[:19],
                bucket=r.get("bucket"),
                tax="Y" if r.get("process_tax") else "",
                pnl=r.get("pnl"),
                reason=str(r.get("reason") or "")[:40],
            )
        )
    lines.extend(
        [
            "",
            f"State: `{_rel_or_abs(STATE_PATH)}`",
            f"Report: `{_rel_or_abs(REPORT_PATH)}`",
            "",
            "**Measure-only.** Suggestions require Brad GO before knobs.",
            "",
        ]
    )
    return "\n".join(lines)


def format_tg_card(payload: Mapping[str, Any], *, suggestions: Optional[Sequence[str]] = None) -> str:
    """Short no_agent fallback card. Prefer agent path which opens with plain English."""
    s = payload.get("summary") or {}
    ctx = payload.get("context") or {}
    nav = ctx.get("nav") or {}
    sb = ctx.get("scoreboard") or {}
    wr = s.get("exit_wr")
    wr_s = f"{float(wr)*100:.0f}%" if wr is not None else "—"
    msm = ctx.get("membership_sizing_matrix") or {}
    pnl = s.get("realized_pnl_usd")
    tax = s.get("process_tax_usd")
    util = nav.get("util_pct")
    path = sb.get("path_health") or "—"
    goal = sb.get("goal_label") or "—"
    regime = ctx.get("regime") or sb.get("regime") or "—"
    lines = [
        "Analyst weekly 7d — plain English",
        (
            f"Closed-trade P&L about ${pnl} this week; win rate on exits {wr_s} "
            f"(thin sample — not a skill claim)."
        ),
        (
            f"Tagged process tax ${tax}. Book using ~{util}% of capital. "
            f"Market posture: {regime}; path {path}; goal label {goal}."
        ),
        (
            f"Primary buys/sells {s.get('n_primary_buys')}/{s.get('n_primary_sells')}; "
            f"same-day buy+sell pair-days {s.get('same_day_buy_sell_pair_days')} "
            f"(churn signal if high)."
        ),
        (
            f"Sizing matrix: {msm.get('n_rows')} rows; "
            f"{len(msm.get('block_max_held') or [])} held names at add-cap; "
            f"{msm.get('n_inconsistent')} rule mismatches."
        ),
    ]
    eject = ctx.get("eject_cohort_card") or {}
    if eject and not eject.get("error"):
        pct = eject.get("pct_cleared_live_kindling")
        pct_s = "—" if pct is None else f"{float(pct) * 100:.0f}%"
        lines.append(
            f"Eject cohort: {eject.get('n_ejects')} shells; {pct_s} ever cleared kindling; "
            f"fee-aware net ${eject.get('pnl_net_usd')} (fees ${eject.get('rt_fee_usd')})."
        )
    lines.extend(
        [
            "Shorthand card follows for scanners; full plain decode is the Sunday agent report.",
            f"PnL ${pnl} · WR {wr_s} · tax ${tax} · util {util}%",
            f"Primary B/S {s.get('n_primary_buys')}/{s.get('n_primary_sells')} · same-day loops {s.get('same_day_buy_sell_pair_days')}",
            f"Path {path} · goal {goal} · regime {regime}",
            (
                f"Matrix: rows {msm.get('n_rows')} · block_max_held {len(msm.get('block_max_held') or [])} · "
                f"inconsistent {msm.get('n_inconsistent')} · pyramid {((msm.get('regime_live_add_risk') or {}).get('allow_pyramid'))}"
            ),
        ]
    )
    if eject and not eject.get("error"):
        lines.append(
            f"Eject card: n={eject.get('n_ejects')} · %kindling={eject.get('pct_cleared_live_kindling')} · "
            f"net=${eject.get('pnl_net_usd')}"
        )
    if suggestions:
        lines.append("Top ideas:")
        for i, sug in enumerate(list(suggestions)[:5], 1):
            lines.append(f"{i}. {sug}")
    else:
        seeds = payload.get("seed_hypotheses") or []
        if seeds:
            lines.append("Seed themes:")
            for i, h in enumerate(seeds[:4], 1):
                lines.append(f"{i}. [{h.get('priority')}] {h.get('theme')}: {str(h.get('hint') or '')[:120]}")
    lines.append("Full: reports/ANALYST_WEEKLY_TRADE_REVIEW_LATEST.md")
    lines.append("Agent plain-English SSOT: reports/ANALYST_WEEKLY_TRADE_REVIEW_AGENT_LATEST.md")
    return "\n".join(lines) + "\n"


def write_artifacts(payload: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_markdown(payload), encoding="utf-8")


def load_latest() -> Optional[Dict[str, Any]]:
    data = _load_json(STATE_PATH)
    return data if isinstance(data, dict) else None
