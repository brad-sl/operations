"""
Runner-side deposit/withdrawal detection from live USD + holdings NAV.

Reuses portfolio_external_flows classification. Persists NAV snapshots in
phase6_runner_state.json and audit logs for diagnostics.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.portfolio_external_flows import (
    FLOWS_JSONL,
    MIN_FLOW_USD,
    classify_external_flow_usd,
)
from phase6.core.portfolio_disposition import (
    detect_manual_disposition,
    normalize_position_values,
)

logger = logging.getLogger(__name__)

# Absolute paths — dashboard often runs with cwd=/ and relative paths miss the ledger
# (would hide post-SL rebuy blocks on Signals ·blocked / ·ready).
try:
    from phase6.core.paths import PROJECT_ROOT, STATE_DIR
except Exception:  # pragma: no cover
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    STATE_DIR = PROJECT_ROOT / "data" / "state"

RUNNER_EVENTS_JSONL = STATE_DIR / "capital_events_runner.jsonl"
DEFAULT_STATE_FILE = STATE_DIR / "phase6_runner_state.json"
TRADES_JSONL = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"

STOP_EXCHANGE_REASONS = frozenset(
    {"stop_loss_exchange", "stop_loss", "sl", "stoploss"}
)
# Live TP market exits (shadow_tp) — shorter cool-off than SL (default 24h)
TP_EXIT_REASONS = frozenset(
    {
        "take_profit_trail",
        "take_profit_fixed_tp",
        "take_profit_fixed",
        "take_profit_breakeven_lock",
        "take_profit_exchange",
    }
)
# Bot strategy profit / lifecycle exits (dual_peak, extension_partial, etc.).
# Same capital treatment as TP: NO cash hold, short cool-off only — never manual.
LIFECYCLE_EXIT_PREFIXES = (
    "lifecycle_",
    "lifecycle_dual_peak",
    "lifecycle_extension",
    "lifecycle_exit",
)


def _reason_is_stop_exchange(reason: str) -> bool:
    r = str(reason or "").lower()
    return (
        r in STOP_EXCHANGE_REASONS
        or r == "stop_loss_exchange"
        or "stop_loss" in r
        or r.startswith("dust_sweep_after_sl")
        or "dust_sweep_after_sl" in r
    )


def _reason_is_strategy_profit_exit(reason: str) -> bool:
    """True for live TP + lifecycle trims — bot exits, not operator manual liquidations."""
    r = str(reason or "").lower()
    if not r:
        return False
    if r in TP_EXIT_REASONS or r.startswith("take_profit") or "take_profit" in r:
        return True
    if r.startswith("lifecycle_") or r.startswith("lifecycle"):
        return True
    if "lifecycle_dual_peak" in r or "lifecycle_extension" in r:
        return True
    # signal_source sometimes lands in reason/source field
    if r.startswith("lifecycle_dual_peak") or r.startswith("lifecycle_extension_partial"):
        return True
    return False


def _reason_is_lifecycle_exit(reason: str) -> bool:
    r = str(reason or "").lower()
    return bool(r) and (
        r.startswith("lifecycle_")
        or r.startswith("lifecycle")
        or "lifecycle_dual_peak" in r
        or "lifecycle_extension" in r
    )


def _cash_usd_from_runner(runner: Any) -> float:
    ex = getattr(runner, "exchange", None)
    if not ex:
        return 0.0
    usd = float(ex.get_account_balance("USD") or 0.0)
    try:
        usdc = float(ex.get_account_balance("USDC") or 0.0)
    except Exception:
        usdc = 0.0
    return usd + usdc


def _holdings_usd_from_runner(runner: Any) -> float:
    raw = getattr(runner, "portfolio", None) and runner.portfolio.get_enriched_positions() or {}
    if isinstance(raw, dict) and "positions" in raw:
        positions = raw.get("positions") or raw.get("value_usd") or {}
    else:
        positions = raw or {}
    total = 0.0
    for k, v in (positions.items() if isinstance(positions, dict) else []):
        if isinstance(v, dict):
            total += float(v.get("value_usd", v.get("amount", 0.0)) or 0.0)
        else:
            total += float(v or 0.0)
    return total


def snapshot_nav_from_runner(runner: Any) -> Dict[str, float]:
    cash = _cash_usd_from_runner(runner)
    holdings = _holdings_usd_from_runner(runner)
    return {
        "cash_usd": round(cash, 2),
        "holdings_usd": round(holdings, 2),
        "total_usd": round(cash + holdings, 2),
    }


def load_persisted_nav_snapshot(state_file: Path = DEFAULT_STATE_FILE) -> Optional[Dict[str, float]]:
    if not state_file.exists():
        return None
    try:
        data = json.loads(state_file.read_text())
        snap = data.get("capital_nav_snapshot")
        if not isinstance(snap, dict):
            return None
        return {
            "cash_usd": float(snap.get("cash_usd", 0)),
            "holdings_usd": float(snap.get("holdings_usd", 0)),
            "total_usd": float(snap.get("total_usd", 0)),
        }
    except Exception:
        return None


def persist_nav_snapshot(
    runner: Any,
    snap: Dict[str, float],
    state_file: Optional[str] = None,
) -> None:
    path = Path(state_file or getattr(runner, "state_file", None) or DEFAULT_STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    state: Dict[str, Any] = {}
    if path.exists():
        try:
            state = json.loads(path.read_text())
        except Exception:
            state = {}
    state["capital_nav_snapshot"] = {
        **snap,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(state, indent=2))


def load_persisted_position_snapshot(state_file: Path) -> Dict[str, float]:
    if not state_file.exists():
        return {}
    try:
        data = json.loads(state_file.read_text())
        snap = data.get("capital_position_snapshot")
        if isinstance(snap, dict):
            return {str(k): float(v) for k, v in snap.get("positions", snap).items() if k != "ts"}
        if isinstance(snap, dict):
            return {str(k): float(v) for k, v in snap.items()}
    except Exception:
        pass
    return {}


def persist_position_snapshot(
    runner: Any,
    positions: Dict[str, float],
    state_file: Optional[str] = None,
) -> None:
    path = Path(state_file or getattr(runner, "state_file", None) or DEFAULT_STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    state: Dict[str, Any] = {}
    if path.exists():
        try:
            state = json.loads(path.read_text())
        except Exception:
            state = {}
    state["capital_position_snapshot"] = {
        "positions": positions,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(state, indent=2))


def _cancel_stops_for_pairs(runner: Any, pairs: List[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    client = getattr(getattr(runner, "stop_loss_coordinator", None), "client", None)
    if not client:
        client = getattr(runner, "exchange", None)
    if not client:
        return out
    try:
        from phase6.core.sl_preflight import cancel_open_stops_for_pair

        for pair in pairs:
            try:
                out[pair] = int(cancel_open_stops_for_pair(client, pair) or 0)
            except Exception as exc:
                logger.warning("[MANUAL-SELL] stop cancel failed %s: %s", pair, exc)
    except Exception as exc:
        logger.warning("[MANUAL-SELL] stop cancel import failed: %s", exc)
    return out


def _register_manual_sell_cooldown(
    runner: Any,
    pairs: List[str],
    hours: float,
    state_path: str,
) -> None:
    if not pairs:
        return
    path = Path(state_path)
    state: Dict[str, Any] = {}
    if path.exists():
        try:
            state = json.loads(path.read_text())
        except Exception:
            state = {}
    cd = state.get("manual_sell_cooldown") or {}
    if not isinstance(cd, dict):
        cd = {}
    expires = datetime.now(timezone.utc).timestamp() + hours * 3600.0
    for p in pairs:
        cd[p] = expires
    state["manual_sell_cooldown"] = cd
    path.write_text(json.dumps(state, indent=2))
    runner._manual_sell_cooldown = cd
    try:
        from phase6.core.capital_controls import persist_manual_sell_cooldown

        persist_manual_sell_cooldown(runner, state_file=str(path))
    except Exception:
        pass


def load_manual_sell_cooldown_pairs(state_file: Path, runner: Any = None) -> List[str]:
    active: List[str] = []
    mem = getattr(runner, "_manual_sell_cooldown", None) if runner is not None else None
    if isinstance(mem, dict) and mem:
        now = datetime.now(timezone.utc).timestamp()
        active = [p for p, exp in mem.items() if float(exp) > now]
    if not state_file.exists():
        return sorted(set(active))
    try:
        data = json.loads(state_file.read_text())
        cd = data.get("manual_sell_cooldown") or {}
        now = datetime.now(timezone.utc).timestamp()
        from_disk = [p for p, exp in cd.items() if float(exp) > now]
        return sorted(set(active + from_disk))
    except Exception:
        return sorted(set(active))


def _parse_trade_ts(raw: str) -> Optional[float]:
    if not raw:
        return None
    try:
        s = raw.strip().replace("Z", "+00:00")
        if " " in s and "T" not in s:
            s = s.replace(" ", "T", 1)
        if "+" not in s[10:] and not s.endswith("Z"):
            dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(s)
        return dt.timestamp()
    except Exception:
        return None


def _load_recent_ledger_sells(hours: float, jsonl_path: Path = TRADES_JSONL) -> List[dict]:
    if not jsonl_path.exists():
        return []
    cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600.0
    out: List[dict] = []
    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            t = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(t.get("side", "")).upper() != "SELL":
            continue
        ts = _parse_trade_ts(str(t.get("timestamp", "")))
        if ts is None or ts < cutoff:
            continue
        out.append(t)
    return out


def split_disposition_pairs_by_ledger(
    pairs_sold: List[str],
    window_hours: float = 48.0,
    jsonl_path: Path = TRADES_JSONL,
) -> Tuple[List[str], List[str], List[str]]:
    """
    Classify disposition pairs from recent ledger SELLs.

    Returns (stop_pairs, tp_pairs, manual_pairs):
      - stop: exchange SL / dust after SL → SL cooldown policy
      - tp: live take_profit_* OR lifecycle_* (dual_peak / extension_partial)
            → post-TP cool-off only (no cash hold / no 48h manual)
      - manual: true operator liquidations → manual hold + longer cooldown

    Lifecycle must never fall through to manual — that parks cash and blocks
    redeploy after a successful profit-side trim (BTC 2026-08-26 class bug).
    """
    if not pairs_sold:
        return [], [], []
    sold_set = set(pairs_sold)
    stop_pairs: set = set()
    tp_pairs: set = set()
    for t in _load_recent_ledger_sells(window_hours, jsonl_path=jsonl_path):
        pair = t.get("pair")
        if pair not in sold_set:
            continue
        reason = str(
            t.get("reason") or t.get("exit_reason") or t.get("source") or t.get("signal_source") or ""
        )
        if _reason_is_stop_exchange(reason):
            stop_pairs.add(pair)
        elif _reason_is_strategy_profit_exit(reason):
            tp_pairs.add(pair)
    # Prefer stop over tp if both somehow present; manual = neither
    tp_pairs -= stop_pairs
    manual_pairs = [p for p in pairs_sold if p not in stop_pairs and p not in tp_pairs]
    return sorted(stop_pairs), sorted(tp_pairs), manual_pairs


def apply_manual_disposition(runner: Any, event: Dict[str, Any], settings: Dict[str, Any]) -> None:
    et = event.get("event_type")
    if et == "manual_liquidation_to_cash":
        pairs_sold = list(event.get("pairs_sold") or [])
        pair_deltas = event.get("pair_deltas") or {}
        window = float(settings.get("stop_loss_ledger_lookback_hours", 48.0))
        ledger_path = Path(settings.get("ledger_jsonl_path") or TRADES_JSONL)
        stop_pairs, tp_pairs, manual_pairs = split_disposition_pairs_by_ledger(
            pairs_sold, window_hours=window, jsonl_path=ledger_path
        )
        event["pairs_exchange_stop"] = stop_pairs
        event["pairs_take_profit"] = tp_pairs
        event["pairs_manual_intent"] = manual_pairs
        # Annotate lifecycle subset of tp_pairs for audit (same capital policy as TP)
        life_pairs = []
        try:
            for t in _load_recent_ledger_sells(window, jsonl_path=ledger_path):
                p = t.get("pair")
                if p in tp_pairs and _reason_is_lifecycle_exit(
                    str(t.get("reason") or t.get("exit_reason") or t.get("signal_source") or "")
                ):
                    life_pairs.append(p)
            event["pairs_lifecycle_exit"] = sorted(set(life_pairs))
        except Exception:
            event["pairs_lifecycle_exit"] = []

        stop_hours = float(settings.get("stop_loss_exchange_block_rebuy_hours", 72.0))
        manual_hours = float(settings.get("manual_sell_block_rebuy_hours", 48.0))
        # TP cool-off is ledger-driven (post_tp_block_rebuy_hours, default 24).
        # Do NOT also stamp capital-controls 48/72h or park TP proceeds as cash hold.
        tp_hours = 24.0
        try:
            from phase6.core.shadow_tp import load_exit_automation

            tp_cfg = (load_exit_automation().get("take_profit") or {})
            if tp_cfg.get("post_tp_block_rebuy_hours") is not None:
                tp_hours = float(tp_cfg["post_tp_block_rebuy_hours"])
        except Exception:
            pass
        stop_hold = bool(settings.get("stop_loss_exchange_hold_cash", True))
        manual_hold = bool(settings.get("manual_sell_hold_cash", True))

        hold_add = 0.0
        skipped_hold_usd = 0.0
        stop_hold_add = 0.0
        if manual_hold and manual_pairs:
            for p in manual_pairs:
                hold_add += abs(float(pair_deltas.get(p, 0.0) or 0.0))
            if hold_add <= 0.0 and manual_pairs and len(manual_pairs) == len(pairs_sold):
                hold_add = float(event.get("cash_delta_usd") or event.get("sold_usd") or 0.0)
            elif hold_add <= 0.0 and manual_pairs:
                total_sold = sum(abs(float(pair_deltas.get(p, 0.0) or 0.0)) for p in pairs_sold)
                cash_delta = float(event.get("cash_delta_usd") or 0.0)
                if total_sold > 0 and cash_delta > 0:
                    manual_sold = sum(
                        abs(float(pair_deltas.get(p, 0.0) or 0.0)) for p in manual_pairs
                    )
                    hold_add = cash_delta * (manual_sold / total_sold)

        # TG-03: when stop_hold=true, exchange-stop proceeds also park as cash hold (repair path).
        if stop_hold and stop_pairs:
            for p in stop_pairs:
                stop_hold_add += abs(float(pair_deltas.get(p, 0.0) or 0.0))
            if stop_hold_add <= 0.0 and stop_pairs and not manual_pairs and not tp_pairs:
                stop_hold_add = float(event.get("cash_delta_usd") or event.get("sold_usd") or 0.0)
            elif stop_hold_add <= 0.0 and stop_pairs:
                total_sold = sum(abs(float(pair_deltas.get(p, 0.0) or 0.0)) for p in pairs_sold)
                cash_delta = float(event.get("cash_delta_usd") or 0.0)
                if total_sold > 0 and cash_delta > 0:
                    stop_sold = sum(abs(float(pair_deltas.get(p, 0.0) or 0.0)) for p in stop_pairs)
                    stop_hold_add = cash_delta * (stop_sold / total_sold)
            hold_add += stop_hold_add
            event["cash_hold_added_exchange_stop_usd"] = round(stop_hold_add, 2)

        # TP proceeds are free to redeploy after the short post-TP block — never cash-hold.
        if tp_pairs:
            tp_sold = sum(abs(float(pair_deltas.get(p, 0.0) or 0.0)) for p in tp_pairs)
            event["cash_hold_skipped_take_profit_usd"] = round(tp_sold, 2)
            event["pairs_take_profit_no_cash_hold"] = list(tp_pairs)

        if not stop_hold and stop_pairs:
            for p in stop_pairs:
                skipped_hold_usd += abs(float(pair_deltas.get(p, 0.0) or 0.0))
            if skipped_hold_usd <= 0.0 and stop_pairs:
                skipped_hold_usd = float(event.get("cash_delta_usd") or 0.0) * (
                    len(stop_pairs) / max(1, len(pairs_sold))
                )
            event["cash_hold_skipped_exchange_stop_usd"] = round(skipped_hold_usd, 2)

        if hold_add > 0.0:
            prev_hold = float(getattr(runner, "_manual_liquidation_cash_hold_usd", 0.0) or 0.0)
            runner._manual_liquidation_cash_hold_usd = round(prev_hold + hold_add, 2)
            event["cash_hold_usd"] = runner._manual_liquidation_cash_hold_usd
            event["cash_hold_added_usd"] = round(hold_add, 2)
            try:
                from phase6.core.capital_controls import persist_manual_cash_hold

                persist_manual_cash_hold(runner)
            except Exception:
                pass

        state_path = getattr(runner, "state_file", None) or str(DEFAULT_STATE_FILE)
        if stop_pairs:
            _register_manual_sell_cooldown(runner, stop_pairs, stop_hours, state_path)
        if manual_pairs:
            _register_manual_sell_cooldown(runner, manual_pairs, manual_hours, state_path)
        # TP: do not write capital-controls cooldown — load_buy_block_status uses ledger + 24h.
        # (Registering here used to stack 48h manual on top of 24h post-TP.)

        event["rebuy_cooldown_hours_stop_exchange"] = stop_hours if stop_pairs else None
        event["rebuy_cooldown_hours_manual"] = manual_hours if manual_pairs else None
        event["rebuy_cooldown_hours_take_profit"] = tp_hours if tp_pairs else None
        event["rebuy_blocked_pairs"] = list(pairs_sold)
        event["stop_loss_exchange_hold_cash"] = stop_hold
        if tp_pairs and not stop_pairs and not manual_pairs:
            # Lifecycle dual_peak / extension_partial share this action (no cash hold).
            event["action"] = "take_profit_no_cash_hold"
            if event.get("pairs_lifecycle_exit"):
                event["action_detail"] = "lifecycle_or_tp_no_cash_hold"
        elif stop_pairs and manual_pairs:
            event["action"] = (
                "split_stop_hold_and_manual"
                if stop_hold
                else "split_stop_exchange_vs_manual"
            )
        elif stop_pairs and tp_pairs:
            event["action"] = "split_stop_and_take_profit"
        elif stop_pairs:
            event["action"] = (
                "hold_cash_block_rebuy_stop_exchange"
                if stop_hold
                else "block_rebuy_stop_exchange_only"
            )
        else:
            event["action"] = "hold_cash_block_rebuy"
        if settings.get("manual_sell_cancel_stops") and pairs_sold:
            # Cancel stops for manual only — TP/SL already exited
            cancel_targets = list(manual_pairs) if manual_pairs else []
            if cancel_targets:
                event["stops_cancelled"] = _cancel_stops_for_pairs(runner, cancel_targets)
    elif et == "manual_crypto_swap":
        event["action"] = "acknowledge_swap"
        pairs_sold = event.get("pairs_sold") or []
        if settings.get("manual_sell_cancel_stops") and pairs_sold:
            event["stops_cancelled"] = _cancel_stops_for_pairs(runner, pairs_sold)


def get_deployment_cooldown_pairs(runner: Any, hours: Optional[int] = None) -> List[str]:
    """Pairs blocked from auto-BUY: manual/stop cooldowns + recent stop-loss ledger.

    hours default: capital_event_stop_loss_exchange_block_rebuy_hours (repair default 72).
    """
    if hours is None:
        try:
            hours = int(float(_runner_capital_settings(runner).get(
                "stop_loss_exchange_block_rebuy_hours", 72
            )))
        except (TypeError, ValueError):
            hours = 72
    state_path = Path(getattr(runner, "state_file", None) or DEFAULT_STATE_FILE)
    manual = load_manual_sell_cooldown_pairs(state_path, runner=runner)
    stopped: List[str] = []
    if hasattr(runner, "_get_recently_stopped_pairs"):
        try:
            stopped = runner._get_recently_stopped_pairs(hours=int(hours))
        except Exception:
            pass
    # Ledger fallback (dashboard + runners whose ledger API ignores hours=)
    try:
        status = load_buy_block_status(hours=float(hours), state_file=state_path)
        stopped = list(set(stopped) | {
            p for p, meta in status.items()
            if meta.get("blocked") and str(meta.get("source") or "").startswith("ledger")
        })
    except Exception:
        pass
    return sorted(set(manual + stopped))


def _exp_to_ts(raw: Any) -> Optional[float]:
    """Parse cooldown expiry: unix float/int or ISO string → epoch seconds."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        pass
    return _parse_trade_ts(s)


def _default_stop_block_hours() -> float:
    try:
        cfg_path = Path("config/trading_config_phase6.json")
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text())
            gs = cfg.get("global_settings") or {}
            raw = gs.get("capital_event_stop_loss_exchange_block_rebuy_hours", 72)
            return float(raw)
    except Exception:
        pass
    try:
        from phase6.core.runtime_knobs import stop_loss_block_rebuy_hours

        return float(stop_loss_block_rebuy_hours())
    except Exception:
        return 72.0


def load_buy_block_status(
    hours: Optional[float] = None,
    state_file: Optional[Path] = None,
    jsonl_path: Path = TRADES_JSONL,
    account_id: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Active auto-BUY blocks for dashboard / gates (no runner required).

    Merges:
      1) capital_controls store + runner_state ``manual_sell_cooldown`` (explicit expiry)
      2) recent ledger stop-loss SELLs → block until sell_ts + hours (default 72h)

    Returns pair → {
      blocked, reason, source, expires_at (ISO), expires_ts, hours_remaining, block_hours
    }
    """
    now = datetime.now(timezone.utc).timestamp()
    if hours is None:
        hours = _default_stop_block_hours()
        # Prefer live capital_controls policy when present
        try:
            from phase6.core import capital_controls_store as store

            if account_id:
                st = store.load_account_capital_state(account_id)
            else:
                st = store.load_for_runner(None)
            pol = (st or {}).get("capital_controls_policy") or {}
            if pol.get("stop_loss_exchange_block_rebuy_hours") is not None:
                hours = float(pol["stop_loss_exchange_block_rebuy_hours"])
        except Exception:
            try:
                cc = STATE_DIR / "capital_user_controls.json"
                if cc.exists():
                    pol = (json.loads(cc.read_text()).get("capital_controls_policy") or {})
                    if pol.get("stop_loss_exchange_block_rebuy_hours") is not None:
                        hours = float(pol["stop_loss_exchange_block_rebuy_hours"])
            except Exception:
                pass
    try:
        hours_f = float(hours)
    except (TypeError, ValueError):
        hours_f = 72.0
    if hours_f <= 0:
        hours_f = 72.0

    # pair -> (expires_ts, reason, source)
    best: Dict[str, Tuple[float, str, str]] = {}

    def _put(pair: str, exp_ts: float, reason: str, source: str) -> None:
        if not pair or exp_ts <= now:
            return
        prev = best.get(pair)
        if prev is None or exp_ts > prev[0]:
            best[pair] = (exp_ts, reason, source)

    # 1) Durable manual / registered cooldowns
    cooldown_maps: List[Tuple[Dict[str, Any], str]] = []
    try:
        from phase6.core import capital_controls_store as store

        if account_id:
            st = store.load_account_capital_state(account_id)
        else:
            st = store.load_for_runner(None, runner_state_path=state_file or DEFAULT_STATE_FILE)
        if isinstance(st, dict):
            cooldown_maps.append((st.get("manual_sell_cooldown") or {}, "capital_controls"))
    except Exception:
        pass
    try:
        cc = STATE_DIR / "capital_user_controls.json"
        if cc.exists():
            raw = json.loads(cc.read_text())
            cooldown_maps.append(
                (raw.get("manual_sell_cooldown_active") or raw.get("manual_sell_cooldown") or {},
                 "capital_user_controls")
            )
    except Exception:
        pass
    sf = Path(state_file or DEFAULT_STATE_FILE)
    try:
        if sf.exists():
            data = json.loads(sf.read_text())
            cooldown_maps.append((data.get("manual_sell_cooldown") or {}, "runner_state"))
    except Exception:
        pass

    for cmap, src in cooldown_maps:
        if not isinstance(cmap, dict):
            continue
        for pair, exp_raw in cmap.items():
            exp_ts = _exp_to_ts(exp_raw)
            if exp_ts is None:
                continue
            _put(str(pair), exp_ts, "rebuy_cooldown", src)

    # 2) Ledger stop-loss SELLs inside window → synthetic expiry
    cutoff = now - hours_f * 3600.0
    try:
        for t in _load_recent_ledger_sells(hours_f, jsonl_path=jsonl_path):
            pair = t.get("pair")
            if not pair:
                continue
            reason = str(t.get("reason") or t.get("exit_reason") or t.get("source") or "").lower()
            is_stop = _reason_is_stop_exchange(reason)
            if not is_stop:
                continue
            ts = _parse_trade_ts(str(t.get("timestamp", "")))
            if ts is None or ts < cutoff:
                continue
            exp_ts = ts + hours_f * 3600.0
            _put(str(pair), exp_ts, "post_sl_rebuy_block", "ledger_stop_loss")
    except Exception:
        pass

    # 3) Live take-profit + lifecycle strategy SELLs → shorter cool-off (default 24h)
    #    Prevents same-cycle / FOMO rebuy after banking a winner (LINK-class giveback loop).
    #    Lifecycle dual_peak / extension_partial must use this path — NOT 48h manual hold.
    tp_hours = 24.0
    try:
        from phase6.core.shadow_tp import load_exit_automation

        tp_cfg = (load_exit_automation().get("take_profit") or {})
        if tp_cfg.get("post_tp_block_rebuy_hours") is not None:
            tp_hours = float(tp_cfg["post_tp_block_rebuy_hours"])
    except Exception:
        pass
    if tp_hours > 0:
        tp_cutoff = now - tp_hours * 3600.0
        # Load enough history for the longer of SL/TP windows
        lookback = max(hours_f, tp_hours)
        try:
            for t in _load_recent_ledger_sells(lookback, jsonl_path=jsonl_path):
                pair = t.get("pair")
                if not pair:
                    continue
                reason = str(
                    t.get("reason")
                    or t.get("exit_reason")
                    or t.get("source")
                    or t.get("signal_source")
                    or ""
                )
                if not _reason_is_strategy_profit_exit(reason):
                    continue
                # Don't double-count stops that also matched profit keywords
                if _reason_is_stop_exchange(reason):
                    continue
                ts = _parse_trade_ts(str(t.get("timestamp", "")))
                if ts is None or ts < tp_cutoff:
                    continue
                exp_ts = ts + tp_hours * 3600.0
                block_reason = (
                    "post_lifecycle_rebuy_block"
                    if _reason_is_lifecycle_exit(reason)
                    else "post_tp_rebuy_block"
                )
                src = (
                    "ledger_lifecycle"
                    if block_reason == "post_lifecycle_rebuy_block"
                    else "ledger_take_profit"
                )
                _put(str(pair), exp_ts, block_reason, src)
        except Exception:
            pass

    out: Dict[str, Dict[str, Any]] = {}
    for pair, (exp_ts, reason, source) in best.items():
        left = max(0.0, (exp_ts - now) / 3600.0)
        # block_hours reflects the rule that created this block
        bh = (
            tp_hours
            if reason in ("post_tp_rebuy_block", "post_lifecycle_rebuy_block")
            else hours_f
        )
        out[pair] = {
            "blocked": True,
            "reason": reason,
            "source": source,
            "expires_ts": exp_ts,
            "expires_at": datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat(),
            "hours_remaining": round(left, 2),
            "block_hours": bh,
        }

    # Operator waivers (e.g. clear bug-driven blocks so pairs can re-enter)
    # data/state/buy_block_waivers.json:
    #   {"pairs": {"UNI-USD": {"note": "...", "expires_ts": null}}}
    try:
        wpath = STATE_DIR / "buy_block_waivers.json"
        if wpath.exists():
            wraw = json.loads(wpath.read_text())
            wpairs = (wraw.get("pairs") or {}) if isinstance(wraw, dict) else {}
            for pair, meta in (wpairs.items() if isinstance(wpairs, dict) else []):
                p = str(pair)
                if p not in out:
                    continue
                exp_w = None
                if isinstance(meta, dict) and meta.get("expires_ts") is not None:
                    try:
                        exp_w = float(meta["expires_ts"])
                    except (TypeError, ValueError):
                        exp_w = None
                if exp_w is not None and exp_w <= now:
                    continue  # waiver expired
                # Drop block while waiver active
                out.pop(p, None)
    except Exception:
        pass

    # EXIT-H4: structure-aware early release of post_tp blocks only
    try:
        out = _apply_post_tp_structure_early_release(out, now=now)
    except Exception:
        pass

    return out


def _post_tp_structure_cfg() -> Dict[str, Any]:
    """Knobs from exit_automation.take_profit (fail-closed to flat 24h)."""
    defaults = {
        "structure_aware": True,
        "early_release_phases": [1, 2],  # ignition, trend
        "min_hours_floor": 4.0,  # never release before this
        "require_structure_ok": True,
    }
    try:
        from phase6.core.shadow_tp import load_exit_automation

        tp = (load_exit_automation().get("take_profit") or {})
        defaults["structure_aware"] = bool(
            tp.get("post_tp_structure_aware", defaults["structure_aware"])
        )
        if tp.get("post_tp_early_release_phases") is not None:
            defaults["early_release_phases"] = [
                int(x) for x in (tp.get("post_tp_early_release_phases") or [])
            ]
        if tp.get("post_tp_min_hours_floor") is not None:
            defaults["min_hours_floor"] = float(tp["post_tp_min_hours_floor"])
        defaults["require_structure_ok"] = bool(
            tp.get("post_tp_require_structure_ok", defaults["require_structure_ok"])
        )
    except Exception:
        pass
    return defaults


def _apply_post_tp_structure_early_release(
    blocks: Dict[str, Dict[str, Any]],
    *,
    now: float,
) -> Dict[str, Dict[str, Any]]:
    """
    If a pair is post_tp blocked but currently in early run phase (ignition/trend)
    with structure_ok, drop the block after min_hours_floor so dry powder can
    fish real early opportunities (not FOMO scraps).
    """
    cfg = _post_tp_structure_cfg()
    if not cfg.get("structure_aware", True):
        return blocks
    floor_h = float(cfg.get("min_hours_floor") or 4.0)
    allow_phases = {int(x) for x in (cfg.get("early_release_phases") or [1, 2])}
    require_struct = bool(cfg.get("require_structure_ok", True))

    try:
        from phase6.core.run_phase_deploy import (
            PHASE_IGNITION,
            PHASE_TREND,
            classify_run_phase,
            load_run_phase_config,
            fetch_daily_candles_public,
        )
        from phase6.core.run_lifecycle import classify_structure
    except Exception:
        return blocks

    # Map phase names if ints missing
    if not allow_phases:
        allow_phases = {PHASE_IGNITION, PHASE_TREND}

    phase_cfg = load_run_phase_config(None)
    drop: List[str] = []
    for pair, meta in list(blocks.items()):
        if not isinstance(meta, dict):
            continue
        if str(meta.get("reason") or "") not in (
            "post_tp_rebuy_block",
            "post_lifecycle_rebuy_block",
        ):
            continue
        # elapsed since block started = block_hours - hours_remaining
        try:
            bh = float(meta.get("block_hours") or 24.0)
            left = float(meta.get("hours_remaining") or 0.0)
            elapsed = max(0.0, bh - left)
        except (TypeError, ValueError):
            continue
        if elapsed < floor_h:
            continue
        try:
            candles = fetch_daily_candles_public(pair, limit=40) or []
            if len(candles) < 15:
                continue
            snap = classify_run_phase(pair, candles, phase_cfg)
            phase = int(getattr(snap, "phase", 0) or 0)
            if phase not in allow_phases:
                continue
            struct_ok = True
            if require_struct:
                try:
                    sc = classify_structure(candles, pair=pair)
                    struct_ok = bool(getattr(sc, "structure_ok_for_entry", False))
                except Exception:
                    # fallback: phase alone
                    struct_ok = phase in (PHASE_IGNITION, PHASE_TREND)
            if require_struct and not struct_ok:
                continue
            drop.append(pair)
            logger.info(
                "[POST-TP] structure early-release %s phase=%s elapsed_h=%.1f",
                pair,
                phase,
                elapsed,
            )
        except Exception as e:
            logger.debug("[POST-TP] structure check fail %s: %s", pair, e)
            continue
    for p in drop:
        blocks.pop(p, None)
    return blocks


def effective_allocator_cash_usd(runner: Any) -> float:
    cash = _cash_usd_from_runner(runner)
    wr = (getattr(runner, "config_dict", None) or {}).get("withdrawal_reserve", {})
    min_reserve = float(wr.get("min_reserve_usd", 50.0))
    manual_hold = float(getattr(runner, "_manual_liquidation_cash_hold_usd", 0.0) or 0.0)
    return max(0.0, cash - min_reserve - manual_hold)


def filter_trade_plan_manual_cooldown(runner: Any, plan: Any) -> Any:
    blocked = set(get_deployment_cooldown_pairs(runner))
    if not blocked or not getattr(plan, "actions", None):
        return plan
    kept = []
    for a in plan.actions:
        if a.get("action", "").upper() == "BUY" and a.get("pair") in blocked:
            logger.info(
                "[MANUAL-SELL] blocked auto-rebuy %s ($%.2f)",
                a.get("pair"),
                float(a.get("usd", 0) or 0),
            )
            continue
        kept.append(a)
    plan.actions = kept
    return plan


# Soft gate (#2): do not light-tilt / add into bags sitting on top of their stop.
# Armed gate (#1, 2026-08-21): gap-gated — allow adds on long runners when stop cushion
# is healthy; still block near-stop race (manufactured SL). Full-bag SL reattach is CR-03.
NEAR_STOP_ADD_REASONS = frozenset(
    {
        "light_tilt_cash",
        "opportunistic_rotation_from_weak",
    }
)


def _near_stop_add_settings(runner: Any) -> Dict[str, Any]:
    cfg = getattr(runner, "config_dict", None) or {}
    rm = cfg.get("risk_management") or {}
    reasons = rm.get("near_stop_block_reasons")
    if reasons is None:
        reason_set = set(NEAR_STOP_ADD_REASONS)
    else:
        reason_set = {str(r) for r in reasons}
    min_gap = float(rm.get("near_stop_min_gap_pct", 0.02))
    # Explicit armed-add cushion; falls back to near_stop_min_gap_pct.
    armed_min_gap = rm.get("armed_stop_allow_add_min_gap_pct")
    if armed_min_gap is None:
        armed_min_gap = min_gap
    return {
        "enabled": bool(rm.get("near_stop_add_block_enabled", True)),
        "min_stop_gap_pct": min_gap,
        "armed_allow_add_min_gap_pct": float(armed_min_gap),
        "max_unrealized_pct": float(rm.get("near_stop_max_unrealized_pct", -0.01)),
        "reasons": reason_set,
        "require_existing_position": bool(
            rm.get("near_stop_require_existing_position", True)
        ),
        "min_position_usd": float(rm.get("near_stop_min_position_usd", 25.0)),
        "stop_loss_pct": float(rm.get("stop_loss_pct", rm.get("sl_base_pct", 0.03))),
    }


def _enriched_position_maps(
    runner: Any,
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
    """pair -> (value_usd, entry_price, current_price)."""
    values: Dict[str, float] = {}
    entries: Dict[str, float] = {}
    currents: Dict[str, float] = {}
    raw = getattr(runner, "portfolio", None) and runner.portfolio.get_enriched_positions() or {}
    if isinstance(raw, dict) and "positions" in raw:
        raw = raw.get("positions") or {}
    if not isinstance(raw, dict):
        return values, entries, currents
    for k, v in raw.items():
        pair = k if isinstance(k, str) and "-USD" in k else f"{k}-USD"
        if isinstance(v, dict):
            usd = float(v.get("value_usd", 0) or 0)
            if usd <= 0:
                amt = float(v.get("amount", v.get("qty", 0)) or 0)
                px = float(v.get("current_price", v.get("price", 0)) or 0)
                if amt > 0 and px > 0:
                    usd = amt * px
            values[pair] = usd
            ep = float(
                v.get("entry_price")
                or v.get("original_entry")
                or v.get("buy_fill_price")
                or v.get("entry")
                or 0
            )
            if ep > 0:
                entries[pair] = ep
            cp = float(v.get("current_price") or v.get("price") or 0)
            if cp > 0:
                currents[pair] = cp
        else:
            try:
                values[pair] = float(v or 0)
            except (TypeError, ValueError):
                values[pair] = 0.0
    return values, entries, currents


def _latest_registry_stop_for_pair(pair: str) -> Optional[Dict[str, Any]]:
    """
    Best-effort protective stop meta for pair.
    Prefer currently-open registry rows (open-id set, closed pops).
    Fall back to newest row with stop_price (suspend/cancel often leaves stale opens).
    """
    try:
        from phase6.core.protective_orders_registry import load_all_registry_rows
    except Exception:
        return None
    rows = load_all_registry_rows()
    if not rows:
        return None
    open_by_id: Dict[str, Dict[str, Any]] = {}
    newest_any: Optional[Dict[str, Any]] = None
    for row in rows:
        if row.get("pair") != pair:
            continue
        newest_any = row
        oid = row.get("sl_order_id")
        if not oid:
            continue
        if row.get("status") == "closed":
            open_by_id.pop(str(oid), None)
        else:
            open_by_id[str(oid)] = row
    if open_by_id:
        # newest open by timestamp
        def _ts(r: Dict[str, Any]) -> str:
            return str(r.get("timestamp") or "")

        return max(open_by_id.values(), key=_ts)
    if newest_any and newest_any.get("stop_price"):
        return newest_any
    return None


def _price_for_pair(runner: Any, pair: str, currents: Dict[str, float]) -> float:
    if currents.get(pair, 0) > 0:
        return float(currents[pair])
    ex = getattr(runner, "exchange", None)
    if not ex:
        return 0.0
    try:
        if hasattr(ex, "get_price"):
            return float(ex.get_price(pair) or 0)
    except Exception:
        return 0.0
    return 0.0


def _resolve_stop_price(
    *,
    stop_price: Optional[float],
    entry_price: float,
    settings: Dict[str, Any],
) -> float:
    stop = float(stop_price or 0)
    if stop <= 0 and float(entry_price or 0) > 0:
        sl_pct = float(settings.get("stop_loss_pct", 0.03) or 0.03)
        stop = float(entry_price) * (1.0 - sl_pct)
    return stop


def evaluate_armed_stop_add_block(
    *,
    pair: str,
    position_usd: float,
    entry_price: float,
    current_price: float,
    stop_price: Optional[float],
    settings: Dict[str, Any],
    registry_open: bool,
) -> Optional[str]:
    """
    Gap-gated armed-stop add gate (P6-ARMED-STOP-GAP-ALLOW-20260821).

    When a bag already has an open protective stop, allow BUY adds only if
    mark-to-stop gap >= armed_allow_add_min_gap_pct (default = near_stop_min_gap).
    Blocks the near-stop race; permits long-runner pyramids with healthy cushion.

    Pure helper (no I/O). Returns block reason or None to allow.
    """
    if not settings.get("enabled", True):
        return None
    if not registry_open:
        return None
    min_pos = float(settings.get("min_position_usd", 25.0))
    if float(position_usd or 0) < min_pos:
        return None

    px = float(current_price or 0)
    entry = float(entry_price or 0)
    stop = _resolve_stop_price(stop_price=stop_price, entry_price=entry, settings=settings)
    min_gap = float(
        settings.get("armed_allow_add_min_gap_pct", settings.get("min_stop_gap_pct", 0.02))
    )

    # No mark or no stop → cannot prove cushion; keep race closed.
    if px <= 0 or stop <= 0:
        return (
            f"armed_stop_gap_unknown (px={px:.4f} stop={stop:.4f} pair={pair})"
        )

    gap_pct = (px - stop) / px
    if gap_pct < min_gap:
        return (
            f"armed_stop_gap:{gap_pct*100:.2f}%<min {min_gap*100:.2f}%"
            f" (px={px:.4f} stop={stop:.4f})"
        )
    return None


def evaluate_near_stop_add_block(
    *,
    pair: str,
    reason: str,
    position_usd: float,
    entry_price: float,
    current_price: float,
    stop_price: Optional[float],
    settings: Dict[str, Any],
) -> Optional[str]:
    """
    Return skip reason string if BUY should be blocked, else None.
    Pure helper for isolation tests (no runner I/O).
    """
    if not settings.get("enabled", True):
        return None
    reason = str(reason or "")
    reasons = settings.get("reasons") or NEAR_STOP_ADD_REASONS
    if reason not in reasons:
        return None
    if settings.get("require_existing_position", True):
        if float(position_usd or 0) < float(settings.get("min_position_usd", 25.0)):
            return None
    entry = float(entry_price or 0)
    px = float(current_price or 0)
    if px <= 0:
        return None
    stop = _resolve_stop_price(stop_price=stop_price, entry_price=entry, settings=settings)
    if stop <= 0:
        return None

    gap_pct = (px - stop) / px
    min_gap = float(settings.get("min_stop_gap_pct", 0.02))
    if gap_pct < min_gap:
        return (
            f"near_stop_gap:{gap_pct*100:.2f}%<min {min_gap*100:.2f}%"
            f" (px={px:.4f} stop={stop:.4f})"
        )

    if entry > 0:
        ur = (px - entry) / entry
        max_ur = float(settings.get("max_unrealized_pct", -0.01))
        if ur <= max_ur:
            return (
                f"near_stop_unrealized:{ur*100:.2f}%<=max {max_ur*100:.2f}%"
                f" (px={px:.4f} entry={entry:.4f})"
            )
    return None


def filter_trade_plan_near_open_stop(runner: Any, plan: Any) -> Any:
    """
    Armed stop + near-stop gate (P6-NEAR-STOP-REBALANCE-RACE + gap-allow 2026-08-21).

    Armed gate (all BUY reasons, existing bag + open registry stop):
      block only when mark-to-stop gap < armed_allow_add_min_gap_pct (or gap unknown).
      Healthy cushion → allow long-runner add (CR-03 reattaches full-bag SL after).

    Soft (legacy): for light_tilt / opportunistic reasons, also block on
    gap < min or unrealized <= max (even without registry stop).

    Stops are suspended inside rebalance context; registry "open" is the durable
    signal that the bag is a protected position for this gate.
    """
    if not getattr(plan, "actions", None):
        return plan
    settings = _near_stop_add_settings(runner)
    if not settings["enabled"]:
        return plan

    values, entries, currents = _enriched_position_maps(runner)
    kept: List[Dict[str, Any]] = []
    for a in plan.actions:
        if str(a.get("action", "")).upper() != "BUY":
            kept.append(a)
            continue
        pair = str(a.get("pair") or a.get("product_id") or "")
        if not pair:
            kept.append(a)
            continue
        reason = str(a.get("reason") or "")
        pos_usd = float(values.get(pair, 0) or 0)
        entry = float(entries.get(pair, 0) or 0)
        px = _price_for_pair(runner, pair, currents)
        reg = _latest_registry_stop_for_pair(pair)
        stop_px = None
        reg_open = bool(reg and str(reg.get("status", "open")) != "closed")
        if reg:
            try:
                stop_px = float(reg.get("stop_price") or 0) or None
            except (TypeError, ValueError):
                stop_px = None
            if entry <= 0:
                try:
                    entry = float(reg.get("entry_price") or 0)
                except (TypeError, ValueError):
                    pass

        # Gap-gated armed stop: block near-stop race; allow healthy long-runner adds.
        armed_block = evaluate_armed_stop_add_block(
            pair=pair,
            position_usd=pos_usd,
            entry_price=entry,
            current_price=px,
            stop_price=stop_px,
            settings=settings,
            registry_open=reg_open,
        )
        if armed_block:
            logger.info(
                "[ARMED-STOP] blocked %s %s $%.2f — %s (sl=%s)",
                reason or "BUY",
                pair,
                float(a.get("usd", 0) or 0),
                armed_block,
                str((reg or {}).get("sl_order_id", ""))[:8],
            )
            continue
        if reg_open and pos_usd >= float(settings.get("min_position_usd", 25.0)):
            stop_for_log = _resolve_stop_price(
                stop_price=stop_px, entry_price=entry, settings=settings
            )
            gap_log = ((px - stop_for_log) / px) if px > 0 and stop_for_log > 0 else None
            logger.info(
                "[ARMED-STOP] allow %s %s $%.2f — healthy gap%s (sl=%s stop=%.4f)",
                reason or "BUY",
                pair,
                float(a.get("usd", 0) or 0),
                f" {gap_log*100:.1f}%" if gap_log is not None else "",
                str((reg or {}).get("sl_order_id", ""))[:8],
                stop_for_log or 0.0,
            )

        block = evaluate_near_stop_add_block(
            pair=pair,
            reason=reason,
            position_usd=pos_usd,
            entry_price=entry,
            current_price=px,
            stop_price=stop_px,
            settings=settings,
        )
        if block:
            logger.info(
                "[NEAR-STOP] blocked %s %s $%.2f — %s",
                reason or "BUY",
                pair,
                float(a.get("usd", 0) or 0),
                block,
            )
            continue
        kept.append(a)
    plan.actions = kept
    return plan


def clear_manual_cash_hold_on_withdrawal(runner: Any, withdrawal_usd: float) -> None:
    hold = float(getattr(runner, "_manual_liquidation_cash_hold_usd", 0.0) or 0.0)
    if hold <= 0:
        return
    runner._manual_liquidation_cash_hold_usd = round(max(0.0, hold - abs(withdrawal_usd)), 2)
    try:
        from phase6.core.capital_controls import persist_manual_cash_hold

        persist_manual_cash_hold(runner)
    except Exception:
        pass


def detect_external_flow(
    prev: Optional[Dict[str, float]],
    current: Dict[str, float],
    min_flow: float = MIN_FLOW_USD,
) -> Tuple[float, Dict[str, float]]:
    """Returns (signed_flow_usd, deltas)."""
    if not prev:
        return 0.0, {"delta_total": 0.0, "delta_cash": 0.0, "delta_holdings": 0.0}
    d_total = current["total_usd"] - prev["total_usd"]
    d_cash = current["cash_usd"] - prev["cash_usd"]
    d_hold = current["holdings_usd"] - prev["holdings_usd"]
    flow = classify_external_flow_usd(d_total, d_cash, d_hold, min_flow=min_flow)
    return flow, {
        "delta_total": round(d_total, 2),
        "delta_cash": round(d_cash, 2),
        "delta_holdings": round(d_hold, 2),
    }


def append_runner_capital_event(record: Dict[str, Any]) -> None:
    """Durable diagnostics log (runner + shared flows audit for external flows only)."""
    RUNNER_EVENTS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, default=str)
    with RUNNER_EVENTS_JSONL.open("a") as f:
        f.write(line + "\n")
    et = record.get("event_type") or ""
    if et not in ("deposit", "withdrawal"):
        return
    # Mirror external cash flows only (not manual sells / swaps)
    try:
        flow = float(record.get("amount_usd") or record.get("flow_usd") or 0)
        if abs(flow) >= MIN_FLOW_USD:
            from phase6.core.portfolio_external_flows import _append_flow_record

            _append_flow_record(
                record.get("ts") or datetime.now(timezone.utc).isoformat(),
                flow,
                float(record.get("delta_total", flow)),
                float(record.get("delta_cash", flow)),
                float(record.get("delta_holdings", 0)),
            )
    except Exception:
        pass


def _runner_capital_settings(runner: Any) -> Dict[str, Any]:
    """Book capital-event settings: global_settings base, per-account capital_controls overlay.

    W1 personalized settings: hold/cooldown *policy* lives under
    ``trader_accounts.json`` → ``capital_controls`` (see FEAT-TRADER-PERSONALIZED-SETTINGS).
    Runtime hold **amount** stays on runner state.
    """
    gs = (getattr(runner, "config_dict", None) or {}).get("global_settings") or {}
    out = {
        "min_flow_usd": float(gs.get("capital_event_min_flow_usd", MIN_FLOW_USD)),
        "force_rebalance": bool(gs.get("capital_event_force_rebalance", True)),
        "deposit_deploy_cap_usd": float(gs.get("capital_event_deposit_deploy_cap_usd", 0.0)),
        "manual_sell_block_rebuy_hours": float(
            gs.get("capital_event_manual_sell_block_rebuy_hours", 48.0)
        ),
        "stop_loss_exchange_block_rebuy_hours": float(
            gs.get("capital_event_stop_loss_exchange_block_rebuy_hours", 72.0)
        ),
        "stop_loss_exchange_hold_cash": bool(
            gs.get("capital_event_stop_loss_exchange_hold_cash", True)
        ),
        "stop_loss_ledger_lookback_hours": float(
            gs.get("capital_event_stop_loss_ledger_lookback_hours", 48.0)
        ),
        "manual_sell_hold_cash": bool(gs.get("capital_event_manual_sell_hold_cash", True)),
        "manual_sell_cancel_stops": bool(gs.get("capital_event_manual_sell_cancel_stops", True)),
        "ledger_jsonl_path": str(
            gs.get("capital_event_ledger_jsonl_path") or TRADES_JSONL
        ),
        "capital_controls_account_id": None,
        "capital_controls_source": "global_settings",
    }
    try:
        from phase6.core.trader_account_config import capital_controls_for_runner

        cc = capital_controls_for_runner(runner)
        out["manual_sell_hold_cash"] = bool(cc.get("manual_sell_hold_cash", out["manual_sell_hold_cash"]))
        out["manual_sell_block_rebuy_hours"] = float(
            cc.get("manual_sell_block_rebuy_hours", out["manual_sell_block_rebuy_hours"])
        )
        out["stop_loss_exchange_hold_cash"] = bool(
            cc.get("stop_loss_exchange_hold_cash", out["stop_loss_exchange_hold_cash"])
        )
        out["stop_loss_exchange_block_rebuy_hours"] = float(
            cc.get(
                "stop_loss_exchange_block_rebuy_hours",
                out["stop_loss_exchange_block_rebuy_hours"],
            )
        )
        if "manual_sell_cancel_stops" in cc:
            out["manual_sell_cancel_stops"] = bool(cc["manual_sell_cancel_stops"])
        out["capital_controls_account_id"] = cc.get("account_id")
        out["capital_controls_source"] = cc.get("source") or "trader_accounts.capital_controls"
        out["ui_show_hold_banner"] = bool(cc.get("ui_show_hold_banner", True))
    except Exception as exc:
        logger.debug("[CAPITAL-EVENT] capital_controls overlay skipped: %s", exc)
    return out


def _deploy_signal_active(runner: Any) -> bool:
    """False when shadow/regime blocks deploy (usdc_hold / cap 0)."""
    try:
        from phase6.core.usdc_park_transitions import deploy_signal_active

        return deploy_signal_active(getattr(runner, "config_dict", None) or {})
    except Exception:
        gs = (getattr(runner, "config_dict", None) or {}).get("global_settings") or {}
        return float(gs.get("rebalance_cap_usd", 1) or 0) > 0


def execute_capped_deposit_deploy(runner: Any, deposit_usd: float, cap_usd: float) -> Optional[Dict[str, Any]]:
    """
    deploy_capital(source=deposit) for up to cap_usd; execute BUY deltas live only.
    """
    if getattr(runner, "shadow_mode", True):
        logger.info("[CAPITAL-EVENT] shadow — skip live deposit deploy (cap=%.2f)", cap_usd)
        return {"shadow": True, "cap_usd": cap_usd, "deposit_usd": deposit_usd}

    if not _deploy_signal_active(runner):
        logger.info("[CAPITAL-EVENT] deploy signal inactive (park/cap0) — skip immediate deposit deploy")
        return {"skipped": "deploy_signal_inactive"}

    from phase6.core.sentiment_scorer import load_sentiment_scores
    from phase6.scripts.deploy_capital import deploy_capital
    from phase6.core.allocator import TradePlan

    cash = _cash_usd_from_runner(runner)
    wr = (getattr(runner, "config_dict", None) or {}).get("withdrawal_reserve", {})
    min_reserve = float(wr.get("min_reserve_usd", 50.0))
    deployable = max(0.0, cash - min_reserve)
    deploy_amt = min(abs(deposit_usd), cap_usd, deployable)
    if deploy_amt < 50.0:
        logger.info("[CAPITAL-EVENT] deposit deploy below min_move ($%.2f)", deploy_amt)
        return {"skipped": "below_min_move", "deploy_amt": deploy_amt}

    raw_pos = getattr(runner, "portfolio", None) and runner.portfolio.get_enriched_positions() or {}
    if isinstance(raw_pos, dict) and "positions" in raw_pos:
        current_positions = raw_pos.get("positions") or raw_pos.get("value_usd") or {}
    else:
        current_positions = raw_pos or {}

    norm: Dict[str, float] = {}
    for k, v in (current_positions or {}).items():
        if isinstance(v, dict):
            norm[k] = float(v.get("value_usd", v.get("amount", 0.0)) or 0.0)
        else:
            norm[k] = float(v or 0.0)

    universe = getattr(runner, "FIXED_UNIVERSE", [])
    sentiment = load_sentiment_scores(universe=universe)
    rsi = getattr(runner, "rsi_values", {}) or {}
    # Match config block window (default 72h) — same as get_deployment_cooldown_pairs
    cooldown = list(get_deployment_cooldown_pairs(runner) or [])

    new_allocs = deploy_capital(
        current_allocations=norm,
        new_capital=deploy_amt,
        sentiment_scores=sentiment,
        source="deposit",
        candidate_pairs=list(universe),
        rsi_values=rsi,
        cooldown_pairs=cooldown,
    )

    actions: List[Dict[str, Any]] = []
    for pair, target in new_allocs.items():
        old = norm.get(pair, 0.0)
        delta = float(target) - old
        if delta >= 50.0:
            actions.append(
                {
                    "pair": pair,
                    "action": "BUY",
                    "usd": round(delta, 2),
                    "reason": "capital_event_deposit_capped",
                }
            )

    if not actions:
        return {"skipped": "no_buy_actions", "deploy_amt": deploy_amt}

    plan = TradePlan(
        actions=actions,
        new_allocations=new_allocs,
        strategy_used="capital_event_deposit",
        notes=f"deposit deploy cap={cap_usd}",
    )
    executed, skipped = runner._execute_trade_plan(plan)
    logger.info(
        "[CAPITAL-EVENT] capped deposit deploy $%.2f -> executed=%s skipped=%s",
        deploy_amt,
        executed,
        len(skipped or []),
    )
    return {
        "deploy_amt": deploy_amt,
        "executed": executed,
        "skipped": skipped,
        "actions": actions,
    }


def process_runner_capital_events(runner: Any) -> List[Dict[str, Any]]:
    """
    Call at start of each runner cycle (before _should_rebalance).

    Returns new events detected this cycle (may be empty).
    """
    settings = _runner_capital_settings(runner)
    state_path = getattr(runner, "state_file", None) or str(DEFAULT_STATE_FILE)

    try:
        from phase6.core.capital_controls import hydrate_manual_controls_from_state

        hydrate_manual_controls_from_state(runner, state_file=state_path)
    except Exception as exc:
        logger.debug("[CAPITAL] hydrate skipped: %s", exc)

    try:
        from phase6.core.capital_controls import process_capital_control_flags

        control_actions = process_capital_control_flags(runner, state_file=state_path)
        if control_actions:
            if not hasattr(runner, "_capital_events_for_decision"):
                runner._capital_events_for_decision = []
            runner._capital_events_for_decision.extend(control_actions)
    except Exception as exc:
        logger.error("[CAPITAL-CONTROL] flag processing failed: %s", exc)

    current = snapshot_nav_from_runner(runner)
    prev = load_persisted_nav_snapshot(Path(state_path))

    if prev is None:
        live = Path("data/state/phase6_live_state.json")
        if live.exists():
            try:
                st = json.loads(live.read_text())
                ab = st.get("account_balances") or {}
                cash = float(ab.get("USD", 0) or 0) + float(ab.get("USDC", 0) or 0)
                total = float(st.get("total_usd", 0) or 0)
                hold = max(0.0, total - cash)
                prev = {
                    "cash_usd": round(cash, 2),
                    "holdings_usd": round(hold, 2),
                    "total_usd": round(total, 2),
                }
                logger.info(
                    "[CAPITAL-EVENT] bootstrapped NAV baseline from live state (no event)"
                )
            except Exception:
                pass

    if not hasattr(runner, "_capital_events_for_decision"):
        runner._capital_events_for_decision = []

    detected: List[Dict[str, Any]] = []
    flow, deltas = detect_external_flow(prev, current, min_flow=settings["min_flow_usd"])

    # Manual sells/swaps: evaluate before external deposit/withdrawal (cash spike must not skip cooldown)
    disp_record: Optional[Dict[str, Any]] = None
    if prev:
        raw_pos = getattr(runner, "portfolio", None) and runner.portfolio.get_enriched_positions() or {}
        cur_pos = normalize_position_values(raw_pos)
        prev_pos = load_persisted_position_snapshot(Path(state_path))
        if not prev_pos:
            prev_pos = {}
        disp = detect_manual_disposition(
            prev_pos,
            cur_pos,
            deltas.get("delta_cash", 0.0),
            deltas.get("delta_holdings", 0.0),
            deltas.get("delta_total", 0.0),
            min_usd=settings["min_flow_usd"],
        )
        if disp:
            ts = datetime.now(timezone.utc).isoformat()
            disp_record = {
                "ts": ts,
                "source": "runner_cycle",
                "nav_before": prev,
                "nav_after": current,
                **disp,
            }
            apply_manual_disposition(runner, disp_record, settings)
            append_runner_capital_event(disp_record)
            runner._capital_events_for_decision.append(disp_record)
            detected.append(disp_record)
            logger.warning(
                "[PORTFOLIO-DISPOSITION] %s sold=%s bought=%s action=%s",
                disp["event_type"],
                disp.get("pairs_sold"),
                disp.get("pairs_bought"),
                disp_record.get("action"),
            )
            # Shadow hop would-fire log (never orders)
            try:
                from phase6.core.liquidation_redeploy_shadow import (
                    record_from_disposition_event,
                )

                record_from_disposition_event(disp_record)
            except Exception as _shadow_exc:
                logger.debug(
                    "[LIQ-REDEPLOY-SHADOW] disposition hook skipped: %s", _shadow_exc
                )
            if disp.get("event_type") in ("manual_liquidation_to_cash", "manual_crypto_swap"):
                flow = 0.0

    if abs(flow) >= settings["min_flow_usd"]:
        event_type = "deposit" if flow > 0 else "withdrawal"
        ts = datetime.now(timezone.utc).isoformat()
        event = {
            "ts": ts,
            "event_type": event_type,
            "amount_usd": round(abs(flow), 2),
            "flow_usd": round(flow, 2),
            "source": "runner_cycle",
            "nav_before": prev,
            "nav_after": current,
            **deltas,
        }
        append_runner_capital_event(event)
        runner._capital_events_for_decision.append(event)
        detected.append(event)
        logger.warning(
            "[CAPITAL-EVENT] %s $%.2f detected (cash Δ=%.2f holdings Δ=%.2f)",
            event_type,
            abs(flow),
            deltas["delta_cash"],
            deltas["delta_holdings"],
        )

        if event_type == "deposit":
            if settings["force_rebalance"]:
                runner._force_next_rebalance = True
                event["action"] = "force_rebalance_scheduled"
                logger.info("[CAPITAL-EVENT] deposit -> force rebalance this cycle")
            elif settings["deposit_deploy_cap_usd"] > 0:
                result = execute_capped_deposit_deploy(
                    runner,
                    abs(flow),
                    settings["deposit_deploy_cap_usd"],
                )
                event["immediate_deploy"] = result
                event["action"] = "capped_deposit_deploy"
        else:
            event["action"] = "logged_withdrawal"
            clear_manual_cash_hold_on_withdrawal(runner, abs(flow))

    persist_position_snapshot(
        runner,
        normalize_position_values(
            getattr(runner, "portfolio", None) and runner.portfolio.get_enriched_positions() or {}
        ),
        state_file=state_path,
    )
    persist_nav_snapshot(runner, current, state_file=state_path)
    try:
        from phase6.core.capital_controls import write_controls_status

        write_controls_status(runner, state_file=state_path)
    except Exception:
        pass
    return detected


def clear_capital_events_after_rebalance_log(runner: Any) -> None:
    """Call after decision context persisted for a rebalance."""
    runner._capital_events_for_decision = []