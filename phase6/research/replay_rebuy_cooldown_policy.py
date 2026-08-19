#!/usr/bin/env python3
"""
Replay: after sell-to-cash anchors, would rebuy have fired by T+24/48/72h?

Honest proxy (limitations in report notes):
- Anchors: capital_events manual_liquidation_to_cash + ledger SELL (stop / arch4).
- "Rebuy fired": ledger BUY on same pair in (T, T+H].
- "Rebuy blocked by cooldown": runner log lines [MANUAL-SELL] blocked auto-rebuy.
- Rebalance_history: count live rebalance cycles in window (not per-pair intent).

Does NOT reconstruct full allocator plans when no BUY and no log block.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
CAPITAL_JSONL = ROOT / "data/state/capital_events_runner.jsonl"
TRADES_JSONL = ROOT / "trades/phase6_trades.jsonl"
REBAL_JSONL = ROOT / "data/state/rebalance_history/default.jsonl"
RUNNER_LOG = ROOT / "logs/phase6_runner.log"
OUT_JSON = ROOT / "data/state/rebuy_cooldown_replay_latest.json"
OUT_MD = ROOT / "data/state/rebuy_cooldown_replay_latest.md"

WINDOWS_H = (24, 48, 72)
BLOCK_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ .* blocked auto-rebuy ([A-Z0-9]+-USD) \(\$([0-9.]+)\)"
)


def parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        s = raw.strip().replace("Z", "+00:00")
        if " " in s and "T" not in s:
            s = s.replace(" ", "T", 1)
        if "+" not in s[10:] and not s.endswith("Z"):
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(s)
    except Exception:
        return None


def load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def load_blocked_rebuys(log_path: Path) -> List[dict]:
    rows = []
    if not log_path.exists():
        return rows
    for line in log_path.read_text().splitlines():
        m = BLOCK_RE.search(line)
        if not m:
            continue
        ts = parse_ts(m.group(1))
        if not ts:
            continue
        rows.append(
            {
                "ts": ts.isoformat(),
                "pair": m.group(2),
                "usd": float(m.group(3)),
            }
        )
    return rows


@dataclass
class Anchor:
    pair: str
    t0: str
    source: str
    sold_usd: Optional[float] = None
    extra: Optional[str] = None


def collect_anchors(
    capital_events: List[dict], trades: List[dict], since: Optional[datetime] = None
) -> List[Anchor]:
    anchors: List[Anchor] = []
    seen: set = set()

    for ev in capital_events:
        if ev.get("event_type") != "manual_liquidation_to_cash":
            continue
        ts = parse_ts(str(ev.get("ts", "")))
        if not ts or (since and ts < since):
            continue
        sold = float(ev.get("sold_usd") or ev.get("cash_delta_usd") or 0)
        for pair in ev.get("pairs_sold") or []:
            key = (pair, ts.isoformat())
            if key in seen:
                continue
            seen.add(key)
            anchors.append(
                Anchor(
                    pair=pair,
                    t0=ts.isoformat(),
                    source="capital_event_manual_liquidation",
                    sold_usd=sold if len(ev.get("pairs_sold") or []) == 1 else None,
                    extra=f"multi_pair_event sold_total={sold}",
                )
            )

    sell_reasons_sl = {"stop_loss", "sl", "stoploss", "stop_loss_exchange"}
    for t in trades:
        if str(t.get("side", "")).upper() != "SELL":
            continue
        pair = t.get("pair")
        if not pair:
            continue
        reason = str(t.get("reason") or t.get("source") or "")
        if reason not in sell_reasons_sl and "stop" not in reason.lower():
            if str(t.get("source", "")) != "arch4_rebalance":
                continue
        ts = parse_ts(str(t.get("timestamp", "")))
        if not ts or (since and ts < since):
            continue
        key = (pair, ts.isoformat())
        if key in seen:
            continue
        seen.add(key)
        usd = t.get("usd_value")
        try:
            usd_f = float(usd) if usd is not None else None
        except (TypeError, ValueError):
            usd_f = None
        anchors.append(
            Anchor(
                pair=pair,
                t0=ts.isoformat(),
                source=f"ledger_sell:{reason or 'unknown'}",
                sold_usd=usd_f,
            )
        )

    anchors.sort(key=lambda a: a.t0)
    return anchors


def rebalance_cycles_in_window(
    events: List[dict], t0: datetime, hours: float
) -> int:
    end = t0 + timedelta(hours=hours)
    n = 0
    for ev in events:
        ts = parse_ts(str(ev.get("timestamp", "")))
        if not ts or ts <= t0 or ts > end:
            continue
        if ev.get("mode") == "live" and str(ev.get("reason", "")) in (
            "daily_rebalance",
            "fresh_start",
        ):
            if int(ev.get("executed", 0) or 0) >= 0:
                n += 1
    return n


def analyze(
    anchors: List[Anchor],
    trades: List[dict],
    blocked: List[dict],
    rebals: List[dict],
) -> Dict[str, Any]:
    buys_by_pair: Dict[str, List[Tuple[datetime, dict]]] = defaultdict(list)
    for t in trades:
        if str(t.get("side", "")).upper() != "BUY":
            continue
        pair = t.get("pair")
        ts = parse_ts(str(t.get("timestamp", "")))
        if pair and ts:
            buys_by_pair[pair].append((ts, t))

    blocked_parsed = []
    for b in blocked:
        ts = parse_ts(b["ts"])
        if ts:
            blocked_parsed.append((ts, b))

    per_anchor = []
    agg = {
        str(h): {
            "rebuy_ledger_buy_in_window": 0,
            "blocked_log_in_window": 0,
            "rebalance_cycles_in_window": 0,
            "neither_buy_nor_blocked": 0,
        }
        for h in WINDOWS_H
    }

    for anc in anchors:
        t0 = parse_ts(anc.t0)
        if not t0:
            continue
        row: Dict[str, Any] = {"anchor": asdict(anc), "windows": {}}
        for h in WINDOWS_H:
            end = t0 + timedelta(hours=h)
            hs = str(h)
            buys = [
                (ts, t)
                for ts, t in buys_by_pair.get(anc.pair, [])
                if t0 < ts <= end
            ]
            blocks = [
                b
                for ts, b in blocked_parsed
                if b["pair"] == anc.pair and t0 < ts <= end
            ]
            cycles = rebalance_cycles_in_window(rebals, t0, h)
            fired = len(buys) > 0
            blocked_hit = len(blocks) > 0
            row["windows"][str(h)] = {
                "rebalance_cycles": cycles,
                "ledger_buys": [
                    {
                        "ts": ts.isoformat(),
                        "usd": t.get("usd_value"),
                        "source": t.get("source"),
                        "reason": t.get("reason"),
                    }
                    for ts, t in buys
                ],
                "blocked_log": blocks,
                "would_have_rebuy_signal": fired or blocked_hit,
            }
            if fired:
                agg[hs]["rebuy_ledger_buy_in_window"] += 1
            if blocked_hit:
                agg[hs]["blocked_log_in_window"] += 1
            agg[hs]["rebalance_cycles_in_window"] += cycles
            if not fired and not blocked_hit:
                agg[hs]["neither_buy_nor_blocked"] += 1
        per_anchor.append(row)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "windows_hours": list(WINDOWS_H),
        "anchor_count": len(anchors),
        "notes": [
            "Anchors from capital_events (inferred manual liquidation) and ledger SELL (stops/arch4).",
            "would_have_rebuy_signal = ledger BUY or log-confirmed cooldown block in (T, T+H].",
            "Silent windows do not prove allocator would not have bought — logging gap (no per-pair plan in rebalance_history).",
            "Policy default under test: 72h block; this replay measures overlap with actual/blocked rebuys, not counterfactual RSI.",
        ],
        "aggregate_by_window": agg,
        "anchors": per_anchor,
    }


def render_md(report: Dict[str, Any]) -> str:
    lines = [
        "# Rebuy cooldown replay (T+24 / 48 / 72h)",
        f"Generated: {report['generated_at']}",
        f"Anchors: {report['anchor_count']}",
        "",
        "## Aggregate (per anchor, first hit in window)",
        "| Window | Ledger BUY | Log blocked | No signal |",
        "|--------|------------|-------------|-----------|",
    ]
    for h in WINDOWS_H:
        a = report["aggregate_by_window"][str(h)]
        lines.append(
            f"| +{h}h | {a['rebuy_ledger_buy_in_window']} | {a['blocked_log_in_window']} | {a['neither_buy_nor_blocked']} |"
        )
    lines.extend(["", "## Notes", ""])
    for n in report["notes"]:
        lines.append(f"- {n}")
    lines.extend(["", "## Notable anchors (blocked or BUY within 72h)", ""])
    for row in report["anchors"]:
        w72 = row["windows"].get("72", {})
        if not w72.get("ledger_buys") and not w72.get("blocked_log"):
            continue
        a = row["anchor"]
        lines.append(f"### {a['pair']} @ {a['t0'][:19]} ({a['source']})")
        for h in WINDOWS_H:
            w = row["windows"][str(h)]
            if w["ledger_buys"]:
                lines.append(f"- +{h}h BUY: {w['ledger_buys']}")
            if w["blocked_log"]:
                lines.append(f"- +{h}h blocked: {w['blocked_log']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    since = datetime(2026, 7, 1, tzinfo=timezone.utc)
    capital = load_jsonl(CAPITAL_JSONL)
    trades = load_jsonl(TRADES_JSONL)
    rebals = load_jsonl(REBAL_JSONL)
    blocked = load_blocked_rebuys(RUNNER_LOG)

    anchors = collect_anchors(capital, trades, since=since)
    report = analyze(anchors, trades, blocked, rebals)
    unique_blocks = len({(b["ts"], b["pair"]) for b in blocked})
    report["unique_blocked_log_events"] = unique_blocks
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2))
    OUT_MD.write_text(render_md(report))
    print(json.dumps({k: report[k] for k in ("anchor_count", "aggregate_by_window", "notes")}, indent=2))
    print(f"Wrote {OUT_JSON} and {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())