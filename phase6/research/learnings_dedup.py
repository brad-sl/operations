"""
Deduplicate analyst_learnings.json by (cycle, thesis prefix) — keep latest.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def dedup_learnings(data: Dict[str, Any], max_entries: int = 40) -> Dict[str, Any]:
    entries = list(data.get("learnings") or [])
    seen = {}
    for e in reversed(entries):
        key = (e.get("cycle"), (e.get("thesis") or "")[:80])
        if key not in seen:
            seen[key] = e
    deduped = list(reversed(seen.values()))
    if len(deduped) > max_entries:
        deduped = deduped[-max_entries:]
    data["learnings"] = deduped
    return data


def dedup_learnings_file(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path) as f:
        data = json.load(f)
    before = len(data.get("learnings") or [])
    data = dedup_learnings(data)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return before - len(data.get("learnings") or [])