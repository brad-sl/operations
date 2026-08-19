#!/usr/bin/env python3
"""Refined contingency backtest pass — meaningful hedges + doc arms + report."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path

from phase6.research.run_usd_hold_contingency_backtest import (
    FEE_RT,
    INITIAL,
    OUT_JSON,
    OUT_MD,
    ROOT,
    ContingencyParams,
    align,
    buy_hold,
    fetch_daily,
    metrics,
    run_contingency,
    score,
    usdc_flat,
)


def main() -> int:
    now = datetime.now(timezone.utc)
    end_ms = int(now.timestamp() * 1000)
    start_ms = int((now - timedelta(days=400 + 548)).timestamp() * 1000)
    raw = {}
    for name, sym in {
        "BTC": "BTCUSDT",
        "PAXG": "PAXGUSDT",
        "TRX": "TRXUSDT",
        "BNB": "BNBUSDT",
        "ETH": "ETHUSDT",
        "SOL": "SOLUSDT",
    }.items():
        print("fetch", name)
        raw[name] = fetch_daily(sym, start_ms, end_ms)
        time.sleep(0.1)
    days, px = align(raw)
    print("aligned", days[0], days[-1], len(days))

    def window_days(n: int):
        return [d for d in days if d >= days[-1] - timedelta(days=n)]

    def baselines_for(wdays):
        paxg = {d: px["PAXG"][d] for d in wdays}
        out = {}
        for asset in ("PAXG", "BTC", "TRX", "BNB", "ETH", "SOL"):
            eq, tr = buy_hold(wdays, {d: px[asset][d] for d in wdays})
            m = metrics(eq, tr, (wdays[-1] - wdays[0]).days)
            m["strategy"] = f"bh_{asset}"
            m["score"] = score(m)
            out[m["strategy"]] = m
        for apy, lab in ((0.0, "usdc_0"), (0.04, "usdc_4apy")):
            eq, tr = usdc_flat(wdays, apy=apy)
            m = metrics(eq, tr, (wdays[-1] - wdays[0]).days)
            m["strategy"] = lab
            m["score"] = score(m)
            out[lab] = m
        for w in (0.10, 0.20, 0.25, 0.50, 0.75, 1.0):
            p0 = paxg[wdays[0]]
            units = (INITIAL * w * (1 - FEE_RT / 2)) / p0
            cash = INITIAL * (1 - w)
            eq = [cash + units * paxg[d] for d in wdays]
            eq[-1] = cash + units * paxg[wdays[-1]] * (1 - FEE_RT / 2)
            m = metrics(eq, 1, (wdays[-1] - wdays[0]).days)
            m["strategy"] = f"static_{int(w * 100)}paxg"
            m["score"] = score(m)
            out[m["strategy"]] = m
        btc = {d: px["BTC"][d] for d in wdays}
        return out, btc, paxg

    doc_arms = [
        ContingencyParams("doc_s14_12m25_w100_exitL", 14, -25, 1.0, True, True, 10.0, None, True),
        ContingencyParams("doc_s14_12m25_w20_exitL", 14, -25, 0.20, True, True, 10.0, None, True),
        ContingencyParams("doc_s14_12m25_w50_exitL", 14, -25, 0.50, True, True, 10.0, None, True),
        ContingencyParams("doc_s14_12m25_w20_bullOnly", 14, -25, 0.20, True, False, None, None, True),
        ContingencyParams("doc_s14_12m25_w50_bullOnly", 14, -25, 0.50, True, False, None, None, True),
        ContingencyParams("doc_s14_12m25_w100_bullOnly", 14, -25, 1.0, True, False, None, None, True),
        ContingencyParams("doc_s14_no12m_w20_bullOnly", 14, -25, 0.20, True, False, None, None, False),
        ContingencyParams("doc_s14_no12m_w50_bullOnly", 14, -25, 0.50, True, False, None, None, False),
        ContingencyParams("doc_s14_no12m_w100_bullOnly", 14, -25, 1.0, True, False, None, None, False),
        ContingencyParams("doc_s7_no12m_w50_bullOnly", 7, -25, 0.50, True, False, None, None, False),
        ContingencyParams("doc_s21_12m25_w50_bullOnly", 21, -25, 0.50, True, False, None, None, True),
        ContingencyParams("doc_s14_12m25_w50_trail12", 14, -25, 0.50, True, False, None, -0.12, True),
        ContingencyParams("doc_s14_12m35_w50_bullOnly", 14, -35, 0.50, True, False, None, None, True),
        ContingencyParams("bear_s14_w50_thaw15", 14, -25, 0.50, True, False, 15.0, None, False),
        ContingencyParams("bear_s14_w100_thaw15", 14, -25, 1.0, True, False, 15.0, None, False),
        ContingencyParams("bear_s30_w50_thaw15", 30, -25, 0.50, True, False, 15.0, None, False),
    ]

    grid = list(
        product(
            [7, 14, 21, 30],
            [-15.0, -25.0, -35.0],
            [0.1, 0.2, 0.5, 1.0],
            [None, 10.0, 15.0],
            [None, -0.12],
            [True, False],
        )
    )

    def run_window(wdays):
        base, btc, paxg = baselines_for(wdays)
        rows = []
        for p in doc_arms:
            eq, tr, info = run_contingency(wdays, btc, paxg, p)
            m = metrics(eq, tr, (wdays[-1] - wdays[0]).days)
            m["score"] = score(m)
            dd = abs(m["max_drawdown_pct"])
            cal = None if dd < 1e-9 else round(m["total_return_pct"] / dd, 3)
            rows.append(
                {
                    "name": p.name,
                    "family": "doc",
                    "metrics": m,
                    "info": {
                        "entries": info["entries"],
                        "pct_days_hedged": info["pct_days_hedged"],
                        "entry_dates": info["entry_dates"],
                        "exit_dates": info["exit_dates"],
                        "params": info["params"],
                    },
                    "calmar": cal,
                    "score": m["score"],
                }
            )
        for streak, g12, wt, thaw, trail, req12 in grid:
            pname = f"g_s{streak}_12m{int(g12) if req12 else 'off'}_w{int(wt*100)}_th{thaw}_tr{trail}"
            p = ContingencyParams(pname, streak, g12, wt, True, False, thaw, trail, req12)
            eq, tr, info = run_contingency(wdays, btc, paxg, p)
            m = metrics(eq, tr, (wdays[-1] - wdays[0]).days)
            m["score"] = score(m)
            dd = abs(m["max_drawdown_pct"])
            cal = None if dd < 1e-9 else round(m["total_return_pct"] / dd, 3)
            rows.append(
                {
                    "name": pname,
                    "family": "grid",
                    "metrics": m,
                    "info": {
                        "entries": info["entries"],
                        "pct_days_hedged": info["pct_days_hedged"],
                        "entry_dates": info["entry_dates"][:8],
                        "exit_dates": info["exit_dates"][:8],
                        "params": info["params"],
                    },
                    "calmar": cal,
                    "score": m["score"],
                }
            )

        meaningful = [
            r
            for r in rows
            if r["info"]["pct_days_hedged"] >= 10.0 and r["info"]["entries"] >= 1
        ]
        meaningful_ret = sorted(
            meaningful, key=lambda r: r["metrics"]["total_return_pct"], reverse=True
        )
        meaningful_score = sorted(meaningful, key=lambda r: r["score"], reverse=True)
        paxg_dd = abs(base["bh_PAXG"]["max_drawdown_pct"])
        usdc0 = base["usdc_0"]["total_return_pct"]
        balanced = [
            r
            for r in meaningful
            if r["metrics"]["total_return_pct"] > usdc0 + 1
            and abs(r["metrics"]["max_drawdown_pct"]) <= paxg_dd + 0.5
        ]
        balanced = sorted(
            balanced,
            key=lambda r: r["metrics"]["total_return_pct"]
            - abs(r["metrics"]["max_drawdown_pct"]),
            reverse=True,
        )
        return {
            "start": wdays[0].isoformat(),
            "end": wdays[-1].isoformat(),
            "n": len(wdays),
            "baselines": base,
            "baseline_by_return": sorted(
                base.values(), key=lambda m: m["total_return_pct"], reverse=True
            ),
            "doc_arms": [r for r in rows if r["family"] == "doc"],
            "top_meaningful_return": meaningful_ret[:12],
            "top_meaningful_score": meaningful_score[:12],
            "top_balanced": balanced[:12],
            "n_meaningful": len(meaningful),
            "n_total_timed": len(rows),
        }

    results = {"as_of": now.isoformat(), "windows": {}}
    for wname, n in [("last_18m", 548), ("last_12m", 365), ("full_aligned", 10000)]:
        wdays = days if wname == "full_aligned" else window_days(n)
        print("run", wname, len(wdays))
        results["windows"][wname] = run_window(wdays)

    w18 = results["windows"]["last_18m"]
    w12 = results["windows"]["last_12m"]
    bh = w18["baselines"]["bh_PAXG"]
    usdc = w18["baselines"]["usdc_0"]
    usdc4 = w18["baselines"]["usdc_4apy"]
    btc = w18["baselines"]["bh_BTC"]
    static20 = w18["baselines"]["static_20paxg"]
    static25 = w18["baselines"]["static_25paxg"]
    static50 = w18["baselines"]["static_50paxg"]
    tm = w18["top_meaningful_return"][0] if w18["top_meaningful_return"] else None
    bal = w18["top_balanced"][0] if w18["top_balanced"] else None
    doc_best = sorted(
        w18["doc_arms"], key=lambda r: r["metrics"]["total_return_pct"], reverse=True
    )[0]

    viable = {
        "recommended_structure": "static_ballast_or_park",
        "go_no_go": "shadow_static_ballast_first",
        "rationale": [
            "PAXG buy&hold strongly beat cash on 18m — gold trend dominated.",
            "Timed BTC-bear rules under-captured gold upside vs always-on PAXG this window.",
            "Optimum operable contingency = 20–25% static PAXG ballast + USDC rest.",
            "If using timed overlay: exit on bull/30d thaw only — not flat_b layer (whipsaw).",
        ],
        "entry_exit": {
            "preferred_simple": {
                "type": "static_paxg_ballast",
                "paxg_pct_equity": 0.20,
                "rest": "USDC",
                "rebalance": "none_or_quarterly",
                "exit": "reduce when layered crypto re-entry / bull",
                "proxy_18m": static20,
            },
            "alt_25": static25,
            "max_return_path": {
                "type": "bh_paxg_100",
                "metrics": bh,
                "dd_warning": bh["max_drawdown_pct"],
            },
            "optional_timed_overlay": {
                "entry": "BTC bear streak >= 14d AND optional BTC 12m <= -25%, park/bear",
                "size": "raise PAXG sleeve 20% -> up to 50%",
                "exit": "BTC bull (30d>=+15%) OR BTC 30d >= +10%; NOT flat_b layer",
                "best_doc_like": doc_best["name"],
                "metrics_18m": doc_best["metrics"],
                "hedged_pct_days": doc_best["info"]["pct_days_hedged"],
            },
        },
    }

    plain = (
        f"18m ({w18['start']}→{w18['end']}): USDC0 {usdc['total_return_pct']}%, "
        f"USDC4% {usdc4['total_return_pct']}%, "
        f"PAXG BH {bh['total_return_pct']}% (DD {bh['max_drawdown_pct']}%), "
        f"BTC BH {btc['total_return_pct']}%, "
        f"static 20% PAXG {static20['total_return_pct']}% (DD {static20['max_drawdown_pct']}%), "
        f"static 25% {static25['total_return_pct']}% (DD {static25['max_drawdown_pct']}%), "
        f"static 50% {static50['total_return_pct']}% (DD {static50['max_drawdown_pct']}%). "
        f"Best doc timed: {doc_best['name']} ret {doc_best['metrics']['total_return_pct']}% "
        f"hedged {doc_best['info']['pct_days_hedged']}% days. "
        f"Go/no-go: {viable['go_no_go']}."
    )
    print("\nPLAIN:", plain)

    for wname, w in results["windows"].items():
        print("\n====", wname)
        for m in w["baseline_by_return"][:8]:
            print(
                f"  {m['strategy']:18} ret={m['total_return_pct']:+7.2f}% dd={m['max_drawdown_pct']:7.2f}%"
            )
        print("  DOC:")
        for r in sorted(
            w["doc_arms"], key=lambda x: x["metrics"]["total_return_pct"], reverse=True
        ):
            print(
                f"   {r['name'][:46]:46} ret={r['metrics']['total_return_pct']:+7.2f}% "
                f"dd={r['metrics']['max_drawdown_pct']:7.2f}% hedged={r['info']['pct_days_hedged']:5.1f}% "
                f"in={r['info']['entries']}"
            )
        print("  TOP meaningful ret:")
        for r in w["top_meaningful_return"][:6]:
            print(
                f"   {r['name'][:46]:46} ret={r['metrics']['total_return_pct']:+7.2f}% "
                f"dd={r['metrics']['max_drawdown_pct']:7.2f}% hedged={r['info']['pct_days_hedged']:5.1f}% "
                f"cal={r['calmar']}"
            )

    out = {
        "as_of": results["as_of"],
        "method": "binance.vision daily; fee 0.2% RT; BTC layers bull_reentry_layered; PAXG sleeve",
        "plain_english": plain,
        "viable_policy": viable,
        "optimum": {
            "max_return_18m": {
                "name": "bh_PAXG",
                "total_return_pct": bh["total_return_pct"],
                "max_drawdown_pct": bh["max_drawdown_pct"],
                "sharpe": bh["sharpe"],
            },
            "static_20": static20,
            "static_25": static25,
            "static_50": static50,
            "usdc_0": usdc,
            "usdc_4apy": usdc4,
            "btc": btc,
            "best_doc_arm_18m": doc_best,
            "best_timed_meaningful_18m": tm,
            "best_balanced_18m": bal,
        },
        "windows": {
            wn: {
                "start": w["start"],
                "end": w["end"],
                "n": w["n"],
                "baselines": w["baselines"],
                "doc_arms": w["doc_arms"],
                "top_meaningful_return": w["top_meaningful_return"][:10],
                "top_meaningful_score": w["top_meaningful_score"][:10],
                "top_balanced": w["top_balanced"][:10],
                "n_meaningful": w["n_meaningful"],
            }
            for wn, w in results["windows"].items()
        },
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str))
    print("WROTE", OUT_JSON)

    md = [
        "# USD hold contingency backtest (refined)",
        f"**As of:** {now.date()}",
        "**Status:** OFFLINE RESEARCH — not live",
        f"**JSON:** `{OUT_JSON.relative_to(ROOT)}`",
        f"**Fees:** {FEE_RT*100:.2f}% RT | **Initial:** ${INITIAL:,.0f}",
        "",
        "## Plain English",
        plain,
        "",
        f"**Go/no-go:** `{viable['go_no_go']}`",
        "",
        "## Optimum returns (~18m primary)",
        "",
        "| Strategy | Return% | MaxDD% | Sharpe | Notes |",
        "|---|---:|---:|---:|---|",
        f"| **PAXG 100% BH** | {bh['total_return_pct']} | {bh['max_drawdown_pct']} | {bh['sharpe']} | Max return |",
        f"| Static 50% PAXG | {static50['total_return_pct']} | {static50['max_drawdown_pct']} | {static50['sharpe']} | |",
        f"| Static 25% PAXG | {static25['total_return_pct']} | {static25['max_drawdown_pct']} | {static25['sharpe']} | |",
        f"| **Static 20% PAXG** | {static20['total_return_pct']} | {static20['max_drawdown_pct']} | {static20['sharpe']} | Recommended ballast |",
        f"| USDC 4% APY | {usdc4['total_return_pct']} | {usdc4['max_drawdown_pct']} | n/a | Yield floor |",
        f"| USDC 0% | {usdc['total_return_pct']} | 0 | 0 | Pure park |",
        f"| BTC 100% BH | {btc['total_return_pct']} | {btc['max_drawdown_pct']} | {btc['sharpe']} | Failed USD store |",
        f"| ETH 100% BH | {w18['baselines']['bh_ETH']['total_return_pct']} | {w18['baselines']['bh_ETH']['max_drawdown_pct']} | {w18['baselines']['bh_ETH']['sharpe']} | |",
        f"| SOL 100% BH | {w18['baselines']['bh_SOL']['total_return_pct']} | {w18['baselines']['bh_SOL']['max_drawdown_pct']} | {w18['baselines']['bh_SOL']['sharpe']} | |",
        f"| TRX 100% BH | {w18['baselines']['bh_TRX']['total_return_pct']} | {w18['baselines']['bh_TRX']['max_drawdown_pct']} | {w18['baselines']['bh_TRX']['sharpe']} | Best major crypto BH |",
        "",
        "## Timed contingency (BTC → PAXG)",
        "",
        "Exiting on flat/re-entry **layer** is too twitchy. Serious arms exit on **bull / 30d thaw** only.",
        "",
        "### Doc arms (18m)",
        "",
        "| Arm | Ret% | DD% | %days hedged | Entries |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in sorted(
        w18["doc_arms"], key=lambda x: x["metrics"]["total_return_pct"], reverse=True
    ):
        md.append(
            f"| `{r['name']}` | {r['metrics']['total_return_pct']} | {r['metrics']['max_drawdown_pct']} | "
            f"{r['info']['pct_days_hedged']} | {r['info']['entries']} |"
        )

    md += [
        "",
        "### Best meaningful timed (≥10% days hedged) — 18m",
        "",
        "| Ret% | DD% | Calmar | Hedged% | Name |",
        "|---:|---:|---:|---:|---|",
    ]
    for r in w18["top_meaningful_return"][:8]:
        md.append(
            f"| {r['metrics']['total_return_pct']} | {r['metrics']['max_drawdown_pct']} | "
            f"{r['calmar']} | {r['info']['pct_days_hedged']} | `{r['name']}` |"
        )

    md += [
        "",
        "## Viable entry/exit policy",
        "",
        "### A) Recommended first (simple)",
        "",
        "1. Default park: **USDC**.",
        "2. While contingency armed: **20% PAXG / 80% USDC** static ballast.",
        "3. No BTC-timed entry required for ballast.",
        "4. Reduce PAXG → USDC when crypto bull / layered re-entry turns on.",
        "5. Ceiling **20%** unless separate decision to size up.",
        "",
        (
            f"Proxy 18m: static 20% ≈ **{static20['total_return_pct']}%** ret, "
            f"**{static20['max_drawdown_pct']}%** DD "
            f"(vs PAXG100 **{bh['total_return_pct']}%** / **{bh['max_drawdown_pct']}%** DD, USDC0 **0%**)."
        ),
        "",
        "### B) Optional timed overlay",
        "",
        "| Leg | Rule |",
        "|-----|------|",
        "| Entry | BTC bear streak ≥ **14d** AND optional BTC 12m ≤ **−25%** AND park/bear |",
        "| Size | Raise PAXG 20% → up to **50%** equity |",
        "| Exit | BTC **bull** (30d≥+15%) OR BTC 30d ≥ **+10%** |",
        "| Do not | Exit on `flat_b` / breakout layer alone |",
        "| Trail | Optional PAXG −12% from local peak while oversized |",
        "",
        (
            f"Best doc-like arm: `{doc_best['name']}` → "
            f"ret {doc_best['metrics']['total_return_pct']}%, "
            f"DD {doc_best['metrics']['max_drawdown_pct']}%, "
            f"hedged {doc_best['info']['pct_days_hedged']}% days."
        ),
        "",
        "### C) Do not",
        "",
        f"- Use BTC/ETH/SOL as USD store (18m BTC **{btc['total_return_pct']}%**).",
        "- Expect timed rules to beat 100% PAXG in a one-way gold uptrend.",
        "- Go live without PAXG venue + SL + dust path + shadow.",
        "",
        "## 12m check",
        "",
        "| Strategy | Ret% | DD% |",
        "|---|---:|---:|",
    ]
    for k in [
        "bh_PAXG",
        "static_20paxg",
        "static_25paxg",
        "static_50paxg",
        "usdc_0",
        "usdc_4apy",
        "bh_BTC",
        "bh_TRX",
    ]:
        m = w12["baselines"][k]
        md.append(f"| {k} | {m['total_return_pct']} | {m['max_drawdown_pct']} |")

    md += [
        "",
        "### Doc arms 12m",
        "",
        "| Arm | Ret% | DD% | Hedged% |",
        "|---|---:|---:|---:|",
    ]
    for r in sorted(
        w12["doc_arms"], key=lambda x: x["metrics"]["total_return_pct"], reverse=True
    )[:10]:
        md.append(
            f"| `{r['name']}` | {r['metrics']['total_return_pct']} | "
            f"{r['metrics']['max_drawdown_pct']} | {r['info']['pct_days_hedged']} |"
        )

    md += [
        "",
        "## Method",
        "",
        "- Binance Vision 1d USDT closes (USDT≈USD).",
        "- BTC signals from `bull_reentry_layered` frozen knobs.",
        "- Timed sleeve: cash ↔ PAXG only.",
        "- Meaningful filter: ≥10% days hedged (avoids near-zero-trade score gaming).",
        "",
        "## Rationale",
        "",
    ]
    for line in viable["rationale"]:
        md.append(f"- {line}")

    OUT_MD.write_text("\n".join(md))
    print("WROTE", OUT_MD)

    # patch contingency policy doc with backtest pointer
    pol = ROOT / "docs/research/USD_HOLD_VALUE_CONTINGENCY_POLICY.md"
    if pol.exists():
        txt = pol.read_text()
        marker = "\n## Backtest pointer\n"
        block = (
            marker
            + "\n"
            + f"- Report: `reports/USD_HOLD_CONTINGENCY_BACKTEST_2026-08-01.md`\n"
            + f"- JSON: `data/state/usd_hold_contingency_backtest_latest.json`\n"
            + f"- Runner: `phase6/research/run_usd_hold_contingency_backtest.py` "
            + f"+ refined pass script\n"
            + f"- As-of plain English: {plain}\n"
        )
        if "## Backtest pointer" in txt:
            pre = txt.split("## Backtest pointer")[0].rstrip()
            txt = pre + "\n" + block
        else:
            txt = txt.rstrip() + "\n" + block
        pol.write_text(txt)
        print("Updated policy doc pointer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
