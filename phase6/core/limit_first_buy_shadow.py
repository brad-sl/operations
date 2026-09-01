#!/usr/bin/env python3
"""
Limit-first buy shadow — market-buy counterfactual fee board (Phase C).

Doctrine (LIMIT_FIRST_BUY_DESIGN Phase C)
----------------------------------------
Live path still MARKET IOC. This module never places limit (or any) orders.
It logs, for each observed market buy:

  - would_limit_px (bid-style passive ref from fill or live book)
  - actual_fee (realized or live taker rate × notional)
  - maker_fee_if_rested (live maker rate × notional)
  - fee_delta_if_maker_upper_bound = actual − maker  (FANTASY if fill)

Honesty:
  - Fill rate at post_only bid is **unknown until Phase D pilot**.
  - fee_delta is an **upper-bound cost-cut** assuming the limit would have
    rested and filled fully as maker — NOT realized savings.
  - Edge class: cost_cut_engineering / ATTENTION_ONLY — not alpha, not printer.

Artifacts:
  data/state/limit_first_buy_shadow_latest.json
  data/state/limit_first_buy_shadow_events.jsonl
  reports/LIMIT_FIRST_BUY_SHADOW_LATEST.md
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT, STATE_DIR

LATEST = STATE_DIR / "limit_first_buy_shadow_latest.json"
EVENTS = STATE_DIR / "limit_first_buy_shadow_events.jsonl"
MD_REPORT = PROJECT_ROOT / "reports" / "LIMIT_FIRST_BUY_SHADOW_LATEST.md"
TRADES_JSONL = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
FILLS_JSONL = PROJECT_ROOT / "trades" / "phase6_exchange_fills.jsonl"
FEE_TIER = STATE_DIR / "fee_tier_snapshot_latest.json"

DEFAULT_TAKER = 0.008  # Intro 2 fallback
DEFAULT_MAKER = 0.004
LOOKBACK_HOURS = 72
PLACE_ORDERS = False  # hard fence


@dataclass
class FeeRates:
    taker: float = DEFAULT_TAKER
    maker: float = DEFAULT_MAKER
    tier: str = "fallback_intro2"
    source: str = "default"


@dataclass
class ShadowCfg:
    lookback_hours: int = LOOKBACK_HOURS
    fill_wait_s: float = 45.0
    price_ref: str = "bid"
    post_only: bool = True
    market_fallback: bool = False  # Brad locked skip
    place_orders: bool = False
    mutate_config: bool = False
    live_gate: str = "OFF"


# ---------------------------------------------------------------------------
# Pure (isolation)
# ---------------------------------------------------------------------------


def load_fee_rates(path: Optional[Path] = None) -> FeeRates:
    p = path or FEE_TIER
    if p.exists():
        try:
            d = json.loads(p.read_text())
            tier = (d.get("tier") or {}) if d.get("ok") else {}
            t = tier.get("taker_fee_rate")
            m = tier.get("maker_fee_rate")
            if t is not None and m is not None:
                return FeeRates(
                    taker=float(t),
                    maker=float(m),
                    tier=str(tier.get("pricing_tier") or "live"),
                    source="fee_tier_snapshot",
                )
        except Exception:
            pass
    return FeeRates()


def cf_fee_delta(
    notional: float,
    *,
    actual_fee: Optional[float] = None,
    taker_rate: float = DEFAULT_TAKER,
    maker_rate: float = DEFAULT_MAKER,
) -> Dict[str, Any]:
    """Upper-bound maker CF on a filled buy notional. Pure."""
    n = float(notional or 0)
    if n <= 0:
        return {
            "notional": 0.0,
            "actual_fee": 0.0,
            "maker_fee_if_rested": 0.0,
            "fee_delta_if_maker_upper_bound": 0.0,
            "actual_fee_imputed": False,
            "ok": False,
        }
    imputed = False
    if actual_fee is None or actual_fee < 0:
        actual = taker_rate * n
        imputed = True
    else:
        actual = float(actual_fee)
        # If actual is absurdly small/zero, impute taker
        if actual <= 0:
            actual = taker_rate * n
            imputed = True
    maker = maker_rate * n
    delta = actual - maker
    return {
        "notional": round(n, 6),
        "actual_fee": round(actual, 6),
        "maker_fee_if_rested": round(maker, 6),
        "fee_delta_if_maker_upper_bound": round(delta, 6),
        "actual_fee_imputed": imputed,
        "taker_rate": taker_rate,
        "maker_rate": maker_rate,
        "ok": True,
        "fillability": "unknown_until_pilot",
        "cf_class": "fee_delta_if_rested_upper_bound",
        "edge_class": "ATTENTION_ONLY_cost_cut",
    }


def would_limit_price(
    *,
    fill_px: Optional[float],
    bid: Optional[float] = None,
    last: Optional[float] = None,
    price_ref: str = "bid",
) -> Optional[float]:
    """Passive limit ref for CF. Prefer live/historical bid; else slight under fill."""
    ref = (price_ref or "bid").lower()
    if ref == "bid" and bid and bid > 0:
        return float(bid)
    if last and last > 0 and ref in ("bid", "mid"):
        # No book: treat last as mid, bid ≈ last * 0.9995
        return float(last) * 0.9995 if ref == "bid" else float(last)
    if fill_px and fill_px > 0:
        return float(fill_px) * 0.9995  # more passive than taker fill
    return None


def parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except Exception:
            return None
    s = str(raw).strip()
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


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Event I/O
# ---------------------------------------------------------------------------


def append_event(ev: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ev = dict(ev)
    ev.setdefault("ts", _iso())
    ev["place_orders"] = False
    with EVENTS.open("a") as f:
        f.write(json.dumps(ev, default=str) + "\n")


def log_market_buy_counterfactual(
    result: Dict[str, Any],
    *,
    rates: Optional[FeeRates] = None,
    bid: Optional[float] = None,
    last: Optional[float] = None,
) -> Dict[str, Any]:
    """Call after a successful *market* buy (live or post-hoc). No orders.

    Safe to invoke from OrderExecutor; failures must never break the buy path.
    """
    rates = rates or load_fee_rates()
    pair = str(result.get("pair") or result.get("product_id") or "")
    entry = float(result.get("entry_price") or result.get("price") or 0)
    size = float(result.get("size") or result.get("qty") or result.get("filled_size") or 0)
    notional = float(result.get("usd_value") or result.get("notional") or 0)
    if notional <= 0 and entry > 0 and size > 0:
        notional = entry * size
    fee = result.get("fee") or result.get("fee_usd") or result.get("total_fees")
    try:
        fee_f = float(fee) if fee is not None else None
    except (TypeError, ValueError):
        fee_f = None
    style = str(result.get("execution_style") or "market_ioc")
    if "limit" in style.lower():
        # Don't CF a live limit fill as if it were market
        return {"skipped": True, "reason": "already_limit_style"}

    cf = cf_fee_delta(
        notional,
        actual_fee=fee_f,
        taker_rate=rates.taker,
        maker_rate=rates.maker,
    )
    wpx = would_limit_price(
        fill_px=entry or None, bid=bid, last=last or entry or None, price_ref="bid"
    )
    ev = {
        "kind": "market_buy_cf",
        "pair": pair,
        "order_id": result.get("order_id"),
        "entry_price": entry,
        "size": size,
        "would_limit_px": wpx,
        "execution_style_actual": style,
        "signal_source": result.get("signal_source"),
        "fee_tier": rates.tier,
        "fee_source": rates.source,
        **cf,
        "note": "Upper-bound fee delta if limit rested+filled maker; fill rate unknown",
    }
    try:
        append_event(ev)
    except Exception:
        pass
    return ev


# ---------------------------------------------------------------------------
# Batch board from ledger
# ---------------------------------------------------------------------------


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def load_recent_market_buys(
    *,
    lookback_hours: int = LOOKBACK_HOURS,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Ledger buys (process path). Exchange fills BUY MARKET when available."""
    now = now or datetime.now(timezone.utc)
    cut = now - timedelta(hours=int(lookback_hours))
    out: List[Dict[str, Any]] = []
    seen_oid: set = set()

    # Prefer exchange fills for order_type truth
    for row in _iter_jsonl(FILLS_JSONL) or []:
        order = row.get("order") if isinstance(row.get("order"), dict) else row
        if not isinstance(order, dict):
            continue
        side = str(order.get("side") or "").upper()
        if side not in ("BUY", "BUY_SIDE", ""):
            # some rows only in nested
            if str(order.get("side") or "").lower() != "buy":
                oc = order.get("order_configuration") or {}
                if not any(k.startswith("market") for k in oc):
                    continue
        oc = order.get("order_configuration") or {}
        is_market = "market_market_ioc" in oc or str(order.get("order_type") or "").upper() == "MARKET"
        is_limit = "limit_limit_gtc" in oc or str(order.get("order_type") or "").upper() == "LIMIT"
        if is_limit or not is_market:
            # skip SL etc.
            if "stop_limit" in str(oc).lower():
                continue
            if not is_market:
                continue
        ts = parse_ts(
            order.get("completion_time")
            or order.get("created_time")
            or row.get("ingested_at")
        )
        if ts and ts < cut:
            continue
        oid = order.get("order_id") or order.get("id")
        if oid and oid in seen_oid:
            continue
        if oid:
            seen_oid.add(oid)
        filled = float(order.get("filled_size") or 0)
        avg = float(order.get("average_filled_price") or 0)
        fees = order.get("total_fees")
        try:
            fees_f = float(fees) if fees is not None else None
        except (TypeError, ValueError):
            fees_f = None
        notional = filled * avg if filled and avg else 0.0
        if notional <= 0:
            continue
        out.append(
            {
                "pair": order.get("product_id") or order.get("pair"),
                "order_id": oid,
                "entry_price": avg,
                "size": filled,
                "usd_value": notional,
                "fee_usd": fees_f,
                "ts": ts.isoformat() if ts else None,
                "source": "exchange_fill",
                "execution_style": "market_ioc",
                "side": "BUY",
            }
        )

    # Ledger buys as supplement (may duplicate — dedupe by oid/time/pair)
    for row in _iter_jsonl(TRADES_JSONL) or []:
        side = str(row.get("side") or row.get("action") or "").upper()
        if side != "BUY":
            continue
        ts = parse_ts(row.get("timestamp") or row.get("ts") or row.get("time"))
        if ts and ts < cut:
            continue
        oid = row.get("order_id")
        if oid and oid in seen_oid:
            continue
        entry = float(row.get("entry_price") or row.get("price") or 0)
        size = float(row.get("qty") or row.get("size") or 0)
        notional = float(row.get("usd_value") or 0)
        if notional <= 0 and entry > 0 and size > 0:
            notional = entry * size
        if notional <= 0:
            continue
        if oid:
            seen_oid.add(oid)
        out.append(
            {
                "pair": row.get("pair"),
                "order_id": oid,
                "entry_price": entry,
                "size": size,
                "usd_value": notional,
                "fee_usd": row.get("fee") or row.get("fee_usd"),
                "ts": ts.isoformat() if ts else None,
                "source": "ledger",
                "signal_source": row.get("signal_source"),
                "execution_style": row.get("execution_style") or "market_ioc",
                "side": "BUY",
            }
        )
    return out


def summarize_buys(buys: Sequence[Dict[str, Any]], rates: FeeRates) -> Dict[str, Any]:
    rows = []
    sum_notional = 0.0
    sum_actual = 0.0
    sum_maker = 0.0
    sum_delta = 0.0
    for b in buys:
        cf = cf_fee_delta(
            float(b.get("usd_value") or 0),
            actual_fee=float(b["fee_usd"]) if b.get("fee_usd") not in (None, "") else None,
            taker_rate=rates.taker,
            maker_rate=rates.maker,
        )
        if not cf.get("ok"):
            continue
        wpx = would_limit_price(
            fill_px=float(b.get("entry_price") or 0) or None,
            last=float(b.get("entry_price") or 0) or None,
        )
        row = {
            "pair": b.get("pair"),
            "ts": b.get("ts"),
            "order_id": b.get("order_id"),
            "source": b.get("source"),
            "signal_source": b.get("signal_source"),
            "would_limit_px": wpx,
            "entry_price": b.get("entry_price"),
            **cf,
        }
        rows.append(row)
        sum_notional += cf["notional"]
        sum_actual += cf["actual_fee"]
        sum_maker += cf["maker_fee_if_rested"]
        sum_delta += cf["fee_delta_if_maker_upper_bound"]
    return {
        "n_buys": len(rows),
        "sum_notional": round(sum_notional, 2),
        "sum_actual_fee": round(sum_actual, 4),
        "sum_maker_fee_if_rested": round(sum_maker, 4),
        "sum_fee_delta_upper_bound": round(sum_delta, 4),
        "avg_fee_delta_upper_bound": round(sum_delta / len(rows), 4) if rows else 0.0,
        "rows": rows,
    }


def live_book_snapshot(pairs: Sequence[str], exchange: Any = None) -> List[Dict[str, Any]]:
    """Optional current bid would-limit board (no orders)."""
    out = []
    if exchange is None:
        return out
    for pair in pairs:
        try:
            refs = {}
            if hasattr(exchange, "get_best_bid_ask"):
                refs = exchange.get_best_bid_ask(pair) or {}
            bid = refs.get("bid")
            last = refs.get("last")
            wpx = would_limit_price(fill_px=last, bid=bid, last=last)
            out.append(
                {
                    "pair": pair,
                    "bid": bid,
                    "ask": refs.get("ask"),
                    "last": last,
                    "would_limit_px": wpx,
                    "policy": "post_only bid, wait 45s, skip if unfilled",
                }
            )
        except Exception as e:
            out.append({"pair": pair, "error": str(e)[:120]})
    return out


def write_board(payload: Dict[str, Any]) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    rates = payload.get("fee_rates") or {}
    s = payload.get("summary") or {}
    lines = [
        "# Limit-first buy shadow (Phase C)",
        "",
        f"**As of:** {payload.get('ts')}  ",
        f"**Live gate:** {payload.get('live_gate', 'OFF')}  ",
        f"**place_orders:** False  ",
        "",
        "## Honesty",
        "",
        "- This is a **counterfactual upper bound** on buy-leg fee if every market buy",
        "  had instead **rested and filled as maker**.",
        "- **Fill rate at post_only bid is unknown** until Phase D pilot.",
        "- Not alpha. Not a money printer. Cost-cut engineering only.",
        f"- Edge class: `{payload.get('edge_class')}`",
        "",
        "## Fee tier",
        "",
        f"- Tier: **{rates.get('tier')}** (source={rates.get('source')})",
        f"- Taker {rates.get('taker')} / Maker {rates.get('maker')}",
        "",
        f"## Lookback {payload.get('lookback_hours')}h market buys",
        "",
        f"- N buys: **{s.get('n_buys')}**",
        f"- Notional: **${s.get('sum_notional')}**",
        f"- Actual fees (used/imputed): **${s.get('sum_actual_fee')}**",
        f"- Maker if rested: **${s.get('sum_maker_fee_if_rested')}**",
        f"- **Fee Δ upper bound: ${s.get('sum_fee_delta_upper_bound')}** "
        f"(avg ${s.get('avg_fee_delta_upper_bound')}/buy)",
        "",
        "Do **not** read Δ as money already saved.",
        "",
        f"State: `{_rel(LATEST)}`  ",
        f"Events: `{_rel(EVENTS)}`",
        "",
    ]
    MD_REPORT.parent.mkdir(parents=True, exist_ok=True)
    MD_REPORT.write_text("\n".join(lines))
    return LATEST


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except Exception:
        return str(p)


def run_limit_first_buy_shadow(
    cfg: Optional[ShadowCfg] = None,
    *,
    exchange: Any = None,
    pairs: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Batch CF board from recent market buys. No orders / no config writes."""
    cfg = cfg or ShadowCfg()
    assert cfg.place_orders is False
    rates = load_fee_rates()
    buys = load_recent_market_buys(lookback_hours=cfg.lookback_hours)
    summary = summarize_buys(buys, rates)
    # Persist CF rows as events (dedupe by writing board only; optional append)
    for row in summary.get("rows") or []:
        append_event({"kind": "batch_cf_row", **row})

    book = []
    if pairs and exchange is not None:
        book = live_book_snapshot(list(pairs), exchange)

    payload = {
        "ts": _iso(),
        "live_gate": cfg.live_gate,
        "place_orders": False,
        "phase": "C",
        "edge_class": "ATTENTION_ONLY_cost_cut",
        "lookback_hours": cfg.lookback_hours,
        "policy": {
            "post_only": cfg.post_only,
            "price_ref": cfg.price_ref,
            "fill_wait_s": cfg.fill_wait_s,
            "market_fallback": cfg.market_fallback,
            "unfilled": "skip",
        },
        "fee_rates": asdict(rates),
        "summary": {k: v for k, v in summary.items() if k != "rows"},
        "recent_rows": (summary.get("rows") or [])[-30:],
        "live_book_would_limit": book,
        "success_metrics_note": (
            "Fillability proxy only after Phase D; until then report fee Δ upper bound "
            "and N, never claim realized maker savings."
        ),
    }
    write_board(payload)
    return payload


def telegram_summary(payload: Dict[str, Any]) -> str:
    """Short body; empty when N=0 (quiet-ok)."""
    s = payload.get("summary") or {}
    n = int(s.get("n_buys") or 0)
    if n <= 0:
        return ""
    return (
        f"Limit-first C shadow (no orders)\n"
        f"lookback buys={n} · notional=${s.get('sum_notional')}\n"
        f"fee Δ upper bound ${s.get('sum_fee_delta_upper_bound')} "
        f"(if all rested maker — fill rate unknown)\n"
        f"live_gate=OFF · not a printer"
    )
