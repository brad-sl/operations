#!/usr/bin/env python3
"""7-day anomaly monitor for the four tryout money arms (Brad GO 2026-10-01).

Measure + TG on anomaly only. Never flips knobs. Kill files still operator.
Quiet stdout when clean (Hermes no_agent friendly).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

STATE = ROOT / "data" / "state"
CONFIG = ROOT / "config" / "tryout_money_arms_monitor.json"
LATEST = STATE / "tryout_money_arms_monitor_latest.json"
CRUMBS = STATE / "tryout_money_arms_monitor_crumbs.jsonl"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    d = dt or _utc_now()
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.isoformat()


def _load_json(path: Path, default: Any = None) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")


def _append_crumb(row: Dict[str, Any]) -> None:
    CRUMBS.parent.mkdir(parents=True, exist_ok=True)
    with CRUMBS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
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
        return dt
    except Exception:
        return None


def _today_utc() -> str:
    return _utc_now().strftime("%Y-%m-%d")


def _count_jsonl_kind_today(path: Path, kinds: List[str], ts_key: str = "ts") -> int:
    if not path.is_file():
        return 0
    want = set(kinds)
    day = _today_utc()
    n = 0
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if str(row.get("kind") or "") not in want:
                continue
            ts = _parse_ts(row.get(ts_key))
            if ts is None:
                continue
            if ts.astimezone(timezone.utc).strftime("%Y-%m-%d") == day:
                n += 1
    except Exception:
        return n
    return n


def load_cfg() -> Dict[str, Any]:
    raw = _load_json(CONFIG, {})
    return raw if isinstance(raw, dict) else {}


def arm_status() -> Dict[str, Any]:
    from phase6.core.tryout_scale_window import load_cfg as sw_cfg, kill_switch_on as sw_kill
    from phase6.core.tryout_decision_discipline import load_config as disc_cfg
    from phase6.core.knife_filter_shadow import load_knife_live_config, knife_live_kill_on
    from phase6.core.tryout_scale_up_ladder import autonomous_apply_allowed, status_plain, load_ladder
    from phase6.core.tryout_scale_up_live import is_live_armed, kill_switch_on as su_kill, load_decision

    sw = sw_cfg()
    disc = disc_cfg()
    knife = load_knife_live_config()
    ladder = load_ladder()
    return {
        "scale_window": {
            "live_apply": bool(sw.get("live_apply")),
            "kill": sw_kill(),
            "cooloff_h": sw.get("post_eject_pair_cooloff_hours"),
        },
        "scale_up": {
            "decision_live_apply": is_live_armed(load_decision()),
            "kill": su_kill(),
            "ladder": status_plain(),
            "autonomous_apply": autonomous_apply_allowed(ladder),
            "force_armed": bool(ladder.get("force_armed_by_brad")),
        },
        "discipline": {
            "live_apply": bool(disc.get("live_apply")),
        },
        "knife": {
            "live_gate": bool(knife.get("live_gate")) and not knife_live_kill_on(),
            "primary_arm": knife.get("primary_arm"),
            "kill": knife_live_kill_on(),
        },
    }


def collect_anomalies(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    thr = cfg.get("anomaly_thresholds") if isinstance(cfg.get("anomaly_thresholds"), dict) else {}
    anomalies: List[Dict[str, Any]] = []

    # Auto eject volume
    max_eject = int(thr.get("max_auto_ejects_per_utc_day") or 4)
    n_eject = _count_jsonl_kind_today(
        STATE / "tryout_scale_window_crumbs.jsonl", ["auto_eject", "eject"]
    )
    if n_eject > max_eject:
        anomalies.append(
            {
                "code": "auto_eject_burst",
                "severity": "high",
                "detail": f"eject_events_today={n_eject} > {max_eject}",
            }
        )

    # Kindling apply volume
    max_kindle = int(thr.get("max_kindling_steps_per_utc_day") or 2)
    n_kindle = _count_jsonl_kind_today(
        STATE / "tryout_scale_up_live_crumbs.jsonl",
        ["live_apply", "apply", "auto_apply"],
    )
    # also check apply latest
    apply_latest = _load_json(STATE / "tryout_scale_up_live_apply_latest.json", {})
    if isinstance(apply_latest, dict):
        ts = _parse_ts(apply_latest.get("as_of") or apply_latest.get("ts"))
        if ts and ts.astimezone(timezone.utc).strftime("%Y-%m-%d") == _today_utc():
            n_kindle = max(n_kindle, int(apply_latest.get("n_applied") or 0))
    if n_kindle > max_kindle:
        anomalies.append(
            {
                "code": "kindling_burst",
                "severity": "high",
                "detail": f"kindling_steps_today={n_kindle} > {max_kindle}",
            }
        )

    # Ghosts
    try:
        from phase6.core.tryout_seat_ledger import build_seat_ledger

        led = build_seat_ledger()
        n_ghosts = int(led.get("n_ghosts") or 0)
        max_g = int(thr.get("max_ghosts") or 2)
        if n_ghosts > max_g:
            anomalies.append(
                {
                    "code": "ghost_tax",
                    "severity": "med",
                    "detail": f"ghosts={n_ghosts} > {max_g} pairs={led.get('ghosts')}",
                }
            )
    except Exception as e:
        anomalies.append(
            {"code": "ledger_error", "severity": "med", "detail": str(e)[:160]}
        )

    # Cooloff breach: open lot on cooloff pair
    cool = _load_json(STATE / "tryout_scale_window_cooloff.json", {})
    lots = _load_json(STATE / "tryout_scale_up_open_lots.json", {})
    open_pairs = set()
    if isinstance(lots, dict):
        for k, v in (lots.get("lots") or lots or {}).items() if isinstance(lots.get("lots"), dict) else []:
            if isinstance(v, dict) and str(v.get("status") or "").startswith("tryout"):
                open_pairs.add(str(k).upper())
        # alternate shape: list
        if isinstance(lots.get("lots"), list):
            for v in lots["lots"]:
                if isinstance(v, dict):
                    open_pairs.add(str(v.get("pair") or "").upper())
    if isinstance(cool, dict):
        pairs_cool = cool.get("pairs") if isinstance(cool.get("pairs"), dict) else cool
        if isinstance(pairs_cool, dict):
            now = _utc_now()
            for pair, meta in pairs_cool.items():
                pn = str(pair).upper().replace("_", "-")
                until = None
                if isinstance(meta, dict):
                    until = _parse_ts(meta.get("until") or meta.get("expires_at"))
                elif isinstance(meta, str):
                    until = _parse_ts(meta)
                if until and until > now and pn in open_pairs:
                    anomalies.append(
                        {
                            "code": "cooloff_breach_open",
                            "severity": "high",
                            "detail": f"{pn} open while cooloff until {until.isoformat()}",
                        }
                    )

    # Arm drift: expected ON but off
    arms = arm_status()
    if cfg.get("arms", {}).get("scale_window_auto_eject") and not arms["scale_window"]["live_apply"]:
        anomalies.append(
            {
                "code": "arm_drift_scale_window_off",
                "severity": "high",
                "detail": "expected live_apply ON",
            }
        )
    if cfg.get("arms", {}).get("decision_discipline_live") and not arms["discipline"]["live_apply"]:
        anomalies.append(
            {
                "code": "arm_drift_discipline_off",
                "severity": "high",
                "detail": "expected discipline live_apply ON",
            }
        )
    if cfg.get("arms", {}).get("knife_live_gate") and not arms["knife"]["live_gate"]:
        anomalies.append(
            {
                "code": "arm_drift_knife_off",
                "severity": "high",
                "detail": "expected knife live_gate ON (or kill file present)",
            }
        )
    if cfg.get("arms", {}).get("scale_up_kindling_auto") and not arms["scale_up"]["autonomous_apply"]:
        anomalies.append(
            {
                "code": "arm_drift_scale_up_auto_off",
                "severity": "high",
                "detail": f"expected autonomous_apply ON · {arms['scale_up']['ladder']}",
            }
        )

    # Naked SL check on tryout shells if helper available
    if thr.get("flag_naked_sl", True):
        try:
            from phase6.core.tryout_seat_ledger import build_seat_ledger

            led = build_seat_ledger()
            shells = list(led.get("open_shells") or [])
            # lightweight: if monitor_reentry state flags missing stops
            sl_state = _load_json(STATE / "sl_tp_monitor_latest.json", {}) or _load_json(
                STATE / "monitor_reentry_sl_tp_latest.json", {}
            )
            if isinstance(sl_state, dict):
                missing = sl_state.get("missing") or sl_state.get("naked") or sl_state.get("pairs_missing_sl")
                if isinstance(missing, list):
                    hit = [p for p in missing if str(p).upper() in {s.upper() for s in shells}]
                    if hit:
                        anomalies.append(
                            {
                                "code": "naked_sl_tryout",
                                "severity": "critical",
                                "detail": f"tryout shells missing SL: {hit}",
                            }
                        )
        except Exception:
            pass

    return anomalies


def run_monitor(*, force_telegram: bool = False) -> Dict[str, Any]:
    cfg = load_cfg()
    now = _utc_now()
    until = _parse_ts(cfg.get("monitor_until"))
    expired = bool(until and now > until)
    arms = arm_status()
    anomalies = [] if expired or not cfg.get("enabled", True) else collect_anomalies(cfg)

    # Board snapshot
    board = _load_json(STATE / "tryout_scale_window_latest.json", {})
    disc = _load_json(STATE / "tryout_decision_discipline_latest.json", {})
    knife_live = _load_json(STATE / "knife_filter_live_gate_latest.json", {})

    if expired:
        plain = "money-arms monitor EXPIRED — quiet"
    elif not anomalies:
        plain = (
            f"money-arms OK · anomalies=0 · sw={arms['scale_window']['live_apply']} "
            f"su_auto={arms['scale_up']['autonomous_apply']} "
            f"disc={arms['discipline']['live_apply']} knife={arms['knife']['live_gate']}"
        )
    else:
        bits = "; ".join(f"{a['code']}:{a['detail']}" for a in anomalies[:6])
        plain = f"money-arms ANOMALY n={len(anomalies)} · {bits}"
    payload = {
        "schema": "tryout_money_arms_monitor_v1",
        "as_of": _iso(now),
        "enabled": bool(cfg.get("enabled", True)),
        "expired": expired,
        "monitor_until": cfg.get("monitor_until"),
        "arms": arms,
        "n_anomalies": len(anomalies),
        "anomalies": anomalies,
        "board_n_would_eject": (board or {}).get("n_would_eject") if isinstance(board, dict) else None,
        "discipline_last": (disc or {}).get("last_triple") if isinstance(disc, dict) else None,
        "knife_last": {
            "pair": (knife_live or {}).get("pair"),
            "allow": (knife_live or {}).get("allow"),
            "reason": (knife_live or {}).get("reason"),
        }
        if isinstance(knife_live, dict)
        else None,
        "plain_english": plain,
    }
    _write_json(LATEST, payload)
    _append_crumb(
        {
            "kind": "monitor_tick",
            "ts": payload["as_of"],
            "n_anomalies": payload["n_anomalies"],
            "expired": expired,
            "codes": [a.get("code") for a in anomalies],
        }
    )
    return payload


def telegram_body(payload: Dict[str, Any], *, force: bool = False) -> str:
    if payload.get("expired"):
        return ""
    n = int(payload.get("n_anomalies") or 0)
    if n <= 0 and not force:
        return ""
    lines = [
        "TRYOUT MONEY-ARMS MONITOR",
        f"as_of={payload.get('as_of')} · anomalies={n}",
        f"until={payload.get('monitor_until')}",
    ]
    arms = payload.get("arms") or {}
    sw = arms.get("scale_window") or {}
    su = arms.get("scale_up") or {}
    disc = arms.get("discipline") or {}
    knife = arms.get("knife") or {}
    lines.append(
        f"arms: sw_live={sw.get('live_apply')} kill={sw.get('kill')} · "
        f"su_auto={su.get('autonomous_apply')} · disc={disc.get('live_apply')} · "
        f"knife={knife.get('live_gate')} arm={knife.get('primary_arm')}"
    )
    for a in payload.get("anomalies") or []:
        lines.append(f"  · [{a.get('severity')}] {a.get('code')}: {a.get('detail')}")
    if n <= 0 and force:
        lines.append("  · (forced ping — clean)")
    lines.append(f"latest: {LATEST}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tryout money-arms 7d anomaly monitor")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--telegram", action="store_true", help="Print TG body only if anomalies")
    ap.add_argument("--force-telegram", action="store_true")
    args = ap.parse_args()
    payload = run_monitor(force_telegram=bool(args.force_telegram))
    if args.telegram or args.force_telegram:
        body = telegram_body(payload, force=bool(args.force_telegram))
        if body:
            print(body)
        return 0
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(payload.get("plain_english"))
        for a in payload.get("anomalies") or []:
            print(f"  [{a.get('severity')}] {a.get('code')}: {a.get('detail')}")
    return 0 if int(payload.get("n_anomalies") or 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
