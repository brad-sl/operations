#!/usr/bin/env python3
"""Hard-exit operator loop: pending inbox, Telegram notify, approve/reject.

Never auto-sells. Brad stays in the decision loop.

State:
  data/state/regime_hard_exit_shadow.json   — latest scan (runner)
  data/state/hard_exit_pending.json         — open proposals awaiting decision
  data/state/hard_exit_decisions.jsonl      — audit trail
  data/state/hard_exit_notify_dedupe.json   — anti-spam fingerprints

CLI:
  PYTHONPATH=. python3 -m phase6.scripts.hard_exit_controls list
  PYTHONPATH=. python3 -m phase6.scripts.hard_exit_controls reject --all
  PYTHONPATH=. python3 -m phase6.scripts.hard_exit_controls reject --id <id>
  PYTHONPATH=. python3 -m phase6.scripts.hard_exit_controls approve --id <id>
  PYTHONPATH=. python3 -m phase6.scripts.hard_exit_controls notify-test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger("phase6.hard_exit_controls")

PENDING = ROOT / "data/state/hard_exit_pending.json"
DECISIONS = ROOT / "data/state/hard_exit_decisions.jsonl"
DEDUPE = ROOT / "data/state/hard_exit_notify_dedupe.json"
SHADOW = ROOT / "data/state/regime_hard_exit_shadow.json"
APPROVED_EXECUTE = ROOT / "data/state/hard_exit_approved_execute.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def proposal_id(p: Dict[str, Any], as_of: str = "") -> str:
    raw = "|".join(
        [
            str(p.get("pair") or ""),
            str(p.get("usd") or p.get("usd_amount") or ""),
            ",".join(str(x) for x in (p.get("exit_reasons") or [])),
            str(as_of)[:13],  # hour bucket
        ]
    )
    return "he-" + hashlib.sha1(raw.encode()).hexdigest()[:12]


def fingerprint(proposals: List[Dict[str, Any]]) -> str:
    parts = sorted(
        f"{p.get('pair')}:{','.join(p.get('exit_reasons') or [])}:{p.get('usd')}"
        for p in proposals
    )
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def sync_pending_from_shadow(shadow: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merge latest shadow proposals into pending inbox (open only)."""
    shadow = shadow or _load(SHADOW, {})
    proposals = list(shadow.get("proposals") or [])
    as_of = str(shadow.get("as_of") or _iso())
    pending = _load(
        PENDING,
        {
            "schema": "hard_exit_pending_v1",
            "updated_at": None,
            "items": [],
        },
    )
    items: List[Dict[str, Any]] = list(pending.get("items") or [])
    by_id = {i.get("id"): i for i in items if i.get("status") == "pending"}

    for p in proposals:
        pid = proposal_id(p, as_of)
        if pid in by_id:
            continue
        # skip if same pair+reasons already pending
        key = (p.get("pair"), tuple(p.get("exit_reasons") or []))
        if any(
            (i.get("pair"), tuple(i.get("exit_reasons") or [])) == key and i.get("status") == "pending"
            for i in items
        ):
            continue
        items.append(
            {
                "id": pid,
                "status": "pending",
                "created_at": _iso(),
                "pair": p.get("pair"),
                "usd": p.get("usd") or p.get("usd_amount"),
                "exit_reasons": p.get("exit_reasons") or [],
                "exit_class": p.get("exit_class") or "hard_exit",
                "reason": p.get("reason") or "regime_hard_exit",
                "shadow_as_of": as_of,
                "regime": shadow.get("regime"),
                "strategy_mode": shadow.get("strategy_mode"),
            }
        )
    pending["items"] = items
    pending["updated_at"] = _iso()
    pending["n_pending"] = sum(1 for i in items if i.get("status") == "pending")
    _save(PENDING, pending)
    return pending


def _should_notify(fp: str, dedupe_hours: float = 12.0) -> bool:
    d = _load(DEDUPE, {"fingerprints": {}})
    fps = d.get("fingerprints") or {}
    prev = fps.get(fp)
    if prev:
        try:
            t = datetime.fromisoformat(str(prev).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if _now() - t < timedelta(hours=dedupe_hours):
                return False
        except Exception:
            pass
    fps[fp] = _iso()
    # prune old
    cut = _now() - timedelta(days=7)
    kept = {}
    for k, v in fps.items():
        try:
            t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if t >= cut:
                kept[k] = v
        except Exception:
            kept[k] = v
    d["fingerprints"] = kept
    _save(DEDUPE, d)
    return True


def send_telegram(html: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Telegram credentials missing — hard-exit notify not sent")
        return False
    try:
        import requests

        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": html,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning("Telegram hard-exit notify failed: %s", e)
        return False


def format_notify_message(pending_items: List[Dict[str, Any]], regime: str = "") -> str:
    lines = [
        "<b>HARD EXIT — operator decision needed</b>",
        "Shadow only — <b>no auto sell</b>.",
        f"Regime: <code>{regime or '?'}</code>",
        "",
    ]
    for i in pending_items[:8]:
        lines.append(
            f"• <b>{i.get('pair')}</b> ${i.get('usd')} — "
            f"{', '.join(i.get('exit_reasons') or [])}"
        )
        lines.append(f"  id=<code>{i.get('id')}</code>")
    if len(pending_items) > 8:
        lines.append(f"… +{len(pending_items) - 8} more")
    lines += [
        "",
        "<b>Decide:</b>",
        "<code>PYTHONPATH=. python3 -m phase6.scripts.hard_exit_controls list</code>",
        "<code>… approve --id &lt;id&gt;</code>  or  <code>reject --id &lt;id&gt;</code>",
        "<code>… reject --all</code>",
        "",
        "Approve only stages intent; execute is a separate confirm step.",
    ]
    return "\n".join(lines)


def maybe_notify_hard_exits(
    shadow: Dict[str, Any],
    *,
    notify: bool = True,
    dedupe_hours: float = 12.0,
    force: bool = False,
) -> Dict[str, Any]:
    """Call after writing shadow. Syncs pending + optional Telegram."""
    pending = sync_pending_from_shadow(shadow)
    open_items = [i for i in (pending.get("items") or []) if i.get("status") == "pending"]
    proposals = list(shadow.get("proposals") or [])
    result = {
        "n_proposals": len(proposals),
        "n_pending": len(open_items),
        "notified": False,
        "skipped": None,
    }
    if not proposals and not open_items:
        result["skipped"] = "empty"
        return result
    if not open_items:
        result["skipped"] = "no_open_pending"
        return result
    fp = fingerprint(proposals) if proposals else fingerprint(open_items)
    if notify and (force or _should_notify(fp, dedupe_hours=dedupe_hours)):
        ok = send_telegram(
            format_notify_message(open_items, regime=str(shadow.get("regime") or ""))
        )
        result["notified"] = ok
        result["fingerprint"] = fp
        _append_decision(
            {
                "action": "notify",
                "ok": ok,
                "n": len(open_items),
                "fingerprint": fp,
                "ts": _iso(),
            }
        )
    else:
        result["skipped"] = "dedupe" if notify else "notify_disabled"
    return result


def _append_decision(row: Dict[str, Any]) -> None:
    DECISIONS.parent.mkdir(parents=True, exist_ok=True)
    with DECISIONS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def list_pending() -> List[Dict[str, Any]]:
    pending = _load(PENDING, {"items": []})
    return [i for i in (pending.get("items") or []) if i.get("status") == "pending"]


def decide(item_id: str, status: str, note: str = "") -> Dict[str, Any]:
    assert status in ("approved", "rejected")
    pending = _load(PENDING, {"items": []})
    found = None
    for i in pending.get("items") or []:
        if i.get("id") == item_id and i.get("status") == "pending":
            i["status"] = status
            i["decided_at"] = _iso()
            i["note"] = note
            found = i
            break
    if not found:
        raise SystemExit(f"pending id not found: {item_id}")
    pending["updated_at"] = _iso()
    pending["n_pending"] = sum(1 for i in pending.get("items") or [] if i.get("status") == "pending")
    _save(PENDING, pending)
    _append_decision({"action": status, "id": item_id, "item": found, "ts": _iso(), "note": note})

    if status == "approved":
        # Stage execute packet — does NOT place orders
        packet = _load(
            APPROVED_EXECUTE,
            {"schema": "hard_exit_approved_execute_v1", "legs": [], "staged_at": None},
        )
        legs = list(packet.get("legs") or [])
        legs.append(
            {
                "id": found["id"],
                "pair": found.get("pair"),
                "side": "SELL",
                "usd": found.get("usd"),
                "exit_reasons": found.get("exit_reasons"),
                "staged_at": _iso(),
                "execute": False,
                "note": "Staged only — run execute --confirm-live to place (not auto).",
            }
        )
        packet["legs"] = legs
        packet["staged_at"] = _iso()
        packet["operator"] = "brad"
        _save(APPROVED_EXECUTE, packet)
    return found


def reject_all(note: str = "reject_all") -> int:
    pending = _load(PENDING, {"items": []})
    n = 0
    for i in pending.get("items") or []:
        if i.get("status") == "pending":
            i["status"] = "rejected"
            i["decided_at"] = _iso()
            i["note"] = note
            n += 1
            _append_decision({"action": "rejected", "id": i.get("id"), "item": i, "ts": _iso()})
    pending["updated_at"] = _iso()
    pending["n_pending"] = 0
    _save(PENDING, pending)
    return n


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description="Hard-exit operator controls")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Show pending hard-exit proposals")
    p_rej = sub.add_parser("reject", help="Reject proposal(s)")
    p_rej.add_argument("--id", default=None)
    p_rej.add_argument("--all", action="store_true")
    p_rej.add_argument("--note", default="")

    p_ap = sub.add_parser("approve", help="Approve (stage only — no orders)")
    p_ap.add_argument("--id", required=True)
    p_ap.add_argument("--note", default="")

    p_n = sub.add_parser("notify-test", help="Force Telegram notify from current pending/shadow")
    p_n.add_argument("--force", action="store_true", default=True)

    sub.add_parser("sync", help="Sync pending from shadow file")

    p_ex = sub.add_parser(
        "execute-status",
        help="Show staged approve packet (orders never auto)",
    )

    args = ap.parse_args(argv)

    if args.cmd == "sync":
        p = sync_pending_from_shadow()
        print(json.dumps({"n_pending": p.get("n_pending"), "path": str(PENDING)}, indent=2))
        return 0

    if args.cmd == "list":
        sync_pending_from_shadow()
        items = list_pending()
        if not items:
            print("No pending hard-exit proposals.")
            if SHADOW.exists():
                sh = _load(SHADOW, {})
                print(f"Latest shadow n={sh.get('n')} as_of={sh.get('as_of')}")
            return 0
        print(f"Pending: {len(items)}")
        for i in items:
            print(
                f"  {i.get('id')}  {i.get('pair')}  ${i.get('usd')}  "
                f"{i.get('exit_reasons')}  since={i.get('created_at')}"
            )
        print("\nApprove (stage): python3 -m phase6.scripts.hard_exit_controls approve --id <id>")
        print("Reject:          python3 -m phase6.scripts.hard_exit_controls reject --id <id>")
        return 0

    if args.cmd == "reject":
        if args.all:
            n = reject_all(note=args.note or "reject_all")
            print(f"Rejected {n} pending")
            return 0
        if not args.id:
            raise SystemExit("--id or --all required")
        decide(args.id, "rejected", note=args.note)
        print(f"Rejected {args.id}")
        return 0

    if args.cmd == "approve":
        item = decide(args.id, "approved", note=args.note)
        print(f"APPROVED (staged, no order): {item.get('pair')} ${item.get('usd')}")
        print(f"Packet: {APPROVED_EXECUTE}")
        print("Orders are NOT placed. Manual sell or future execute --confirm-live required.")
        send_telegram(
            f"<b>Hard exit APPROVED (staged)</b>\n"
            f"{item.get('pair')} ${item.get('usd')}\n"
            f"id=<code>{item.get('id')}</code>\n"
            f"<i>No order placed</i>"
        )
        return 0

    if args.cmd == "notify-test":
        sh = _load(SHADOW, {})
        if not sh.get("proposals"):
            # synthetic if empty so wiring can be tested
            sh = {
                "regime": sh.get("regime") or "transition",
                "proposals": [
                    {
                        "pair": "TEST-USD",
                        "usd": 1.0,
                        "exit_reasons": ["notify_test"],
                    }
                ],
                "as_of": _iso(),
                "n": 1,
            }
        r = maybe_notify_hard_exits(sh, notify=True, force=True, dedupe_hours=0)
        print(json.dumps(r, indent=2))
        return 0

    if args.cmd == "execute-status":
        pkt = _load(APPROVED_EXECUTE, {})
        print(json.dumps(pkt, indent=2))
        print("\nNote: execute path intentionally not auto. Place sells manually or extend with --confirm-live.")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
