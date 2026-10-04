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

    msm = _load_json(PROJECT_ROOT / "data" / "state" / "membership_sizing_matrix_latest.json")
    if isinstance(msm, dict):
        rows = msm.get("rows") or []
        block_max = [
            {
                "pair": r.get("pair"),
                "role": r.get("role"),
                "scale_path": r.get("scale_path"),
                "max_add_usd": r.get("max_add_usd"),
                "block_reason": r.get("block_reason"),
                "held_usd": r.get("held_usd"),
            }
            for r in rows
            if isinstance(r, dict) and float(r.get("max_add_usd") or 0) <= 0 and float(r.get("held_usd") or 0) > 5
        ][:12]
        ctx["matrix_block_max_held"] = block_max
        ctx["matrix_regime"] = (msm.get("regime") or msm.get("live_regime") or ctx.get("regime"))
        if msm.get("regime"):
            ctx["regime"] = msm.get("regime")

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
                "Review prior 7d trades + free quest outside history; propose concrete ways to improve "
                "deposit-adj take-home (~5%/mo north star). Prefer less process tax and higher quality "
                "scale/membership over new digs."
            ),
            "rules": [
                "Ground every claim in fact pack numbers or cited state files.",
                "No live config/knob/order writes — suggestions + backlog IDs only.",
                "Honesty over cosmetics; paper MTM ≠ filled PnL.",
                "If N is thin, say so — no edge theater.",
                "Separate process tax vs true alpha miss.",
                "Quest OK: membership matrix, scale-window board, money-arms monitor, regime/add-risk, OPT leaderboard, dwell.",
            ],
            "output_contract": [
                "1) Week scorecard (PnL, WR, tax, util, regime) — 5 lines max",
                "2) What worked / what hurt — bullets with $ or counts",
                "3) Top 3–7 suggestions ranked P0/P1/P2 with: lever, expected effect, evidence, risk, GO needed?",
                "4) Explicit non-suggestions (do not touch)",
                "5) Optional: 1 measurement experiment for next week",
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
    s = payload.get("summary") or {}
    ctx = payload.get("context") or {}
    nav = ctx.get("nav") or {}
    sb = ctx.get("scoreboard") or {}
    wr = s.get("exit_wr")
    wr_s = f"{float(wr)*100:.0f}%" if wr is not None else "—"
    lines = [
        "📊 Analyst weekly 7d trade review",
        f"PnL ${s.get('realized_pnl_usd')} · WR {wr_s} · tax ${s.get('process_tax_usd')} · util {nav.get('util_pct')}%",
        f"Primary B/S {s.get('n_primary_buys')}/{s.get('n_primary_sells')} · same-day loops {s.get('same_day_buy_sell_pair_days')}",
        f"Path {sb.get('path_health') or '—'} · goal {sb.get('goal_label') or '—'} · regime {ctx.get('regime') or sb.get('regime') or '—'}",
    ]
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
    lines.append(f"Full: reports/ANALYST_WEEKLY_TRADE_REVIEW_LATEST.md")
    return "\n".join(lines) + "\n"


def write_artifacts(payload: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_markdown(payload), encoding="utf-8")


def load_latest() -> Optional[Dict[str, Any]]:
    data = _load_json(STATE_PATH)
    return data if isinstance(data, dict) else None
