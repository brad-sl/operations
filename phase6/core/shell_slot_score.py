"""Evening shell-slot scorecard. Measure-only. No knobs, no orders.

Scores the natural 21:00 X + ~21:05 rebalance window against the current
tryout shell. Used for the 2026-09-24..26 three-slot proof (Brad GO).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
STABLE = frozenset({"USD", "USDC", "USDT", "DAI", "PAXG-USD", "PAXG"})
WINDOW_DATES = ("2026-09-24", "2026-09-25", "2026-09-26")
SLOT_HHMM = "21:00"
DUST_NOTIONAL_BUG = 10.0


def _parse_ts(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    s = str(raw).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def slot_id_for(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(PT)
    return f"{local.date().isoformat()}|{SLOT_HHMM}"


def in_proof_window(slot_id: str) -> bool:
    day = slot_id.split("|", 1)[0]
    return day in WINDOW_DATES and slot_id.endswith(f"|{SLOT_HHMM}")


def _pair_of(row: Dict[str, Any]) -> str:
    return str(row.get("pair") or row.get("product_id") or row.get("symbol") or "")


def _reason(row: Dict[str, Any]) -> str:
    return str(row.get("exit_reason") or row.get("reason") or row.get("sell_reason") or "")


def _notional(row: Dict[str, Any]) -> float:
    for k in ("notional_usd", "usd_value", "notional"):
        if row.get(k) is not None:
            try:
                return abs(float(row[k]))
            except (TypeError, ValueError):
                pass
    try:
        px = float(row.get("price") or row.get("fill_price") or 0)
        qty = float(row.get("size") or row.get("qty") or row.get("amount") or 0)
        return abs(px * qty)
    except (TypeError, ValueError):
        return 0.0


def is_risk_buy(row: Dict[str, Any]) -> bool:
    side = str(row.get("side") or row.get("action") or "").upper()
    if not side.startswith("B"):
        return False
    pair = _pair_of(row).upper()
    asset = pair.split("-")[0]
    return asset not in STABLE and pair not in STABLE


def is_bug_exit(row: Dict[str, Any]) -> bool:
    side = str(row.get("side") or "").upper()
    if not side.startswith("S"):
        return False
    reason = _reason(row).lower()
    if reason.startswith("process_bug"):
        return True
    if "dust" in reason and _notional(row) >= DUST_NOTIONAL_BUG:
        return True
    return False


def classify_doors(pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
    sent_clear = []
    rsi_only = []
    quiet = []
    for p in pairs or []:
        if not p.get("eligible", True):
            continue
        pair = p.get("pair")
        reasons = [str(r) for r in (p.get("reasons") or [])]
        try:
            eng = float(p.get("eng_sent") if p.get("eng_sent") is not None else -1)
        except (TypeError, ValueError):
            eng = -1.0
        sent_fail = any("sentiment" in r.lower() for r in reasons)
        rsi_fail = any(r.lower().startswith("rsi") or "rsi " in r.lower() for r in reasons)
        if eng >= 0.30 and not sent_fail:
            sent_clear.append(pair)
            if rsi_fail and not sent_fail and all("rsi" in r.lower() for r in reasons):
                rsi_only.append(pair)
        elif sent_fail or eng < 0.30:
            quiet.append(pair)
    return {
        "sent_clear": sent_clear,
        "rsi_only_block": rsi_only,
        "quiet_sensor": quiet,
    }


def wave2_hint(doors: Dict[str, Any], n_fills: int, n_bugs: int) -> str:
    if n_bugs:
        return "STOP — process bug this slot. No loosen."
    if n_fills:
        return "Wave 1 success — watch exit. No scale, no loosen."
    if doors.get("rsi_only_block"):
        return "W2-C or W2-A candidate — sent cleared, RSI is the only block. Still needs dated GO."
    if doors.get("quiet_sensor") and not doors.get("sent_clear"):
        return "W2-D — quiet sensor. Do not cut the floor."
    if doors.get("sent_clear"):
        return "Sent cleared but not a clean RSI-only block. Read reasons before any GO."
    return "No door print. Treat as idle, not a loosen signal."


def score_slot(
    *,
    readiness: Dict[str, Any],
    ledger_rows: List[Dict[str, Any]],
    now: Optional[datetime] = None,
    prior_slot_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    sid = slot_id_for(now)
    local = now.astimezone(PT)
    slot_start = datetime(
        local.year, local.month, local.day, 21, 0, tzinfo=PT
    ).astimezone(timezone.utc)
    fills = []
    bugs = []
    for row in ledger_rows:
        ts = _parse_ts(row.get("timestamp") or row.get("ts") or row.get("filled_at"))
        if ts is None or ts < slot_start:
            continue
        if is_risk_buy(row):
            fills.append(
                {
                    "pair": _pair_of(row),
                    "ts": ts.isoformat(),
                    "reason": _reason(row) or row.get("reason"),
                }
            )
        if is_bug_exit(row):
            bugs.append(
                {
                    "pair": _pair_of(row),
                    "ts": ts.isoformat(),
                    "reason": _reason(row),
                    "notional": round(_notional(row), 2),
                }
            )
    doors = classify_doors(list(readiness.get("pairs") or []))
    prior = [s for s in (prior_slot_ids or []) if in_proof_window(s) and s != sid]
    n_scored_including = len(set(prior + ([sid] if in_proof_window(sid) else [])))
    card = {
        "slot_id": sid,
        "as_of": now.astimezone(PT).isoformat(),
        "in_proof_window": in_proof_window(sid),
        "slot_index": n_scored_including if in_proof_window(sid) else None,
        "slot_index_of": 3,
        "can_buy": readiness.get("can_buy_before_next_rebalance"),
        "seats_used": readiness.get("seats_used_today"),
        "max_seats": readiness.get("max_new_seats_per_day"),
        "plain_english": readiness.get("plain_english"),
        "doors": [
            {
                "pair": p.get("pair"),
                "allowed": p.get("allowed"),
                "eng": p.get("eng_sent"),
                "rsi": p.get("rsi"),
                "reasons": p.get("reasons"),
            }
            for p in (readiness.get("pairs") or [])
        ],
        "classify": doors,
        "n_risk_fills": len(fills),
        "fills": fills,
        "n_bug_exits": len(bugs),
        "bug_exits": bugs,
        "wave2_hint": wave2_hint(doors, len(fills), len(bugs)),
        "final_slot": in_proof_window(sid) and n_scored_including >= 3,
        "measure_only": True,
        "knobs_touched": False,
    }
    card["telegram"] = telegram_body(card)
    return card


def telegram_body(card: Dict[str, Any]) -> str:
    """Short card or empty. Empty stdout = no Telegram."""
    if not card.get("in_proof_window"):
        return ""
    bugs = card.get("bug_exits") or []
    fills = card.get("fills") or []
    rsi_only = (card.get("classify") or {}).get("rsi_only_block") or []
    final = bool(card.get("final_slot"))
    if not bugs and not fills and not rsi_only and not final:
        return ""
    lines = [f"Shell slot {card.get('slot_id')} ({card.get('slot_index')}/3)"]
    if bugs:
        lines.append("BUG " + ", ".join(f"{b.get('pair')} {b.get('reason')}" for b in bugs))
    if fills:
        lines.append("FILL " + ", ".join(str(f.get("pair")) for f in fills))
    if rsi_only:
        lines.append("RSI-only block: " + ", ".join(rsi_only))
    lines.append(str(card.get("wave2_hint") or ""))
    lines.append("No knobs.")
    return "\n".join(lines)


def render_md(card: Dict[str, Any]) -> str:
    doors = card.get("doors") or []
    door_lines = "\n".join(
        f"- {d.get('pair')}: allowed={d.get('allowed')} eng={d.get('eng')} rsi={d.get('rsi')} {d.get('reasons')}"
        for d in doors
    ) or "- none"
    return "\n".join(
        [
            f"# Shell slot score — {card.get('slot_id')}",
            "",
            f"**As of:** `{card.get('as_of')}`",
            f"**Index:** {card.get('slot_index')}/3 · window={card.get('in_proof_window')}",
            f"**Hint:** {card.get('wave2_hint')}",
            "",
            card.get("plain_english") or "",
            "",
            "## Doors",
            door_lines,
            "",
            f"Fills: {card.get('n_risk_fills')} · bug exits: {card.get('n_bug_exits')}",
            "",
            "Measure-only. No knobs.",
            "",
        ]
    )


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
