#!/usr/bin/env python3
"""Idle cash drawdown schedule + USDC yield curve dig (offline).

Question: how fast does paced tryout ($75 x max 2/day) pull cash, how long does
the stub sit idle, and what yield band is rational for parking that stub in USDC
until free cash is needed for buys.

No orders. No config writes.
"""
from __future__ import annotations

import json
import math
import sqlite3
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
EQUITY = 2292.0
CASH_NOW = 2210.55
PAXG = 81.34
SEAT = 75.0
MAX_SEATS_PER_DAY = 2
MAX_CONCURRENT_TRYOUT = 2  # recovery pace
POST_TP_H = 24.0
POST_SL_H = 72.0
# research-class USDC APY bands (NOT live venue quote — never product claim)
APY_BANDS = {
    "research_low": 0.02,
    "research_mid": 0.041,  # Coinbase-class research ~4.1% (Aug 2026 class articles)
    "research_high": 0.047,  # Wallet onchain class ~4.7% — different product surface
}


def daily_yield(usd: float, apy: float) -> float:
    return usd * apy / 365.0


def main():
    con = sqlite3.connect(str(PROJECT / "data" / "phase6.db"))

    # --- Historical cash fraction from account_balances if usable ---
    ab_cols = [c[1] for c in con.execute("PRAGMA table_info(account_balances)").fetchall()]
    print("account_balances cols", ab_cols)
    ab_n = con.execute("SELECT COUNT(*) FROM account_balances").fetchone()[0]
    print("account_balances n", ab_n)

    cash_series = []
    if ab_n and "ts" in ab_cols:
        # try common shapes
        q = "SELECT * FROM account_balances ORDER BY ts"
        rows = con.execute(q).fetchall()
        col = ab_cols
        for r in rows:
            d = dict(zip(col, r))
            ts = d.get("ts") or d.get("timestamp")
            # find cash-like
            cash = None
            total = None
            for k, v in d.items():
                lk = k.lower()
                if v is None:
                    continue
                if lk in ("cash_usd", "usd", "cash", "balance_usd"):
                    try:
                        cash = float(v)
                    except Exception:
                        pass
                if lk in ("total_usd", "nav", "equity", "total"):
                    try:
                        total = float(v)
                    except Exception:
                        pass
            if cash is not None:
                cash_series.append({"ts": ts, "cash": cash, "total": total})

    # Fallback: reconstruct from live_state history if present / period_snapshots
    ps_cols = [c[1] for c in con.execute("PRAGMA table_info(period_snapshots)").fetchall()]
    print("period_snapshots cols", ps_cols)
    ps_n = con.execute("SELECT COUNT(*) FROM period_snapshots").fetchone()[0]
    print("period_snapshots n", ps_n)
    if ps_n:
        rows = con.execute("SELECT * FROM period_snapshots ORDER BY rowid DESC LIMIT 5").fetchall()
        for r in rows:
            print("ps", dict(zip(ps_cols, r)))

    # Rebalance history from jsonl
    hist_path = PROJECT / "data" / "state" / "rebalance_history" / "default.jsonl"
    rebal_rows = []
    if hist_path.exists():
        for line in hist_path.read_text().splitlines():
            if not line.strip():
                continue
            rebal_rows.append(json.loads(line))
    print("rebalance history n", len(rebal_rows))

    # Deployed capital per day from ledger buys last 60d
    ledger = PROJECT / "trades" / "phase6_trades.jsonl"
    cut = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    buys_by_day = {}
    sells_by_day = {}
    open_approx = []  # crude
    if ledger.exists():
        for line in ledger.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            ts = r.get("timestamp") or r.get("ts") or ""
            if ts < cut:
                continue
            side = str(r.get("side") or "").lower()
            pair = r.get("pair")
            qty = float(r.get("qty") or 0 or 0)
            px = float(r.get("price") or r.get("exit_price") or r.get("entry_price") or 0 or 0)
            if not qty or not px:
                # try notional fields
                notional = r.get("notional_usd") or r.get("usd") or r.get("filled_value")
                try:
                    notional = float(notional) if notional is not None else None
                except Exception:
                    notional = None
            else:
                notional = abs(qty * px)
            if notional is None or notional < 5:
                continue
            day = str(ts)[:10]
            reason = str(r.get("reason") or "")
            if side in ("buy", "b"):
                buys_by_day.setdefault(day, []).append(
                    {"pair": pair, "usd": notional, "reason": reason[:60], "ts": ts}
                )
            elif side in ("sell", "s"):
                sells_by_day.setdefault(day, []).append(
                    {"pair": pair, "usd": notional, "reason": reason[:60], "ts": ts, "pnl": r.get("pnl")}
                )

    days = sorted(set(buys_by_day) | set(sells_by_day))
    print("\n=== Daily buy notional (60d) ===")
    daily_buy_usd = []
    for d in days:
        b = sum(x["usd"] for x in buys_by_day.get(d, []))
        s = sum(x["usd"] for x in sells_by_day.get(d, []))
        nb = len(buys_by_day.get(d, []))
        daily_buy_usd.append(b)
        if b > 0 or s > 100:
            print(f"{d} buys={nb} buy$={b:.0f} sell$={s:.0f}")

    nonzero_buy_days = [x for x in daily_buy_usd if x > 0]
    print(
        f"buy days {len(nonzero_buy_days)}/{len(days)} "
        f"mean_buy_day$={statistics.mean(nonzero_buy_days) if nonzero_buy_days else 0:.0f} "
        f"median={statistics.median(nonzero_buy_days) if nonzero_buy_days else 0:.0f} "
        f"max={max(nonzero_buy_days) if nonzero_buy_days else 0:.0f}"
    )

    # --- Forward cash drawdown under CURRENT policy (deterministic scenarios) ---
    # Start: cash C0, 0 tryout seats. Each day can open up to min(2, free seats) x $75
    # if "signal day". Model signal hit rates.
    print("\n=== Forward cash schedule under paced tryout ===")

    def simulate(
        cash0: float,
        days: int,
        signal_p: float,
        seat_hold_days_mean: float,
        label: str,
        max_seats_day: int = MAX_SEATS_PER_DAY,
        seat_usd: float = SEAT,
        max_concurrent: int = MAX_CONCURRENT_TRYOUT,
        recycle_cooldown_days: float = 1.0,  # after exit, average before re-fill (TP 1d / mix)
    ):
        """Simple inventory model.
        - open seats list of remaining hold days
        - each day: free completed seats -> cash; maybe open new up to caps if random signal
        - no path PnL (size-only cash absorption)
        """
        import random

        random.seed(42)
        cash = cash0
        seats = []  # remaining days until exit
        series = []
        deployed_peak = 0.0
        min_cash = cash0
        days_cash_above = {0.5: 0, 0.75: 0, 0.9: 0, 0.95: 0}  # fraction of initial cash still idle
        total_bought = 0.0
        opens = 0
        for day in range(days):
            # exits
            still = []
            for rem in seats:
                if rem <= 1:
                    cash += seat_usd  # ignore pnl; size returns
                else:
                    still.append(rem - 1)
            seats = still
            # opens
            free_slots = max_concurrent - len(seats)
            opened_today = 0
            if free_slots > 0 and random.random() < signal_p:
                n_open = min(max_seats_day, free_slots, int(cash // seat_usd))
                # hold time ~ exponential-ish around mean
                for _ in range(n_open):
                    hold = max(1, int(random.gauss(seat_hold_days_mean, seat_hold_days_mean * 0.4)))
                    # add cooldown into next eligibility by extending hold slightly? keep separate
                    seats.append(hold)
                    cash -= seat_usd
                    total_bought += seat_usd
                    opens += 1
                    opened_today += 1
            deployed = len(seats) * seat_usd
            deployed_peak = max(deployed_peak, deployed)
            min_cash = min(min_cash, cash)
            frac_idle = cash / cash0 if cash0 else 0
            for thr in days_cash_above:
                if frac_idle >= thr:
                    days_cash_above[thr] += 1
            series.append(
                {
                    "day": day,
                    "cash": cash,
                    "deployed": deployed,
                    "n_seats": len(seats),
                    "opened": opened_today,
                    "idle_frac": frac_idle,
                }
            )
        # time until cash first drops below thresholds
        def first_below(frac):
            thr = cash0 * frac
            for row in series:
                if row["cash"] < thr:
                    return row["day"]
            return None

        avg_idle = statistics.mean(r["cash"] for r in series)
        avg_deployed = statistics.mean(r["deployed"] for r in series)
        return {
            "label": label,
            "signal_p": signal_p,
            "seat_hold_days_mean": seat_hold_days_mean,
            "days": days,
            "opens": opens,
            "total_bought_turnover": total_bought,
            "avg_cash": avg_idle,
            "avg_deployed": avg_deployed,
            "min_cash": min_cash,
            "deployed_peak": deployed_peak,
            "avg_idle_frac": avg_idle / cash0,
            "days_idle_frac_ge": days_cash_above,
            "day_first_cash_lt_90pct": first_below(0.90),
            "day_first_cash_lt_75pct": first_below(0.75),
            "day_first_cash_lt_50pct": first_below(0.50),
            "terminal_cash": series[-1]["cash"] if series else cash0,
            "terminal_deployed": series[-1]["deployed"] if series else 0,
            "series_tail": series[:: max(1, days // 10)],
        }

    scenarios = []
    # hold means from prior dig: often 1-3 days under SL/TP
    for sig_p, hold, lab in [
        (0.15, 2.0, "sparse_signals_15pct_hold2d"),
        (0.35, 2.0, "moderate_signals_35pct_hold2d"),
        (0.60, 2.0, "rich_signals_60pct_hold2d"),
        (0.35, 1.0, "moderate_hold1d_fast_turnover"),
        (0.35, 5.0, "moderate_hold5d_slow"),
        (1.00, 2.0, "always_signal_every_day_hold2d"),  # upper bound pull speed
    ]:
        # monte carlo 200 paths
        paths = [simulate(CASH_NOW, 60, sig_p, hold, lab) for _ in range(1)]
        # actually need multi seed
        import random

        stats_paths = []
        for seed in range(200):
            random.seed(seed)
            # re-implement inline with seed - call simulate which seeds 42 fixed - bug
            # fix: pass seed into simulate by patching
            stats_paths.append(
                _simulate_seeded(
                    CASH_NOW, 60, sig_p, hold, lab, seed,
                    MAX_SEATS_PER_DAY, SEAT, MAX_CONCURRENT_TRYOUT,
                )
            )
        scenarios.append(_aggregate(stats_paths, lab, sig_p, hold))

    for sc in scenarios:
        print(
            f"{sc['label']}: avg_cash=${sc['avg_cash']:.0f} ({sc['avg_idle_frac']*100:.0f}% idle) "
            f"avg_dep=${sc['avg_deployed']:.0f} peak_dep=${sc['deployed_peak_p90']:.0f} "
            f"min_cash_p10=${sc['min_cash_p10']:.0f} "
            f"t90p50={sc['day_lt90_p50']} t75p50={sc['day_lt75_p50']} t50p50={sc['day_lt50_p50']} "
            f"opens60d_mean={sc['opens_mean']:.0f}"
        )

    # Steady-state max deployed under policy = 2 * 75 = 150 ALWAYS
    steady_max = MAX_CONCURRENT_TRYOUT * SEAT
    stub = CASH_NOW - steady_max
    print("\n=== Steady-state identity ===")
    print(f"max concurrent tryout notional = ${steady_max:.0f}")
    print(f"structural idle stub if fully seated = ${stub:.0f} ({stub/CASH_NOW*100:.1f}% of cash)")
    print(f"only way to eat stub = raise seat size, concurrent seats, or exit recovery into full deploy")

    # Time-to-steady under always-signal
    # day0 open 2, day1 if still open can't open more; when one exits open 1...
    # With hold=2d always signal: seats stay full after day0
    print("time to full $150 seat: 1 day if 2 signals (always), else geometric in signal_p")

    # --- USDC yield on structural stub + on transitional idle ---
    print("\n=== Yield on cash layers ===")
    layers = {
        "structural_stub_if_2seats_full": stub,
        "all_cash_now_no_seats": CASH_NOW,
        "cash_minus_one_seat_buffer": CASH_NOW - SEAT,
        "cash_minus_two_seat_buffer": CASH_NOW - 2 * SEAT,
        "cash_minus_four_seat_buffer": CASH_NOW - 4 * SEAT,
    }
    yield_table = {}
    for name, usd in layers.items():
        yield_table[name] = {
            "usd": usd,
            **{
                f"usd_per_day_{k}": daily_yield(usd, apy)
                for k, apy in APY_BANDS.items()
            },
            **{
                f"usd_per_30d_{k}": daily_yield(usd, apy) * 30
                for k, apy in APY_BANDS.items()
            },
            **{
                f"usd_per_365d_{k}": usd * apy
                for k, apy in APY_BANDS.items()
            },
        }
        y = yield_table[name]
        print(
            f"{name}: ${usd:.0f} -> mid ${y['usd_per_day_research_mid']:.3f}/d "
            f"(${y['usd_per_30d_research_mid']:.2f}/30d, ${y['usd_per_365d_research_mid']:.1f}/yr)"
        )

    # Opportunity: keep reserve R in USD for near buys; rest USDC
    # Unwind friction: assume need USD T hours before rebalance; USDC->USD is liquid same-cycle on CB
    print("\n=== Reserve ladder (USD keep vs USDC park) ===")
    # Expected buy need over next horizon
    horizons = [1, 3, 7, 14, 30]
    # under policy max pull per day = 150
    reserve_ladder = []
    for h in horizons:
        max_need = min(steady_max, MAX_SEATS_PER_DAY * SEAT * h)  # but concurrent caps at 150
        # concurrent means over h days turnover can exceed 150
        # max turnover h days = seats_per_day * h * seat, but inventory capped
        max_turnover = MAX_SEATS_PER_DAY * SEAT * h
        # practical need for free USD: one rebalance wave + buffer = 2*75 + small
        wave = 2 * SEAT
        for reserve in [wave, wave + 50, 2 * wave, 300, 500]:
            usdc = max(0.0, CASH_NOW - reserve)
            mid_30 = daily_yield(usdc, APY_BANDS["research_mid"]) * 30
            reserve_ladder.append(
                {
                    "horizon_d": h,
                    "max_turnover_uncapped": max_turnover,
                    "concurrent_cap": steady_max,
                    "usd_reserve": reserve,
                    "usdc_park": usdc,
                    "yield_30d_mid": mid_30,
                    "yield_day_mid": daily_yield(usdc, APY_BANDS["research_mid"]),
                    "covers_wave": reserve >= wave,
                }
            )
    # print unique reserves for h=7
    seen = set()
    for row in reserve_ladder:
        if row["horizon_d"] != 7:
            continue
        key = row["usd_reserve"]
        if key in seen:
            continue
        seen.add(key)
        print(
            f"7d view reserveUSD=${row['usd_reserve']:.0f} USDC=${row['usdc_park']:.0f} "
            f"-> ${row['yield_day_mid']:.3f}/d (${row['yield_30d_mid']:.2f}/30d) "
            f"covers_2seat_wave={row['covers_wave']}"
        )

    # Break-even: days of mid yield on stub vs one extra bad $75 SL
    sl_loss = SEAT * 0.034 + SEAT * 0.016
    stub_day = daily_yield(stub, APY_BANDS["research_mid"])
    be_days = sl_loss / stub_day if stub_day else None
    print(f"\nOne clean $75 SL+fee ~${sl_loss:.2f}; stub mid yield ${stub_day:.4f}/d -> breakeven ~{be_days:.0f} days of stub yield")

    # Deploy-open conflict note from live status
    pkg = json.loads((PROJECT / "data" / "state" / "park_package_status.json").read_text())
    a = pkg.get("bucket_a") or {}
    c = pkg.get("bucket_c") or {}
    live_note = {
        "live_usdc_park_enabled": a.get("live_usdc_park_enabled"),
        "park_signal": a.get("park_signal"),
        "deploy_open": a.get("deploy_open"),
        "recommended_a_action": a.get("recommended_a_action"),
        "regime": (c.get("regime") or {}).get("regime"),
        "strategy_mode": (c.get("regime") or {}).get("strategy_mode"),
        "usdc_balance_now": 0.0,
        "usd_balance_now": CASH_NOW,
    }
    print("live A", live_note)

    out = {
        "schema": "idle_cash_yield_curve_dig_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "book": {
            "equity": EQUITY,
            "cash_usd": CASH_NOW,
            "paxg_usd": PAXG,
            "usdc_usd": 0.0,
        },
        "policy": {
            "seat_usd": SEAT,
            "max_seats_per_day": MAX_SEATS_PER_DAY,
            "max_concurrent_tryout": MAX_CONCURRENT_TRYOUT,
            "steady_max_deployed_usd": steady_max,
            "structural_idle_stub_usd": stub,
            "post_tp_h": POST_TP_H,
            "post_sl_h": POST_SL_H,
        },
        "apy_bands_research_not_quote": APY_BANDS,
        "apy_disclaimer": "Research-class published rates only. Not a live Coinbase account quote. Never hard-code as product APY.",
        "historical_buys_60d": {
            "n_days": len(days),
            "n_buy_days": len(nonzero_buy_days),
            "mean_buy_day_usd": statistics.mean(nonzero_buy_days) if nonzero_buy_days else 0,
            "median_buy_day_usd": statistics.median(nonzero_buy_days) if nonzero_buy_days else 0,
            "max_buy_day_usd": max(nonzero_buy_days) if nonzero_buy_days else 0,
            "sum_buy_usd": sum(daily_buy_usd),
        },
        "forward_scenarios": scenarios,
        "yield_layers": yield_table,
        "reserve_ladder_7d_sample": [r for r in reserve_ladder if r["horizon_d"] == 7],
        "breakeven_one_sl_vs_stub_yield_days_mid": be_days,
        "live_usdc_state": live_note,
        "optimal_curve_plain": {
            "layer_1_usd_reserve": {
                "usd": 150,
                "why": "Always cover next 2-seat wave without forced USDC unwind race",
            },
            "layer_2_usdc_structural": {
                "usd": stub,
                "why": "Under current recovery concurrent cap, this cash cannot be absorbed by tryout seats — pure yield candidate until policy raises caps or exits recovery",
            },
            "layer_3_usdc_transitional": {
                "usd": "cash above reserve minus currently open seat notional",
                "why": "Can convert back on deploy/rebalance; same-cycle unwind is design of live_usdc_park",
            },
            "do_not": "Park 100% USDC with $0 USD if a 09:00 wave must fire same hour without unwind path tested",
        },
        "honesty": [
            "Under max 2 concurrent $75 seats, ~$2060 of current cash is STRUCTURALLY unusable by tryout — yield question is mostly about that stub, not about racing the next buy.",
            "USDC yield cents/day does not fix path bleed; it only harvests the idle stub.",
            "Live package currently recommends usdc_redeploy_unwind because flat deploy_open=true — executor will NOT accumulate USDC until park_signal or policy allows park-while-micro-deploy.",
            "Random signal scenarios bound cash ABSORPTION speed; live gates may be slower (post-TP 24h, quality bars).",
            "APY bands are research-class web figures, not this account's live rewards rate.",
        ],
    }

    state = PROJECT / "data" / "state" / "idle_cash_yield_curve_dig_latest.json"
    state.write_text(json.dumps(out, indent=2, default=str))
    print("Wrote", state)

    # Markdown
    lines = [
        "# Idle cash drawdown + USDC yield curve dig",
        "",
        f"- as_of: `{out['as_of']}`",
        f"- cash now: **${CASH_NOW:.0f}** USD · USDC **$0** · PAXG ~**${PAXG:.0f}** · equity ~**${EQUITY:.0f}**",
        f"- policy: tryout **${SEAT:.0f}** · max **{MAX_SEATS_PER_DAY}/day** · max concurrent **{MAX_CONCURRENT_TRYOUT}** → steady max deployed **${steady_max:.0f}**",
        "",
        "## Plain English answer",
        "",
        f"1. **How fast does idle cash get drawn down?** Under current recovery caps, cash is **not** marching to zero. "
        f"The tryout machine can only hold **${steady_max:.0f}** at once (2×$75). After at most **one full wave** "
        f"(same day if two signals clear), you are at steady state: ~**${steady_max:.0f}** in seats and ~**${stub:.0f}** still idle.",
        "",
        f"2. **How much remains, for how long?** The **~${stub:.0f} structural stub** remains for as long as "
        f"**max concurrent seats stay at 2 and size stays $75** — days, weeks, or the whole recovery phase. "
        f"Only raising caps, leaving recovery, or a non-tryout deploy path eats that stub.",
        "",
        "3. **Yield curve implication:** That structural stub is the clean USDC candidate. "
        "Keep a **USD reserve ≈ next wave ($150)** (+ small buffer) so buys do not depend on a last-second unwind. "
        "Park the rest in USDC while policy keeps concurrent tryout tiny.",
        "",
        "## Steady-state identity (most important math)",
        "",
        f"| Piece | $ |",
        f"|-------|--:|",
        f"| Cash now | {CASH_NOW:.0f} |",
        f"| Max concurrent tryout | {steady_max:.0f} |",
        f"| **Structural idle stub** | **{stub:.0f}** |",
        f"| Stub / cash | {stub/CASH_NOW*100:.1f}% |",
        "",
        "Drawdown of *usable* idle into seats is fast (hours–1 day when signals exist). "
        "Drawdown of the *stub* is **policy-bound**, not market-bound.",
        "",
        "## Forward absorption scenarios (60d Monte Carlo, size-only)",
        "",
        "Model: up to 2 opens/day on signal probability, max 2 concurrent, $75, hold time mean, cash returns at exit (no PnL).",
        "",
        "| Scenario | avg cash | avg idle% | avg deployed | p90 peak dep | p10 min cash | day cash<90% (p50) | day cash<75% (p50) | day cash<50% (p50) | opens/60d |",
        "|----------|---------:|----------:|-------------:|-------------:|-------------:|------------------:|------------------:|------------------:|--------------:|",
    ]
    for sc in scenarios:
        lines.append(
            f"| {sc['label']} | {sc['avg_cash']:.0f} | {sc['avg_idle_frac']*100:.0f}% | "
            f"{sc['avg_deployed']:.0f} | {sc['deployed_peak_p90']:.0f} | {sc['min_cash_p10']:.0f} | "
            f"{sc['day_lt90_p50']} | {sc['day_lt75_p50']} | {sc['day_lt50_p50']} | {sc['opens_mean']:.0f} |"
        )

    lines += [
        "",
        "Reading: even **always_signal** cannot push average deployed above **$150**. "
        "Cash **never** approaches 50% drawdown from tryout pacing alone.",
        "",
        "## Historical buy pace (ledger 60d)",
        "",
        f"- buy days: **{out['historical_buys_60d']['n_buy_days']}** / {out['historical_buys_60d']['n_days']}",
        f"- mean buy-day notional: **${out['historical_buys_60d']['mean_buy_day_usd']:.0f}** "
        f"(median ${out['historical_buys_60d']['median_buy_day_usd']:.0f}, max ${out['historical_buys_60d']['max_buy_day_usd']:.0f})",
        f"- sum buys 60d: **${out['historical_buys_60d']['sum_buy_usd']:.0f}**",
        "",
        "## USDC yield bands (research-class — NOT a live account quote)",
        "",
        f"| band | APY |",
        f"|------|----:|",
    ]
    for k, v in APY_BANDS.items():
        lines.append(f"| {k} | {v*100:.2f}% |")
    lines += [
        "",
        f"Disclaimer: {out['apy_disclaimer']}",
        "",
        "### Yield on layers (mid ~4.1%)",
        "",
        "| layer | $ | $/day | $/30d | $/yr |",
        "|-------|--:|------:|------:|-----:|",
    ]
    for name, y in yield_table.items():
        lines.append(
            f"| {name} | {y['usd']:.0f} | {y['usd_per_day_research_mid']:.3f} | "
            f"{y['usd_per_30d_research_mid']:.2f} | {y['usd_per_365d_research_mid']:.1f} |"
        )

    lines += [
        "",
        f"One clean tryout SL+fees (~${sl_loss:.2f}) ≈ **{be_days:.0f} days** of mid yield on the structural stub alone.",
        "",
        "## Optimal cash curve (proposed)",
        "",
        "| Layer | Where | Size (today) | Role |",
        "|-------|-------|-------------:|------|",
        f"| L0 Working | open tryout seats | 0–{steady_max:.0f} | risk on |",
        f"| L1 USD reserve | USD | **~150–200** | next 1–2 seat wave + dust buffer; never starve 09:00 |",
        f"| L2 USDC structural | USDC | **~{stub-50:.0f}–{stub:.0f}** | cannot be used by 2×$75 policy — harvest yield |",
        f"| L3 Gold | PAXG MICRO | ~{PAXG:.0f} | ballast, not cash curve |",
        "",
        "### Horizon view",
        "",
        "| Horizon | Expected max tryout pull | Cash still idle if caps hold | USDC action |",
        "|---------|--------------------------|------------------------------|------------|",
        f"| 0–1 day | up to $150 if 2 signals | ~${stub:.0f}+ | Park stub now; keep $150–200 USD |",
        f"| 1–7 days | turnover may recycle seats; inventory still ≤$150 | stub remains | Stay USDC on stub |",
        f"| 14–30 days | same unless policy changes | stub remains | Yield compounds on stub; revisit if recovery lifts caps |",
        f"| Policy change (4 seats or $150 size) | recompute reserve = new wave | stub shrinks | Unwind USDC into USD before first larger wave |",
        "",
        "## Live executor conflict (important)",
        "",
        f"- `live_usdc_park_enabled`: **{live_note['live_usdc_park_enabled']}**",
        f"- `park_signal`: **{live_note['park_signal']}** · `deploy_open`: **{live_note['deploy_open']}**",
        f"- recommended A action: **{live_note['recommended_a_action']}**",
        f"- balances: USD ${live_note['usd_balance_now']:.0f} · USDC ${live_note['usdc_balance_now']:.0f}",
        "",
        "Today the package is in **deploy-open** posture, so the A executor prefers **USD powder** "
        "(`usdc_redeploy_unwind`) and will **not** fill USDC just because cash is idle under micro tryout. "
        "That is why you see $0 USDC despite toggle ON — **signal design**, not missing yield desire.",
        "",
        "To implement the optimal curve under flat cautious deploy you need a **policy add**: "
        "**park-while-micro-deploy** (or `a_yield_on_structural_stub`) that converts cash above USD reserve "
        "to USDC even when `deploy_open` and tryout caps keep concurrent risk tiny — then auto-unwind "
        "only when reserve would breach before a wave.",
        "",
        "## Honesty",
        "",
    ]
    for h in out["honesty"]:
        lines.append(f"- {h}")
    lines += [
        "",
        "## Decision framing (no live flip in this dig)",
        "",
        "| Question | Answer |",
        "|----------|--------|",
        f"| How fast is cash drawn down? | **To the $150 seat cap in ≤1 day** when signals exist; **not** further under current concurrent max. |",
        f"| How much stays idle how long? | **~${stub:.0f} for the life of 2×$75 recovery caps.** |",
        f"| Should that gap be USDC? | **Yes, rationally** — it's the yield curve's main mass. Keep ~$150–200 USD reserve. |",
        f"| Why isn't it USDC now? | Deploy-open A logic **unwinds/keeps USD**; park_signal false. Product gap vs desire. |",
        f"| Is yield the path fix? | **No** — ~$2–7/30d on stub mid APY. Process edge still dominates. |",
        "",
        "JSON: `data/state/idle_cash_yield_curve_dig_latest.json`",
        "",
    ]
    report = PROJECT / "reports" / "IDLE_CASH_YIELD_CURVE_DIG_LATEST.md"
    report.write_text("\n".join(lines) + "\n")
    print("Wrote", report)


def _simulate_seeded(
    cash0, days, signal_p, seat_hold_days_mean, label, seed,
    max_seats_day, seat_usd, max_concurrent,
):
    import random

    random.seed(seed)
    cash = cash0
    seats = []
    series = []
    deployed_peak = 0.0
    min_cash = cash0
    total_bought = 0.0
    opens = 0
    for day in range(days):
        still = []
        for rem in seats:
            if rem <= 1:
                cash += seat_usd
            else:
                still.append(rem - 1)
        seats = still
        free_slots = max_concurrent - len(seats)
        if free_slots > 0 and random.random() < signal_p:
            n_open = min(max_seats_day, free_slots, int(cash // seat_usd))
            for _ in range(n_open):
                hold = max(1, int(random.gauss(seat_hold_days_mean, max(0.5, seat_hold_days_mean * 0.4))))
                seats.append(hold)
                cash -= seat_usd
                total_bought += seat_usd
                opens += 1
        deployed = len(seats) * seat_usd
        deployed_peak = max(deployed_peak, deployed)
        min_cash = min(min_cash, cash)
        series.append({"day": day, "cash": cash, "deployed": deployed, "n_seats": len(seats)})

    def first_below(frac):
        thr = cash0 * frac
        for row in series:
            if row["cash"] < thr:
                return row["day"]
        return None

    return {
        "label": label,
        "avg_cash": statistics.mean(r["cash"] for r in series),
        "avg_deployed": statistics.mean(r["deployed"] for r in series),
        "min_cash": min_cash,
        "deployed_peak": deployed_peak,
        "avg_idle_frac": statistics.mean(r["cash"] for r in series) / cash0,
        "day_lt90": first_below(0.90),
        "day_lt75": first_below(0.75),
        "day_lt50": first_below(0.50),
        "opens": opens,
        "total_bought": total_bought,
        "terminal_cash": series[-1]["cash"],
        "terminal_deployed": series[-1]["deployed"],
    }


def _aggregate(paths, lab, sig_p, hold):
    def med(key):
        xs = [p[key] for p in paths if p[key] is not None]
        return statistics.median(xs) if xs else None

    def mean(key):
        return statistics.mean(p[key] for p in paths)

    def pctl(key, p):
        xs = sorted(p[key] for p in paths)
        k = max(0, min(len(xs) - 1, int(round((len(xs) - 1) * p))))
        return xs[k]

    return {
        "label": lab,
        "signal_p": sig_p,
        "seat_hold_days_mean": hold,
        "avg_cash": mean("avg_cash"),
        "avg_deployed": mean("avg_deployed"),
        "avg_idle_frac": mean("avg_idle_frac"),
        "min_cash_p10": pctl("min_cash", 0.10),
        "deployed_peak_p90": pctl("deployed_peak", 0.90),
        "day_lt90_p50": med("day_lt90"),
        "day_lt75_p50": med("day_lt75"),
        "day_lt50_p50": med("day_lt50"),
        "opens_mean": mean("opens"),
        "total_bought_mean": mean("total_bought"),
    }


if __name__ == "__main__":
    main()
