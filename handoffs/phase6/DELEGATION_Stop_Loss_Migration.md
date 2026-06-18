# Delegation Record: Stop-Loss Migration

**Delegated:** 2026-06-01
**Handoff:** Handoff_Stop_Loss_Migration.md
**Status:** Delegated (tool failure — manual handoff provided)

**Goal for Subagent:**
Migrate stop-loss logic from src/ into phase6/core/ so the live runner no longer depends on legacy code.

**Full Handoff Document:**
See `handoffs/phase6/Handoff_Stop_Loss_Migration.md`

**Instructions to Subagent:**
- Read the full handoff document above.
- Work only inside `phase6/core/`.
- Do not touch `src/stop_loss/`.
- Update `PHASE6_CURRENT_STATUS.md` upon completion.
- Validate using shadow mode runs.

**Next Action:**
Once the `delegate_task` tool is fixed, re-delegate using this record.