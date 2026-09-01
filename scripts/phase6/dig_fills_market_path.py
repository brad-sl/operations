#!/usr/bin/env python3
"""Fills / MARKET-only path dig (read-only). No live order changes.

Answers:
  1) Why verified fills are MARKET + STOP_LIMIT only
  2) Code path vs config intent
  3) Realized fee bps vs config fee constants vs live /transaction_summary if available
  4) Whether a maker entry path even exists in the live client
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

NOW = datetime.now(timezone.utc)
ACC = "3176ac3f-deca-4fca-9c67-87ba91f96558"
OUT_JSON = ROOT / "reports" / "FILLS_MARKET_PATH_DIG.json"
OUT_MD = ROOT / "reports" / "FILLS_MARKET_PATH_DIG.md"


def parse_ts(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        if s > 1e12:
            s = s / 1000.0
        return datetime.fromtimestamp(s, tz=timezone.utc)
    s = str(s).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def fnum(x, default=None):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def load_fills() -> List[dict]:
    """Reuse fee-audit shape from exchange_fills + verified."""
    fills: List[dict] = []
    ef = ROOT / "trades/phase6_exchange_fills.jsonl"
    if ef.exists():
        for ln in ef.read_text().strip().splitlines():
            if not ln.strip():
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            o = d.get("order") or {}
            lr = d.get("ledger_row") or {}
            ts = parse_ts(
                o.get("last_fill_time")
                or o.get("created_time")
                or lr.get("timestamp")
                or d.get("ingested_at")
            )
            pair = o.get("product_id") or lr.get("pair")
            side = (o.get("side") or lr.get("side") or "").upper()
            filled_val = fnum(o.get("filled_value"))
            if filled_val is None:
                q = fnum(o.get("filled_size") or lr.get("qty"))
                px = fnum(
                    o.get("average_filled_price")
                    or lr.get("exit_price")
                    or lr.get("entry_price")
                )
                if q is not None and px is not None:
                    filled_val = q * px
            fees = fnum(o.get("total_fees"))
            if fees is None:
                fees = fnum(lr.get("fees"))
            if fees is None:
                cd = o.get("commission_detail_total") or {}
                fees = fnum(cd.get("total_commission") or cd.get("client_commission"))
            ot = (o.get("order_type") or lr.get("order_type") or "").upper()
            # Coinbase sometimes embeds config type
            oc = o.get("order_configuration") or {}
            if not ot and isinstance(oc, dict):
                if "market_market_ioc" in oc:
                    ot = "MARKET"
                elif "sor_limit_ioc" in oc or "limit_limit_gtc" in oc or "limit_limit_fok" in oc:
                    ot = "LIMIT"
                elif any("stop" in k for k in oc.keys()):
                    ot = "STOP_LIMIT"
            fills.append(
                {
                    "source": "exchange_fills",
                    "order_id": o.get("order_id") or lr.get("order_id"),
                    "ts": ts,
                    "pair": pair,
                    "side": side,
                    "notional": filled_val,
                    "fees": fees or 0.0,
                    "order_type": ot,
                    "reason": lr.get("reason") or lr.get("exit_reason") or "",
                    "signal_source": lr.get("signal_source") or "",
                    "completion": o.get("completion_percentage"),
                    "status": o.get("status"),
                    "raw_order_keys": sorted(list(o.keys()))[:40],
                    "has_commission_detail": bool(o.get("commission_detail_total")),
                    "total_value_after_fees": fnum(o.get("total_value_after_fees")),
                    "number_of_fills": o.get("number_of_fills"),
                }
            )

    vdir = ROOT / f"data/state/trading_log/{ACC}"
    if vdir.exists():
        for p in sorted(vdir.glob("verified_fills_*.jsonl")):
            for ln in p.read_text().strip().splitlines():
                if not ln.strip():
                    continue
                try:
                    d = json.loads(ln)
                except Exception:
                    continue
                ts = parse_ts(d.get("ts") or d.get("timestamp") or d.get("filled_at"))
                fills.append(
                    {
                        "source": "verified",
                        "order_id": d.get("order_id"),
                        "ts": ts,
                        "pair": d.get("pair") or d.get("product_id"),
                        "side": (d.get("side") or "").upper(),
                        "notional": fnum(d.get("notional") or d.get("filled_value")),
                        "fees": fnum(d.get("fees"), 0.0) or 0.0,
                        "order_type": (d.get("order_type") or "").upper(),
                        "reason": d.get("reason") or "",
                        "signal_source": d.get("signal_source") or "",
                    }
                )

    # dedupe by order_id prefer exchange_fills + fees
    m: Dict[str, dict] = {}
    no_id: List[dict] = []
    for f in fills:
        oid = f.get("order_id")
        if not oid:
            no_id.append(f)
            continue
        prev = m.get(oid)
        if not prev:
            m[oid] = f
            continue
        score = (1 if f["source"] == "exchange_fills" else 0) + (1 if f["fees"] else 0)
        pscore = (1 if prev["source"] == "exchange_fills" else 0) + (
            1 if prev["fees"] else 0
        )
        if score >= pscore:
            merged = dict(prev)
            merged.update({k: v for k, v in f.items() if v not in (None, "", [])})
            merged["fees"] = max(float(prev.get("fees") or 0), float(f.get("fees") or 0))
            m[oid] = merged
    out = list(m.values()) + no_id
    for f in out:
        n = f.get("notional") or 0
        fee = f.get("fees") or 0
        f["fee_pct"] = (fee / n * 100) if n and n > 0 else None
        ot = (f.get("order_type") or "").upper()
        if "STOP" in ot:
            f["liq"] = "taker_stop"
        elif "MARKET" in ot:
            f["liq"] = "taker_market"
        elif "LIMIT" in ot:
            f["liq"] = "limit_unknown_liq"  # no maker flag on rows
        else:
            f["liq"] = "unknown"
    return out


def window_stats(rows: List[dict], days: int) -> dict:
    cut = NOW - timedelta(days=days)
    rs = [r for r in rows if r.get("ts") and r["ts"] >= cut]
    fees = sum(r.get("fees") or 0 for r in rs)
    notional = sum(r.get("notional") or 0 for r in rs if r.get("notional"))
    rates = sorted(
        r["fee_pct"]
        for r in rs
        if r.get("fee_pct") is not None and (r.get("notional") or 0) > 1
    )

    def pct(xs, p):
        if not xs:
            return None
        return round(xs[int(round((p / 100) * (len(xs) - 1)))], 4)

    ot = Counter((r.get("order_type") or "—") for r in rs)
    liq = Counter(r.get("liq") for r in rs)
    side = Counter(r.get("side") for r in rs)
    reason = Counter((r.get("reason") or r.get("signal_source") or "—")[:48] for r in rs)
    by_side_fee = defaultdict(float)
    by_side_n = Counter()
    by_liq_fee = defaultdict(float)
    for r in rs:
        by_side_fee[r.get("side") or "?"] += r.get("fees") or 0
        by_side_n[r.get("side") or "?"] += 1
        by_liq_fee[r.get("liq") or "?"] += r.get("fees") or 0
    # BUY vs SELL fee rates
    buy_rates = [
        r["fee_pct"]
        for r in rs
        if r.get("side") == "BUY" and r.get("fee_pct") is not None and (r.get("notional") or 0) > 1
    ]
    sell_rates = [
        r["fee_pct"]
        for r in rs
        if r.get("side") == "SELL" and r.get("fee_pct") is not None and (r.get("notional") or 0) > 1
    ]
    buy_rates.sort()
    sell_rates.sort()
    # samples near median fee
    samples = []
    for r in sorted(rs, key=lambda x: -(x.get("fees") or 0))[:8]:
        samples.append(
            {
                "ts": r["ts"].isoformat() if r.get("ts") else None,
                "pair": r.get("pair"),
                "side": r.get("side"),
                "order_type": r.get("order_type"),
                "notional": round(r.get("notional") or 0, 2),
                "fees": round(r.get("fees") or 0, 4),
                "fee_pct": round(r["fee_pct"], 4) if r.get("fee_pct") is not None else None,
                "reason": r.get("reason") or r.get("signal_source"),
            }
        )
    return {
        "days": days,
        "n": len(rs),
        "total_fees": round(fees, 4),
        "total_notional": round(notional, 2),
        "fee_pct_of_notional": round(fees / notional * 100, 4) if notional else None,
        "fee_pct_median": pct(rates, 50),
        "fee_pct_p25": pct(rates, 25),
        "fee_pct_p75": pct(rates, 75),
        "fee_pct_mean": round(sum(rates) / len(rates), 4) if rates else None,
        "n_with_rate": len(rates),
        "order_types": ot.most_common(),
        "liq_class": liq.most_common(),
        "sides": dict(side),
        "fees_by_side": {k: round(v, 4) for k, v in by_side_fee.items()},
        "fees_by_liq": {k: round(v, 4) for k, v in by_liq_fee.items()},
        "buy_fee_pct_median": pct(buy_rates, 50),
        "sell_fee_pct_median": pct(sell_rates, 50),
        "top_reasons": reason.most_common(15),
        "top_fee_samples": samples,
        "limit_count": sum(1 for r in rs if "LIMIT" in (r.get("order_type") or "") and "STOP" not in (r.get("order_type") or "")),
        "market_count": sum(1 for r in rs if (r.get("order_type") or "") == "MARKET"),
        "stop_count": sum(1 for r in rs if "STOP" in (r.get("order_type") or "")),
    }


def code_path_audit() -> dict:
    """Static facts from source — no execution."""
    oe = (ROOT / "phase6/core/order_executor.py").read_text()
    ex = (ROOT / "phase6/core/exchange_client.py").read_text()
    cl = (ROOT / "phase6/core/config_loader.py").read_text()
    pme = (ROOT / "phase6/core/protected_market_exit.py").read_text()
    facts = {
        "buy_path": "OrderExecutor.execute_buy → exchange.place_market_buy → market_market_ioc (quote_size)",
        "sell_path": "OrderExecutor.execute_sell → protected_market_exit → place_market_sell → market_market_ioc (base_size)",
        "config_order_type_hardcoded": 'config_loader.get_config → order_type="market" (not read from JSON)',
        "config_fee_constants": {
            "COINBASE_MAKER_FEE_RATE": 0.0025,
            "COINBASE_TAKER_FEE_RATE": 0.0040,
            "note": "Stated Advanced-1 style; not used by place_market_* body",
        },
        "execute_buy_calls_place_market_buy": "place_market_buy" in oe and "def execute_buy" in oe,
        "place_limit_buy_on_exchange_client": "def place_limit_buy" in ex,
        "place_limit_sell_on_exchange_client": "def place_limit_sell" in ex,
        "place_market_buy_uses_ioc": "market_market_ioc" in ex,
        "protected_exit_is_market": "place_market_sell" in pme,
        "strategy_doc_string": None,
        "limit_buy_exists_legacy_wrapper": (ROOT / "coinbase_wrapper_FIXED.py").exists()
        and "def place_limit_buy" in (ROOT / "coinbase_wrapper_FIXED.py").read_text(),
        "tp_attach_uses_limit_post_only": "post_only=True" in (ROOT / "phase6/core/stop_loss_manager.py").read_text(),
        "implication": (
            "MARKET-only on verified entry/exit path is by design of current Phase6 executor, "
            "not a mysterious regression of a live maker path. Legacy place_limit_buy lives outside "
            "phase6/core/exchange_client.py and is not called by OrderExecutor."
        ),
    }
    cfg = ROOT / "config/trading_config_phase6.json"
    if cfg.exists():
        try:
            j = json.loads(cfg.read_text())
            gs = j.get("global_settings") or {}
            facts["config_json_order_type_field"] = gs.get("order_type") or j.get("order_type")
            facts["strategy_doc_string"] = (j.get("phase_6_specific") or {}).get("strategy") or gs.get(
                "strategy"
            )
        except Exception as e:
            facts["config_json_error"] = str(e)[:120]
    # method inventory on ExchangeClient
    methods = []
    for line in ex.splitlines():
        if line.strip().startswith("def place_"):
            methods.append(line.strip().split("(")[0].replace("def ", ""))
    facts["exchange_client_place_methods"] = methods
    return facts


def try_live_fee_tier() -> dict:
    """Read-only Coinbase fee summary if live client available. Never places orders."""
    out: Dict[str, Any] = {"attempted": True, "ok": False}
    try:
        from phase6.core.exchange_client import CoinbaseExchangeClient

        # Prefer existing construction patterns
        ex = None
        try:
            ex = CoinbaseExchangeClient(mode="live")
        except TypeError:
            try:
                ex = CoinbaseExchangeClient()
            except Exception as e:
                out["error"] = f"construct: {e}"[:200]
                return out
        except Exception as e:
            out["error"] = f"construct: {e}"[:200]
            return out

        # Ensure live
        if hasattr(ex, "_ensure_live_client"):
            try:
                ex._ensure_live_client()
            except Exception as e:
                out["ensure_error"] = str(e)[:160]

        client = getattr(ex, "real_client", None)
        if client is None:
            out["error"] = "no real_client"
            return out

        # Try known endpoints
        tried = []
        for path in (
            "/api/v3/brokerage/transaction_summary",
            "/api/v3/brokerage/transaction_summary?product_type=SPOT",
        ):
            tried.append(path)
            try:
                if hasattr(client, "_request"):
                    resp = client._request("GET", path.split("?")[0], None) if "?" not in path else client._request(
                        "GET", path, None
                    )
                elif hasattr(client, "get_transaction_summary"):
                    resp = client.get_transaction_summary()
                else:
                    resp = None
                if resp:
                    # scrub nothing secret beyond rates
                    if isinstance(resp, dict):
                        keep = {
                            k: resp.get(k)
                            for k in resp.keys()
                            if any(
                                x in k.lower()
                                for x in (
                                    "fee",
                                    "maker",
                                    "taker",
                                    "tier",
                                    "volume",
                                    "rate",
                                    "pricing",
                                )
                            )
                        }
                        # also common nested
                        for k in ("fee_tier", "goods_and_services", "advanced_trade"):
                            if k in resp:
                                keep[k] = resp[k]
                        out["transaction_summary_keys"] = list(resp.keys())[:40]
                        out["fee_related"] = keep
                        out["ok"] = True
                        out["path"] = path
                        break
            except Exception as e:
                out.setdefault("path_errors", []).append({path: str(e)[:120]})
        out["tried"] = tried

        # SDK method variants
        for meth in ("get_transaction_summary", "get_fees", "get_fee_estimate"):
            if hasattr(client, meth):
                try:
                    r = getattr(client, meth)()
                    out[f"sdk_{meth}"] = r if not isinstance(r, dict) else {
                        k: r.get(k)
                        for k in list(r.keys())[:30]
                    }
                    out["ok"] = True
                except Exception as e:
                    out[f"sdk_{meth}_err"] = str(e)[:120]
    except Exception as e:
        out["error"] = str(e)[:240]
    return out


def nav_snapshot() -> Optional[float]:
    for p in (
        ROOT / "data/state/phase6_live_state.json",
        ROOT / "data/state/dashboard_live_state.json",
    ):
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text())
            for k in ("total_value_usd", "nav_usd", "total_equity", "portfolio_value"):
                if k in d and d[k]:
                    return float(d[k])
            acc = d.get("account") or d.get("balances") or {}
            if isinstance(acc, dict) and acc.get("total_usd"):
                return float(acc["total_usd"])
        except Exception:
            continue
    return None


def fee_gap_analysis(st30: dict, tier: dict) -> dict:
    med = st30.get("fee_pct_median")
    cfg_taker = 0.40  # percent
    cfg_maker = 0.25
    # common Advanced retail lowest tiers (document as reference, not live claim)
    ref_tiers = [
        {"name": "config_loader constants", "maker_pct": 0.25, "taker_pct": 0.40},
        {"name": "if_realized_is_true_taker", "maker_pct": None, "taker_pct": med},
    ]
    gap = None
    if med is not None:
        gap = {
            "realized_median_fee_pct": med,
            "vs_config_taker_0_40": round(med - cfg_taker, 4),
            "vs_config_maker_0_25": round(med - cfg_maker, 4),
            "round_trip_taker_taker_est_pct": round(2 * med, 4),
            "round_trip_if_maker_entry_taker_exit_est": round(
                (cfg_maker if False else 0.25) + med, 4
            ),  # still using realized exit
            "note": (
                "If median ~0.8% is true all-in commission/notional, it is ABOVE config_loader's "
                "0.40% taker constant — either tier is worse than assumed, fee field includes extra, "
                "or notional denominator is partial. Live transaction_summary is ground truth."
            ),
        }
    # savings CF: if half of BUY notional could be maker at 0.25% instead of med
    buy_fees = (st30.get("fees_by_side") or {}).get("BUY") or 0
    # rough: buy fee share
    savings = None
    if med and med > 0 and buy_fees:
        # scale buy fees by (med - maker)/med
        maker = 0.25
        if med > maker:
            savings = {
                "assumption": "30d BUY fees scaled by (realized_med - 0.25%)/realized_med if all buys were maker @0.25%",
                "buy_fees_30d": buy_fees,
                "hypothetical_save_usd": round(buy_fees * (med - maker) / med, 2),
                "caveat": "Ignores unfilled limits, adverse selection, delayed entry; upper-bound fantasy not a plan",
            }
    return {
        "reference_tiers": ref_tiers,
        "gap": gap,
        "maker_buy_savings_upper_bound_30d": savings,
        "live_tier_probe": {
            "ok": tier.get("ok"),
            "fee_related": tier.get("fee_related"),
            "error": tier.get("error"),
        },
    }


def write_md(payload: dict) -> None:
    code = payload["code_path"]
    s30 = payload["stats_30d"]
    s90 = payload["stats_90d"]
    gap = payload["fee_gap"]
    lines = [
        "# Fills / MARKET path dig",
        "",
        f"**As of:** {payload['as_of']}  ",
        f"**NAV snapshot:** {payload.get('nav_usd')}  ",
        "**Mode:** read-only · **no live order/config changes**",
        "",
        "## Plain English",
        "",
        f"**GO/NO-GO live maker path:** `{payload['verdict']['live_maker_path']}`  ",
        f"**Why MARKET-only:** {payload['verdict']['why_market_only']}  ",
        f"**Fee read:** {payload['verdict']['fee_read']}",
        "",
        "### Bottom line",
        "",
        payload["verdict"]["bottom_line"],
        "",
        "## Code path (source of truth)",
        "",
        f"- **BUY:** `{code['buy_path']}`",
        f"- **SELL:** `{code['sell_path']}`",
        f"- **Config order_type:** hardcoded `{code['config_order_type_hardcoded']}`",
        f"- **exchange_client place_* methods:** `{code['exchange_client_place_methods']}`",
        f"- **place_limit_buy on live ExchangeClient?** `{code['place_limit_buy_on_exchange_client']}`",
        f"- **Legacy place_limit_buy exists off-path?** `{code['limit_buy_exists_legacy_wrapper']}`",
        f"- **TP attach can be LIMIT post_only?** `{code['tp_attach_uses_limit_post_only']}` (protective exit, not entry)",
        f"- **Implication:** {code['implication']}",
        "",
        "## Realized fills",
        "",
        "### 30d",
        "",
        f"- n={s30['n']} · fees=${s30['total_fees']} · notional=${s30['total_notional']} · fee/notional={s30['fee_pct_of_notional']}%",
        f"- fee_pct median/p25/p75/mean: {s30['fee_pct_median']} / {s30['fee_pct_p25']} / {s30['fee_pct_p75']} / {s30['fee_pct_mean']}",
        f"- order_types: `{s30['order_types']}`",
        f"- liq class: `{s30['liq_class']}`",
        f"- LIMIT (non-stop) count: **{s30['limit_count']}**",
        f"- BUY fee median %: {s30['buy_fee_pct_median']} · SELL fee median %: {s30['sell_fee_pct_median']}",
        f"- fees by side: `{s30['fees_by_side']}`",
        f"- top reasons: `{s30['top_reasons'][:8]}`",
        "",
        "### 90d",
        "",
        f"- n={s90['n']} · fees=${s90['total_fees']} · notional=${s90['total_notional']} · fee/notional={s90['fee_pct_of_notional']}%",
        f"- fee_pct median: {s90['fee_pct_median']} · order_types: `{s90['order_types']}` · LIMIT count: **{s90['limit_count']}**",
        "",
        "### Top fee samples (30d)",
        "",
    ]
    for s in s30.get("top_fee_samples") or []:
        lines.append(
            f"- {s.get('ts')} **{s.get('pair')}** {s.get('side')} {s.get('order_type')} "
            f"notional=${s.get('notional')} fee=${s.get('fees')} ({s.get('fee_pct')}%) · {s.get('reason')}"
        )
    lines += [
        "",
        "## Fee tier gap",
        "",
        f"- config constants: maker **0.25%** / taker **0.40%** (config_loader; may be stale vs account)",
        f"- gap block: `{json.dumps(gap.get('gap'), default=str)[:500]}`",
        f"- maker-buy savings upper bound (fantasy): `{gap.get('maker_buy_savings_upper_bound_30d')}`",
        f"- live tier probe ok={gap.get('live_tier_probe',{}).get('ok')} fee_related=`{gap.get('live_tier_probe',{}).get('fee_related')}` err=`{gap.get('live_tier_probe',{}).get('error')}`",
        "",
        "## What would a maker path require (design only — not building)",
        "",
        "1. `place_limit_buy` (post_only optional) on `ExchangeClient`",
        "2. OrderExecutor branch: limit-first with timeout → cancel/reprice or market fallback",
        "3. Settlement/fill polling already partially exists for market; must handle partial/unfilled",
        "4. Rebalance SL attach must wait for real fill (already sensitive)",
        "5. Shadow + isolation + Brad GO before any live switch",
        "6. Even perfect maker entry does **not** fix STOP_LIMIT exit taker or churn rate",
        "",
        "## Caveats",
        "",
    ]
    for c in payload.get("caveats") or []:
        lines.append(f"- {c}")
    lines += [
        "",
        "## Artifacts",
        "",
        f"- `{OUT_JSON.relative_to(ROOT)}`",
        f"- `{OUT_MD.relative_to(ROOT)}`",
        f"- `scripts/phase6/dig_fills_market_path.py`",
        "",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n")


def main() -> int:
    fills = load_fills()
    s30 = window_stats(fills, 30)
    s90 = window_stats(fills, 90)
    code = code_path_audit()
    tier = try_live_fee_tier()
    gap = fee_gap_analysis(s30, tier)
    nav = nav_snapshot()

    # Verdict
    limit_n = s90.get("limit_count") or 0
    med = s30.get("fee_pct_median")
    why = (
        "OrderExecutor and ExchangeClient only implement market IOC for entries/exits; "
        "config hardcodes order_type=market; no place_limit_buy on live client. "
        "Not a fill-label bug."
    )
    if med is not None and med >= 0.7:
        fee_read = (
            f"Median fee ~{med}% of notional — taker-like and **above** config's 0.40% taker constant. "
            "Treat config fee constants as stale until live tier confirms."
        )
    elif med is not None:
        fee_read = f"Median fee ~{med}% — closer to advertised taker; still not maker."
    else:
        fee_read = "Could not compute fee median from fills."

    bottom = (
        "There is no active maker entry method on this stack. Fills are MARKET (entries/rebalance) "
        "+ STOP_LIMIT (SL exits) because that is what the code places. "
        "A maker path would be new engineering, not a toggle. "
        "Highest EV remains fewer round-trips + C stand-down; maker is secondary and gated."
    )
    live_maker = "NO — do not wire live maker without design + shadow + Brad GO"

    payload = {
        "as_of": NOW.isoformat(),
        "nav_usd": nav,
        "n_fills_loaded": len(fills),
        "stats_30d": s30,
        "stats_90d": s90,
        "code_path": code,
        "live_fee_tier": tier,
        "fee_gap": gap,
        "verdict": {
            "live_maker_path": live_maker,
            "why_market_only": why,
            "fee_read": fee_read,
            "bottom_line": bottom,
            "limit_fills_90d": limit_n,
            "money_print": False,
            "edge_class": "process_cost_reduction_candidate_not_alpha",
        },
        "caveats": [
            "liquidity maker/taker flag often absent — class from order_type heuristic",
            "fee/notional can mis-state if filled_value incomplete",
            "live tier probe may fail if keys/env not available in this shell",
            "maker savings upper bound is not a promote case",
            "no live changes in this dig",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    write_md(payload)
    print(json.dumps({"ok": True, "verdict": payload["verdict"], "s30": {
        "n": s30["n"], "fees": s30["total_fees"], "med": s30["fee_pct_median"],
        "ots": s30["order_types"], "limit": s30["limit_count"],
    }, "tier_ok": tier.get("ok"), "md": str(OUT_MD)}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
