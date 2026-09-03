#!/usr/bin/env python3
"""
Analyst proposal backlog hygiene (Brad GO 2026-09-02).

- Archive duplicate proposed copies of the same title stem
- Keep unique accepted/implemented history (one canonical per stem preferred)
- Mark remaining valid opens as open / waiting_* (e.g. bear-gated)
- Preserve title stems for novelty dedup via dedupe_titles[]

Does not touch live book/config.
"""
from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "data" / "state" / "analyst_proposed_backlog.json"
ARCHIVE = ROOT / "data" / "state" / "analyst_proposed_backlog_archive_20260902.json"
REPORT = ROOT / "data" / "state" / "analyst_backlog_hygiene_20260902.json"
DECISIONS = ROOT / "docs" / "testing" / "decisions" / "DEC_ANALYST_BACKLOG_HYGIENE_20260902.md"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stem(title: str) -> str:
    t = (title or "").lower().strip()
    t = t.replace("“", "").replace("”", "").replace('"', "").replace("'", "")
    t = re.sub(r"\s+", " ", t)
    return t[:100]


def _sort_key(p: Dict[str, Any]) -> str:
    return str(
        p.get("generated")
        or p.get("created_at")
        or p.get("accepted")
        or p.get("id")
        or ""
    )


TERMINAL = {"accepted", "implemented", "done", "closed", "dropped", "rejected"}
ACTIVE_RUN = {"queued", "running", "in_progress"}


def _classify_open(p: Dict[str, Any]) -> Tuple[str, str]:
    """Return (status, wait_reason) for a unique still-open idea."""
    title = (p.get("title") or "").lower()
    pid = str(p.get("id") or "")
    cat = str(p.get("category") or "").lower()
    why = str(p.get("why") or p.get("description") or "").lower()
    blob = f"{title} {cat} {why} {pid}"

    # Regime-gated
    if "bear_window" in blob or "bear_window_rotation" in blob:
        return (
            "waiting_regime_bear",
            "Shadow/trial tied to bear_window scenario — wait for live bear (or historical-only backtest lane).",
        )
    if re.search(r"\bbear\b", title) and "park" in title:
        return (
            "waiting_regime_bear",
            "Bear-park plan — emit/confirm when live regime is bear.",
        )
    if "emit_only_when_regime" in blob or "when regime is bear" in blob:
        return ("waiting_regime_bear", "Explicitly gated on bear regime.")

    # Phase2 / earn-scale
    if "earn/scale" in title or "phase 2 stabilize" in title:
        return (
            "waiting_phase2",
            "Blocked on phase2_ready + Brad reopen GO (already accepted hold).",
        )

    # Dependency chains
    if "kelly" in title and "post stoch" in title:
        return (
            "waiting_dependency",
            "Queued behind Stoch RSI comparison / 30d reeval gate.",
        )
    if "stoch" in title and ("finish" in title or "comparison" in title):
        return (
            "waiting_dependency",
            "Stoch vs RSI — stoch-30d-reeval scheduled 2026-09-03; keep open until reeval lands.",
        )

    # Daily review fresh items
    if pid.startswith("ANALYST-20260902-002"):
        return (
            "open",
            "Trend-repair observe-only review — can run anytime offline (no live writes).",
        )
    if pid.startswith("ANALYST-20260902-003"):
        return (
            "open",
            "OPT pack refresh + re-entry stress — shadow/offline anytime.",
        )
    if pid.startswith("ANALYST-20260902-004"):
        return (
            "open",
            "Emit next ungated TEST_STRATEGY plan when capacity free — capacity free now.",
        )

    # Polymarket research
    if "polymarket" in title:
        if "backtest" in title or "quantify" in title:
            return (
                "open",
                "Offline backtest allowed under analyst research policy; attach results to CR before promote.",
            )
        return ("open", "Research lane — offline first.")

    # Default unique proposed
    return ("open", "Unique idea retained after hygiene; process or schedule offline.")


def run() -> Dict[str, Any]:
    raw = json.loads(BACKLOG.read_text() or "{}")
    props: List[Dict[str, Any]] = list(raw.get("proposals") or [])
    ts = _now()

    # Backup
    bak = BACKLOG.with_suffix(f".bak_hygiene_{ts[:10].replace('-', '')}.json")
    shutil.copy2(BACKLOG, bak)

    by_stem: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in props:
        if not isinstance(p, dict):
            continue
        by_stem[_stem(str(p.get("title") or ""))].append(p)

    keep: List[Dict[str, Any]] = []
    archived: List[Dict[str, Any]] = []
    dedupe_titles: List[str] = []
    summary_open: List[Dict[str, Any]] = []

    stats = {
        "input_n": len(props),
        "stems": len(by_stem),
        "kept_terminal": 0,
        "kept_open": 0,
        "kept_waiting": 0,
        "archived_duplicate": 0,
        "archived_other": 0,
    }

    for stem, rows in sorted(by_stem.items(), key=lambda kv: kv[0]):
        if not stem:
            continue
        title_display = rows[0].get("title") or stem
        dedupe_titles.append(str(title_display))

        terminals = [
            p
            for p in rows
            if str(p.get("status") or "").lower() in TERMINAL
        ]
        actives = [
            p
            for p in rows
            if str(p.get("status") or "").lower() in ACTIVE_RUN
        ]
        proposed = [
            p
            for p in rows
            if str(p.get("status") or "").lower()
            in ("proposed", "open", "waiting", "")
            or str(p.get("status") or "").lower().startswith("waiting")
        ]
        # anything else
        other = [
            p
            for p in rows
            if p not in terminals and p not in actives and p not in proposed
        ]

        # Prefer one terminal canonical: implemented > accepted > done
        def term_rank(p: Dict[str, Any]) -> Tuple[int, str]:
            s = str(p.get("status") or "").lower()
            rank = {"implemented": 0, "accepted": 1, "done": 2, "closed": 3}.get(s, 9)
            return (rank, _sort_key(p))

        if terminals:
            terminals_sorted = sorted(terminals, key=term_rank)
            canonical = dict(terminals_sorted[0])
            # If multiple terminals of same stem, keep best + archive rest
            keep.append(canonical)
            stats["kept_terminal"] += 1
            for p in terminals_sorted[1:]:
                ap = dict(p)
                ap["status"] = "archived_duplicate"
                ap["hygiene_at"] = ts
                ap["hygiene_reason"] = f"duplicate terminal of {canonical.get('id')}"
                ap["canonical_id"] = canonical.get("id")
                archived.append(ap)
                stats["archived_duplicate"] += 1
            # Archive all proposed/active duplicates of a done idea
            for p in proposed + actives + other:
                ap = dict(p)
                ap["status"] = "archived_duplicate"
                ap["hygiene_at"] = ts
                ap["hygiene_reason"] = (
                    f"superseded by {canonical.get('status')} {canonical.get('id')}"
                )
                ap["canonical_id"] = canonical.get("id")
                archived.append(ap)
                stats["archived_duplicate"] += 1
            continue

        # No terminal — keep active run states, else one open/waiting
        if actives:
            # keep all distinct actives (usually 1)
            seen_ids = set()
            for p in sorted(actives, key=_sort_key):
                if p.get("id") in seen_ids:
                    ap = dict(p)
                    ap["status"] = "archived_duplicate"
                    ap["hygiene_at"] = ts
                    archived.append(ap)
                    stats["archived_duplicate"] += 1
                    continue
                seen_ids.add(p.get("id"))
                q = dict(p)
                st, reason = _classify_open(q)
                # preserve queued/running label but add wait metadata
                if str(q.get("status")).lower() in ACTIVE_RUN:
                    q["queue_status"] = q.get("status")
                    if st.startswith("waiting"):
                        q["status"] = st
                    # else keep running/queued
                q["hygiene_at"] = ts
                q["open_reason"] = reason
                keep.append(q)
                if str(q.get("status", "")).startswith("waiting"):
                    stats["kept_waiting"] += 1
                else:
                    stats["kept_open"] += 1
                summary_open.append(
                    {
                        "id": q.get("id"),
                        "status": q.get("status"),
                        "title": q.get("title"),
                        "reason": reason,
                    }
                )
            for p in proposed + other:
                ap = dict(p)
                ap["status"] = "archived_duplicate"
                ap["hygiene_at"] = ts
                ap["hygiene_reason"] = "duplicate of active item"
                archived.append(ap)
                stats["archived_duplicate"] += 1
            continue

        # Pure proposed stack → one survivor
        if proposed:
            survivor = dict(sorted(proposed, key=_sort_key)[0])
            # Prefer latest id if newer ANALYST-20260902
            for p in proposed:
                if str(p.get("id") or "").startswith("ANALYST-20260902"):
                    survivor = dict(p)
            st, reason = _classify_open(survivor)
            survivor["status"] = st
            survivor["hygiene_at"] = ts
            survivor["open_reason"] = reason
            keep.append(survivor)
            if st.startswith("waiting"):
                stats["kept_waiting"] += 1
            else:
                stats["kept_open"] += 1
            summary_open.append(
                {
                    "id": survivor.get("id"),
                    "status": st,
                    "title": survivor.get("title"),
                    "reason": reason,
                }
            )
            for p in proposed:
                if p.get("id") == survivor.get("id"):
                    continue
                ap = dict(p)
                ap["status"] = "archived_duplicate"
                ap["hygiene_at"] = ts
                ap["hygiene_reason"] = f"duplicate proposed; kept {survivor.get('id')}"
                ap["canonical_id"] = survivor.get("id")
                archived.append(ap)
                stats["archived_duplicate"] += 1
            for p in other:
                ap = dict(p)
                ap["status"] = "archived_other"
                ap["hygiene_at"] = ts
                archived.append(ap)
                stats["archived_other"] += 1
            continue

        for p in other:
            ap = dict(p)
            ap["status"] = "archived_other"
            ap["hygiene_at"] = ts
            archived.append(ap)
            stats["archived_other"] += 1

    # Stable sort keep: waiting/open first by priority, then terminals
    def keep_rank(p: Dict[str, Any]) -> Tuple[int, int, str]:
        s = str(p.get("status") or "").lower()
        if s == "open":
            bucket = 0
        elif s.startswith("waiting"):
            bucket = 1
        elif s in ACTIVE_RUN:
            bucket = 2
        elif s == "accepted":
            bucket = 3
        elif s == "implemented":
            bucket = 4
        else:
            bucket = 5
        pr = str(p.get("priority") or "Medium").lower()
        pr_n = {"high": 0, "medium": 1, "low": 2}.get(pr, 3)
        return (bucket, pr_n, str(p.get("id") or ""))

    keep_sorted = sorted(keep, key=keep_rank)

    out = {
        "schema": "analyst_proposed_backlog_v2",
        "hygiene_at": ts,
        "hygiene_note": (
            "Brad GO 2026-09-02: dedupe spam; open vs waiting_*; "
            "duplicates archived; stems kept for novelty dedup."
        ),
        "dedupe_titles": sorted(set(dedupe_titles)),
        "proposals": keep_sorted,
        "stats": {
            **stats,
            "kept_n": len(keep_sorted),
            "archived_n": len(archived),
            "dedupe_title_n": len(set(dedupe_titles)),
        },
        "open_queue": summary_open,
    }

    ARCHIVE.write_text(json.dumps({"archived_at": ts, "items": archived}, indent=2) + "\n")
    BACKLOG.write_text(json.dumps(out, indent=2) + "\n")
    REPORT.write_text(
        json.dumps(
            {
                "as_of": ts,
                "backup": str(bak),
                "archive": str(ARCHIVE),
                "stats": out["stats"],
                "open_queue": summary_open,
                "kept_ids": [p.get("id") for p in keep_sorted],
            },
            indent=2,
        )
        + "\n"
    )

    # Decision doc
    lines = [
        "# Analyst backlog hygiene — 2026-09-02",
        "",
        f"**When:** {ts}",
        "**Brad:** hygiene pass — valid open/waiting; archive duplicate spam.",
        "",
        "## Stats",
        f"- Input: {stats['input_n']}",
        f"- Unique stems: {stats['stems']}",
        f"- Kept: {len(keep_sorted)} (terminal {stats['kept_terminal']}, open {stats['kept_open']}, waiting {stats['kept_waiting']})",
        f"- Archived duplicates: {stats['archived_duplicate']}",
        f"- Archive file: `{ARCHIVE}`",
        f"- Backup: `{bak}`",
        "",
        "## Open / waiting queue (process these)",
        "",
    ]
    for row in summary_open:
        lines.append(
            f"- **{row.get('status')}** `{row.get('id')}` — {row.get('title')}\n"
            f"  - {row.get('reason')}"
        )
    lines.extend(
        [
            "",
            "## Rules after hygiene",
            "- New proposals still title-dedup against `dedupe_titles` + kept titles.",
            "- `waiting_regime_bear` stays until live bear (offline hist backtest still allowed).",
            "- `open` = can process offline anytime; attach results to CR before live promote.",
            "",
        ]
    )
    DECISIONS.write_text("\n".join(lines) + "\n")

    return out["stats"] | {"open_queue": summary_open, "kept_n": len(keep_sorted)}


if __name__ == "__main__":
    s = run()
    print(json.dumps(s, indent=2, default=str))
