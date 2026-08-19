"""
Daily Dose D1/D2 helpers — edited package + publish-ready text.

Does not touch sentiment_cache, runner, or allocator.
Telegram live send is gated (default OFF) unless Brad OK + env + CLI.
"""
from __future__ import annotations

import json
import re
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from phase6.core.daily_dose_editorial import (
    apply_shortlist_diversity,
    ensure_story_lane,
    format_tickers_display,
    is_btc_only_card,
    md_source_link,
    primary_basket_pair,
)
from phase6.core.paths import (
    DAILY_DOSE_EDITED,
    DAILY_DOSE_HISTORY,
    DAILY_DOSE_LATEST,
    DAILY_DOSE_PUBLISH_READY,
)

EDITED_SCHEMA = 4
VALID_STATUS = frozenset({"APPROVED", "REVISE", "DRAFT"})
TG_MAX_BULLETS = 5
TITLE_SOFT_MAX = 140


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"missing dose file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected object in {path}")
    return data


def load_latest(path: Path = DAILY_DOSE_LATEST) -> Dict[str, Any]:
    return load_json(path)


def load_edited(path: Path = DAILY_DOSE_EDITED) -> Dict[str, Any]:
    return load_json(path)


def _clip_title(title: str, max_len: int = TITLE_SOFT_MAX) -> str:
    t = re.sub(r"\s+", " ", (title or "").strip())
    if len(t) <= max_len:
        return t
    cut = t[: max_len - 1].rsplit(" ", 1)[0]
    return (cut or t[: max_len - 1]).rstrip(",;:") + "…"


def select_items(
    items: Sequence[Dict[str, Any]],
    keep_ids: Optional[Sequence[str]] = None,
    drop_ids: Optional[Sequence[str]] = None,
    top_n: int = TG_MAX_BULLETS,
    *,
    apply_diversity: bool = True,
) -> List[Dict[str, Any]]:
    out = [deepcopy(i) for i in items if isinstance(i, dict)]
    drop = set(drop_ids or [])
    if drop:
        out = [i for i in out if i.get("id") not in drop]
    if keep_ids:
        want = list(keep_ids)
        by_id = {i.get("id"): i for i in out}
        ordered = [by_id[k] for k in want if k in by_id]
        out = ordered if ordered else out
    # Enrich + diversity before hard top_n cut (unless keep_ids pinned order)
    if apply_diversity and not keep_ids:
        pool = out[: max(top_n * 4, top_n)]
        out = apply_shortlist_diversity(pool, top_n=top_n)
    else:
        out = out[: max(0, int(top_n))]
    return [ensure_story_lane(i) for i in out]


def build_edited_package(
    latest: Dict[str, Any],
    *,
    status: str,
    reviewer: str,
    notes: str = "",
    keep_ids: Optional[Sequence[str]] = None,
    drop_ids: Optional[Sequence[str]] = None,
    top_n: int = TG_MAX_BULLETS,
    title_overrides: Optional[Dict[str, str]] = None,
    why_overrides: Optional[Dict[str, str]] = None,
    checklist: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    status_u = (status or "").strip().upper()
    if status_u not in VALID_STATUS:
        raise ValueError(f"status must be one of {sorted(VALID_STATUS)}, got {status!r}")

    items_in = latest.get("items") or []
    if not isinstance(items_in, list):
        raise ValueError("latest.items must be a list")

    items = select_items(
        items_in,
        keep_ids=keep_ids,
        drop_ids=drop_ids,
        top_n=top_n,
        apply_diversity=not bool(keep_ids),
    )
    overrides = title_overrides or {}
    # why_overrides accepted but ignored (platform-why retired 2026-08-13)
    _ = why_overrides
    for it in items:
        oid = it.get("id")
        if oid in overrides and overrides[oid].strip():
            it.setdefault("title_original", it.get("title"))
            it["title"] = overrides[oid].strip()
            it.setdefault("editorial", {})
            notes_e = list(it["editorial"].get("notes") or [])
            notes_e.append("human_title_override")
            it["editorial"]["notes"] = notes_e
        filled = ensure_story_lane(it)
        it.clear()
        it.update(filled)
        it["title_display"] = _clip_title(str(it.get("title") or ""))
        it.pop("why_it_matters_platform", None)
        it["primary_pair"] = primary_basket_pair(it)
        it["btc_only"] = is_btc_only_card(it)

    btc_tape_n = sum(1 for i in items if (i.get("story_lane") or "") == "btc_tape")
    btc_only_n = sum(1 for i in items if is_btc_only_card(i))
    primary_counts: Dict[str, int] = {}
    for i in items:
        pp = str(i.get("primary_pair") or primary_basket_pair(i))
        primary_counts[pp] = primary_counts.get(pp, 0) + 1
    default_checklist = {
        "drop_roundups": True,
        "drop_vague_explainers": True,
        "one_card_per_event": True,
        "active_voice": True,
        "max_5_tg_bullets": len(items) <= TG_MAX_BULLETS,
        "no_trade_recommendations": True,
        "diversity_btc_tape_max_2": btc_tape_n <= 2,
        "diversity_btc_only_max_2": btc_only_n <= 2,
        "tone_positive_honest": True,
    }
    if checklist:
        default_checklist.update(checklist)
        default_checklist.pop("why_it_matters_platform", None)

    pkg = {
        "schema_version": EDITED_SCHEMA,
        "source_draft": {
            "path": str(DAILY_DOSE_LATEST),
            "generated_at": latest.get("generated_at"),
            "draft_item_count": len(items_in),
            "method": (latest.get("meta") or {}).get("method"),
        },
        "edited_at": utc_now_iso(),
        "items": items,
        "editorial_review": {
            "status": status_u,
            "notes": notes or "",
            "reviewer": reviewer or "content-editor",
            "at": utc_now_iso(),
            "checklist": default_checklist,
            "tg_bullet_cap": TG_MAX_BULLETS,
            "dropped_from_draft": max(0, len(items_in) - len(items)),
            "btc_tape_count": btc_tape_n,
            "btc_only_count": btc_only_n,
            "primary_pair_counts": primary_counts,
            "editorial_method": "v4_basket_pair_diversity_domain_links_2026-08-13",
        },
        "meta": {
            "note": "Edited package for publisher — not a trading signal",
            "trading": "never wired",
            "basket": (latest.get("meta") or {}).get("basket"),
            "thin_day": latest.get("thin_day"),
            "audience": "platform_trader",
            "why_framing": "retired",
            "link_style": "domain_markdown",
        },
    }
    return pkg


def write_edited(pkg: Dict[str, Any], path: Path = DAILY_DOSE_EDITED) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pkg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def format_publish_text(
    pkg: Dict[str, Any],
    *,
    date_label: Optional[str] = None,
    max_bullets: int = TG_MAX_BULLETS,
) -> str:
    er = pkg.get("editorial_review") or {}
    items = (pkg.get("items") or [])[:max_bullets]
    if date_label is None:
        raw = pkg.get("edited_at") or utc_now_iso()
        try:
            date_label = raw[:10]
        except Exception:
            date_label = "today"

    lines = [
        f"Daily dose · {date_label}",
        "(Not a trade signal — news for traders on this platform)",
        "",
    ]
    if not items:
        lines.append("_No items cleared editorial._")
    else:
        for i, it in enumerate(items, 1):
            title = it.get("title_display") or it.get("title") or "(untitled)"
            src = it.get("source") or ""
            url = it.get("url") or ""
            tickers = format_tickers_display(it.get("tickers") or [])
            link = md_source_link(src, url)
            lines.append(f"{i}. {title}")
            lines.append(f"   {link} · {tickers}")
            lines.append("")

    lines.append(f"Editorial: {er.get('status', '?')} · {er.get('reviewer', '?')}")
    lines.append("Not a trade signal · Daily Dose publication cycle")
    lines.append("")
    return "\n".join(lines)


def publish_gate_errors(pkg: Dict[str, Any]) -> List[str]:
    errs = []
    er = pkg.get("editorial_review") or {}
    st = (er.get("status") or "").upper()
    if st != "APPROVED":
        errs.append(f"editorial_review.status must be APPROVED (got {st or 'missing'})")
    items = pkg.get("items")
    if not isinstance(items, list):
        errs.append("items must be a list")
    elif len(items) == 0:
        errs.append("items empty — nothing to publish")
    else:
        btc_tape_n = sum(1 for i in items if (i.get("story_lane") or "") == "btc_tape")
        if btc_tape_n > 2:
            errs.append(f"diversity: btc_tape count {btc_tape_n} > 2")
        btc_only_n = sum(1 for i in items if is_btc_only_card(i))
        if btc_only_n > 2:
            errs.append(f"diversity: btc_only count {btc_only_n} > 2")
    return errs


def write_publish_ready(text: str, path: Path = DAILY_DOSE_PUBLISH_READY) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return path


def append_publish_history(
    pkg: Dict[str, Any],
    *,
    publish_path: Path,
    telegram_attempted: bool = False,
    telegram_sent: bool = False,
) -> None:
    er = pkg.get("editorial_review") or {}
    row = {
        "event": "daily_dose_publish",
        "at": utc_now_iso(),
        "status": er.get("status"),
        "reviewer": er.get("reviewer"),
        "n_items": len(pkg.get("items") or []),
        "item_ids": [i.get("id") for i in (pkg.get("items") or [])],
        "publish_path": str(publish_path),
        "telegram_attempted": telegram_attempted,
        "telegram_sent": telegram_sent,
        "editorial_method": er.get("editorial_method"),
        "btc_tape_count": er.get("btc_tape_count"),
    }
    DAILY_DOSE_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with DAILY_DOSE_HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def telegram_send_allowed(
    *,
    env_flag: str,
    brad_ok_flag_path: Path,
    cli_allow: bool,
) -> tuple[bool, str]:
    """Live TG. All three required."""
    import os

    if not cli_allow:
        return False, "cli --allow-telegram not set"
    if os.environ.get(env_flag, "").strip() not in ("1", "true", "TRUE", "yes", "YES"):
        return False, f"env {env_flag} not enabled"
    if not brad_ok_flag_path.is_file():
        return False, f"missing Brad OK flag file: {brad_ok_flag_path}"
    return True, "ok"


def stub_telegram_send(text: str) -> Dict[str, Any]:
    """Never actually sends. Records intent only."""
    return {
        "sent": False,
        "stub": True,
        "bytes": len(text.encode("utf-8")),
        "message": "Telegram send stub — disk only",
    }


def hermes_telegram_send(text: str, target: str = "telegram") -> Dict[str, Any]:
    """Live send via Hermes CLI (stdin → hermes send -t telegram)."""
    try:
        proc = subprocess.run(
            ["hermes", "send", "-t", target],
            input=text,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        ok = proc.returncode == 0
        return {
            "sent": ok,
            "stub": False,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[:500],
            "stderr": (proc.stderr or "")[:500],
            "bytes": len(text.encode("utf-8")),
        }
    except Exception as exc:
        return {
            "sent": False,
            "stub": False,
            "error": str(exc),
            "bytes": len(text.encode("utf-8")),
        }
