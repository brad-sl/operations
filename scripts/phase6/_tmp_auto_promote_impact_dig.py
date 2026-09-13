#!/usr/bin/env python3
"""Counterfactual: auto-promote best preferred-arm pair → basket impacts."""
from __future__ import annotations

import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/home/brad/projects/crypto-trading-bot")


def load(p: str | Path):
    path = ROOT / p if not str(p).startswith("/") else Path(p)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def main() -> None:
    d = load("data/state/basket_swap_brad_decision.json") or {}
    b = load("data/state/basket_swap_confidence_board_latest.json") or {}
    cf = load("data/state/basket_swap_shadow_counterfactual_latest.json") or {}
    l2 = load("data/state/l2_deployability_latest.json") or {}
    live = load("data/state/phase6_live_state.json") or {}
    cfg = load("config/trading_config_phase6.json") or {}

    pref = (d.get("preferred_arm") or "").strip() or "risk_adj_mom"
    print("=== SSOT ===")
    print("preferred_arm", pref)
    print("live_membership_swaps", d.get("live_membership_swaps"))
    print("regime", d.get("regime_arm_switch"))
    print("board_status", b.get("status"))

    pairs = (cfg.get("global_settings") or {}).get("pairs") or []
    print("basket_n", len(pairs))
    print("basket", pairs)

    # holdings
    pos = live.get("positions") or live.get("active_positions") or {}
    if isinstance(pos, list):
        held = {}
        for row in pos:
            if isinstance(row, dict):
                pair = row.get("pair") or row.get("product_id")
                usd = row.get("value_usd") or row.get("usd_value") or row.get("market_value")
                if pair:
                    held[pair] = usd
    elif isinstance(pos, dict):
        held = {}
        for k, v in pos.items():
            if not isinstance(k, str) or not k.endswith("-USD"):
                continue
            if isinstance(v, dict):
                held[k] = v.get("value_usd") or v.get("usd_value") or v.get("market_value") or v.get("notional")
            else:
                try:
                    held[k] = float(v)
                except Exception:
                    held[k] = v
    else:
        held = {}
    print("held_nonzero:")
    for k, v in sorted(held.items()):
        try:
            fv = float(v or 0)
        except Exception:
            continue
        if fv >= 1:
            print(f"  {k}: ${fv:.2f}")

    cash = live.get("cash_usd") or (live.get("balances") or {}).get("USD") or (live.get("balances") or {}).get("USDC")
    print("cash_usd", cash, "total_usd", live.get("total_usd"))

    # L2
    print("\n=== L2 ===")
    print("l2 keys", list(l2.keys())[:20] if l2 else None)
    if l2:
        s = l2.get("summary") or l2.get("stats") or {}
        print("summary", json.dumps(s, default=str)[:500])
        rows = l2.get("rows") or l2.get("scored") or l2.get("results") or []
        print("l2 rows", len(rows))
        for r in rows[:12]:
            if not isinstance(r, dict):
                continue
            print(
                {
                    k: r.get(k)
                    for k in (
                        "add",
                        "remove",
                        "arm",
                        "l2_ok",
                        "deployable",
                        "blocked_reason",
                        "reasons",
                        "status",
                        "would_buy",
                    )
                    if k in r or k in ("add", "remove", "arm")
                }
            )

    # preferred arm proposals
    print("\n=== preferred arm proposals ===")
    props_path = ROOT / f"data/state/basket_select_arms/{pref}/proposals.jsonl"
    latest_path = ROOT / f"data/state/basket_select_arms/{pref}/latest.json"
    if latest_path.exists():
        print("latest", json.dumps(load(latest_path), default=str)[:900])
    props = []
    if props_path.exists():
        for line in props_path.read_text().splitlines():
            if line.strip():
                props.append(json.loads(line))
    print("props_n", len(props))
    # membership ok rate
    ok_n = 0
    for r in props:
        mp = r.get("membership_potential") or {}
        ok = bool(r.get("membership_potential_ok")) or bool(mp.get("ok"))
        if ok:
            ok_n += 1
    print("membership_ok_rate", ok_n, "/", len(props))
    for r in props[-10:]:
        mp = r.get("membership_potential") or {}
        print(
            r.get("ts"),
            r.get("remove"),
            "→",
            r.get("add"),
            "delta",
            r.get("delta"),
            "m_ok",
            bool(r.get("membership_potential_ok") or mp.get("ok")),
            "m_reason",
            mp.get("reason") or mp.get("status") or mp.get("fail_reason"),
            "held_rem",
            r.get("remove_held_usd"),
        )

    # CF for preferred + both contenders
    print("\n=== CF L1 by arm (168h completed) ===")
    rows = cf.get("unique_results") or []
    for arm in ("risk_adj_mom", "rel_btc_stable", "baseline_hybrid", "dual_agree"):
        scored = []
        for r in rows:
            if r.get("arm") != arm:
                continue
            h = (r.get("horizons") or {}).get("168h") or {}
            if h.get("status") == "ok" and h.get("excess_pct") is not None:
                scored.append(
                    {
                        "ex7": float(h["excess_pct"]),
                        "add_ret": h.get("add_ret_pct"),
                        "rem_ret": h.get("rem_ret_pct"),
                        "ts": r.get("ts"),
                        "remove": r.get("remove"),
                        "add": r.get("add"),
                    }
                )
        if not scored:
            print(arm, "n=0")
            continue
        xs = [s["ex7"] for s in scored]
        print(
            arm,
            "n",
            len(xs),
            "mean_ex7",
            round(st.mean(xs), 2),
            "med",
            round(st.median(xs), 2),
            "hit",
            round(sum(1 for x in xs if x > 0) / len(xs), 2),
            "p10",
            round(sorted(xs)[max(0, len(xs) // 10)], 2),
            "p90",
            round(sorted(xs)[min(len(xs) - 1, 9 * len(xs) // 10)], 2),
        )
        scored.sort(key=lambda s: s["ex7"], reverse=True)
        print("  best", scored[0])
        print("  worst", scored[-1])

    # "best pair" definition candidates:
    # 1) highest mean excess add among preferred proposals with completed 7d
    # 2) latest preferred nomination
    print("\n=== best-pair candidates under auto-promote rules ===")
    # latest preferred nomination
    if props:
        last = props[-1]
        print("LATEST_NOM", last.get("remove"), "→", last.get("add"), "ts", last.get("ts"))

    # best completed CF on preferred arm
    pref_scored = []
    for r in rows:
        if r.get("arm") != pref:
            continue
        h = (r.get("horizons") or {}).get("168h") or {}
        if h.get("status") == "ok" and h.get("excess_pct") is not None:
            pref_scored.append(
                (
                    float(h["excess_pct"]),
                    r.get("ts"),
                    r.get("remove"),
                    r.get("add"),
                    h.get("add_ret_pct"),
                    h.get("rem_ret_pct"),
                )
            )
    pref_scored.sort(reverse=True)
    if pref_scored:
        print("BEST_CF_7d", pref_scored[0])
        print("WORST_CF_7d", pref_scored[-1])

    # if auto-promoted EVERY preferred membership-ok write: count churn + remove held risk
    print("\n=== auto-promote every M-ok preferred write (churn CF) ===")
    m_ok_props = []
    for r in props:
        mp = r.get("membership_potential") or {}
        ok = bool(r.get("membership_potential_ok")) or bool(mp.get("ok"))
        if ok:
            m_ok_props.append(r)
    print("m_ok_count", len(m_ok_props))
    adds = Counter(r.get("add") for r in m_ok_props)
    rems = Counter(r.get("remove") for r in m_ok_props)
    print("top adds", adds.most_common(8))
    print("top removes", rems.most_common(8))

    # match CF excess for those remove→add on preferred arm
    pair_ex = []
    for r in m_ok_props:
        key = (r.get("remove"), r.get("add"))
        # find CF rows
        exs = []
        for c in rows:
            if c.get("arm") != pref:
                continue
            if c.get("remove") == key[0] and c.get("add") == key[1]:
                h = (c.get("horizons") or {}).get("168h") or {}
                if h.get("status") == "ok" and h.get("excess_pct") is not None:
                    exs.append(float(h["excess_pct"]))
        if exs:
            pair_ex.append((key, st.mean(exs), len(exs)))
    if pair_ex:
        pair_ex.sort(key=lambda x: x[1], reverse=True)
        print("m_ok with CF mean_ex7:")
        for p in pair_ex[:10]:
            print(" ", p)
        xs = [p[1] for p in pair_ex]
        print(
            "auto_promote_m_ok portfolio of swaps mean_ex7",
            round(st.mean(xs), 2),
            "hit",
            round(sum(1 for x in xs if x > 0) / len(xs), 2),
            "n_pairs",
            len(xs),
        )

    # pick metrics win rate if exists
    pm = load("data/state/basket_pick_metrics_summary.json") or load(
        "data/state/basket_pick_metrics_latest.json"
    )
    print("\n=== pick metrics ===")
    if pm:
        print(json.dumps(pm, default=str)[:1200])

    # recovery / soft_down gates
    print("\n=== recovery/config fences ===")
    oo = cfg.get("operator_override") or {}
    print("operator_override keys", list(oo.keys())[:20])
    for k, v in oo.items():
        if "recovery" in k.lower() or "soft" in k.lower():
            print(k, json.dumps(v, default=str)[:300])

    # buy_block
    bb = (cfg.get("global_settings") or {}).get("buy_block_pairs") or cfg.get("buy_block_pairs")
    print("buy_block_pairs", bb)

    out = {
        "preferred_arm": pref,
        "live_swaps": d.get("live_membership_swaps"),
        "basket_n": len(pairs),
        "m_ok_props": len(m_ok_props),
        "best_cf": pref_scored[0] if pref_scored else None,
        "worst_cf": pref_scored[-1] if pref_scored else None,
        "latest_nom": (
            {
                "remove": props[-1].get("remove"),
                "add": props[-1].get("add"),
                "ts": props[-1].get("ts"),
            }
            if props
            else None
        ),
    }
    (ROOT / "data/state/auto_promote_cf_impact_dig_latest.json").write_text(
        json.dumps(out, indent=2, default=str) + "\n"
    )
    print("\nwrote data/state/auto_promote_cf_impact_dig_latest.json")


if __name__ == "__main__":
    main()
