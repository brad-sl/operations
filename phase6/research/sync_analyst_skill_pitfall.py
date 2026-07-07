"""
Append latest analyst evolution_note to Hermes skill pitfalls (idempotent marker).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEARNINGS = ROOT / "data/state/analyst_learnings.json"
REPO_SKILL = ROOT / "phase6/research/skills/crypto-analyst-scenario-run/SKILL.md"
MARKER_PREFIX = "<!-- pitfall:"


def latest_evolution_note() -> str | None:
    if not LEARNINGS.exists():
        return None
    with open(LEARNINGS) as f:
        data = json.load(f)
    items = data.get("learnings") or []
    if not items:
        return None
    return (items[-1] or {}).get("evolution_note")


def sync_repo_skill() -> bool:
    note = latest_evolution_note()
    if not note or not REPO_SKILL.exists():
        return False
    text = REPO_SKILL.read_text()
    slug = re.sub(r"[^a-z0-9]+", "-", note.lower())[:48].strip("-")
    marker = f"{MARKER_PREFIX} {slug} -->"
    if marker in text:
        return False
    insertion = f"\n- {note} {marker}\n"
    if "## Pitfalls" in text:
        text = text.replace("## Pitfalls", "## Pitfalls" + insertion, 1)
    else:
        text += "\n## Pitfalls\n" + insertion
    REPO_SKILL.write_text(text)
    return True


def main() -> int:
    changed = sync_repo_skill()
    print("skill pitfall synced" if changed else "skill pitfall unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())