#!/usr/bin/env python3
"""Symlink Phase6 / trading skills from default Hermes home into crypto-* profiles.

Idempotent. Relative symlinks so moves of ~/.hermes stay coherent if both sides move together.

Default sources live under ~/.hermes/skills/. Profiles load only their own
~/.hermes/profiles/<name>/skills/ tree — without this seed, workers cannot
skill_view phase6 playbooks and must rely on handoff paste alone.

Usage:
  python scripts/ops/seed_phase6_profile_skills.py
  python scripts/ops/seed_phase6_profile_skills.py --profiles crypto-analyst crypto-engineer
  python scripts/ops/seed_phase6_profile_skills.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
DEFAULT_SKILLS = HOME / "skills"

LINKS = [
    ("trading-bot-operations", "trading-bot-operations"),
    ("soft-down-recovery-implementer", "soft-down-recovery-implementer"),
    ("scale-first-action-architecture", "scale-first-action-architecture"),
    ("crypto-data-acquisition", "crypto-data-acquisition"),
    (
        "software-development/trading-config-path-integrity",
        "software-development/trading-config-path-integrity",
    ),
    (
        "software-development/offline-strategy-honesty",
        "software-development/offline-strategy-honesty",
    ),
    (
        "software-development/regime-premise-and-basket",
        "software-development/regime-premise-and-basket",
    ),
]

DEFAULT_PROFILES = [
    "crypto-analyst",
    "crypto-engineer",
    "crypto-orchestrator",
    "crypto-monitor",
]


def seed(profiles: list[str], *, dry_run: bool = False) -> list[str]:
    log: list[str] = []
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = HOME / "backups" / f"phase6-seed-{ts}"
    if not dry_run:
        backup.mkdir(parents=True, exist_ok=True)

    for profile in profiles:
        pskills = HOME / "profiles" / profile / "skills"
        if not pskills.is_dir():
            log.append(f"SKIP {profile}: no skills dir at {pskills}")
            continue
        if not dry_run:
            tops = sorted(p.name for p in pskills.iterdir())
            (backup / f"{profile}-skills-top.json").write_text(
                json.dumps(tops, indent=2)
            )

        for src_rel, dest_rel in LINKS:
            src = DEFAULT_SKILLS / src_rel
            dest = pskills / dest_rel
            if not src.exists():
                log.append(f"MISS src {src_rel}")
                continue
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_symlink():
                if dest.resolve() == src.resolve():
                    log.append(f"OK {profile}:{dest_rel}")
                    continue
                log.append(f"REPLACE {profile}:{dest_rel}")
                if not dry_run:
                    dest.unlink()
            elif dest.exists():
                log.append(f"SKIP real-dir {profile}:{dest_rel}")
                continue
            else:
                log.append(f"LINK {profile}:{dest_rel}")
            if dry_run:
                continue
            rel = os.path.relpath(src, start=dest.parent)
            dest.symlink_to(rel)

    if not dry_run:
        (backup / "seed-log.json").write_text(json.dumps(log, indent=2))
        log.append(f"BACKUP {backup}")
    return log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", nargs="*", default=DEFAULT_PROFILES)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    for line in seed(args.profiles, dry_run=args.dry_run):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
