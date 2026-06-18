# Subagent Prompt — Stop-Loss Migration (Phase 6)

You are a focused coding subagent. Your only job is to complete the Stop-Loss Migration per the attached Handoff Document.

## Handoff Document (Full)
See: `handoffs/phase6/Handoff_Stop_Loss_Migration.md`

## Critical Constraints
- Work exclusively inside `phase6/core/`
- Never modify anything in `src/stop_loss/`
- Preserve exact existing stop-loss behavior
- Update `PHASE6_CURRENT_STATUS.md` when done

## Expected Deliverables
1. Updated `phase6/core/stop_loss_manager.py` (or new subpackage)
2. Updated `phase6/core/phase6_runner.py` (remove TODO, use local module)
3. Updated `phase6/core/config_loader.py` if needed
4. Test run in shadow mode with validation log

## Success Criteria (from Handoff)
- No import from `src/stop_loss/` in the runner
- Stop-loss decisions logged via TradeLedger
- Shadow mode runs cleanly for 10+ cycles
- Behavior matches pre-migration

Start by reading the full Handoff Document, then the current `phase6_runner.py` and `stop_loss_manager.py`.

Report completion by updating the Master Task Tracking List and the delegation record.