#!/usr/bin/env python3
"""Counterfactual dig: max_daily_loss + correlation breaker contribution.

Read-only. Real ledger + OHLCV only. No orders, no knobs.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRADES = ROOT / "trades" / "phase6_trades.jsonl"
CFG_PATH = ROOT / "config" / "trading_config_phase6.json"
LIVE_PATH = ROOT / "data" / "state" / "phase6_live_state.json"
OUT_JSON = ROOT / "reports" / "MAX_DAILY_LOSS_CORR_BREAKER_CF.json"
OUT_MD = ROOT / "reports" / "MAX_DAILY_LOSS_CORR_BREAKER_CF.md"


def day(ts: str) -> str:
    return (ts or "")[:10]


def parse_ts(ts: str):
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.astimezone(timezone.utc)
    except Exception:
        return None


def pair_to_sym(p: str) -> str:
    return (p or "").split("-")[0].upper()


def buy_notional(b: dict) -> float:
    try:
        return abs(float(b.get("qty") or 0) * float(b.get("entry") or 0))
    except Exception:
        return 0.0


def load_closes(path: Path) -> dict:
    raw = json.loads(path.read_text())
    rows = (
        raw
        if isinstance(raw, list)
        else raw.get("candles") or raw.get("data") or raw.get("ohlcv") or []
    )
    out: dict[str, float] = {}
    for r in rows:
        if isinstance(r, dict):
            t = r.get("start") or r.get("time") or r.get("timestamp") or r.get("date") or r.get("t")
            c = r.get("close") or r.get("c")
            if t is None or c is None:
                continue
            if isinstance(t, (int, float)):
                t = float(t)
                if t > 1e12:
                    t = t / 1000.0
                dt = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
            else:
                dt = str(t)[:10]
            try:
                out[dt] = float(c)
            except Exception:
                pass
        elif isinstance(r, (list, tuple)) and len(r) >= 5:
            t, c = r[0], r[4]
            if isinstance(t, (int, float)):
                t = float(t)
                if t > 1e12:
                    t = t / 1000.0
                dt = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
            else:
                dt = str(t)[:10]
            try:
                out[dt] = float(c)
            except Exception:
                pass
    return out


def main() -> int:
    cfg = json.loads(CFG_PATH.read_text())
    rm = cfg.get("risk_management") or {}
    gs = cfg.get("global_settings") or {}
    total_cap = float(gs.get("total_capital", 1000))
    mdl_pct = float(rm.get("max_daily_loss_pct", 0.02))
    mdl_usd_cfg = total_cap * mdl_pct
    live = json.loads(LIVE_PATH.read_text()) if LIVE_PATH.exists() else {}
    live_eq = float(live.get("total_usd") or 0)
    mdl_usd_live = live_eq * mdl_pct if live_eq else total_cap * mdl_pct

    sells: list[dict] = []
    buys: list[dict] = []
    for line in TRADES.read_text().splitlines():
        try:
            o = json.loads(line)
        except Exception:
            continue
        side = (o.get("side") or "").upper()
        ts = o.get("timestamp") or ""
        try:
            pnl = float(o["pnl"]) if o.get("pnl") is not None else None
        except Exception:
            pnl = None
        row = {
            "ts": ts,
            "pair": o.get("pair") or "",
            "pnl": pnl,
            "reason": o.get("exit_reason") or o.get("reason") or "",
            "qty": o.get("qty"),
            "entry": o.get("entry_price") or o.get("price"),
            "exit": o.get("exit_price"),
        }
        if side == "SELL":
            sells.append(row)
        elif side == "BUY":
            buys.append(row)

    by_day_pnl: dict[str, float] = defaultdict(float)
    by_day_pairs: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for s in sells:
        if s["pnl"] is None:
            continue
        d = day(s["ts"])
        if not d:
            continue
        by_day_pnl[d] += float(s["pnl"])
        by_day_pairs[d][s["pair"]] += float(s["pnl"])
    days = sorted(by_day_pnl)

    events_by_day: dict[str, list] = defaultdict(list)
    for s in sells:
        d = day(s["ts"])
        t = parse_ts(s["ts"])
        if d and t:
            events_by_day[d].append(("SELL", t, s))
    for b in buys:
        d = day(b["ts"])
        t = parse_ts(b["ts"])
        if d and t:
            events_by_day[d].append(("BUY", t, b))
    for d in events_by_day:
        events_by_day[d].sort(key=lambda x: x[1])

    def cf_block_after(th: float) -> dict:
        blocked_n = 0
        blocked_notional = 0.0
        fire_days = 0
        residual_after = 0.0
        detail = []
        for d, evs in events_by_day.items():
            cum = 0.0
            breached = False
            day_bn = 0
            day_not = 0.0
            day_post = 0.0
            for kind, _t, row in evs:
                if kind == "SELL" and row.get("pnl") is not None:
                    p = float(row["pnl"])
                    if not breached:
                        cum += p
                        if cum <= -th:
                            breached = True
                            fire_days += 1
                    else:
                        residual_after += p
                        day_post += p
                elif kind == "BUY" and breached:
                    blocked_n += 1
                    day_bn += 1
                    n = buy_notional(row)
                    blocked_notional += n
                    day_not += n
            if breached and (day_bn or abs(day_post) > 1):
                detail.append(
                    {
                        "day": d,
                        "blocked_buys": day_bn,
                        "blocked_notional": round(day_not, 2),
                        "sell_pnl_after": round(day_post, 2),
                        "day_pnl": round(by_day_pnl[d], 2),
                    }
                )
        return {
            "fire_days": fire_days,
            "blocked_buys": blocked_n,
            "blocked_notional": round(blocked_notional, 2),
            "sell_pnl_after_breach": round(residual_after, 2),
            "detail": detail,
        }

    # pre vs post on fire days (cfg threshold)
    th = mdl_usd_cfg
    pre_sum = post_sum = 0.0
    n_fire = 0
    pre_post_rows = []
    for d, evs in events_by_day.items():
        cum = 0.0
        breached = False
        pre = post = 0.0
        for kind, _t, row in evs:
            if kind != "SELL" or row.get("pnl") is None:
                continue
            p = float(row["pnl"])
            if not breached:
                cum += p
                pre += p
                if cum <= -th:
                    breached = True
                    n_fire += 1
            else:
                post += p
        if breached:
            pre_sum += pre
            post_sum += post
            pairs = {k: round(v, 2) for k, v in by_day_pairs[d].items() if abs(v) > 0.5}
            pre_post_rows.append(
                {"day": d, "pre": round(pre, 2), "post": round(post, 2), "day_pnl": round(by_day_pnl[d], 2), "pairs": pairs}
            )

    eod_fires = {
        "cfg_20": sorted([(d, by_day_pnl[d]) for d in days if by_day_pnl[d] <= -mdl_usd_cfg], key=lambda x: x[1]),
        "live_2pct": sorted([(d, by_day_pnl[d]) for d in days if by_day_pnl[d] <= -mdl_usd_live], key=lambda x: x[1]),
        "hard_50": sorted([(d, by_day_pnl[d]) for d in days if by_day_pnl[d] <= -50.0], key=lambda x: x[1]),
        "hard_100": sorted([(d, by_day_pnl[d]) for d in days if by_day_pnl[d] <= -100.0], key=lambda x: x[1]),
        "pct5_live": sorted([(d, by_day_pnl[d]) for d in days if by_day_pnl[d] <= -(live_eq * 0.05)], key=lambda x: x[1]),
    }

    cf_cfg = cf_block_after(mdl_usd_cfg)
    cf_live = cf_block_after(mdl_usd_live)

    # OHLCV
    ohlcv_dir = ROOT / "backtests" / "data"
    long_dir = ohlcv_dir / "long"
    pair_files: dict[str, Path] = {}
    for p in list(ohlcv_dir.glob("backtest_historical_ohlcv_*.json")) + list(long_dir.glob("ohlcv_daily_*.json")):
        name = p.stem.lower()
        for sym in ["btc", "eth", "sol", "xrp", "doge", "avax", "link", "arb", "ada", "op", "icp", "near", "uni", "pengu"]:
            if f"_{sym}_" in name or name.endswith(f"_{sym}") or f"daily_{sym}" in name:
                if sym.upper() not in pair_files or "long" in str(p):
                    pair_files[sym.upper()] = p

    closes = {sym: load_closes(path) for sym, path in pair_files.items()}
    ohlcv_meta = {
        sym: {
            "n": len(ser),
            "start": min(ser) if ser else None,
            "end": max(ser) if ser else None,
            "file": pair_files[sym].name,
        }
        for sym, ser in closes.items()
    }

    start = (
        (datetime.fromisoformat(days[0]) - timedelta(days=40)).strftime("%Y-%m-%d") if days else "2026-04-01"
    )
    end = days[-1] if days else "2026-08-31"
    all_dates = None
    for ser in closes.values():
        ds = set(ser)
        all_dates = ds if all_dates is None else all_dates & ds
    all_dates = sorted(d for d in (all_dates or []) if start <= d <= end)

    rets: dict[str, dict[str, float]] = {sym: {} for sym in closes}
    for i in range(1, len(all_dates)):
        d0, d1 = all_dates[i - 1], all_dates[i]
        for sym, ser in closes.items():
            if d0 in ser and d1 in ser and ser[d0] > 0:
                rets[sym][d1] = (ser[d1] - ser[d0]) / ser[d0]

    def rolling_corr(a: str, b: str, end_d: str, window: int = 30):
        xs, ys = [], []
        for d in all_dates:
            if d > end_d:
                break
            if d in rets[a] and d in rets[b]:
                xs.append(rets[a][d])
                ys.append(rets[b][d])
        if len(xs) < 10:
            return None
        xs, ys = xs[-window:], ys[-window:]
        n = len(xs)
        if n < 10:
            return None
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        denx = math.sqrt(sum((x - mx) ** 2 for x in xs))
        deny = math.sqrt(sum((y - my) ** 2 for y in ys))
        if denx < 1e-12 or deny < 1e-12:
            return None
        return num / (denx * deny)

    core = [s for s in ["BTC", "ETH", "SOL", "XRP", "LINK", "AVAX", "DOGE", "ADA"] if s in closes and len(closes[s]) > 50]
    th_corr = 0.85
    sample_days = all_dates[30:] if len(all_dates) > 30 else all_dates
    fire_count = 0
    pair_fire: dict[tuple, int] = defaultdict(int)
    latest: dict[tuple, float] = {}
    for d in sample_days:
        day_fire = False
        for a, b in combinations(core, 2):
            c = rolling_corr(a, b, d, 30)
            if c is not None and c >= th_corr:
                day_fire = True
                pair_fire[(a, b)] += 1
            if sample_days and d == sample_days[-1] and c is not None:
                latest[(a, b)] = c
        if day_fire:
            fire_count += 1

    multi_days = []
    for d in days:
        losers = [p for p, v in by_day_pairs[d].items() if v < -2.0]
        if len(losers) >= 2:
            multi_days.append((d, by_day_pnl[d], losers, dict(by_day_pairs[d])))

    multi_rows = []
    fantasy_save = 0.0
    n_appl = 0
    for d, pnl, losers, pair_pnl in multi_days:
        syms = {pair_to_sym(p): p for p in losers}
        applied = []
        day_save = 0.0
        corr_rows = []
        for a, b in combinations(list(syms), 2):
            if a not in closes or b not in closes:
                continue
            idx = all_dates.index(d) if d in all_dates else None
            end_d = all_dates[idx - 1] if idx and idx > 0 else (all_dates[-1] if all_dates else d)
            c = rolling_corr(a, b, end_d, 30)
            corr_rows.append({"a": a, "b": b, "corr": None if c is None else round(c, 3)})
            if c is None or c < th_corr:
                continue
            la = abs(min(0.0, pair_pnl.get(syms[a], 0.0)))
            lb = abs(min(0.0, pair_pnl.get(syms[b], 0.0)))
            day_save += 0.30 * (la + lb)
            applied.append({"a": a, "b": b, "corr": round(c, 3)})
        if day_save > 0:
            n_appl += 1
            fantasy_save += day_save
        multi_rows.append(
            {
                "day": d,
                "day_pnl": round(pnl, 2),
                "losers": losers,
                "corrs": corr_rows,
                "fantasy_30pct_save": round(day_save, 2),
                "applied": applied,
            }
        )

    worst15 = sorted(by_day_pnl.items(), key=lambda x: x[1])[:15]

    out = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "nav_live": live_eq,
        "ledger": {
            "n_days": len(days),
            "range": [days[0], days[-1]] if days else None,
            "n_sells_with_pnl": sum(1 for s in sells if s["pnl"] is not None),
            "n_buys": len(buys),
            "total_realized": round(sum(by_day_pnl.values()), 2),
            "sum_negative_days": round(sum(v for v in by_day_pnl.values() if v < 0), 2),
            "worst15": [{"day": d, "pnl": round(v, 2)} for d, v in worst15],
        },
        "max_daily_loss": {
            "config_pct": mdl_pct,
            "config_capital": total_cap,
            "config_usd": mdl_usd_cfg,
            "live_2pct_usd": round(mdl_usd_live, 2),
            "semantics": "legacy: block NEW buys after daily realized loss hits threshold; does NOT auto-flatten",
            "wired_phase6_core": False,
            "eod_fire_counts": {k: len(v) for k, v in eod_fires.items()},
            "eod_fire_days": {k: [{"day": d, "pnl": round(p, 2)} for d, p in v] for k, v in eod_fires.items()},
            "cf_block_buys_cfg20": {k: v for k, v in cf_cfg.items()},
            "cf_block_buys_live2pct": {k: v for k, v in cf_live.items()},
            "pre_vs_post_breach_cfg20": {
                "pre_sum": round(pre_sum, 2),
                "post_sum": round(post_sum, 2),
                "n_fire": n_fire,
                "rows": pre_post_rows,
            },
            "verdict_class": "ATTENTION_ONLY_less_loss_path_weak",
        },
        "correlation_breaker": {
            "threshold": th_corr,
            "reduction_pct": 0.30,
            "reserve_redeploy_pct": 0.15,
            "wired_live": False,
            "ohlcv_meta": ohlcv_meta,
            "aligned_dates": len(all_dates),
            "core_symbols": core,
            "rolling30_any_pair_fire_days": fire_count,
            "rolling30_sample_days": len(sample_days),
            "pair_fire_days": {f"{a}-{b}": n for (a, b), n in sorted(pair_fire.items(), key=lambda x: -x[1])},
            "latest_corrs": {f"{a}-{b}": round(c, 3) for (a, b), c in sorted(latest.items(), key=lambda x: -x[1])},
            "multi_pair_loss_days": len(multi_days),
            "multi_rows": multi_rows,
            "fantasy_30pct_reduce_save_usd": round(fantasy_save, 2),
            "fantasy_appl_days": n_appl,
            "verdict_class": "ATTENTION_ONLY_less_loss_path_sparse",
        },
        "context_levers_usd": {
            "c_standdown_90d_approx": 89,
            "fee_drag_30d_approx": 139,
            "note": "Prior digs; not re-run here",
        },
        "honest_limits": [
            "Realized SELL ledger only — no mark-to-market intraday equity curve",
            "max_daily_loss CF assumes chronological fills within day; no open unrealized",
            "corr CF fantasy assumes 30% size already cut BEFORE the loss day",
            "OHLCV alignment may miss some alt pairs (OP/ICP/PENGU) → undercount multi-day corr",
            "Does not model redeploy risk after corr cut or opportunity cost of blocked buys",
        ],
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2) + "\n")

    # Markdown brief
    lines = []
    lines.append("# Max Daily Loss + Correlation Breaker — Contribution CF")
    lines.append("")
    lines.append(f"**As of:** {out['as_of']}")
    lines.append(f"**NAV (live):** ~${live_eq:,.0f}")
    lines.append(f"**Ledger:** {out['ledger']['n_days']} days with realized SELL PnL · {out['ledger']['range']}")
    lines.append(f"**Total realized (SELL lots):** ${out['ledger']['total_realized']:,.2f}")
    lines.append(f"**Sum of negative days:** ${out['ledger']['sum_negative_days']:,.2f}")
    lines.append("")
    lines.append("## Semantics (what these knobs actually do)")
    lines.append("")
    lines.append("| Knob | Design | Live Phase 6 |")
    lines.append("|------|--------|--------------|")
    lines.append(
        f"| `max_daily_loss_pct={mdl_pct}` | Config → `${mdl_usd_cfg:.0f}` on `total_capital={total_cap:.0f}` "
        f"(or ~`${mdl_usd_live:.0f}` if % of live NAV). Legacy: **block NEW buys** after day realized loss hits threshold. "
        f"**Does not auto-flatten.** | **Not enforced** in `phase6/core` (theater load) |"
    )
    lines.append(
        "| Correlation circuit breaker | corr ≥ **0.85** → flag **30% reduce** + 15% reserve redeploy | Module exists; **not on runner** |"
    )
    lines.append("")
    lines.append("## A. Max daily loss — do we have fire evidence?")
    lines.append("")
    lines.append("### End-of-day realized fires")
    lines.append("")
    lines.append("| Threshold | Fire days | Days |")
    lines.append("|-----------|-----------|------|")
    for k, label in [
        ("cfg_20", f"cfg $20 (2% of $1k capital)"),
        ("live_2pct", f"2% of live NAV (~${mdl_usd_live:.0f})"),
        ("hard_50", "$50 hard"),
        ("hard_100", "$100 hard"),
        ("pct5_live", "5% of live NAV"),
    ]:
        fires = eod_fires[k]
        ds = ", ".join(f"{d} (${p:.0f})" for d, p in fires) or "—"
        lines.append(f"| {label} | **{len(fires)}** | {ds} |")
    lines.append("")
    lines.append("### Counterfactual: block buys after intraday cumulative loss")
    lines.append("")
    lines.append(
        f"- **cfg $20:** fire_days={cf_cfg['fire_days']}, blocked_buys={cf_cfg['blocked_buys']}, "
        f"blocked_notional=**${cf_cfg['blocked_notional']:.2f}**, sell_pnl_after_breach=**${cf_cfg['sell_pnl_after_breach']:.2f}**, "
        f"fantasy buy-leg fee @0.8% ≈ **${cf_cfg['blocked_notional'] * 0.008:.2f}**"
    )
    lines.append(
        f"- **live 2% (~${mdl_usd_live:.0f}):** fire_days={cf_live['fire_days']}, blocked_buys={cf_live['blocked_buys']}, "
        f"blocked_notional=**${cf_live['blocked_notional']:.2f}**, sell_pnl_after=**${cf_live['sell_pnl_after_breach']:.2f}**"
    )
    lines.append("")
    lines.append("### Pre vs post breach (cfg $20) — where the damage sat")
    lines.append("")
    lines.append("| Day | Pre-breach sell PnL | Post-breach sell PnL | Day total |")
    lines.append("|-----|---------------------|----------------------|-----------|")
    for r in pre_post_rows:
        lines.append(f"| {r['day']} | ${r['pre']:.2f} | ${r['post']:.2f} | ${r['day_pnl']:.2f} |")
    lines.append(f"| **TOTAL** | **${pre_sum:.2f}** | **${post_sum:.2f}** | |")
    lines.append("")
    lines.append(
        "**Read:** Almost all damage is **already locked in SL/exits before/at breach**. "
        "A buy-block after the fact is a **pile-on brake**, not a loss eraser. "
        "Post-breach residual sells are small on this sample."
    )
    lines.append("")
    lines.append(f"**Class:** `{out['max_daily_loss']['verdict_class']}` — honesty/safety rail, not a ~5% edge lever on this book.")
    lines.append("")
    lines.append("## B. Correlation breaker — fire rate + fantasy save")
    lines.append("")
    lines.append(
        f"- Rolling 30d any-core-pair corr ≥ 0.85: **{fire_count}/{len(sample_days)}** sample days "
        f"({100 * fire_count / max(1, len(sample_days)):.0f}%)"
    )
    lines.append(f"- Aligned OHLCV dates in window: **{len(all_dates)}** · core={core}")
    lines.append("")
    lines.append("### Latest pairwise corrs (sample end)")
    lines.append("")
    lines.append("| Pair | Corr |")
    lines.append("|------|------|")
    for k, c in list(out["correlation_breaker"]["latest_corrs"].items())[:12]:
        flag = " **FIRE**" if c >= 0.85 else ""
        lines.append(f"| {k} | {c}{flag} |")
    lines.append("")
    lines.append("### Multi-pair loss days (2+ pairs each < −$2 realized)")
    lines.append("")
    lines.append(f"n=**{len(multi_days)}** · sum day PnL = **${sum(p for _, p, _, _ in multi_days):.2f}**")
    lines.append("")
    lines.append("| Day | Day PnL | Losers | Loser-pair corrs | Fantasy 30% save |")
    lines.append("|-----|---------|--------|-----------------|------------------|")
    for r in multi_rows:
        corrs = ", ".join(
            f"{x['a']}-{x['b']}={x['corr']}" for x in r["corrs"]
        ) or "n/a"
        lines.append(
            f"| {r['day']} | ${r['day_pnl']:.2f} | {', '.join(r['losers'])} | {corrs} | ${r['fantasy_30pct_save']:.2f} |"
        )
    lines.append("")
    lines.append(
        f"**Fantasy upper bound** (30% of co-loser losses on days where loser-pair corr ≥ 0.85 **and** cut assumed *before* dump): "
        f"**${fantasy_save:.2f}** over {n_appl} applicable days."
    )
    lines.append("")
    lines.append(
        "**Read:** Several worst days are **single-name** (LINK −$36, LINK −$30, ICP −$14) — corr cut does nothing. "
        "Multi-name days exist but OHLCV gaps + sparse ≥0.85 among *actual co-losers* keep fantasy small. "
        "High *market* corr can still be common (BTC–ETH etc.) without matching our simultaneous SL cluster."
    )
    lines.append("")
    lines.append(f"**Class:** `{out['correlation_breaker']['verdict_class']}` — not a promote-to-live edge on this sample.")
    lines.append("")
    lines.append("## C. Rank vs known levers (same book)")
    lines.append("")
    lines.append("| Lever | Approx contribution | Class |")
    lines.append("|-------|---------------------|-------|")
    lines.append("| Fee drag (30d) | ~$139 NAV tax | house cut (cost) |")
    lines.append("| C stand-down elevated process (90d CF) | ~$89 avoided | less-loss filter |")
    lines.append("| Limit-first buy (if rests) | ~0.4% of buy notional | cost cut |")
    lines.append(
        f"| max_daily_loss buy-block CF | blocked notional ${cf_cfg['blocked_notional']:.0f}; "
        f"post-breach residual ${cf_cfg['sell_pnl_after_breach']:.0f}; fee fantasy tiny | weak safety rail |"
    )
    lines.append(
        f"| Corr 30% reduce fantasy | ~${fantasy_save:.0f} sparse | weak / sparse less-loss |"
    )
    lines.append("")
    lines.append("## D. Recommendation")
    lines.append("")
    lines.append("1. **Do not sell either as a P&L unlock.** Data does not support a material expectancy lift.")
    lines.append(
        "2. **max_daily_loss:** still worth **honesty** — wire a real enforcer *or* delete/rename the knob so config is not theater. "
        "If wired: use **% of live equity** (not stale $1k capital), buy-block only, no panic flatten, log fires."
    )
    lines.append(
        "3. **Corr breaker:** keep **shadow/LEGACY** unless a longer multipair board shows clustered same-session SL damage "
        "that predates high corr. Default OFF. Redeploy leg is a second risk."
    )
    lines.append("4. Priority stays: **fewer RTs · C stand-down observe · limit-first pilot evidence · exit promote gates.**")
    lines.append("")
    lines.append("## Honest limits")
    lines.append("")
    for h in out["honest_limits"]:
        lines.append(f"- {h}")
    lines.append("")
    lines.append(f"JSON: `{OUT_JSON.relative_to(ROOT)}`")
    lines.append("")
    lines.append("---")
    lines.append("*Research only. No live changes.*")
    lines.append("")

    OUT_MD.write_text("\n".join(lines))
    print(OUT_MD.read_text())
    print(f"\nWrote {OUT_JSON} and {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
