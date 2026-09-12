"""
Exit stack proof packet (PC-02).

Inventory live vs shadow exit layers + ledger RT bank (TP vs SL) + disposition honesty.
Measure-only — never flips live knobs.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT

SCHEMA = "exit_stack_proof_v1"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "exit_stack_proof_latest.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "EXIT_STACK_PROOF_LATEST.md"
LEDGER_PATH = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
EXIT_CFG_PATH = PROJECT_ROOT / "config" / "exit_automation.json"
REGIME_POLICY_PATH = PROJECT_ROOT / "config" / "regime_cash_policy.json"
TRADING_CFG_PATH = PROJECT_ROOT / "config" / "trading_config_phase6.json"
REGIME_EXIT_MAP_PATH = PROJECT_ROOT / "config" / "regime_exit_policy_map.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _pnl(row: Mapping[str, Any]) -> float:
    for k in ("pnl", "realized_pnl", "pnl_usd"):
        if row.get(k) is not None:
            try:
                return float(row[k])
            except (TypeError, ValueError):
                continue
    return 0.0


def classify_exit_reason(row: Mapping[str, Any]) -> str:
    """Disposition taxonomy for RT scoreboard (honest buckets)."""
    reason = str(
        row.get("reason") or row.get("exit_reason") or row.get("done_reason") or ""
    ).strip()
    r = reason.lower()
    if not r:
        return "blank_untagged"
    if any(k in r for k in ("stop_loss", "stop-loss", "exchange_stop", "sl_hit", "sl_")):
        return "sl_exchange"
    if "dust_sweep" in r:
        return "dust_sweep"
    if any(k in r for k in ("take_profit", "fixed_tp", "trail")):
        return "tp_profit"
    if "dual_peak" in r or "lifecycle_dual_peak" in r:
        return "dual_peak"
    if "lifecycle_extension" in r or "extension_partial" in r:
        return "lifecycle_partial"
    if "hard_exit" in r or "regime_hard_exit" in r:
        return "hard_exit"
    if "rotation" in r:
        return "rotation"
    if "operator" in r or "manual" in r or "preserve_disarm" in r:
        return "operator_manual"
    if "test_cleanup" in r or "cleanup" in r:
        return "test_cleanup"
    return "other"


def is_process_tax_exit(bucket: str) -> bool:
    return bucket in {"sl_exchange", "dust_sweep"}


def load_ledger_rows(path: Path = LEDGER_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


@dataclass
class WindowBank:
    days: int
    n_sell: int = 0
    n_buy: int = 0
    by_bucket: Dict[str, int] = field(default_factory=dict)
    pnl_by_bucket: Dict[str, float] = field(default_factory=dict)
    tp_bank_usd: float = 0.0
    sl_bank_usd: float = 0.0
    process_tax_usd: float = 0.0
    other_pnl_usd: float = 0.0
    net_pnl_usd: float = 0.0
    blank_untagged: int = 0
    tp_vs_sl_count: str = ""
    pairs_sl: List[str] = field(default_factory=list)
    pairs_tp: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["by_bucket"] = dict(sorted((self.by_bucket or {}).items(), key=lambda kv: (-kv[1], kv[0])))
        d["pnl_by_bucket"] = {k: round(v, 4) for k, v in sorted((self.pnl_by_bucket or {}).items())}
        d["tp_bank_usd"] = round(self.tp_bank_usd, 4)
        d["sl_bank_usd"] = round(self.sl_bank_usd, 4)
        d["process_tax_usd"] = round(self.process_tax_usd, 4)
        d["other_pnl_usd"] = round(self.other_pnl_usd, 4)
        d["net_pnl_usd"] = round(self.net_pnl_usd, 4)
        return d


def score_window(
    rows: Sequence[Mapping[str, Any]],
    *,
    days: int,
    now: Optional[datetime] = None,
) -> WindowBank:
    now = now or _utc_now()
    since = now - timedelta(days=int(days))
    bank = WindowBank(days=int(days))
    sl_pairs: Counter = Counter()
    tp_pairs: Counter = Counter()
    for row in rows:
        ts = _parse_ts(row.get("timestamp") or row.get("ts") or row.get("created_at"))
        if ts is None or ts < since:
            continue
        side = str(row.get("side") or row.get("action") or "").upper()
        if side == "BUY":
            bank.n_buy += 1
            continue
        if side != "SELL":
            continue
        bank.n_sell += 1
        bucket = classify_exit_reason(row)
        pnl = _pnl(row)
        bank.by_bucket[bucket] = bank.by_bucket.get(bucket, 0) + 1
        bank.pnl_by_bucket[bucket] = bank.pnl_by_bucket.get(bucket, 0.0) + pnl
        bank.net_pnl_usd += pnl
        pair = str(row.get("pair") or "").upper()
        if bucket == "blank_untagged":
            bank.blank_untagged += 1
        if bucket == "tp_profit":
            bank.tp_bank_usd += pnl
            if pair:
                tp_pairs[pair] += 1
        elif bucket == "sl_exchange":
            bank.sl_bank_usd += pnl
            if pair:
                sl_pairs[pair] += 1
        if is_process_tax_exit(bucket):
            bank.process_tax_usd += pnl
        else:
            bank.other_pnl_usd += pnl
    n_tp = bank.by_bucket.get("tp_profit", 0)
    n_sl = bank.by_bucket.get("sl_exchange", 0)
    bank.tp_vs_sl_count = f"{n_tp}:{n_sl}"
    bank.pairs_sl = [p for p, _ in sl_pairs.most_common(8)]
    bank.pairs_tp = [p for p, _ in tp_pairs.most_common(8)]
    return bank


def inventory_exit_layers(
    *,
    exit_cfg: Optional[Mapping[str, Any]] = None,
    regime_policy: Optional[Mapping[str, Any]] = None,
    trading_cfg: Optional[Mapping[str, Any]] = None,
    regime_exit_map: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    exit_cfg = exit_cfg if exit_cfg is not None else _read_json(EXIT_CFG_PATH)
    regime_policy = regime_policy if regime_policy is not None else _read_json(REGIME_POLICY_PATH)
    trading_cfg = trading_cfg if trading_cfg is not None else _read_json(TRADING_CFG_PATH)
    regime_exit_map = regime_exit_map if regime_exit_map is not None else _read_json(REGIME_EXIT_MAP_PATH)

    tp = (exit_cfg or {}).get("take_profit") or {}
    he = (regime_policy or {}).get("hard_exit") or {}
    life = (trading_cfg or {}).get("run_lifecycle") or {}
    dp = life.get("dual_peak_exit") or (trading_cfg or {}).get("dual_peak_exit") or {}
    map_live = bool((regime_exit_map or {}).get("live_apply"))

    layers = [
        {
            "layer": "stop_loss_exchange",
            "role": "cap ~3% loss from bag entry",
            "state": "live",
            "live_orders": True,
            "notes": "Exchange SL + A1 settle/naked-bag fail-closed",
        },
        {
            "layer": "take_profit_trail_fixed",
            "role": "bank trail after arm / fixed +6% fallback",
            "state": str(tp.get("mode") or "off"),
            "live_orders": bool(str(tp.get("mode") or "").lower() == "live" and tp.get("live_market_exit")),
            "live_attach_on_buy": bool(tp.get("live_attach_on_buy")),
            "live_market_exit": bool(tp.get("live_market_exit")),
            "fixed_tp_pct": tp.get("fixed_tp_pct"),
            "trail": tp.get("trail"),
            "auto_promote": bool(((exit_cfg or {}).get("promotion") or {}).get("auto_promote")),
            "notes": str(tp.get("note") or "")[:200],
        },
        {
            "layer": "hard_exit_rsi_sent",
            "role": "RSI overbought / weak-sent dump vs ride-to-SL",
            "state": (
                "live_cautious_flat"
                if bool(he.get("enabled"))
                and bool((he.get("cautious_flat") or {}).get("enabled"))
                and not bool(he.get("shadow_only") and not (he.get("cautious_flat") or {}).get("enabled"))
                else ("shadow" if he.get("shadow_only") or he.get("operator_approve") else "configured")
            ),
            "enabled": bool(he.get("enabled")),
            "shadow_only": bool(he.get("shadow_only")),
            "live_apply": bool(he.get("live_apply")),
            "operator_approve": bool(he.get("operator_approve")),
            "cautious_flat": he.get("cautious_flat") or {},
            "notes": str(he.get("note") or "")[:200],
        },
        {
            "layer": "dual_peak_lifecycle",
            "role": "run-lifecycle failed-high / MFE stall trim",
            "state": str(dp.get("mode") or ("off" if not dp.get("enabled") else "unknown")),
            "enabled": bool(dp.get("enabled")),
            "extension_partial_live": bool(dp.get("extension_partial_live")),
            "extension_partial_shadow": bool(dp.get("extension_partial_shadow")),
            "notes": str(dp.get("note") or "")[:200],
        },
        {
            "layer": "regime_exit_map",
            "role": "per-regime shadow knobs (not global TP)",
            "state": "live" if map_live else "shadow",
            "live_apply": map_live,
            "notes": "Global trail/fixed live via exit_automation; map stays shadow unless live_apply",
        },
    ]
    return layers


def disposition_honesty(windows: Mapping[str, WindowBank]) -> Dict[str, Any]:
    """Flag untagged / ambiguous exit tags that break trust SOP."""
    issues: List[str] = []
    w30 = windows.get("30d") or windows.get("d30")
    w7 = windows.get("7d") or windows.get("d7")
    for label, w in (("7d", w7), ("30d", w30)):
        if w is None:
            continue
        if w.n_sell and w.blank_untagged / max(w.n_sell, 1) >= 0.05:
            issues.append(
                f"{label}: blank_untagged {w.blank_untagged}/{w.n_sell} "
                f"({100.0 * w.blank_untagged / w.n_sell:.1f}%) — tag gap"
            )
        # dual_peak counted separate from tp — good; warn if dual_peak massive vs tp with no clarity
        dp = w.by_bucket.get("dual_peak", 0)
        tp = w.by_bucket.get("tp_profit", 0)
        if dp and not tp and w.n_sell >= 5:
            issues.append(f"{label}: dual_peak={dp} with tp_profit=0 — confirm lifecycle not mislabeled as TP bank")
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "taxonomy": [
            "sl_exchange",
            "tp_profit",
            "dual_peak",
            "lifecycle_partial",
            "hard_exit",
            "rotation",
            "operator_manual",
            "dust_sweep",
            "blank_untagged",
            "other",
        ],
    }


def decide_go_nogo(
    layers: Sequence[Mapping[str, Any]],
    windows: Mapping[str, WindowBank],
    honesty: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Explicit go/no-go for further live exit knob flips.
    Does NOT recommend flipping without Brad — defaults conservative.
    """
    tp_layer = next((L for L in layers if L.get("layer") == "take_profit_trail_fixed"), {})
    he_layer = next((L for L in layers if L.get("layer") == "hard_exit_rsi_sent"), {})
    w30 = windows.get("30d")
    w7 = windows.get("7d")

    decisions: Dict[str, Any] = {
        "take_profit_live_keep": {
            "decision": "KEEP_AS_IS",
            "go": None,
            "detail": (
                f"Already mode={tp_layer.get('state')}, live_market_exit={tp_layer.get('live_market_exit')}; "
                f"auto_promote={tp_layer.get('auto_promote')}. No silent flip."
            ),
        },
        "hard_exit_global_auto": {
            "decision": "NO-GO",
            "go": False,
            "detail": (
                f"operator_approve={he_layer.get('operator_approve')}, "
                f"live_apply={he_layer.get('live_apply')}, shadow_only={he_layer.get('shadow_only')}. "
                "Need clear CF edge vs ride-to-SL + Brad GO before global auto."
            ),
        },
        "hard_exit_cautious_flat": {
            "decision": "KEEP_AS_IS",
            "go": None,
            "detail": "Cautious flat path already staged; do not widen regimes without evidence.",
        },
        "live_attach_on_buy_h2": {
            "decision": "NO-GO",
            "go": False,
            "detail": f"live_attach_on_buy={tp_layer.get('live_attach_on_buy')} — wired default false; software market exit primary.",
        },
    }

    # Process tax pressure
    tax_note = ""
    if w30 and w30.n_sell:
        sl_n = w30.by_bucket.get("sl_exchange", 0)
        tp_n = w30.by_bucket.get("tp_profit", 0)
        tax_note = (
            f"30d SL bank ${w30.sl_bank_usd:.2f} (n={sl_n}) vs TP bank ${w30.tp_bank_usd:.2f} (n={tp_n}); "
            f"process_tax_usd={w30.process_tax_usd:.2f}; net={w30.net_pnl_usd:.2f}."
        )
        if sl_n > max(tp_n * 5, 10) and w30.sl_bank_usd < -1:
            decisions["process_tax_pressure"] = {
                "decision": "WATCH",
                "go": None,
                "detail": tax_note + " SL-heavy — exit quality still the tax engine; no new aggressive exit flips.",
            }
        else:
            decisions["process_tax_pressure"] = {
                "decision": "WATCH",
                "go": None,
                "detail": tax_note,
            }
    if w7:
        decisions["window_7d"] = {
            "decision": "INFO",
            "go": None,
            "detail": (
                f"7d sells={w7.n_sell} tp:sl={w7.tp_vs_sl_count} "
                f"tp_bank=${w7.tp_bank_usd:.2f} sl_bank=${w7.sl_bank_usd:.2f}"
            ),
        }

    if not honesty.get("ok"):
        decisions["disposition_tags"] = {
            "decision": "FIX_FIRST",
            "go": False,
            "detail": "; ".join(honesty.get("issues") or []) or "tag gaps",
        }
    else:
        decisions["disposition_tags"] = {
            "decision": "OK",
            "go": True,
            "detail": "blank/ambiguous tags within tolerance",
        }

    # Headline
    any_nogo = any(v.get("go") is False for v in decisions.values())
    headline = "NO-GO further live exit knob expansion without Brad"
    if tp_layer.get("live_orders") and not any_nogo:
        headline = "TP live KEEP; no further exit flips without Brad GO"
    return {
        "headline": headline,
        "any_hard_nogo": any_nogo,
        "brad_required_for_any_live_flip": True,
        "decisions": decisions,
    }


def build_exit_stack_proof(
    *,
    rows: Optional[Sequence[Mapping[str, Any]]] = None,
    exit_cfg: Optional[Mapping[str, Any]] = None,
    regime_policy: Optional[Mapping[str, Any]] = None,
    trading_cfg: Optional[Mapping[str, Any]] = None,
    regime_exit_map: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
    write: bool = False,
) -> Dict[str, Any]:
    now = now or _utc_now()
    rows = list(rows if rows is not None else load_ledger_rows())
    layers = inventory_exit_layers(
        exit_cfg=exit_cfg,
        regime_policy=regime_policy,
        trading_cfg=trading_cfg,
        regime_exit_map=regime_exit_map,
    )
    w7 = score_window(rows, days=7, now=now)
    w30 = score_window(rows, days=30, now=now)
    windows = {"7d": w7, "30d": w30}
    honesty = disposition_honesty(windows)
    verdict = decide_go_nogo(layers, windows, honesty)

    payload = {
        "schema": SCHEMA,
        "as_of_utc": now.astimezone(timezone.utc).isoformat(),
        "layers": layers,
        "windows": {"7d": w7.to_dict(), "30d": w30.to_dict()},
        "disposition_honesty": honesty,
        "go_nogo": verdict,
        "plain_english": (
            f"{verdict.get('headline')}. "
            f"30d TP bank ${w30.tp_bank_usd:.2f} (n={w30.by_bucket.get('tp_profit', 0)}) vs "
            f"SL bank ${w30.sl_bank_usd:.2f} (n={w30.by_bucket.get('sl_exchange', 0)}). "
            f"Blank tags 30d: {w30.blank_untagged}/{w30.n_sell}."
        ),
        "links": {
            "exit_automation": str(EXIT_CFG_PATH),
            "hard_exit": "config/regime_cash_policy.json → hard_exit",
            "gated_master": "P6-EXIT-PROFIT-LIVE-GATES-20260807",
            "prior_scoreboard": "reports/EXIT_PROMOTE_SCOREBOARD_LATEST.md",
        },
        "actions_taken": [
            "pc02_exit_stack_proof_builder",
            "measure_only — no live knob flips",
        ],
    }
    if write:
        write_artifacts(payload)
    return payload


def render_markdown(payload: Mapping[str, Any]) -> str:
    g = payload.get("go_nogo") or {}
    lines = [
        f"# Exit stack proof — {payload.get('as_of_utc', '')}",
        "",
        f"**Headline:** {g.get('headline')}",
        "",
        f"> {payload.get('plain_english', '')}",
        "",
        "## Live vs shadow inventory",
        "",
        "| Layer | State | Live orders | Notes |",
        "|-------|-------|-------------|-------|",
    ]
    for L in payload.get("layers") or []:
        notes = str(L.get("notes") or "").replace("|", "/")[:80]
        lines.append(
            f"| {L.get('layer')} | {L.get('state')} | {L.get('live_orders', L.get('live_apply', '—'))} | {notes} |"
        )
    lines.extend(["", "## Ledger RT banks", ""])
    for key in ("7d", "30d"):
        w = (payload.get("windows") or {}).get(key) or {}
        lines.append(f"### {key}")
        lines.append(
            f"- sells={w.get('n_sell')} buys={w.get('n_buy')} · tp:sl counts={w.get('tp_vs_sl_count')}"
        )
        lines.append(
            f"- TP bank `${w.get('tp_bank_usd')}` · SL bank `${w.get('sl_bank_usd')}` · "
            f"process_tax `${w.get('process_tax_usd')}` · net `${w.get('net_pnl_usd')}`"
        )
        lines.append(f"- buckets: `{w.get('by_bucket')}`")
        lines.append("")
    hon = payload.get("disposition_honesty") or {}
    lines.extend(
        [
            "## Disposition honesty",
            f"- ok: `{hon.get('ok')}`",
            f"- issues: {hon.get('issues') or []}",
            "",
            "## Go / no-go packet",
            f"- brad_required_for_any_live_flip: `{g.get('brad_required_for_any_live_flip')}`",
            "",
        ]
    )
    for name, dec in (g.get("decisions") or {}).items():
        lines.append(f"- **{name}**: `{dec.get('decision')}` — {dec.get('detail')}")
    lines.extend(
        [
            "",
            "## Must not",
            "- Flip live TP/hard_exit without Brad GO",
            "- Claim CF without stops as edge",
            "- Treat would-fire tick spam as N",
            "",
        ]
    )
    return "\n".join(lines)


def write_artifacts(
    payload: Mapping[str, Any],
    *,
    state_path: Path = STATE_PATH,
    report_path: Path = REPORT_PATH,
) -> Dict[str, str]:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    report_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": str(state_path), "md": str(report_path)}


def build_live_exit_stack_proof(*, write: bool = True) -> Dict[str, Any]:
    return build_exit_stack_proof(write=write)
