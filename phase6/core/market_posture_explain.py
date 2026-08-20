"""Market heat vs risk posture + Why idle (trader-facing explain).

Participation is optional; explanation is mandatory at scale.
No live orders / no bag writes — read-only overlays for dashboard + research.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from phase6.core.paths import PROJECT_ROOT, STATE_DIR, load_trading_basket

logger = logging.getLogger("phase6.market_posture")

HEAT_CACHE = STATE_DIR / "market_heat_cache.json"
MOVER_WATCH_PATH = STATE_DIR / "mover_not_in_bag_watchlist.json"
SHADOW_PATH = STATE_DIR / "regime_boundary_layer_shadow_latest.json"
RC_PATH = STATE_DIR / "regime_cash_status.json"
LIVE_PATH = STATE_DIR / "phase6_live_state.json"

# Majors for "board heat" strip (Coinbase public stats)
HEAT_PRODUCTS = (
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "XRP-USD",
    "DOGE-USD",
    "LINK-USD",
    "ADA-USD",
    "AVAX-USD",
)
# Extra scan set for mover∉bag (discovery feed — not bag write)
MOVER_SCAN_EXTRA = (
    "HYPE-USD",
    "ZEC-USD",
    "SUI-USD",
    "APT-USD",
    "NEAR-USD",
    "PEPE-USD",
    "WIF-USD",
    "ONDO-USD",
    "RENDER-USD",
    "INJ-USD",
)
STABLE_PREFIXES = ("USD", "USDT", "USDC", "DAI", "EUR", "GBP")
HEAT_TTL_SEC = 300
HEAT_HOT_BTC = 3.0  # 24h % — "board looks hot"
HEAT_HOT_MEDIAN_BASKET = 4.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_json(url: str, timeout: float = 6.0) -> Optional[Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "phase6-market-posture/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as e:
        logger.debug("heat fetch fail %s: %s", url, e)
        return None


def fetch_product_stats_24h(product_id: str) -> Optional[Dict[str, Any]]:
    """Coinbase Exchange public stats — open/last/volume → 24h %. No auth."""
    data = _http_json(f"https://api.exchange.coinbase.com/products/{product_id}/stats")
    if not isinstance(data, dict):
        return None
    try:
        last = float(data.get("last") or 0)
        open_ = float(data.get("open") or 0)
        if open_ <= 0 or last <= 0:
            return None
        chg = (last / open_ - 1.0) * 100.0
        return {
            "pair": product_id,
            "last": last,
            "open": open_,
            "change_24h_pct": round(chg, 3),
            "volume": float(data.get("volume") or 0),
        }
    except (TypeError, ValueError):
        return None


def load_or_refresh_heat(
    *,
    products: Optional[Sequence[str]] = None,
    ttl_sec: int = HEAT_TTL_SEC,
    force: bool = False,
) -> Dict[str, Any]:
    """Cached 24h heat for majors + basket overlap."""
    products = list(products or HEAT_PRODUCTS)
    now = time.time()
    if HEAT_CACHE.exists() and not force:
        try:
            cached = json.loads(HEAT_CACHE.read_text(encoding="utf-8"))
            if now - float(cached.get("fetched_epoch") or 0) < ttl_sec and cached.get("by_pair"):
                return cached
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    by_pair: Dict[str, Any] = {}
    for pid in products:
        row = fetch_product_stats_24h(pid)
        if row:
            by_pair[pid] = row

    btc = (by_pair.get("BTC-USD") or {}).get("change_24h_pct")
    changes = [float(v["change_24h_pct"]) for v in by_pair.values() if v.get("change_24h_pct") is not None]
    changes_sorted = sorted(changes)
    median = None
    if changes_sorted:
        mid = len(changes_sorted) // 2
        median = (
            changes_sorted[mid]
            if len(changes_sorted) % 2 == 1
            else (changes_sorted[mid - 1] + changes_sorted[mid]) / 2.0
        )

    hot = False
    if btc is not None and float(btc) >= HEAT_HOT_BTC:
        hot = True
    if median is not None and float(median) >= HEAT_HOT_MEDIAN_BASKET:
        hot = True

    # Top movers in scanned set
    ranked = sorted(
        by_pair.values(),
        key=lambda r: float(r.get("change_24h_pct") or -999),
        reverse=True,
    )
    out = {
        "as_of": _now_iso(),
        "fetched_epoch": now,
        "source": "coinbase_exchange_stats",
        "ttl_sec": ttl_sec,
        "by_pair": by_pair,
        "btc_change_24h_pct": btc,
        "median_change_24h_pct": round(median, 3) if median is not None else None,
        "hot": hot,
        "hot_thresholds": {"btc_pct": HEAT_HOT_BTC, "median_pct": HEAT_HOT_MEDIAN_BASKET},
        "top_movers": [
            {"pair": r["pair"], "change_24h_pct": r["change_24h_pct"], "last": r.get("last")}
            for r in ranked[:8]
        ],
        "note": "24h board heat ≠ 30d regime posture. Heat is optics; posture gates risk.",
    }
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        HEAT_CACHE.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    return out


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _held_pairs(live: Dict[str, Any]) -> Set[str]:
    held: Set[str] = set()
    for pos in live.get("trading_positions") or live.get("positions") or []:
        if not isinstance(pos, dict):
            continue
        pair = pos.get("pair")
        try:
            val = float(pos.get("value_usd") or 0)
        except (TypeError, ValueError):
            val = 0.0
        if pair and pair not in ("USD", "USDC", "USDT") and val >= 5.0:
            held.add(str(pair))
    return held


def build_why_idle(
    *,
    rc: Optional[Dict[str, Any]] = None,
    shadow: Optional[Dict[str, Any]] = None,
    heat: Optional[Dict[str, Any]] = None,
    live: Optional[Dict[str, Any]] = None,
    basket: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Trader-facing reasons cash/idle can be correct."""
    rc = rc if rc is not None else _load_json(RC_PATH)
    shadow = shadow if shadow is not None else _load_json(SHADOW_PATH)
    heat = heat if heat is not None else load_or_refresh_heat()
    live = live if live is not None else _load_json(LIVE_PATH)
    try:
        basket_list = list(basket) if basket is not None else list(load_trading_basket())
    except Exception:
        basket_list = []
    basket_set = set(basket_list)
    held = _held_pairs(live)

    mode = str(rc.get("strategy_mode") or "")
    allow = rc.get("allow_new_buys")
    park = mode == "usdc_park" or allow is False
    layer = str(rc.get("regime_layer") or rc.get("regime") or "unknown")
    coarse = str(rc.get("regime") or "unknown")
    cap = rc.get("rebalance_cap_usd")
    btc_30d = rc.get("btc_return_pct")
    shadow_stance = rc.get("shadow_stance") or shadow.get("shadow_stance")
    cream_n = int(shadow.get("shadow_would_buy_count") or 0)
    cream_pairs = list(shadow.get("shadow_would_buy_pairs") or [])
    live_would = int((shadow.get("live") or {}).get("would_buy_count") or 0)

    # Cash hold
    hold_usd = 0.0
    for path in (
        STATE_DIR / "capital_user_controls.json",
        STATE_DIR / "capital_controls_status.json",
        STATE_DIR / "runner_capital_controls.json",
    ):
        blob = _load_json(path)
        for key in ("manual_liquidation_cash_hold_usd", "cash_hold_usd", "hold_usd"):
            if blob.get(key) is not None:
                try:
                    hold_usd = float(blob.get(key) or 0)
                    break
                except (TypeError, ValueError):
                    pass
        if hold_usd > 0:
            break

    blocked: List[str] = []
    try:
        from phase6.core.runner_capital_events import load_buy_block_status

        bs = load_buy_block_status() or {}
        blocked = sorted(p for p, info in bs.items() if isinstance(info, dict) and info.get("blocked"))
    except Exception:
        blocked = list((shadow.get("buy_blocked_pairs") or []))

    reasons: List[Dict[str, Any]] = []
    # 1) Stance
    if park:
        reasons.append(
            {
                "code": "stance_park",
                "title": "Risk posture is PARK",
                "detail": (
                    f"Coarse {coarse} · layer {layer} · mode {mode or 'usdc_park'} · "
                    f"cap ${float(cap or 0):.0f} · allow_new_buys={allow}. "
                    f"BTC ~30d {btc_30d}% — not a missing market feed."
                ),
                "severity": "primary",
            }
        )
    else:
        reasons.append(
            {
                "code": "stance_deploy",
                "title": "Risk posture allows gated buys",
                "detail": f"Layer {layer} · mode {mode} · cap ${float(cap or 0):.0f}. Entry gates still apply.",
                "severity": "info",
            }
        )

    # 2) Cream / entry quality
    if park and cream_n == 0:
        reasons.append(
            {
                "code": "cream_empty",
                "title": "Cream gates: no pair would buy",
                "detail": (
                    f"Shadow stance `{shadow_stance}` would-buy count **0** "
                    "(strict RSI/sentiment/util). Green board ≠ quality entry."
                ),
                "severity": "primary",
            }
        )
    elif cream_n > 0 and park:
        reasons.append(
            {
                "code": "cream_blocked_by_park",
                "title": f"Cream sees {cream_n} pair(s) — live PARK blocks",
                "detail": f"Would-buy under shadow: {', '.join(cream_pairs)}. Live still park until promote.",
                "severity": "watch",
            }
        )
    elif not park and live_would == 0:
        reasons.append(
            {
                "code": "entry_gates",
                "title": "Deploy on but entry gates empty",
                "detail": "No basket pair cleared RSI/sentiment/lockout for new buys this cycle.",
                "severity": "primary",
            }
        )

    # 3) Universe — movers not in bag
    movers_out: List[Dict[str, Any]] = []
    for m in heat.get("top_movers") or []:
        pair = m.get("pair")
        if not pair or pair in basket_set:
            continue
        if any(pair.startswith(s) or pair.split("-")[0] in STABLE_PREFIXES for s in ("USDT", "USDC")):
            continue
        movers_out.append(m)
    # Also scan heat by_pair for known extras if present
    for pair, row in (heat.get("by_pair") or {}).items():
        if pair in basket_set or pair in {x.get("pair") for x in movers_out}:
            continue
        chg = row.get("change_24h_pct")
        if chg is not None and float(chg) >= 5.0:
            movers_out.append(
                {"pair": pair, "change_24h_pct": chg, "last": row.get("last")}
            )

    if movers_out:
        top = ", ".join(
            f"{m['pair']} {float(m['change_24h_pct']):+.1f}%" for m in movers_out[:5]
        )
        reasons.append(
            {
                "code": "not_in_bag",
                "title": "Some hot names are outside tradable bag",
                "detail": (
                    f"{top}. Bag policy / discovery owns membership — not silent. "
                    "Best-bag tests run separately; this is coverage optics only."
                ),
                "severity": "secondary",
                "pairs": [m.get("pair") for m in movers_out],
            }
        )

    # 4) Cooldown
    if blocked:
        reasons.append(
            {
                "code": "cooldown",
                "title": f"Pair cooldown blocks {len(blocked)}",
                "detail": ", ".join(blocked[:8]) + ("…" if len(blocked) > 8 else ""),
                "severity": "secondary",
                "pairs": blocked,
            }
        )

    # 5) Sticky cash hold
    if hold_usd > 1:
        reasons.append(
            {
                "code": "cash_hold",
                "title": f"Sticky cash hold ${hold_usd:.0f}",
                "detail": "Deployable powder reduced until operator Release — independent of park.",
                "severity": "primary",
            }
        )

    # 6) Already thin book
    if held and park:
        reasons.append(
            {
                "code": "already_in",
                "title": f"Open sleeve: {', '.join(sorted(held)[:6])}",
                "detail": "Not flat cash-only — small risk on; park blocks *new* risk adds.",
                "severity": "info",
            }
        )

    # Headline for scale FAQ
    if park and heat.get("hot"):
        headline = "Market looks hot (24h) — posture is PARK. Idle is explained, not broken."
    elif park:
        headline = "Posture PARK — new buys off until layer/promote allows."
    elif cream_n == 0 and live_would == 0:
        headline = "Deploy allowed but no cream/entry clears — quality over chase."
    else:
        headline = "Gated participation active."

    try:
        total = float(live.get("total_usd") or live.get("total_balance") or 0)
        cash = float(live.get("cash_usd") or 0)
        hold_v = float(live.get("total_holdings_value") or 0)
        util = (hold_v / total) if total > 0 else None
    except (TypeError, ValueError):
        total = cash = hold_v = 0.0
        util = None

    return {
        "as_of": _now_iso(),
        "headline": headline,
        "participation_optional": True,
        "explanation_mandatory": True,
        "heat": {
            "hot": bool(heat.get("hot")),
            "btc_change_24h_pct": heat.get("btc_change_24h_pct"),
            "median_change_24h_pct": heat.get("median_change_24h_pct"),
            "top_movers": heat.get("top_movers") or [],
            "note": heat.get("note"),
        },
        "posture": {
            "regime": coarse,
            "regime_layer": layer,
            "shadow_stance": shadow_stance,
            "strategy_mode": mode,
            "allow_new_buys": allow,
            "rebalance_cap_usd": cap,
            "btc_return_30d_pct": btc_30d,
            "park": park,
        },
        "cream": {
            "shadow_would_buy_count": cream_n,
            "shadow_would_buy_pairs": cream_pairs,
            "live_would_buy_count": live_would,
            "shadow_stance": shadow_stance,
        },
        "book": {
            "total_usd": total,
            "cash_usd": cash,
            "holdings_usd": hold_v,
            "util": util,
            "held_pairs": sorted(held),
            "cash_hold_usd": hold_usd,
        },
        "basket_n": len(basket_list),
        "buy_blocked_pairs": blocked,
        "movers_not_in_bag": movers_out[:12],
        "reasons": reasons,
        "scale_faq": (
            "We don't promise full exposure every green day. "
            "We promise clear posture, quality entries, bag coverage process, "
            "and a written why when cash wins."
        ),
    }


def build_market_posture_payload(*, force_heat: bool = False) -> Dict[str, Any]:
    """Full overlay for /api/metrics."""
    # Include basket + a few discovery-interesting names in heat scan
    try:
        basket = list(load_trading_basket())
    except Exception:
        basket = []
    products = list(dict.fromkeys(list(HEAT_PRODUCTS) + basket[:12] + list(MOVER_SCAN_EXTRA)))
    heat = load_or_refresh_heat(products=products, force=force_heat)
    why = build_why_idle(heat=heat, basket=basket)
    return {
        "market_heat": {
            "hot": why["heat"]["hot"],
            "btc_change_24h_pct": why["heat"]["btc_change_24h_pct"],
            "median_change_24h_pct": why["heat"]["median_change_24h_pct"],
            "top_movers": why["heat"]["top_movers"],
            "as_of": heat.get("as_of"),
            "note": why["heat"]["note"],
        },
        "why_idle": why,
        "cream_summary": why["cream"],
    }


def refresh_mover_not_in_bag_watchlist(*, force_heat: bool = True) -> Dict[str, Any]:
    """P1: write discovery-friendly watchlist. Does NOT mutate trading bag."""
    try:
        basket = set(load_trading_basket())
    except Exception:
        basket = set()
    products = list(dict.fromkeys(list(HEAT_PRODUCTS) + list(MOVER_SCAN_EXTRA) + list(basket)))
    heat = load_or_refresh_heat(products=products, force=force_heat)
    cont = _load_json(STATE_DIR / "pair_discovery_contenders.json")
    contender_ids = set()
    for c in cont.get("contenders") or cont.get("promote_eligible") or []:
        if isinstance(c, str):
            contender_ids.add(c)
        elif isinstance(c, dict) and c.get("pair"):
            contender_ids.add(str(c["pair"]))

    rows = []
    for pair, row in (heat.get("by_pair") or {}).items():
        if pair in basket:
            continue
        base = pair.split("-")[0]
        if base in STABLE_PREFIXES or pair.startswith("USDT"):
            continue
        chg = row.get("change_24h_pct")
        if chg is None:
            continue
        rows.append(
            {
                "pair": pair,
                "change_24h_pct": chg,
                "last": row.get("last"),
                "in_discovery_contenders": pair in contender_ids,
                "in_active_basket": False,
            }
        )
    rows.sort(key=lambda r: float(r["change_24h_pct"]), reverse=True)
    out = {
        "as_of": _now_iso(),
        "note": (
            "Mover ∩ not-in-bag — optics for discovery / best-bag research. "
            "No auto bag write. Bag policy tested elsewhere."
        ),
        "active_basket": sorted(basket),
        "watchlist": rows[:25],
        "n": len(rows),
        "heat_hot": heat.get("hot"),
        "btc_change_24h_pct": heat.get("btc_change_24h_pct"),
    }
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        MOVER_WATCH_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        report = PROJECT_ROOT / "reports" / "MOVER_NOT_IN_BAG_WATCHLIST_LATEST.md"
        lines = [
            "# Mover ∉ bag watchlist",
            "",
            f"**As of:** {out['as_of']}",
            f"**BTC 24h:** {out.get('btc_change_24h_pct')} · heat_hot={out.get('heat_hot')}",
            "",
            out["note"],
            "",
            "| Pair | 24h % | In discovery contenders? |",
            "|------|------:|--------------------------|",
        ]
        for r in out["watchlist"]:
            lines.append(
                f"| {r['pair']} | {float(r['change_24h_pct']):+.2f} | "
                f"{'yes' if r['in_discovery_contenders'] else 'no'} |"
            )
        if not out["watchlist"]:
            lines.append("| — | — | (none outside bag in scan set) |")
        lines.append("")
        lines.append(f"Active basket ({len(basket)}): " + ", ".join(sorted(basket)))
        lines.append("")
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out["report"] = str(report)
    except OSError as e:
        out["write_error"] = str(e)
    return out
