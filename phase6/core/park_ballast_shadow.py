"""
Park / ballast shadow decision logger (Step 2).

Writes what the decision matrix *would* do — no orders, no arm/disarm.
See docs/research/PARK_BALLAST_DECISION_MATRIX.md
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT, STATE_DIR

logger = logging.getLogger("phase6.park_ballast_shadow")

DECISION_LATEST = STATE_DIR / "park_ballast_decision_latest.json"
DECISION_HISTORY = STATE_DIR / "park_ballast_decision_history.jsonl"
REGIME_STATUS = STATE_DIR / "regime_cash_status.json"
LIVE_STATE = STATE_DIR / "phase6_live_state.json"
PAXG_CSV = STATE_DIR / "paxg_daily_close_cache.csv"
BTC_OHLCV_CANDIDATES = [
    PROJECT_ROOT / "backtests/data/long/ohlcv_daily_btc.json",
    PROJECT_ROOT / "backtests/data/backtest_historical_ohlcv_btc_2025-04-20_to_2026-04-20.json",
]

# Matrix defaults (placeholders — refine with data later)
KEEP_HOLD_MARGIN_PP = 5.0
KEEP_HOLD_LOOKBACK_D = 30
KEEP_HOLD_MAX_PCT = 0.02  # micro-ish floor for shadow recommendation
FULL_TARGET_PCT = 0.20
STABLE = frozenset({"USD", "USDC", "USDT", "DAI"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _ret_from_closes(closes: Sequence[float], lookback: int) -> Optional[float]:
    if not closes or len(closes) < lookback + 1:
        if closes and len(closes) >= 2:
            # use whatever we have
            a, b = float(closes[0]), float(closes[-1])
            if a > 0:
                return (b / a - 1.0) * 100.0
        return None
    a = float(closes[-(lookback + 1)])
    b = float(closes[-1])
    if a <= 0:
        return None
    return (b / a - 1.0) * 100.0


def load_paxg_30d_ret_pct(lookback: int = KEEP_HOLD_LOOKBACK_D) -> Tuple[Optional[float], str]:
    if not PAXG_CSV.is_file():
        return None, "no_paxg_csv"
    try:
        rows = list(csv.DictReader(PAXG_CSV.open(encoding="utf-8")))
        closes = []
        for r in rows:
            for k in ("close", "Close", "c", "price"):
                if k in r and r[k] not in (None, ""):
                    try:
                        closes.append(float(r[k]))
                        break
                    except ValueError:
                        pass
        ret = _ret_from_closes(closes, lookback)
        return ret, "paxg_daily_close_cache.csv"
    except Exception as e:
        return None, f"paxg_csv_error:{e}"


def load_btc_30d_ret_pct(lookback: int = KEEP_HOLD_LOOKBACK_D) -> Tuple[Optional[float], str]:
    # Prefer regime status detector window
    rc = _load_json(REGIME_STATUS)
    btc = rc.get("btc_return_pct")
    if btc is None and isinstance(rc.get("detector"), dict):
        btc = rc["detector"].get("btc_return_pct")
    if btc is not None:
        try:
            return float(btc), "regime_cash_status.btc_return_pct"
        except (TypeError, ValueError):
            pass
    for path in BTC_OHLCV_CANDIDATES:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            closes = []
            if isinstance(data, list):
                for row in data:
                    if isinstance(row, dict):
                        c = row.get("close") or row.get("c")
                        if c is not None:
                            closes.append(float(c))
                    elif isinstance(row, (list, tuple)) and len(row) >= 5:
                        closes.append(float(row[4]))
            elif isinstance(data, dict) and "candles" in data:
                for row in data["candles"]:
                    if isinstance(row, dict) and row.get("close") is not None:
                        closes.append(float(row["close"]))
            ret = _ret_from_closes(closes, lookback)
            if ret is not None:
                return ret, str(path.name)
        except Exception:
            continue
    return None, "no_btc_ret"


def estimate_basket_30d_ret_pct(
    exchange: Any = None,
    lookback: int = KEEP_HOLD_LOOKBACK_D,
) -> Tuple[Optional[float], str]:
    """
    Best-effort EW of non-stable, non-PAXG positions from live state.
    Without per-pair history we cannot true 30d — mark insufficient.
    """
    # Without multi-pair OHLCV on tick, leave unknown (honest)
    live = _load_json(LIVE_STATE)
    pos = live.get("positions") or live.get("active_positions") or []
    n = 0
    if isinstance(pos, list):
        for p in pos:
            if not isinstance(p, dict):
                continue
            pair = str(p.get("pair") or p.get("product_id") or "")
            base = pair.split("-")[0].upper() if pair else ""
            if base in STABLE or base == "PAXG":
                continue
            n += 1
    if n == 0:
        return None, "no_deploy_basket_positions"
    return None, "basket_30d_ohlcv_not_on_tick"


def crypto_util_pct_from_live() -> Optional[float]:
    live = _load_json(LIVE_STATE)
    try:
        total = float(live.get("total_usd") or live.get("total_holdings_value") or 0)
        cash = float(live.get("cash_usd") or 0)
        if total <= 0:
            return None
        # crypto ≈ non-cash; crude
        crypto = max(0.0, total - cash)
        # subtract PAXG if listed in balances
        bals = live.get("balances") or {}
        if isinstance(bals, dict) and "PAXG" in bals:
            # unknown px here; ignore small error
            pass
        return crypto / total
    except Exception:
        return None


def is_parked(regime_status: Dict[str, Any]) -> bool:
    mode = str(regime_status.get("strategy_mode") or "").lower()
    regime = str(regime_status.get("regime") or "").lower()
    allow = regime_status.get("allow_new_buys")
    if mode in ("usdc_park", "park", "cash"):
        return True
    if allow is False:
        return True
    if regime in ("bear", "transition") and allow is not True:
        return True
    return False


def is_deploy_open(regime_status: Dict[str, Any]) -> bool:
    mode = str(regime_status.get("strategy_mode") or "").lower()
    allow = regime_status.get("allow_new_buys")
    if allow is True and mode in ("deploy", "rebalance", "flat", "bull", "cautious", "flat_cautious_deploy_b"):
        return True
    if allow is True and "deploy" in mode:
        return True
    # flat B with buys on
    if allow is True and str(regime_status.get("regime") or "").lower() in ("flat", "bull"):
        return True
    return bool(allow is True and mode not in ("usdc_park", "park"))


def evaluate_keep_hold(
    *,
    ret_vs_arm: Optional[float],
    paxg_30d_pct: Optional[float],
    btc_30d_pct: Optional[float],
    basket_30d_pct: Optional[float],
    margin_pp: float = KEEP_HOLD_MARGIN_PP,
) -> Dict[str, Any]:
    o1 = False
    if ret_vs_arm is not None and ret_vs_arm > 0:
        o1 = True
    if paxg_30d_pct is not None and paxg_30d_pct > 0:
        o1 = True
    o2 = (
        paxg_30d_pct is not None
        and btc_30d_pct is not None
        and paxg_30d_pct >= btc_30d_pct + margin_pp
    )
    o3_data = basket_30d_pct is not None and paxg_30d_pct is not None
    if o3_data:
        o3 = bool(float(paxg_30d_pct) >= float(basket_30d_pct) + margin_pp)  # type: ignore[arg-type]
    else:
        o3 = False
    # If basket unknown, require O1+O2 only and flag partial
    if basket_30d_pct is None:
        eligible = bool(o1 and o2)
        incomplete = True
    else:
        eligible = bool(o1 and o2 and o3)
        incomplete = False
    return {
        "O1_sleeve_or_paxg_green": o1,
        "O2_paxg_beats_btc_by_margin": o2,
        "O3_paxg_beats_basket_by_margin": o3 if o3_data else None,
        "O3_available": o3_data,
        "eligible": eligible,
        "incomplete_tests": incomplete,
        "margin_pp": margin_pp,
        "inputs": {
            "ret_vs_arm": ret_vs_arm,
            "paxg_30d_pct": paxg_30d_pct,
            "btc_30d_pct": btc_30d_pct,
            "basket_30d_pct": basket_30d_pct,
        },
    }


def build_park_ballast_decision(
    *,
    exchange: Any = None,
    full_config: Optional[Dict[str, Any]] = None,
    preserve_cfg: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    e1_health: Optional[Dict[str, Any]] = None,
    sleeve_row: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from phase6.core.preserve_hold import load_preserve_config, load_state

    cfg = preserve_cfg or load_preserve_config(full_config)
    st = state if state is not None else load_state()
    rc = _load_json(REGIME_STATUS)
    sleeve = sleeve_row or {}
    health = e1_health or {}

    parked = is_parked(rc)
    deploy = is_deploy_open(rc)
    armed = bool(st.get("armed"))
    micro = bool(st.get("soak_micro") or cfg.get("micro_live"))
    util = crypto_util_pct_from_live()
    venue_ok = str(cfg.get("venue_probe_result") or "").upper() in ("A", "PASS", "OK", "")

    paxg_ret, paxg_src = load_paxg_30d_ret_pct()
    btc_ret, btc_src = load_btc_30d_ret_pct()
    basket_ret, basket_src = estimate_basket_30d_ret_pct(exchange)

    ret_vs_arm = sleeve.get("ret_vs_arm")
    if ret_vs_arm is None and st.get("arm_vwap") and sleeve.get("price"):
        try:
            ret_vs_arm = float(sleeve["price"]) / float(st["arm_vwap"]) - 1.0
        except Exception:
            ret_vs_arm = None

    keep = evaluate_keep_hold(
        ret_vs_arm=float(ret_vs_arm) if ret_vs_arm is not None else None,
        paxg_30d_pct=paxg_ret,
        btc_30d_pct=btc_ret,
        basket_30d_pct=basket_ret,
    )

    # --- would_* (shadow only) ---
    would_initiate = (
        (not armed)
        and parked
        and venue_ok
        and (util is None or util < 0.30)
        and bool(cfg.get("enabled"))
    )
    would_initiate_size = "S1_MICRO" if would_initiate else "S0_OFF"

    would_keep_hold = bool(armed and deploy and keep.get("eligible"))
    would_trim_default = bool(armed and deploy and not would_keep_hold)
    would_hold_park = bool(armed and parked and not deploy)

    # Recommended B target (shadow)
    if health.get("naked"):
        recommended = "REPAIR_E1_OR_DISARM"
        b_target = "unchanged_until_e1_safe"
    elif not armed:
        if would_initiate:
            recommended = "OFFER_ARM_MICRO"
            b_target = "S1_MICRO"
        else:
            recommended = "STAY_A_ONLY"
            b_target = "S0"
    elif would_keep_hold:
        recommended = "KEEP_HOLD_MICRO"
        b_target = f"KEEP<={KEEP_HOLD_MAX_PCT:.0%}"
    elif would_trim_default:
        recommended = "TRIM_DEFAULT_TO_A"
        b_target = "S0"
    elif would_hold_park:
        recommended = "HOLD_B_IN_PARK"
        b_target = "S1_MICRO" if micro else "S2_FULL_OR_CURRENT"
    else:
        recommended = "HOLD_OBSERVE"
        b_target = "current"

    notes: List[str] = []
    if keep.get("incomplete_tests"):
        notes.append("Keep-Hold O3 basket 30d unavailable on tick — eligibility used O1+O2 only")
    if would_keep_hold:
        notes.append("Keep-Hold shadow only — no auto hold override wired to trim yet")
    if would_trim_default:
        notes.append("Trim-on-deploy is doctrine; live auto-trim not enabled in this step")
    notes.append("No orders placed by shadow logger")

    return {
        "schema_version": 1,
        "as_of": _now(),
        "method": "park_ballast_decision_matrix_shadow_v1",
        "matrix_doc": "docs/research/PARK_BALLAST_DECISION_MATRIX.md",
        "orders": False,
        "regime": {
            "regime": rc.get("regime"),
            "strategy_mode": rc.get("strategy_mode"),
            "allow_new_buys": rc.get("allow_new_buys"),
            "label": rc.get("label"),
            "btc_return_pct": rc.get("btc_return_pct"),
            "parked": parked,
            "deploy_open": deploy,
        },
        "book": {
            "crypto_util_est": util,
            "preserve_armed": armed,
            "preserve_micro": micro,
            "preserve_usd": sleeve.get("preserve_usd"),
            "ret_vs_arm": ret_vs_arm,
        },
        "e1": {
            "open": health.get("e1_open"),
            "naked": health.get("naked"),
            "reason": health.get("reason"),
            "match_mode": health.get("match_mode"),
            "order_id": st.get("e1_order_id"),
        },
        "returns_lookback": {
            "days": KEEP_HOLD_LOOKBACK_D,
            "paxg_30d_pct": paxg_ret,
            "paxg_src": paxg_src,
            "btc_30d_pct": btc_ret,
            "btc_src": btc_src,
            "basket_30d_pct": basket_ret,
            "basket_src": basket_src,
        },
        "keep_hold": keep,
        "would": {
            "initiate_b": would_initiate,
            "initiate_size": would_initiate_size,
            "trim_default_on_deploy": would_trim_default,
            "keep_hold_on_deploy": would_keep_hold,
            "hold_b_while_parked": would_hold_park,
            "scale_to_full_20pct": False,  # never auto
        },
        "recommended_action": recommended,
        "recommended_b_target": b_target,
        "full_target_pct_policy": FULL_TARGET_PCT,
        "notes": notes,
    }


def write_park_ballast_decision(**kwargs: Any) -> Dict[str, Any]:
    dec = build_park_ballast_decision(**kwargs)
    DECISION_LATEST.parent.mkdir(parents=True, exist_ok=True)
    DECISION_LATEST.write_text(json.dumps(dec, indent=2, default=str) + "\n", encoding="utf-8")
    try:
        hist = {
            "as_of": dec.get("as_of"),
            "recommended_action": dec.get("recommended_action"),
            "recommended_b_target": dec.get("recommended_b_target"),
            "parked": (dec.get("regime") or {}).get("parked"),
            "deploy_open": (dec.get("regime") or {}).get("deploy_open"),
            "e1_open": (dec.get("e1") or {}).get("open"),
            "e1_naked": (dec.get("e1") or {}).get("naked"),
            "keep_eligible": (dec.get("keep_hold") or {}).get("eligible"),
            "would_trim": (dec.get("would") or {}).get("trim_default_on_deploy"),
            "would_keep": (dec.get("would") or {}).get("keep_hold_on_deploy"),
        }
        with DECISION_HISTORY.open("a", encoding="utf-8") as f:
            f.write(json.dumps(hist, default=str) + "\n")
    except Exception as e:
        logger.debug("decision history append failed: %s", e)
    return dec
