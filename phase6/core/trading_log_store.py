"""
Account-scoped verified trading fills (canonical for reconciliation & param audit).

Design (1000-trader scale):
- Partition: data/state/trading_log/{account_id}/verified_fills_{YYYY-MM}.jsonl
- One row per exchange order_id (deduped via sidecar index)
- Legacy trades/phase6_trades.jsonl remains for dashboard compat; prefer this store for audit.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from phase6.core.paths import PROJECT_ROOT, TRADING_LOG_DIR


def default_account_id() -> str:
    """Coinbase portfolio / sub-account the Trading Bot API key can see (whole account scope)."""
    env = (
        os.environ.get("COINBASE_PORTFOLIO_UUID")
        or os.environ.get("PHASE6_ACCOUNT_ID")
        or os.environ.get("TRADER_ACCOUNT_ID")
    )
    if env:
        return str(env).strip()
    return "default"


def default_trader_id() -> str:
    return os.environ.get("PHASE6_TRADER_ID", "default").strip() or "default"


def _account_dir(account_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in account_id)[:128]
    d = TRADING_LOG_DIR / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def _month_key(ts: str) -> str:
    try:
        t = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m")


def verified_fills_path(account_id: str, month: str) -> Path:
    return _account_dir(account_id) / f"verified_fills_{month}.jsonl"


def order_index_path(account_id: str) -> Path:
    return _account_dir(account_id) / "order_id_index.json"


def load_order_index(account_id: str) -> Set[str]:
    p = order_index_path(account_id)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(str(x) for x in (data.get("order_ids") or []))
    except Exception:
        return set()


def save_order_index(account_id: str, order_ids: Set[str]) -> None:
    p = order_index_path(account_id)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "order_ids": sorted(order_ids),
        "count": len(order_ids),
    }
    p.write_text(json.dumps(payload, indent=0) + "\n", encoding="utf-8")


def append_verified_fill(
    row: Dict[str, Any],
    *,
    account_id: Optional[str] = None,
    trader_id: Optional[str] = None,
) -> bool:
    """
    Append one exchange-verified fill if order_id not already indexed for this account.
    Returns True if appended.
    """
    oid = row.get("order_id")
    if not oid:
        return False
    account_id = account_id or row.get("account_id") or default_account_id()
    trader_id = trader_id or row.get("trader_id") or default_trader_id()
    known = load_order_index(account_id)
    oid_s = str(oid)
    if oid_s in known:
        return False

    ts = row.get("timestamp") or datetime.now(timezone.utc).isoformat()
    out = dict(row)
    out.setdefault("account_id", account_id)
    out.setdefault("trader_id", trader_id)
    out.setdefault("record_type", "verified_fill")
    out.setdefault("ingested_at", datetime.now(timezone.utc).isoformat())

    path = verified_fills_path(account_id, _month_key(ts))
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(out) + "\n")

    known.add(oid_s)
    save_order_index(account_id, known)
    return True


def iter_verified_fills(
    account_id: str,
    *,
    months_back: int = 24,
) -> Iterable[Dict[str, Any]]:
    """Stream verified fills for account (newest months first)."""
    adir = _account_dir(account_id)
    if not adir.exists():
        return
    files = sorted(adir.glob("verified_fills_*.jsonl"), reverse=True)
    for fp in files[:months_back]:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def load_verified_fills_list(account_id: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    rows = list(iter_verified_fills(account_id))
    if limit:
        return rows[-limit:]
    return rows


def migrate_legacy_jsonl_to_account_store(
    account_id: Optional[str] = None,
    *,
    legacy_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """One-shot: copy fill_verified+coinbase_trading_bot rows from phase6_trades.jsonl."""
    account_id = account_id or default_account_id()
    legacy = legacy_path or (PROJECT_ROOT / "trades/phase6_trades.jsonl")
    added = 0
    skipped = 0
    if not legacy.exists():
        return {"ok": True, "added": 0, "skipped": 0}
    for line in legacy.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not (r.get("fill_verified") and r.get("coinbase_trading_bot") and r.get("order_id")):
            skipped += 1
            continue
        if append_verified_fill(r, account_id=account_id):
            added += 1
        else:
            skipped += 1
    return {"ok": True, "account_id": account_id, "added": added, "skipped": skipped}