#!/usr/bin/env python3
"""Shadow + multi-regime backfill for liquidation partial redeploy.

Never places orders. Writes:
  data/state/liquidation_redeploy_shadow.jsonl  (append events)
  data/state/liquidation_redeploy_shadow_summary.json
  reports/LIQUIDATION_REDEPLOY_SHADOW_LATEST.md

Modes:
  --backfill   replay free-cap sells from ledger (default)
  --live-once  evaluate latest rotation free-cap + current RSI/sent/regime
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.liquidation_redeploy_shadow import (  # noqa: E402
    Candidate,
    evaluate_shadow,
    merge_cfg,
    size_usd,
)

LEDGER = ROOT / "trades" / "phase6_trades.jsonl"
SHADOW_LOG = ROOT / "data/state/liquidation_redeploy_shadow.jsonl"
SUMMARY = ROOT / "data/state/liquidation_redeploy_scoreboard.json"
# prefer policy name
SUMMARY_PATH = ROOT / "data/state/liquidation_redeploy_shadow_summary.json"
REPORT = ROOT / "reports/LIQUIDATION_REDEPLOY_SHADOW_LATEST.md"
REGIME_STATUS = ROOT / "data/state/regime_cash_status.json"
SENT_CACHE = ROOT / "data/state/sentiment_cache.json"
RSI_CACHE = ROOT / "data/state/rsi_cache.json"
CUT_DEFAULT = "2026-07-01T00:00:00+00:00"
FEE_RT = 0.006


def _parse(ts: Any) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def load_ledger(path: Path = LEDGER) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        dt = _parse(r.get("timestamp"))
        if not dt:
            continue
        side = str(r.get("side") or "").upper()
        reason = str(r.get("reason") or "").lower()
        pair = str(r.get("pair") or "").upper()
        qty = r.get("qty") if r.get("qty") is not None else r.get("quantity")
        px = r.get("entry_price") or r.get("exit_price") or r.get("price")
        try:
            usd = float(qty) * float(px) if qty is not None and px is not None else 0.0
        except Exception:
            usd = 0.0
        try:
            pnl = float(r["pnl"]) if r.get("pnl") is not None else None
        except Exception:
            pnl = None
        rows.append(
            dict(dt=dt, side=side, reason=reason, pair=pair, usd=usd, pnl=pnl, px=float(px or 0) or None)
        )
    rows.sort(key=lambda x: x["dt"])
    return rows


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def live_candidates() -> tuple[list[Candidate], dict[str, Any]]:
    sent = _load_json(SENT_CACHE).get("sentiment") or {}
    rsi = _load_json(RSI_CACHE).get("rsi") or {}
    meta: dict[str, Any] = {"sent_n": len(sent) if isinstance(sent, dict) else 0, "rsi_n": len(rsi) if isinstance(rsi, dict) else 0}
    cands: list[Candidate] = []
    pairs = set()
    if isinstance(sent, dict):
        pairs |= {str(k).upper() for k in sent.keys()}
    if isinstance(rsi, dict):
        pairs |= {str(k).upper() for k in rsi.keys()}
    for pair in sorted(pairs):
        s_raw = sent.get(pair) if isinstance(sent, dict) else None
        if isinstance(s_raw, dict):
            s_val = s_raw.get("score", s_raw.get("sentiment"))
        else:
            s_val = s_raw
        r_raw = rsi.get(pair) if isinstance(rsi, dict) else None
        if isinstance(r_raw, dict):
            r_val = r_raw.get("rsi", r_raw.get("value"))
        else:
            r_val = r_raw
        try:
            s_f = float(s_val) if s_val is not None else None
        except Exception:
            s_f = None
        try:
            r_f = float(r_val) if r_val is not None else None
        except Exception:
            r_f = None
        # crude score aligned with brief: prefer moderate RSI + positive sent
        score = 0.0
        if s_f is not None:
            score += max(-0.5, min(0.5, s_f)) * 0.6 + 0.3
        if r_f is not None:
            # prefer not overbought for entries under flat B
            if r_f <= 55:
                score += 0.25
            elif r_f <= 65:
                score += 0.05
            else:
                score -= 0.2
        cands.append(
            Candidate(
                pair=pair,
                score=round(score, 4),
                rsi=r_f,
                sentiment=s_f,
                is_new_pair=True,
            )
        )
    return cands, meta


def regime_label_at(dt: datetime, btc_rows: list[dict[str, Any]] | None = None) -> str:
    """Coarse regime proxy from BTC path if available; else unknown."""
    # Prefer live status only for "now"; historical: use simple BTC 30d if we can from ledger prices
    return "unknown"


def oracle_forward_return(
    rows: list[dict[str, Any]],
    *,
    t0: datetime,
    pair: str,
    horizon_h: float = 168.0,
) -> float | None:
    """Rough CF: use next sell px or later buy/sell marks on pair — limited.

    Prefer: first trade on pair after t0 with px, vs last trade before/at horizon.
    Returns fractional return or None.
    """
    px0 = None
    px1 = None
    t1 = t0 + timedelta(hours=horizon_h)
    for r in rows:
        if r["pair"] != pair or r["px"] is None:
            continue
        if r["dt"] <= t0:
            px0 = r["px"]
            continue
        if r["dt"] > t1:
            break
        px1 = r["px"]
    if px0 and px1 and px0 > 0:
        return (px1 - px0) / px0
    return None


def best_oracle_candidate(
    rows: list[dict[str, Any]],
    *,
    t0: datetime,
    sell_pair: str,
    universe: list[str],
    horizon_h: float = 168.0,
) -> tuple[str | None, float | None]:
    best_p, best_r = None, None
    for p in universe:
        if p == sell_pair:
            continue
        ret = oracle_forward_return(rows, t0=t0, pair=p, horizon_h=horizon_h)
        if ret is None:
            continue
        if best_r is None or ret > best_r:
            best_r, best_p = ret, p
    return best_p, best_r


def actual_follow_sl_pnl(
    rows: list[dict[str, Any]], *, t0: datetime, window_h: float = 24.0
) -> dict[str, Any]:
    buys = []
    for r in rows:
        if r["side"] != "BUY" or r["dt"] <= t0:
            continue
        if (r["dt"] - t0).total_seconds() > window_h * 3600:
            break
        if "preserve" in r["reason"]:
            continue
        buys.append(r)
    sl_pnl = 0.0
    n_sl = 0
    for b in buys:
        for s in rows:
            if s["dt"] <= b["dt"]:
                continue
            if (s["dt"] - b["dt"]).total_seconds() > 7 * 86400:
                break
            if s["side"] == "SELL" and s["pair"] == b["pair"] and "stop_loss" in s["reason"]:
                sl_pnl += float(s["pnl"] or 0)
                n_sl += 1
                break
    return {
        "n_buys": len(buys),
        "buy_usd": round(sum(b["usd"] for b in buys), 2),
        "n_sl_7d": n_sl,
        "sl_pnl_7d": round(sl_pnl, 2),
    }


def classify_regime_proxy(rows: list[dict[str, Any]], t0: datetime) -> str:
    """BTC mid price path ~30d if present in ledger marks — coarse."""
    btc = [r for r in rows if r["pair"] == "BTC-USD" and r["px"]]
    if len(btc) < 4:
        return "unknown"
    window = [r for r in btc if t0 - timedelta(days=35) <= r["dt"] <= t0]
    if len(window) < 2:
        return "unknown"
    p0, p1 = window[0]["px"], window[-1]["px"]
    if not p0:
        return "unknown"
    ret = (p1 - p0) / p0 * 100.0
    if ret >= 15:
        return "bull"
    if ret <= -10:
        return "bear"
    if abs(ret) <= 8:
        return "flat"
    return "transitional"


def backfill(cfg: dict[str, Any], cut: datetime) -> dict[str, Any]:
    rows = load_ledger()
    universe = sorted({r["pair"] for r in rows if r["pair"]})
    # Live gates as standing flat-B proxy for historical policy shadow
    st = _load_json(REGIME_STATUS)
    entry = st.get("entry") or {}
    allow_buys = bool(st.get("allow_new_buys", True))
    live_cands, cand_meta = live_candidates()

    events: list[dict[str, Any]] = []
    for r in rows:
        if r["dt"] < cut or r["side"] != "SELL" or r["usd"] < 50:
            continue
        if not any(k in r["reason"] for k in ("rotation", "stop_loss", "manual")):
            continue
        regime = classify_regime_proxy(rows, r["dt"])
        # Policy shadow uses *current* RSI/sent as stand-in only for fire taxonomy demo on latest;
        # for history we still run reason/size gates + oracle CF (honest about gate limitation).
        dec = evaluate_shadow(
            sell_pair=r["pair"],
            sell_reason=r["reason"],
            proceeds_usd=r["usd"],
            regime=regime,
            allow_new_buys=True if regime != "bear" else allow_buys,
            entry_gates=entry if entry else {"max_rsi": 55.0, "min_sentiment": 0.25, "min_sentiment_new_pair": 0.35},
            candidates=live_cands,  # structural: historical RSI not in ledger — see oracle
            cfg=cfg,
            cooldown_pairs=[r["pair"]],
        )
        # Override: for historical, candidate gates with *live* scores are not valid →
        # separate fields: policy_size + oracle hop
        sz = size_usd(r["usd"], cfg)
        ok_reason, why = True, "ok"
        from phase6.core.liquidation_redeploy_shadow import reason_allowed

        ok_reason, why = reason_allowed(r["reason"], cfg)
        policy_eligible = ok_reason and sz > 0
        if regime == "bear" and cfg.get("require_regime_allow_new_buys", True):
            # bear proxy often park — mark skip for policy
            policy_fire = False
            policy_skip = "regime_proxy_bear_block"
        elif not policy_eligible:
            policy_fire = False
            policy_skip = why if not ok_reason else "below_min_or_zero"
        else:
            policy_fire = True
            policy_skip = None

        ora_p, ora_r = best_oracle_candidate(
            rows, t0=r["dt"], sell_pair=r["pair"], universe=universe, horizon_h=168.0
        )
        ora_pnl = None
        if policy_fire and ora_r is not None and sz > 0:
            ora_pnl = round(sz * float(ora_r) - sz * float(cfg.get("fee_rt_assumed", FEE_RT)), 2)

        follow = actual_follow_sl_pnl(rows, t0=r["dt"], window_h=24.0)
        hold_pnl = 0.0  # cash hold baseline after fees already paid on sell

        events.append(
            {
                "ts": r["dt"].isoformat(),
                "sell_pair": r["pair"],
                "sell_reason": r["reason"],
                "proceeds_usd": round(r["usd"], 2),
                "regime_proxy": regime,
                "policy_eligible": policy_fire,
                "policy_skip": policy_skip,
                "shadow_size_usd": sz if policy_fire else 0.0,
                "fee_usd": round(sz * float(cfg.get("fee_rt_assumed", FEE_RT)), 4) if policy_fire else 0.0,
                "oracle_pair_7d": ora_p,
                "oracle_ret_7d": None if ora_r is None else round(float(ora_r), 4),
                "oracle_net_pnl_vs_hold": ora_pnl,
                "actual_follow_24h": follow,
                "hold_baseline_pnl": hold_pnl,
                "live_gate_decision_nonhistorical": dec.to_dict(),
            }
        )

    by_reg: dict[str, list] = defaultdict(list)
    for e in events:
        by_reg[e["regime_proxy"]].append(e)

    def agg(xs: list[dict[str, Any]]) -> dict[str, Any]:
        elig = [e for e in xs if e["policy_eligible"]]
        ora = [e for e in elig if e.get("oracle_net_pnl_vs_hold") is not None]
        return {
            "n_events": len(xs),
            "n_policy_eligible": len(elig),
            "eligibility_rate": round(len(elig) / len(xs), 3) if xs else None,
            "sum_shadow_size": round(sum(e["shadow_size_usd"] for e in elig), 2),
            "sum_fees": round(sum(e["fee_usd"] for e in elig), 2),
            "oracle_n": len(ora),
            "oracle_sum_net_pnl": round(sum(e["oracle_net_pnl_vs_hold"] for e in ora), 2) if ora else None,
            "oracle_mean_net_pnl": round(
                sum(e["oracle_net_pnl_vs_hold"] for e in ora) / len(ora), 2
            )
            if ora
            else None,
            "oracle_win_rate": round(
                sum(1 for e in ora if (e["oracle_net_pnl_vs_hold"] or 0) > 0) / len(ora), 3
            )
            if ora
            else None,
            "actual_follow_sl_pnl_sum": round(
                sum(e["actual_follow_24h"]["sl_pnl_7d"] for e in xs), 2
            ),
        }

    summary = {
        "schema": "liquidation_redeploy_shadow_summary_v1",
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "cut": cut.isoformat(),
        "cfg": cfg,
        "candidate_meta_live": cand_meta,
        "note": (
            "Historical policy eligibility = reason allow-list + size + bear proxy block. "
            "Entry RSI/sent gates need live/cache at event time (not fully reconstructed); "
            "oracle_net_pnl is an upper-bound if we always picked the best 7d pair in-universe."
        ),
        "overall": agg(events),
        "by_regime_proxy": {k: agg(v) for k, v in sorted(by_reg.items())},
        "best_case_definition": {
            "product": "Shadow fires only on rotation free-cap; size=min(25% proceeds,$75); net hop expectancy after fees >0 over ≥30d and ≥15 events; second-SL rate ≤ hold path; multi-regime not only bull",
            "oracle_upper_bound": "If every eligible event picked the best 7d forward pair in ledger universe at shadow size, minus fee_rt",
        },
        "events": events,
    }
    return summary


def live_once(cfg: dict[str, Any]) -> dict[str, Any]:
    rows = load_ledger()
    st = _load_json(REGIME_STATUS)
    entry = st.get("entry") or {}
    cands, meta = live_candidates()
    # latest rotation-like sell
    target = None
    for r in reversed(rows):
        if r["side"] != "SELL" or r["usd"] < 50:
            continue
        if "rotation" in r["reason"] or "manual" in r["reason"]:
            target = r
            break
    if not target:
        return {"status": "no_recent_rotation_sell", "candidate_meta": meta}

    dec = evaluate_shadow(
        sell_pair=target["pair"],
        sell_reason=target["reason"],
        proceeds_usd=target["usd"],
        regime=str(st.get("regime") or "unknown"),
        allow_new_buys=bool(st.get("allow_new_buys", True)),
        entry_gates=entry,
        candidates=cands,
        cfg=cfg,
        cooldown_pairs=[target["pair"]],
    )
    payload = {
        "status": "ok",
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "trigger": {
            "ts": target["dt"].isoformat(),
            "pair": target["pair"],
            "reason": target["reason"],
            "usd": round(target["usd"], 2),
        },
        "regime_status": {
            "regime": st.get("regime"),
            "allow_new_buys": st.get("allow_new_buys"),
            "rebalance_cap_usd": st.get("rebalance_cap_usd"),
            "label": st.get("label"),
        },
        "decision": dec.to_dict(),
        "candidate_meta": meta,
        "orders_placed": 0,
        "mode": "shadow",
    }
    return payload


def render_md(summary: dict[str, Any], live: dict[str, Any] | None = None) -> str:
    o = summary.get("overall") or {}
    lines = [
        "# Liquidation redeploy — shadow scoreboard",
        "",
        f"**As of:** {summary.get('as_of')}  ",
        f"**Cut:** {summary.get('cut')}  ",
        f"**Orders placed:** **0** (shadow only)",
        "",
        "## Best-case outcome (what “good” looks like)",
        "",
        "1. **Product best case:** On eligible **rotation** free-cap events, shadow would-fire a **≤$75 / 25%** hop into a gate-passing pair; over ≥30 days and ≥15 fires, **net PnL after fees > hold-cash ($0 hop)**, second-stop rate no worse than baseline, and this is not only a bull artifact.  ",
        "2. **Oracle upper bound (this report):** If we had perfect hindsight and always bought the best 7d pair in-universe at shadow size, what net $ after fees? If *that* is ≤0, live partial cannot be justified.  ",
        "3. **Ops best case:** Skip reasons are explainable by regime (bear park, RSI gate, deny SL proceeds) — not silent bugs.",
        "",
        "## Overall backfill",
        "",
        f"| Metric | Value |",
        f"|--------|------:|",
        f"| Free-cap events | {o.get('n_events')} |",
        f"| Policy eligible (rotation allow-list + size + not bear-block) | {o.get('n_policy_eligible')} ({o.get('eligibility_rate')}) |",
        f"| Shadow notional sum | ${o.get('sum_shadow_size')} |",
        f"| Fee sum @ cfg | ${o.get('sum_fees')} |",
        f"| Oracle n / sum net PnL / mean / WR | {o.get('oracle_n')} / **{o.get('oracle_sum_net_pnl')}** / {o.get('oracle_mean_net_pnl')} / {o.get('oracle_win_rate')} |",
        f"| Actual follow-buy SL PnL (live path) | {o.get('actual_follow_sl_pnl_sum')} |",
        "",
        "## By regime proxy (BTC ~30d path at event)",
        "",
        "| Regime | n | eligible | oracle sum net | oracle WR | actual follow SL $ |",
        "|--------|--:|---------:|---------------:|----------:|-------------------:|",
    ]
    for reg, a in (summary.get("by_regime_proxy") or {}).items():
        lines.append(
            f"| {reg} | {a.get('n_events')} | {a.get('n_policy_eligible')} | {a.get('oracle_sum_net_pnl')} | {a.get('oracle_win_rate')} | {a.get('actual_follow_sl_pnl_sum')} |"
        )
    lines += [
        "",
        f"_{summary.get('note')}_",
        "",
    ]
    if live:
        d = (live.get("decision") or {})
        lines += [
            "## Live-once (latest rotation-class sell + current RSI/sent)",
            "",
            f"- Trigger: `{live.get('trigger')}`  ",
            f"- Regime: `{live.get('regime_status')}`  ",
            f"- **Would fire:** **{d.get('fire')}** · skip=`{d.get('skip_reason')}`  ",
            f"- Size `${d.get('size_usd')}` → `{d.get('candidate_pair')}` score={d.get('candidate_score')} fee=${d.get('fee_usd')}  ",
            f"- Orders placed: **{live.get('orders_placed', 0)}**",
            "",
        ]
    lines += [
        "## Go/no-go",
        "",
        "Shadow collection only. **No live_partial** until product gates in "
        "`docs/features/LIQUIDATION_ROTATION_REDEPLOY_POLICY.md` §5.",
        "",
        "Regen: `bash scripts/phase6/run_liquidation_redeploy_shadow.sh`",
        "",
    ]
    return "\n".join(lines) + "\n"


def append_shadow_log(rows: list[dict[str, Any]]) -> None:
    SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SHADOW_LOG.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true", default=True)
    ap.add_argument("--no-backfill", action="store_true")
    ap.add_argument("--live-once", action="store_true")
    ap.add_argument("--cut", default=CUT_DEFAULT)
    args = ap.parse_args(argv)

    cfg = merge_cfg({"mode": "shadow"})
    cut = _parse(args.cut) or datetime(2026, 7, 1, tzinfo=timezone.utc)

    live_payload = None
    if args.live_once or True:
        # always attach live-once snapshot for ops clarity
        live_payload = live_once(cfg)
        append_shadow_log(
            [
                {
                    "type": "live_once",
                    "as_of": live_payload.get("as_of"),
                    "payload": live_payload,
                }
            ]
        )

    summary = None
    if not args.no_backfill:
        summary = backfill(cfg, cut)
        # compact log lines for eligible only
        append_shadow_log(
            [
                {
                    "type": "backfill_event",
                    "ts": e["ts"],
                    "sell_pair": e["sell_pair"],
                    "policy_eligible": e["policy_eligible"],
                    "shadow_size_usd": e["shadow_size_usd"],
                    "regime_proxy": e["regime_proxy"],
                    "oracle_net_pnl_vs_hold": e.get("oracle_net_pnl_vs_hold"),
                }
                for e in (summary.get("events") or [])
                if e.get("policy_eligible")
            ]
        )
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(render_md(summary, live_payload), encoding="utf-8")
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        (ROOT / f"reports/LIQUIDATION_REDEPLOY_SHADOW_{day}.md").write_text(
            render_md(summary, live_payload), encoding="utf-8"
        )
        o = summary.get("overall") or {}
        print(
            f"backfill events={o.get('n_events')} eligible={o.get('n_policy_eligible')} "
            f"oracle_sum={o.get('oracle_sum_net_pnl')} follow_sl={o.get('actual_follow_sl_pnl_sum')}"
        )
        print("wrote", SUMMARY_PATH)
        print("wrote", REPORT)

    if live_payload:
        d = live_payload.get("decision") or {}
        print(
            f"live_once fire={d.get('fire')} skip={d.get('skip_reason')} "
            f"size={d.get('size_usd')} -> {d.get('candidate_pair')}"
        )
    print("orders_placed=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
