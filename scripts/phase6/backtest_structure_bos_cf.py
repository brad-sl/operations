#!/usr/bin/env python3
"""
Offline CF: structure BOS exit vs hold / 3% SL / 4% arm 2% trail.

Real Coinbase public 1h OHLCV. Honesty rules: report mean ret, hit rate,
vs bags — not "winner" hype.

  cd /home/brad/projects/crypto-trading-bot
  PYTHONPATH=. python3 scripts/phase6/backtest_structure_bos_cf.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.structure_bos_exit import (
    DEFAULTS,
    fetch_candles_public,
    find_run_entries,
    load_bos_config,
    normalize_candles,
    simulate_entry_to_bos,
    walk_long_structure_bos,
)

OUT_JSON = ROOT / "data/state/structure_bos_cf_report.json"
OUT_MD = ROOT / "reports/STRUCTURE_BOS_CF_LATEST.md"
UA = {"User-Agent": "phase6-structure-bos-cf/1.0"}


def fetch_many(pair: str, granularity: int, pages: int = 3) -> List[Dict[str, float]]:
    """
    Pull successive windows by walking start/end (Coinbase max ~300/req).
    Oldest→newest merged.
    """
    # Simple: latest window is enough for ~12d at 1h; for longer use multipage end anchor
    all_rows: List[Dict[str, float]] = []
    end = None
    for _ in range(pages):
        if end is None:
            url = f"https://api.exchange.coinbase.com/products/{pair}/candles?granularity={granularity}"
        else:
            # end exclusive-ish: fetch older
            end_iso = datetime.fromtimestamp(end, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            start_ts = end - granularity * 300
            start_iso = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            url = (
                f"https://api.exchange.coinbase.com/products/{pair}/candles"
                f"?granularity={granularity}&start={start_iso}&end={end_iso}"
            )
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            print(f"fetch fail {pair}: {e}")
            break
        rows = normalize_candles(data)
        if not rows:
            break
        all_rows = rows + all_rows
        end = rows[0]["t"] - 1
        time.sleep(0.25)
    # dedupe by t
    by_t = {r["t"]: r for r in all_rows}
    return [by_t[k] for k in sorted(by_t)]


def mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def run_pair(pair: str, cfg: Dict[str, Any], pages: int = 4) -> Dict[str, Any]:
    gran = int(cfg.get("granularity_sec") or 3600)
    candles = fetch_many(pair, gran, pages=pages)
    if len(candles) < 80:
        return {"pair": pair, "error": f"few_candles={len(candles)}"}

    entries = find_run_entries(
        candles,
        arm_mfe_pct=float(cfg.get("arm_mfe_pct") or 0.04),
        lookback_trough=24,
        cooldown_bars=18,
    )
    # Cap episodes for honesty / runtime
    entries = entries[-40:]

    bos_rets: List[float] = []
    hold_rets: List[float] = []
    trail_rets: List[float] = []
    sl_rets: List[float] = []
    mfes: List[float] = []
    fired_n = 0
    episodes = []

    for ei, ep in entries:
        # path from entry to +min(200 bars, end)
        end = min(len(candles) - 1, ei + 200)
        window = candles[: end + 1]
        sim = simulate_entry_to_bos(window, ei, ep, cfg)
        mfes.append(sim["mfe"])
        # hold to end of window (not infinite bag)
        hold = window[-1]["c"] / ep - 1.0
        hold_rets.append(hold)
        if sim["bos_fired"]:
            fired_n += 1
            bos_rets.append(sim["bos_ret"])
        else:
            bos_rets.append(hold)  # no fire → still holding at window end
        if sim["trail_4_2_ret"] is not None:
            trail_rets.append(sim["trail_4_2_ret"])
        if sim["sl_3pct_ret"] is not None:
            sl_rets.append(sim["sl_3pct_ret"])
        episodes.append(
            {
                "entry_ts": window[ei]["t"],
                "entry_px": ep,
                "bos_fired": sim["bos_fired"],
                "bos_ret": sim["bos_ret"],
                "hold_ret": hold,
                "mfe": sim["mfe"],
                "trail_ret": sim["trail_4_2_ret"],
                "exit_px": (sim["bos"] or {}).get("exit_price"),
            }
        )

    # LINK poster: if pair LINK, also force entry near early-Aug if present
    poster = None
    if pair.startswith("LINK"):
        for i, r in enumerate(candles):
            d = datetime.fromtimestamp(r["t"], tz=timezone.utc).strftime("%Y-%m-%d")
            if d == "2026-08-11":
                poster = simulate_entry_to_bos(candles, i, r["c"], cfg)
                poster["entry_date"] = d
                break
        if poster is None:
            # nearest available
            for i, r in enumerate(candles):
                d = datetime.fromtimestamp(r["t"], tz=timezone.utc).strftime("%Y-%m-%d")
                if d >= "2026-08-10":
                    poster = simulate_entry_to_bos(candles, i, r["c"], cfg)
                    poster["entry_date"] = d
                    break

    return {
        "pair": pair,
        "n_candles": len(candles),
        "n_entries": len(entries),
        "bos_fire_rate": fired_n / len(entries) if entries else 0.0,
        "mean_bos_ret": mean(bos_rets),
        "mean_hold_ret": mean(hold_rets),
        "mean_mfe": mean(mfes),
        "mean_trail_ret": mean(trail_rets) if trail_rets else None,
        "mean_sl_ret_when_hit": mean(sl_rets) if sl_rets else None,
        "delta_bos_minus_hold": mean(bos_rets) - mean(hold_rets) if entries else 0.0,
        "poster_link_aug": poster,
        "sample_episodes": episodes[-8:],
    }


def main() -> int:
    cfg = load_bos_config()
    pairs = ["LINK-USD", "BTC-USD", "SOL-USD", "ETH-USD"]
    results = []
    print("=== Structure BOS CF (1h, real Coinbase) ===")
    print(f"arm_mfe={cfg.get('arm_mfe_pct')} swing={cfg.get('swing_left')}/{cfg.get('swing_right')}")
    for p in pairs:
        print(f"\n--- {p} ---")
        r = run_pair(p, cfg, pages=5)
        results.append(r)
        if r.get("error"):
            print(" ERR", r["error"])
            continue
        print(
            f" entries={r['n_entries']} fire_rate={r['bos_fire_rate']:.0%} "
            f"mean_bos={100*r['mean_bos_ret']:+.2f}% mean_hold={100*r['mean_hold_ret']:+.2f}% "
            f"Δ(bos-hold)={100*r['delta_bos_minus_hold']:+.2f}% mean_mfe={100*r['mean_mfe']:.1f}%"
        )
        if r.get("mean_trail_ret") is not None:
            print(f" mean_trail_4/2={100*r['mean_trail_ret']:+.2f}% (when trail fired)")
        if r.get("poster_link_aug"):
            po = r["poster_link_aug"]
            b = po.get("bos") or {}
            print(
                f" POSTER entry {po.get('entry_date')}: bos_fired={po.get('bos_fired')} "
                f"bos_ret={100*po.get('bos_ret',0):+.2f}% mfe={100*po.get('mfe',0):.1f}% "
                f"exit={b.get('exit_price')}"
            )

    report = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "cfg": {k: cfg[k] for k in cfg if k != "note"},
        "results": results,
        "honesty": [
            "Real Coinbase OHLCV only.",
            "Entries = trough→arm heuristic, not live allocator — shape study not live guarantee.",
            "mean_bos includes non-fires held to window end.",
            "Positive Δ vs hold = less giveback on run failures; not auto promote.",
            "Shadow only — no live structure_bos sells.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str))

    lines = [
        "# Structure BOS exit — offline CF",
        "",
        f"Generated: {report['ts']}",
        "",
        "## Method",
        "- Timeframe: 1h Coinbase public candles",
        "- Arm: MFE ≥ arm_mfe_pct vs entry",
        "- Exit: close breaks last confirmed swing higher-low",
        "- Compare: hold to path window end; optional 4% arm/2% trail; 3% SL when hit",
        "",
        "## Results",
        "",
        "| pair | n | fire% | mean BOS | mean hold | Δ BOS−hold | mean MFE |",
        "|------|---|-------|----------|-----------|------------|----------|",
    ]
    for r in results:
        if r.get("error"):
            lines.append(f"| {r['pair']} | err | | | | | |")
            continue
        lines.append(
            f"| {r['pair']} | {r['n_entries']} | {100*r['bos_fire_rate']:.0f}% | "
            f"{100*r['mean_bos_ret']:+.2f}% | {100*r['mean_hold_ret']:+.2f}% | "
            f"{100*r['delta_bos_minus_hold']:+.2f}% | {100*r['mean_mfe']:.1f}% |"
        )
    lines.extend(
        [
            "",
            "## Honesty",
            *[f"- {h}" for h in report["honesty"]],
            "",
            f"JSON: `{OUT_JSON}`",
            "",
            "## Go/no-go",
            "- **Shadow collect** on live book (runner hook).",
            "- **No live sell** until Brad OK + enough episodes + vs trail/SL scoreboard.",
            "",
        ]
    )
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
