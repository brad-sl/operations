# Phase 6 Migration Status

**Date:** 2026-05-18

## Cleanup & Deprecation Complete

- [x] Moved old `scripts/phase6/` directory to `phase6/archive/scripts_phase6_old`
- [x] Archived backup files (`phase6.py.backup.*`, old dashboards)
- [x] Added `archive/README.md` with clear deprecation notice

## Current State

**Active Development Location:** `phase6/core/`

**Deprecated Locations (do not use for new work):**
- `scripts/phase6/` → now in `archive/`
- Root-level `phase6*.py` backups → now in `archive/`
- Old dashboard HTML files → now in `archive/`

## Naming Normalization

All modules in `phase6/core/` now follow consistent naming:
- `*_runner.py` → `Phase6Runner`
- `*_manager.py` → `StopLossManager`, `LivePortfolioManager`
- `*_engine.py`, `*_scorer.py`, `*_loader.py`

**Next:** Update any remaining references in docs or configs that point to old locations.