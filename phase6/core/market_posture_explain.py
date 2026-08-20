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
    # 1) Stance — plain English for hands-off traders
    btc_30d_s = f"{float(btc_30d):+.1f}%" if btc_30d is not None else "n/a"
    if park:
        reasons.append(
            {
                "code": "stance_park",
                "title": "We're holding cash on purpose",
                "detail": (
                    f"Bitcoin's last month is only about {btc_30d_s} — not a clear enough "
                    "uptrend for new buys. Sitting in cash is the plan today, not a glitch."
                ),
                "severity": "primary",
            }
        )
    else:
        reasons.append(
            {
                "code": "stance_deploy",
                "title": "New buys are allowed (with limits)",
                "detail": (
                    f"Market look is open enough to add a little risk"
                    + (f" (up to about ${float(cap):.0f} this cycle)" if cap is not None else "")
                    + ". We still only buy when a coin looks like a good entry."
                ),
                "severity": "info",
            }
        )

    # 2) Cream / entry quality
    if park and cream_n == 0:
        reasons.append(
            {
                "code": "cream_empty",
                "title": "Nothing looks like a good buy right now",
                "detail": (
                    "Even our picky checklist found zero coins worth buying — prices already "
                    "ran hard or the crowd mood isn't there. A green day alone isn't enough."
                ),
                "severity": "primary",
            }
        )
    elif cream_n > 0 and park:
        pretty = ", ".join(p.replace("-USD", "") for p in cream_pairs[:6]) or "a few names"
        reasons.append(
            {
                "code": "cream_blocked_by_park",
                "title": f"A few coins look interesting ({pretty})",
                "detail": (
                    "Our checklist would consider them, but the account is still in "
                    "cash-first mode — we won't chase until that mode opens up."
                ),
                "severity": "watch",
            }
        )
    elif not park and live_would == 0:
        reasons.append(
            {
                "code": "entry_gates",
                "title": "Ready to buy — but no coin cleared the bar",
                "detail": (
                    "Buying is allowed, yet nothing in your list met the entry rules "
                    "(not too extended, decent sentiment). Waiting beats FOMO."
                ),
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
            f"{str(m['pair']).replace('-USD', '')} {float(m['change_24h_pct']):+.0f}%"
            for m in movers_out[:5]
        )
        reasons.append(
            {
                "code": "not_in_bag",
                "title": "Some of today's rockets aren't on your list",
                "detail": (
                    f"{top}. We only trade a short, curated set — not every meme that pumps. "
                    "That list is reviewed over time so you stay diversified without chasing every ticker."
                ),
                "severity": "secondary",
                "pairs": [m.get("pair") for m in movers_out],
            }
        )

    # 4) Cooldown
    if blocked:
        pretty_b = ", ".join(p.replace("-USD", "") for p in blocked[:8])
        if len(blocked) > 8:
            pretty_b += "…"
        reasons.append(
            {
                "code": "cooldown",
                "title": "A short pause after recent sells",
                "detail": (
                    f"We're not rebuying {pretty_b} right away — a cooling-off period "
                    "so one bad stretch doesn't turn into whiplash."
                ),
                "severity": "secondary",
                "pairs": blocked,
            }
        )

    # 5) Sticky cash hold
    if hold_usd > 1:
        reasons.append(
            {
                "code": "cash_hold",
                "title": f"About ${hold_usd:.0f} is reserved as cash",
                "detail": (
                    "You (or a safety setting) parked that money on the sidelines. "
                    "It won't auto-spend until released."
                ),
                "severity": "primary",
            }
        )

    # 6) Already thin book
    if held and park:
        pretty_h = ", ".join(p.replace("-USD", "") for p in sorted(held)[:6])
        reasons.append(
            {
                "code": "already_in",
                "title": f"You still have a small position ({pretty_h})",
                "detail": (
                    "Not empty — just not adding more while cash-first mode is on. "
                    "What you hold keeps working; we're skipping new FOMO buys."
                ),
                "severity": "info",
            }
        )

    # Headline for lazy / FOMO traders
    if park and heat.get("hot"):
        headline = (
            "Markets look busy today — we're staying mostly in cash on purpose. "
            "That's the strategy, not a bug."
        )
    elif park:
        headline = (
            "New buys are paused. Your money stays in cash until conditions look clearer."
        )
    elif cream_n == 0 and live_would == 0:
        headline = (
            "We can buy, but nothing good enough showed up — better to wait than chase."
        )
    else:
        headline = "We're open to careful buys when something looks solid."

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
            "We don't try to own every green day. "
            "We try to stay diversified with a short coin list, buy only when entries look solid, "
            "and always show you why cash is winning when it is."
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
