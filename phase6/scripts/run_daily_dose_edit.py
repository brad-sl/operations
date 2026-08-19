#!/usr/bin/env python3
"""
Daily Dose D1 — content-editor package writer.

Reads data/state/daily_dose_latest.json
Writes data/state/daily_dose_edited.json with editorial_review.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phase6.core.daily_dose_publish import (  # noqa: E402
    build_edited_package,
    load_latest,
    write_edited,
)
from phase6.core.paths import DAILY_DOSE_EDITED, DAILY_DOSE_LATEST  # noqa: E402


def _parse_overrides(pairs: list[str], label: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--{label} needs id=value, got {p!r}")
        k, v = p.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily Dose D1 editor package")
    ap.add_argument("--input", type=Path, default=DAILY_DOSE_LATEST)
    ap.add_argument("--output", type=Path, default=DAILY_DOSE_EDITED)
    ap.add_argument(
        "--status",
        required=True,
        choices=["APPROVED", "REVISE", "DRAFT", "approved", "revise", "draft"],
    )
    ap.add_argument("--reviewer", default="content-editor")
    ap.add_argument("--notes", default="")
    ap.add_argument("--top", type=int, default=5, help="Max items in edited package (TG cap)")
    ap.add_argument("--keep-ids", default="", help="Comma-separated ids (order preserved)")
    ap.add_argument("--drop-ids", default="", help="Comma-separated ids to drop")
    ap.add_argument(
        "--title-override",
        action="append",
        default=[],
        help="id=New title (repeatable)",
    )
    ap.add_argument(
        "--why-override",
        action="append",
        default=[],
        help="Deprecated no-op (platform-why retired 2026-08-13)",
    )
    ap.add_argument("--print", action="store_true", dest="do_print")
    args = ap.parse_args()

    latest = load_latest(args.input)
    keep = [x.strip() for x in args.keep_ids.split(",") if x.strip()] or None
    drop = [x.strip() for x in args.drop_ids.split(",") if x.strip()] or None
    overrides = _parse_overrides(args.title_override, "title-override")
    if args.why_override:
        print("note: --why-override ignored (platform-why retired)", file=sys.stderr)

    pkg = build_edited_package(
        latest,
        status=args.status.upper(),
        reviewer=args.reviewer,
        notes=args.notes,
        keep_ids=keep,
        drop_ids=drop,
        top_n=args.top,
        title_overrides=overrides or None,
    )
    path = write_edited(pkg, args.output)
    er = pkg["editorial_review"]
    print(
        f"Edited package → {path} status={er['status']} "
        f"items={len(pkg['items'])} dropped={er.get('dropped_from_draft', 0)} "
        f"btc_tape={er.get('btc_tape_count')}"
    )
    if args.do_print:
        for i, it in enumerate(pkg["items"], 1):
            print(f"  {i}. {it.get('title_display') or it.get('title')}")
            print(f"     lane={it.get('story_lane')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
