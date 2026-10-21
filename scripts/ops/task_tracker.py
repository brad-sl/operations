#!/usr/bin/env python3
"""MASTER task tracker → SQLite SSOT helpers.

Purpose
-------
`docs/MASTER_TASK_TRACKING.md` grew too large for reliable agent patch/edit.
This tool stores section-level tracking in SQLite so agents can:

  - import the markdown log once (or re-import idempotently)
  - query / update status without rewriting an 800KB+ markdown file
  - export a short open-items markdown view when humans want a scan surface

Policy (2026-10-21)
-------------------
- **Live SSOT for status updates:** `data/task_tracker.db`
- **Historical archive:** `docs/MASTER_TASK_TRACKING.md` (do not bulk-rewrite)
- **Dispatcher:** Hermes Kanban (`crypto-bot-project`) still runs workers
- New work: write DB row (+ optional short MASTER append of the section id only)
- Kanban ids stay linked via `kanban_ids` JSON on each section

Examples
--------
  python scripts/ops/task_tracker.py init
  python scripts/ops/task_tracker.py import-master
  python scripts/ops/task_tracker.py list --status open
  python scripts/ops/task_tracker.py search WEEKLY-SUGGESTIONS
  python scripts/ops/task_tracker.py set-status WEEKLY-SUGGESTIONS-20261018 done
  python scripts/ops/task_tracker.py export-md --status open -o docs/TASK_TRACKER_OPEN.md
  python scripts/ops/task_tracker.py stats
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "task_tracker.db"
DEFAULT_MASTER = ROOT / "docs" / "MASTER_TASK_TRACKING.md"
DEFAULT_OPEN_MD = ROOT / "docs" / "TASK_TRACKER_OPEN.md"

# Status vocabulary (normalized)
STATUS_DONE = {"done", "complete", "completed", "closed", "shipped", "resolved"}
STATUS_OPEN = {"open", "todo", "ready", "in_progress", "wip", "active", "new"}
STATUS_BLOCKED = {"blocked", "waiting", "needs_input", "gated"}
STATUS_WATCH = {"watch", "soak", "measure", "shadow"}
STATUS_PARKED = {"parked", "deferred", "queued", "backlog", "wontfix"}

KANBAN_RE = re.compile(r"\bt_[a-f0-9]{8}\b", re.I)
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
# Strip trailing status parentheticals for id slug base
SLUG_CLEAN_RE = re.compile(r"[^A-Za-z0-9._+-]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sections (
            id                TEXT PRIMARY KEY,
            master_heading    TEXT NOT NULL,
            title             TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'unknown',
            priority          TEXT,
            body              TEXT NOT NULL DEFAULT '',
            kanban_ids_json   TEXT NOT NULL DEFAULT '[]',
            source_line_start INTEGER,
            source_line_end   INTEGER,
            body_sha1         TEXT,
            imported_at       TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            notes             TEXT NOT NULL DEFAULT '',
            active            INTEGER NOT NULL DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_sections_status ON sections(status);
        CREATE INDEX IF NOT EXISTS idx_sections_active ON sections(active);

        CREATE TABLE IF NOT EXISTS events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id TEXT NOT NULL,
            kind       TEXT NOT NULL,
            payload    TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(section_id) REFERENCES sections(id)
        );

        CREATE INDEX IF NOT EXISTS idx_events_section ON events(section_id);

        CREATE TABLE IF NOT EXISTS artifacts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id TEXT NOT NULL,
            path       TEXT NOT NULL,
            kind       TEXT NOT NULL DEFAULT 'path',
            created_at TEXT NOT NULL,
            FOREIGN KEY(section_id) REFERENCES sections(id)
        );
        """
    )
    con.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
        ("schema_version", "1"),
    )
    con.commit()


def slugify_heading(heading: str) -> str:
    """Stable-ish id from heading; keep known TASK-ID prefixes when present."""
    h = heading.strip()
    # Prefer leading TOKEN like WEEKLY-SUGGESTIONS-20261018 or P6-FOO
    m = re.match(r"^([A-Z0-9][A-Z0-9._+-]{2,})", h)
    if m and re.search(r"[A-Z]", m.group(1)) and (
        "-" in m.group(1) or "_" in m.group(1) or m.group(1).startswith("P")
    ):
        base = m.group(1).rstrip(".:)—-")
    else:
        base = h
    # Drop common trailing status markers from slug
    base = re.sub(
        r"\s*[—(].*$",
        "",
        base,
    )
    base = re.sub(
        r"\s+(DONE|COMPLETE|SHIPPED|OPEN|TODO|BLOCKED|CLOSED)\s*$",
        "",
        base,
        flags=re.I,
    )
    slug = SLUG_CLEAN_RE.sub("-", base).strip("-")
    if not slug:
        slug = hashlib.sha1(h.encode()).hexdigest()[:12]
    # cap length
    return slug[:120]


def infer_status(heading: str, body: str) -> str:
    text = f"{heading}\n{body[:2000]}"
    upper = text.upper()

    # Explicit DONE / SHIPPED in heading wins often
    if re.search(r"\b(DONE|COMPLETE|COMPLETED|CLOSED|SHIPPED)\b", heading, re.I):
        # but "SHIPPED sensor" with open residual still done-ish
        return "done"
    if re.search(r"\b(PARKED|DEFERRED|QUEUED)\b", heading, re.I):
        return "parked"
    if re.search(r"\b(WATCH|SOAK|SHADOW)\b", heading, re.I):
        return "watch"
    if re.search(r"\b(BLOCKED|GATED|NEEDS.?INPUT)\b", heading, re.I):
        return "blocked"

    # Body bullets
    if re.search(r"\*\*Status:\*\*\s*(DONE|COMPLETE|SHIPPED)", text, re.I):
        return "done"
    if re.search(r"\bstatus:\s*(done|complete|shipped)\b", text, re.I):
        return "done"
    if re.search(r"\b(TODO|OPEN|IN PROGRESS|READY)\b", heading, re.I):
        return "open"

    # Heuristic counts
    done_hits = len(re.findall(r"\b(DONE|SHIPPED|COMPLETE)\b", upper))
    open_hits = len(re.findall(r"\b(TODO|OPEN|NOT DONE|PENDING|READY)\b", upper))
    if done_hits >= 2 and open_hits == 0:
        return "done"
    if open_hits and not done_hits:
        return "open"
    if "NO-GO" in upper and "DONE" not in heading.upper():
        return "blocked"
    return "unknown"


def extract_kanban_ids(text: str) -> list[str]:
    return sorted(set(KANBAN_RE.findall(text)))


def extract_artifact_paths(text: str) -> list[str]:
    paths = set()
    for m in re.finditer(
        r"`((?:docs|reports|data|scripts|config|phase6)/[^`\s]+)`", text
    ):
        paths.add(m.group(1))
    return sorted(paths)


def parse_master(text: str) -> list[dict[str, Any]]:
    """Split MASTER into ## sections (level-2 only)."""
    lines = text.splitlines()
    # Find ## headings with line numbers (1-indexed)
    heads: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if line.startswith("## ") and not line.startswith("### "):
            heads.append((i + 1, line[3:].strip()))

    sections: list[dict[str, Any]] = []
    for idx, (start, heading) in enumerate(heads):
        # start = 1-indexed heading line. Body is everything after heading until
        # the line before the next ## heading (or EOF).
        next_start = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines) + 1
        # 0-indexed slice: after heading .. before next heading
        body = "\n".join(lines[start : next_start - 1]).strip("\n")
        end_line = next_start - 1  # 1-indexed last line of section
        sid = slugify_heading(heading)
        full = heading + "\n" + body
        sections.append(
            {
                "id": sid,
                "master_heading": heading,
                "title": heading,
                "status": infer_status(heading, body),
                "body": body,
                "kanban_ids": extract_kanban_ids(full),
                "artifacts": extract_artifact_paths(full),
                "source_line_start": start,
                "source_line_end": end_line,
                "body_sha1": hashlib.sha1(
                    full.encode("utf-8", errors="replace")
                ).hexdigest(),
            }
        )
    # Deduplicate ids: if collision, suffix with short hash
    seen: dict[str, int] = {}
    for s in sections:
        base = s["id"]
        n = seen.get(base, 0)
        seen[base] = n + 1
        if n:
            s["id"] = f"{base}__{s['body_sha1'][:8]}"
    return sections


def import_master(
    con: sqlite3.Connection,
    master_path: Path,
    *,
    deactivate_missing: bool = False,
) -> dict[str, int]:
    text = master_path.read_text(encoding="utf-8", errors="replace")
    sections = parse_master(text)
    now = utc_now()
    inserted = updated = unchanged = 0
    seen_ids: set[str] = set()

    for s in sections:
        seen_ids.add(s["id"])
        kanban_json = json.dumps(s["kanban_ids"])
        row = con.execute(
            "SELECT body_sha1, status, notes FROM sections WHERE id = ?",
            (s["id"],),
        ).fetchone()
        if row is None:
            con.execute(
                """
                INSERT INTO sections(
                    id, master_heading, title, status, priority, body,
                    kanban_ids_json, source_line_start, source_line_end,
                    body_sha1, imported_at, updated_at, notes, active
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                """,
                (
                    s["id"],
                    s["master_heading"],
                    s["title"],
                    s["status"],
                    None,
                    s["body"],
                    kanban_json,
                    s["source_line_start"],
                    s["source_line_end"],
                    s["body_sha1"],
                    now,
                    now,
                    "",
                ),
            )
            con.execute(
                "INSERT INTO events(section_id, kind, payload, created_at) VALUES (?,?,?,?)",
                (s["id"], "import_insert", json.dumps({"status": s["status"]}), now),
            )
            for path in s["artifacts"]:
                con.execute(
                    "INSERT INTO artifacts(section_id, path, kind, created_at) VALUES (?,?,?,?)",
                    (s["id"], path, "path", now),
                )
            inserted += 1
        elif row["body_sha1"] != s["body_sha1"]:
            # Preserve manual status/notes if user already set status via CLI
            # Only auto-refresh status when previous status was unknown or matches old inference path:
            # keep existing status if notes contain 'status_locked' or status was set via set-status event recently.
            preserve_status = row["status"] not in ("unknown", s["status"]) and bool(
                con.execute(
                    "SELECT 1 FROM events WHERE section_id=? AND kind='set_status' LIMIT 1",
                    (s["id"],),
                ).fetchone()
            )
            new_status = row["status"] if preserve_status else s["status"]
            con.execute(
                """
                UPDATE sections SET
                    master_heading=?, title=?, status=?, body=?,
                    kanban_ids_json=?, source_line_start=?, source_line_end=?,
                    body_sha1=?, updated_at=?, active=1
                WHERE id=?
                """,
                (
                    s["master_heading"],
                    s["title"],
                    new_status,
                    s["body"],
                    kanban_json,
                    s["source_line_start"],
                    s["source_line_end"],
                    s["body_sha1"],
                    now,
                    s["id"],
                ),
            )
            con.execute(
                "INSERT INTO events(section_id, kind, payload, created_at) VALUES (?,?,?,?)",
                (
                    s["id"],
                    "import_update",
                    json.dumps({"status": new_status, "preserved": preserve_status}),
                    now,
                ),
            )
            updated += 1
        else:
            con.execute(
                "UPDATE sections SET active=1, updated_at=? WHERE id=?",
                (now, s["id"]),
            )
            unchanged += 1

    deactivated = 0
    if deactivate_missing:
        rows = con.execute("SELECT id FROM sections WHERE active=1").fetchall()
        for r in rows:
            if r["id"] not in seen_ids:
                con.execute(
                    "UPDATE sections SET active=0, updated_at=? WHERE id=?",
                    (now, r["id"]),
                )
                deactivated += 1

    con.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
        ("last_import_at", now),
    )
    con.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
        ("last_import_master", str(master_path)),
    )
    con.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
        ("last_import_sections", str(len(sections))),
    )
    con.commit()
    return {
        "parsed": len(sections),
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "deactivated": deactivated,
    }


def add_event(con: sqlite3.Connection, section_id: str, kind: str, payload: dict) -> None:
    con.execute(
        "INSERT INTO events(section_id, kind, payload, created_at) VALUES (?,?,?,?)",
        (section_id, kind, json.dumps(payload), utc_now()),
    )


def cmd_init(args: argparse.Namespace) -> int:
    con = connect(Path(args.db))
    init_schema(con)
    print(f"initialized {args.db}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    con = connect(Path(args.db))
    init_schema(con)
    stats = import_master(
        con, Path(args.master), deactivate_missing=args.deactivate_missing
    )
    print(json.dumps(stats, indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    con = connect(Path(args.db))
    init_schema(con)
    q = "SELECT id, status, title, kanban_ids_json FROM sections WHERE active=1"
    params: list[Any] = []
    if args.status:
        if args.status == "open":
            q += " AND status IN ('open','unknown','blocked','watch','parked')"
            # "open view" = not done — still allow filter
            if args.strict_open:
                q = q.replace(
                    " AND status IN ('open','unknown','blocked','watch','parked')",
                    " AND status = 'open'",
                )
        elif args.status == "not_done":
            q += " AND status != 'done'"
        else:
            q += " AND status = ?"
            params.append(args.status)
    if args.query:
        q += " AND (id LIKE ? OR title LIKE ? OR body LIKE ?)"
        like = f"%{args.query}%"
        params.extend([like, like, like])
    q += " ORDER BY source_line_start DESC LIMIT ?"
    params.append(args.limit)
    rows = con.execute(q, params).fetchall()
    if args.json:
        out = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "status": r["status"],
                    "title": r["title"],
                    "kanban_ids": json.loads(r["kanban_ids_json"] or "[]"),
                }
            )
        print(json.dumps(out, indent=2))
    else:
        for r in rows:
            kids = ",".join(json.loads(r["kanban_ids_json"] or "[]")[:4])
            print(f"{r['status']:8}  {r['id'][:48]:48}  {kids}")
        print(f"— {len(rows)} rows", file=sys.stderr)
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    con = connect(Path(args.db))
    row = con.execute(
        "SELECT * FROM sections WHERE id = ? OR master_heading LIKE ?",
        (args.id, f"%{args.id}%"),
    ).fetchone()
    if not row:
        # fuzzy id prefix
        row = con.execute(
            "SELECT * FROM sections WHERE id LIKE ? ORDER BY updated_at DESC LIMIT 1",
            (f"{args.id}%",),
        ).fetchone()
    if not row:
        print(f"not found: {args.id}", file=sys.stderr)
        return 1
    d = dict(row)
    d["kanban_ids"] = json.loads(d.pop("kanban_ids_json") or "[]")
    if not args.full:
        d["body"] = (d.get("body") or "")[:2000]
    print(json.dumps(d, indent=2, default=str))
    return 0


def cmd_set_status(args: argparse.Namespace) -> int:
    con = connect(Path(args.db))
    status = args.status.lower().strip()
    row = con.execute("SELECT id, status FROM sections WHERE id=?", (args.id,)).fetchone()
    if not row:
        row = con.execute(
            "SELECT id, status FROM sections WHERE id LIKE ? LIMIT 1",
            (f"{args.id}%",),
        ).fetchone()
    if not row:
        print(f"not found: {args.id}", file=sys.stderr)
        return 1
    now = utc_now()
    con.execute(
        "UPDATE sections SET status=?, updated_at=? WHERE id=?",
        (status, now, row["id"]),
    )
    add_event(
        con,
        row["id"],
        "set_status",
        {"from": row["status"], "to": status, "note": args.note or ""},
    )
    if args.note:
        con.execute(
            "UPDATE sections SET notes = CASE WHEN notes='' THEN ? ELSE notes || '\n' || ? END WHERE id=?",
            (args.note, f"[{now}] {args.note}", row["id"]),
        )
    con.commit()
    print(json.dumps({"id": row["id"], "status": status}))
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    con = connect(Path(args.db))
    row = con.execute("SELECT id, notes FROM sections WHERE id=?", (args.id,)).fetchone()
    if not row:
        row = con.execute(
            "SELECT id, notes FROM sections WHERE id LIKE ? LIMIT 1",
            (f"{args.id}%",),
        ).fetchone()
    if not row:
        print(f"not found: {args.id}", file=sys.stderr)
        return 1
    now = utc_now()
    line = f"[{now}] {args.text}"
    notes = (row["notes"] + "\n" + line).strip() if row["notes"] else line
    con.execute(
        "UPDATE sections SET notes=?, updated_at=? WHERE id=?",
        (notes, now, row["id"]),
    )
    add_event(con, row["id"], "note", {"text": args.text})
    con.commit()
    print(json.dumps({"id": row["id"], "ok": True}))
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    """Add a new section row without editing MASTER (preferred going forward)."""
    con = connect(Path(args.db))
    init_schema(con)
    now = utc_now()
    sid = args.id or slugify_heading(args.title)
    if con.execute("SELECT 1 FROM sections WHERE id=?", (sid,)).fetchone():
        print(f"exists: {sid}", file=sys.stderr)
        return 1
    kids = args.kanban or []
    con.execute(
        """
        INSERT INTO sections(
            id, master_heading, title, status, priority, body,
            kanban_ids_json, body_sha1, imported_at, updated_at, notes, active
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,1)
        """,
        (
            sid,
            args.title,
            args.title,
            args.status,
            args.priority,
            args.body or "",
            json.dumps(kids),
            hashlib.sha1((args.title + (args.body or "")).encode()).hexdigest(),
            now,
            now,
            "",
        ),
    )
    add_event(con, sid, "create", {"status": args.status})
    con.commit()
    print(json.dumps({"id": sid, "status": args.status}))
    return 0


def cmd_export_md(args: argparse.Namespace) -> int:
    con = connect(Path(args.db))
    q = "SELECT * FROM sections WHERE active=1"
    params: list[Any] = []
    if args.status == "not_done":
        q += " AND status != 'done'"
    elif args.status and args.status != "all":
        if args.status == "open":
            q += " AND status IN ('open','unknown','blocked','watch')"
        else:
            q += " AND status = ?"
            params.append(args.status)
    q += " ORDER BY updated_at DESC LIMIT ?"
    params.append(args.limit)
    rows = con.execute(q, params).fetchall()
    lines = [
        f"# Task tracker open view",
        f"",
        f"Generated: {utc_now()}  ",
        f"Source DB: `{args.db}`  ",
        f"Policy: DB is live SSOT for status; MASTER markdown is archive.",
        f"",
        f"| status | id | title | kanban |",
        f"|--------|----|-------|--------|",
    ]
    for r in rows:
        kids = ", ".join(json.loads(r["kanban_ids_json"] or "[]")[:6])
        title = (r["title"] or "").replace("|", "/")[:80]
        lines.append(f"| {r['status']} | `{r['id']}` | {title} | {kids} |")
    lines.append("")
    lines.append(f"_{len(rows)} rows_")
    text = "\n".join(lines) + "\n"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(rows)} rows)")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    con = connect(Path(args.db))
    init_schema(con)
    total = con.execute("SELECT COUNT(*) c FROM sections WHERE active=1").fetchone()["c"]
    by = con.execute(
        "SELECT status, COUNT(*) c FROM sections WHERE active=1 GROUP BY status ORDER BY c DESC"
    ).fetchall()
    meta = {
        r["key"]: r["value"]
        for r in con.execute("SELECT key, value FROM meta").fetchall()
    }
    print(
        json.dumps(
            {
                "db": args.db,
                "active_sections": total,
                "by_status": {r["status"]: r["c"] for r in by},
                "meta": meta,
            },
            indent=2,
        )
    )
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    args.query = args.query
    args.status = None
    args.strict_open = False
    args.limit = args.limit
    args.json = args.json
    return cmd_list(args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="MASTER → SQLite task tracker")
    p.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help=f"SQLite path (default {DEFAULT_DB})",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="Create schema")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("import-master", help="Parse MASTER markdown into DB")
    sp.add_argument("--master", default=str(DEFAULT_MASTER))
    sp.add_argument(
        "--deactivate-missing",
        action="store_true",
        help="Mark sections absent from MASTER as active=0",
    )
    sp.set_defaults(func=cmd_import)

    sp = sub.add_parser("list", help="List sections")
    sp.add_argument("--status", default=None, help="done|open|not_done|blocked|...")
    sp.add_argument("--strict-open", action="store_true")
    sp.add_argument("--query", default=None)
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("search", help="Search id/title/body")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=30)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("get", help="Show one section")
    sp.add_argument("id")
    sp.add_argument("--full", action="store_true")
    sp.set_defaults(func=cmd_get)

    sp = sub.add_parser("set-status", help="Update status (live SSOT write)")
    sp.add_argument("id")
    sp.add_argument("status")
    sp.add_argument("--note", default="")
    sp.set_defaults(func=cmd_set_status)

    sp = sub.add_parser("note", help="Append note")
    sp.add_argument("id")
    sp.add_argument("text")
    sp.set_defaults(func=cmd_note)

    sp = sub.add_parser("add", help="Create section row (no MASTER edit)")
    sp.add_argument("--title", required=True)
    sp.add_argument("--id", default=None)
    sp.add_argument("--status", default="open")
    sp.add_argument("--priority", default=None)
    sp.add_argument("--body", default="")
    sp.add_argument("--kanban", nargs="*", default=[])
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("export-md", help="Write short markdown view")
    sp.add_argument("--status", default="not_done")
    sp.add_argument("--limit", type=int, default=200)
    sp.add_argument("-o", "--out", default=str(DEFAULT_OPEN_MD))
    sp.set_defaults(func=cmd_export_md)

    sp = sub.add_parser("stats", help="Counts + meta")
    sp.set_defaults(func=cmd_stats)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
