#!/usr/bin/env python3
"""Dig: L1 CF winners that turned toxic — common pre-rotation filters."""
from __future__ import annotations

import json
import math
import re
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path("/home/brad/projects/crypto-trading-bot")
OUT = ROOT / "data/state/l1_toxic_winner_filter_dig_latest.json"

# Known meme / hyper-beta / thin-name heuristics (ticker-level; not exhaustive universe)
MEME_OR_NARRATIVE = {
    "PUMP", "USELESS", "RAVE", "TRUMP", "PENGU", "WIF", "BONK", "PEPE", "FLOKI",
    "MOG", "MEW", "POPCAT", "NEIRO", "GOAT", "PNUT", "CHILLGUY", "FARTCOIN",
    "LIGHTER", "SKR", "HYPE", "MOODENG", "GIGA", "SPX", "BRETT", "TOSHI",
}
# Majors / high-liq core (harder to call "toxic seat" solely by name)
CORE_LIQ = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT", "ATOM",
    "NEAR", "UNI", "AAVE", "LTC", "BCH", "ETC", "FIL", "ICP", "APT", "SUI",
    "SEI", "INJ", "OP", "ARB", "TIA", "STX", "IMX", "RENDER", "FET", "CFG",
}


def base(pair: str) -> str:
    return (pair or "").replace("-USD", "").replace("-USDC", "").upper()


def is_memeish(pair: str) -> bool:
    b = base(pair)
    if b in MEME_OR_NARRATIVE:
        return True
    # very short novelty tickers often thin
    if len(b) <= 3 and b not in CORE_LIQ and b not in {"XRP", "SOL", "BNB", "OKB"}:
        # 3-letter non-core still often fine (e.g. FIL) — only flag if in meme set
        return False
    if re.search(r"(PUMP|MOON|INU|PEPE|WIF|BONK)", b):
        return True
    return False


def is_core(pair: str) -> bool:
    return base(pair) in CORE_LIQ


def parse_ts(s: Any) -> Optional[datetime]:
    if not s:
        return None
    t = str(s).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def fnum(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def hget(r: dict, hours: str, key: str) -> Optional[float]:
    h = (r.get("horizons") or {}).get(hours) or {}
    if h.get("status") and h.get("status") != "ok":
        return None
    return fnum(h.get(key))


def load_json(p: Path):
    if not p.exists():
        return None
    return json.loads(p.read_text())


def main() -> None:
    cf = load_json(ROOT / "data/state/basket_swap_shadow_counterfactual_latest.json") or {}
    rows = cf.get("unique_results") or []

    # Enrich from arm proposals if pick_id / ts match
    prop_by_key: Dict[Tuple[str, str, str], dict] = {}
    arms_dir = ROOT / "data/state/basket_select_arms"
    for arm_dir in arms_dir.iterdir() if arms_dir.exists() else []:
        if not arm_dir.is_dir():
            continue
        pj = arm_dir / "proposals.jsonl"
        if not pj.exists():
            continue
        for line in pj.read_text().splitlines():
            if not line.strip():
                continue
            try:
                p = json.loads(line)
            except Exception:
                continue
            arm = arm_dir.name
            key = (arm, str(p.get("remove")), str(p.get("add")))
            # keep latest
            prop_by_key[key] = p
            # also ts-rounded key
            ts = str(p.get("ts") or "")[:13]  # hour
            prop_by_key[(arm, str(p.get("remove")), str(p.get("add")), ts)] = p

    # Build per-swap feature rows with completed 7d and 14d when available
    feats: List[dict] = []
    for r in rows:
        arm = r.get("arm") or ""
        add = r.get("add") or ""
        rem = r.get("remove") or ""
        ex7 = hget(r, "168h", "excess_pct")
        add7 = hget(r, "168h", "add_ret_pct")
        rem7 = hget(r, "168h", "rem_ret_pct")
        btc7 = hget(r, "168h", "btc_ret_pct")
        ex1 = hget(r, "24h", "excess_pct")
        add1 = hget(r, "24h", "add_ret_pct")
        ex3 = hget(r, "72h", "excess_pct")
        add3 = hget(r, "72h", "add_ret_pct")
        ex14 = hget(r, "336h", "excess_pct")
        add14 = hget(r, "336h", "add_ret_pct")
        # path dependence: strong early then fade
        if ex7 is None:
            continue

        prop = prop_by_key.get((arm, rem, add)) or {}
        mp = prop.get("membership_potential") or r.get("membership_potential") or {}
        add_score = fnum(r.get("add_score") if r.get("add_score") is not None else prop.get("add_score"))
        rem_score = fnum(r.get("remove_score") if r.get("remove_score") is not None else prop.get("remove_score"))
        delta = fnum(r.get("delta") if r.get("delta") is not None else prop.get("delta"))
        inbound = fnum(mp.get("inbound_potential"))
        m_ok = bool(r.get("membership_potential_ok") or mp.get("ok") or prop.get("membership_potential_ok"))

        # toxicity labels (post-hoc, for learning filters — not used as live features)
        # A) name-class toxic seat
        name_toxic = is_memeish(add)
        # B) L1 win that later dumped: ex7>5 but add14<<0 or ex14<<0
        late_fade = False
        if add14 is not None and add7 is not None and add7 >= 5 and add14 <= -5:
            late_fade = True
        if ex7 is not None and ex7 >= 5 and ex14 is not None and ex14 <= -5:
            late_fade = True
        # C) huge path chase: 24h add already extended >15% while 7d still "win"
        chase_24 = bool(add1 is not None and add1 >= 15)
        # D) add ends red at 7d despite positive excess (remove crashed harder) — bag-beater not printer
        bag_beater = bool(ex7 is not None and ex7 > 0 and add7 is not None and add7 < 0)
        # E) catastrophic loser at 7d
        cat_loss = bool(ex7 is not None and ex7 <= -20)

        # L1 "winner" definition
        l1_win = bool(ex7 is not None and ex7 >= 5.0)  # material win bar
        l1_big = bool(ex7 is not None and ex7 >= 20.0)

        # toxic winner = L1 win AND (name toxic OR late fade OR (big win + chase))
        toxic_winner = bool(
            l1_win
            and (name_toxic or late_fade or (l1_big and chase_24 and not is_core(add)))
        )
        clean_winner = bool(l1_win and not toxic_winner and is_core(add) and not bag_beater)
        # broader clean: l1 win, not meme, not late fade
        cleanish = bool(l1_win and not name_toxic and not late_fade and not bag_beater)

        feats.append(
            {
                "arm": arm,
                "ts": r.get("ts"),
                "remove": rem,
                "add": add,
                "add_base": base(add),
                "ex7": ex7,
                "add7": add7,
                "rem7": rem7,
                "btc7": btc7,
                "ex1": ex1,
                "add1": add1,
                "ex3": ex3,
                "add3": add3,
                "ex14": ex14,
                "add14": add14,
                "add_score": add_score,
                "rem_score": rem_score,
                "delta": delta,
                "inbound_potential": inbound,
                "m_ok": m_ok,
                "name_toxic": name_toxic,
                "is_core_add": is_core(add),
                "is_core_rem": is_core(rem),
                "late_fade": late_fade,
                "chase_24": chase_24,
                "bag_beater": bag_beater,
                "cat_loss": cat_loss,
                "l1_win": l1_win,
                "l1_big": l1_big,
                "toxic_winner": toxic_winner,
                "clean_winner": clean_winner,
                "cleanish": cleanish,
                "layer_failed": mp.get("layer_failed"),
                "mp_reasons": mp.get("reasons"),
            }
        )

    wins = [f for f in feats if f["l1_win"]]
    toxic = [f for f in feats if f["toxic_winner"]]
    clean = [f for f in feats if f["cleanish"]]
    big = [f for f in feats if f["l1_big"]]

    print("=== COUNTS ===")
    print("completed_7d", len(feats))
    print("l1_win_ex7>=5", len(wins))
    print("l1_big_ex7>=20", len(big))
    print("toxic_winners", len(toxic))
    print("cleanish_winners", len(clean))
    print("name_toxic among wins", sum(1 for f in wins if f["name_toxic"]))
    print("late_fade among wins", sum(1 for f in wins if f["late_fade"]))
    print("chase_24 among wins", sum(1 for f in wins if f["chase_24"]))
    print("bag_beater among wins", sum(1 for f in wins if f["bag_beater"]))
    print("core add among wins", sum(1 for f in wins if f["is_core_add"]))

    def summarize(label: str, xs: List[dict]) -> dict:
        if not xs:
            print(label, "empty")
            return {"n": 0}
        def col(k):
            vals = [f[k] for f in xs if f.get(k) is not None]
            if not vals:
                return None
            return {
                "n": len(vals),
                "mean": round(st.mean(vals), 3),
                "med": round(st.median(vals), 3),
            }

        s = {
            "n": len(xs),
            "ex7": col("ex7"),
            "add7": col("add7"),
            "add1": col("add1"),
            "add14": col("add14"),
            "ex14": col("ex14"),
            "add_score": col("add_score"),
            "delta": col("delta"),
            "inbound": col("inbound_potential"),
            "btc7": col("btc7"),
            "pct_name_toxic": round(sum(1 for f in xs if f["name_toxic"]) / len(xs), 3),
            "pct_core_add": round(sum(1 for f in xs if f["is_core_add"]) / len(xs), 3),
            "pct_chase_24": round(sum(1 for f in xs if f["chase_24"]) / len(xs), 3),
            "pct_late_fade": round(sum(1 for f in xs if f["late_fade"]) / len(xs), 3),
            "pct_bag_beater": round(sum(1 for f in xs if f["bag_beater"]) / len(xs), 3),
            "pct_m_ok": round(sum(1 for f in xs if f["m_ok"]) / len(xs), 3),
            "top_adds": Counter(f["add"] for f in xs).most_common(12),
            "arms": Counter(f["arm"] for f in xs).most_common(),
        }
        print(f"\n=== {label} n={s['n']} ===")
        for k in ("ex7", "add7", "add1", "add14", "add_score", "delta", "inbound", "btc7"):
            print(f"  {k}: {s[k]}")
        for k in ("pct_name_toxic", "pct_core_add", "pct_chase_24", "pct_late_fade", "pct_bag_beater", "pct_m_ok"):
            print(f"  {k}: {s[k]}")
        print("  top_adds", s["top_adds"][:8])
        print("  arms", s["arms"])
        return s

    sum_toxic = summarize("TOXIC_WINNERS", toxic)
    sum_clean = summarize("CLEANISH_WINNERS", clean)
    sum_all_win = summarize("ALL_L1_WINS", wins)
    sum_big = summarize("BIG_WINS", big)

    # Compare toxic vs cleanish on pre-features
    print("\n=== PRE-FEATURE SEPARATION (toxic vs cleanish) ===")

    def mean_or_none(xs, k):
        vals = [f[k] for f in xs if f.get(k) is not None]
        return (round(st.mean(vals), 3), len(vals)) if vals else (None, 0)

    sep = {}
    for k in ("add_score", "delta", "inbound_potential", "add1", "add3", "ex1", "ex3"):
        mt, nt = mean_or_none(toxic, k)
        mc, nc = mean_or_none(clean, k)
        sep[k] = {"toxic_mean": mt, "toxic_n": nt, "clean_mean": mc, "clean_n": nc}
        print(f"  {k}: toxic={mt} (n={nt}) clean={mc} (n={nc})")

    # Rate of name_toxic by add_score terciles among all wins
    scored = [f for f in wins if f.get("add_score") is not None]
    if len(scored) >= 6:
        scored.sort(key=lambda f: f["add_score"])
        n = len(scored)
        bins = {
            "low": scored[: n // 3],
            "mid": scored[n // 3 : 2 * n // 3],
            "high": scored[2 * n // 3 :],
        }
        print("\n=== add_score terciles among L1 wins ===")
        score_bins = {}
        for name, bb in bins.items():
            score_bins[name] = {
                "n": len(bb),
                "mean_score": round(st.mean([f["add_score"] for f in bb]), 3),
                "pct_name_toxic": round(sum(1 for f in bb if f["name_toxic"]) / len(bb), 3),
                "pct_late_fade": round(sum(1 for f in bb if f["late_fade"]) / len(bb), 3),
                "mean_ex7": round(st.mean([f["ex7"] for f in bb]), 3),
                "mean_add14": round(st.mean([f["add14"] for f in bb if f.get("add14") is not None]), 3)
                if any(f.get("add14") is not None for f in bb)
                else None,
                "top": Counter(f["add"] for f in bb).most_common(5),
            }
            print(name, score_bins[name])
    else:
        score_bins = {}

    # 24h extension bins among wins
    print("\n=== add_ret_24h bins among L1 wins (path chase) ===")
    chase_bins = {}
    for lo, hi, name in [(-999, 5, "calm_<5"), (5, 15, "warm_5_15"), (15, 999, "hot_>=15")]:
        bb = [f for f in wins if f.get("add1") is not None and lo <= f["add1"] < hi]
        if not bb:
            continue
        chase_bins[name] = {
            "n": len(bb),
            "pct_name_toxic": round(sum(1 for f in bb if f["name_toxic"]) / len(bb), 3),
            "pct_late_fade": round(sum(1 for f in bb if f["late_fade"]) / len(bb), 3),
            "mean_ex7": round(st.mean([f["ex7"] for f in bb]), 3),
            "mean_add14": round(st.mean([f["add14"] for f in bb if f.get("add14") is not None]), 3)
            if any(f.get("add14") is not None for f in bb)
            else None,
            "pct_still_green_add14": round(
                sum(1 for f in bb if (f.get("add14") or 0) > 0) / max(1, sum(1 for f in bb if f.get("add14") is not None)),
                3,
            ),
            "examples": [(f["add"], f["ex7"], f.get("add1"), f.get("add14")) for f in sorted(bb, key=lambda x: -x["ex7"])[:5]],
        }
        print(name, chase_bins[name])

    # Filter simulation: among L1 wins, what do simple pre-filters keep?
    # Features available approx at proposal: name class, add_score magnitude, m_ok,
    # and *if we had* 24h lookback extension on ADD before seat (pre-feature)
    print("\n=== FILTER SIM on all completed swaps (not just wins) ===")
    # For each filter, report: n kept, mean ex7, hit, pct name toxic among kept wins, mean ex7 of kept

    def eval_filter(name: str, pred) -> dict:
        kept = [f for f in feats if pred(f)]
        if not kept:
            return {"name": name, "n": 0}
        xs = [f["ex7"] for f in kept]
        out = {
            "name": name,
            "n": len(kept),
            "mean_ex7": round(st.mean(xs), 3),
            "med_ex7": round(st.median(xs), 3),
            "hit": round(sum(1 for x in xs if x > 0) / len(xs), 3),
            "pct_name_toxic": round(sum(1 for f in kept if f["name_toxic"]) / len(kept), 3),
            "n_toxic_winners_kept": sum(1 for f in kept if f["toxic_winner"]),
            "n_cleanish_kept": sum(1 for f in kept if f["cleanish"]),
            "n_l1_wins_kept": sum(1 for f in kept if f["l1_win"]),
            "mean_ex7_wins_only": round(st.mean([f["ex7"] for f in kept if f["l1_win"]]), 3)
            if any(f["l1_win"] for f in kept)
            else None,
        }
        print(out)
        return out

    filters = []
    filters.append(eval_filter("baseline_all", lambda f: True))
    filters.append(eval_filter("block_meme_name", lambda f: not f["name_toxic"]))
    filters.append(eval_filter("core_add_only", lambda f: f["is_core_add"]))
    filters.append(eval_filter("m_ok_only", lambda f: f["m_ok"]))
    filters.append(eval_filter("block_meme_and_require_m_ok", lambda f: (not f["name_toxic"]) and f["m_ok"]))
    filters.append(
        eval_filter(
            "block_meme_and_core_or_m_ok",
            lambda f: (not f["name_toxic"]) and (f["is_core_add"] or f["m_ok"]),
        )
    )
    # score caps: extreme scores often meme momentum
    filters.append(
        eval_filter(
            "block_meme_or_add_score_ge_5",
            lambda f: (not f["name_toxic"]) and (f.get("add_score") is None or f["add_score"] < 5),
        )
    )
    filters.append(
        eval_filter(
            "block_if_add1_ge_15_noncore",
            lambda f: not (f.get("add1") is not None and f["add1"] >= 15 and not f["is_core_add"]),
        )
    )
    # combo recommended
    filters.append(
        eval_filter(
            "REC_block_meme_block_hot24_noncore_prefer_m_ok",
            lambda f: (not f["name_toxic"])
            and not (f.get("add1") is not None and f["add1"] >= 15 and not f["is_core_add"])
            and (f["m_ok"] or f["is_core_add"]),
        )
    )
    # Note: add1 is FORWARD 24h after proposal in CF — NOT a pure pre-feature!
    # Need honest label: using forward 24h is leakage for filter design.
    print("\n*** HONESTY: add1/ex1 in CF are FORWARD path after proposal, not pre-seat features. ***")
    print("*** Pre-seat proxies must be: name class, membership M*, missfire, liq, trailing extension at t0. ***")

    # Try to get trailing features from proposal reason strings / scores only
    print("\n=== name-class + m_ok + score only (true pre-features in this artifact) ===")
    pre_only = []
    pre_only.append(eval_filter("pre_block_meme", lambda f: not f["name_toxic"]))
    pre_only.append(eval_filter("pre_core_only", lambda f: f["is_core_add"]))
    pre_only.append(eval_filter("pre_m_ok", lambda f: f["m_ok"]))
    pre_only.append(eval_filter("pre_block_meme_m_ok", lambda f: (not f["name_toxic"]) and f["m_ok"]))
    pre_only.append(eval_filter("pre_block_meme_core", lambda f: (not f["name_toxic"]) and f["is_core_add"]))
    pre_only.append(
        eval_filter(
            "pre_block_meme_score_lt_3",
            lambda f: (not f["name_toxic"]) and (f.get("add_score") is None or f["add_score"] < 3),
        )
    )
    # high score without core
    pre_only.append(
        eval_filter(
            "pre_block_noncore_score_ge_2",
            lambda f: not ((not f["is_core_add"]) and f.get("add_score") is not None and f["add_score"] >= 2),
        )
    )
    pre_only.append(
        eval_filter(
            "pre_REC_core_or_(m_ok_and_not_meme_and_score_lt_5)",
            lambda f: f["is_core_add"]
            or (f["m_ok"] and (not f["name_toxic"]) and (f.get("add_score") is None or f["add_score"] < 5)),
        )
    )

    # List toxic winners explicitly
    print("\n=== TOXIC WINNER TABLE ===")
    toxic_sorted = sorted(toxic, key=lambda f: -f["ex7"])
    for f in toxic_sorted[:25]:
        print(
            f"{f['ts'][:19]} {f['arm'][:12]:12} {f['remove']:>12} → {f['add']:<14} "
            f"ex7={f['ex7']:+7.1f} add7={f.get('add7')} add14={f.get('add14')} "
            f"score={f.get('add_score')} meme={f['name_toxic']} fade={f['late_fade']} chase24={f['chase_24']}"
        )

    # Losers that were also name toxic (for specificity)
    toxic_loss = [f for f in feats if f["name_toxic"] and f["ex7"] is not None and f["ex7"] < 0]
    print("\nname_toxic losses n", len(toxic_loss), "mean_ex7", round(st.mean([f["ex7"] for f in toxic_loss]), 2) if toxic_loss else None)

    # Specificity: if we block meme names, what mean ex7 change overall
    all_xs = [f["ex7"] for f in feats]
    nm = [f["ex7"] for f in feats if not f["name_toxic"]]
    print("all mean_ex7", round(st.mean(all_xs), 2), "hit", round(sum(1 for x in all_xs if x > 0) / len(all_xs), 2))
    print("no_meme mean_ex7", round(st.mean(nm), 2), "hit", round(sum(1 for x in nm if x > 0) / len(nm), 2), "n", len(nm))

    # How often is best arm tip meme?
    print("\n=== by arm: pct name_toxic among L1 wins ===")
    by_arm = {}
    for arm in sorted(set(f["arm"] for f in feats)):
        w = [f for f in wins if f["arm"] == arm]
        if not w:
            continue
        by_arm[arm] = {
            "n_wins": len(w),
            "pct_meme": round(sum(1 for f in w if f["name_toxic"]) / len(w), 3),
            "mean_ex7": round(st.mean([f["ex7"] for f in w]), 2),
            "mean_ex7_nonmeme": round(st.mean([f["ex7"] for f in w if not f["name_toxic"]]), 2)
            if any(not f["name_toxic"] for f in w)
            else None,
        }
        print(arm, by_arm[arm])

    # Membership gate fail reasons on toxic winners vs clean
    print("\n=== m_ok rates ===")
    print("toxic m_ok", sum(1 for f in toxic if f["m_ok"]), "/", len(toxic))
    print("cleanish m_ok", sum(1 for f in clean if f["m_ok"]), "/", len(clean))

    payload = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "n_completed_7d": len(feats),
        "n_l1_win": len(wins),
        "n_toxic_winner": len(toxic),
        "n_cleanish": len(clean),
        "sum_toxic": sum_toxic,
        "sum_cleanish": sum_clean,
        "sum_all_win": sum_all_win,
        "separation": sep,
        "score_bins": score_bins if "score_bins" in dir() else {},
        "chase_bins_FORWARD_LEAKY": chase_bins,
        "filters_all": filters,
        "filters_pre_only": pre_only,
        "by_arm_wins": by_arm,
        "toxic_examples": [
            {
                "ts": f["ts"],
                "arm": f["arm"],
                "remove": f["remove"],
                "add": f["add"],
                "ex7": f["ex7"],
                "add7": f["add7"],
                "add14": f["add14"],
                "add_score": f["add_score"],
                "name_toxic": f["name_toxic"],
                "late_fade": f["late_fade"],
            }
            for f in toxic_sorted[:20]
        ],
        "honesty": [
            "CF horizons are forward path after proposal — do not use 24h add_ret as a pre-seat filter without a trailing feature at t0.",
            "Name-class meme list is heuristic; maintain via config allow/deny, not vibes.",
            "L1 excess can be bag-beater (remove crash) — require add_ret>=0 for 'printer' language.",
            "m_ok rate is low; M-gate already kills most junk but not all L1 toxic winners (many wins never got m_ok).",
        ],
        "recommended_pre_filters": [
            "Block meme/narrative ticker denylist (PUMP/USELESS/RAVE/LIGHTER-class) from ADD",
            "Prefer core liquid ADD OR (membership M-ok AND not meme)",
            "Cap non-core add_score extremes (risk_adj_mom raw scores >> hybrid 0-1)",
            "Require trailing (t0) extension gate: reject non-core ADD if r24 already >= ~10-15% (needs feature wire, not CF forward)",
            "Keep missfire + M1-M3 + remove-flat; do not treat L1 max excess as promote rank",
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
