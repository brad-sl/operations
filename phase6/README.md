# Phase 6 Working Directory

**Purpose:** Single source of truth for all Phase 6 deliverables, specifications, implementation, and task tracking.

This directory exists to prevent regressions and version conflicts that have occurred when work was scattered across the repository.

---

## Directory Structure

```
phase6/
├── core/           # Production-ready Python modules (importable)
├── docs/           # Integration plans, audits, and working documents
├── specs/          # Authoritative feature specifications
├── tasks/          # Task templates, handoff documents, and checklists
├── config/         # Phase 6 specific configuration files
├── archive/        # Deprecated / backup versions (never delete without review)
├── tests/          # Unit and integration tests
└── README.md       # This file
```

---

## Rules of Engagement

1. **This is the only place** for new Phase 6 work.
2. **Never edit** files directly in `scripts/phase6/` or root-level Phase 6 files unless explicitly migrating them here first.
3. All new modules go in `core/`.
4. All specs and planning documents go in `specs/` or `docs/`.
5. Before starting work, read the latest files in `docs/`.
6. After significant changes, update the relevant document in `docs/`.
7. Use `archive/` for anything being replaced (with a clear note).

---

## Current Canonical Documents

- `docs/PHASE6_SINGLE_SOURCE_AUDIT.md` — Definitive mapping of best sources
- `docs/PHASE6_REINTEGRATION_PLAN.md` — High-level roadmap

---

## Git Sync

This directory is tracked in the main `brad-sl/operations` repository.

- All changes here should be committed with clear messages.
- Prefer small, frequent commits over large refactors.
- Tag major versions (e.g. `phase6/v1.0`).

---

## Getting Started

```bash
cd phase6
# Read the latest audit and plan
cat docs/PHASE6_SINGLE_SOURCE_AUDIT.md
cat docs/PHASE6_REINTEGRATION_PLAN.md
```

**Owner:** Brad + Scotty (AI collaborator)  
**Last Updated:** 2026-05-18