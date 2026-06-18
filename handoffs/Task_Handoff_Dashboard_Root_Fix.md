# Task Handoff: Dashboard Root Route Diagnosis

**Task ID:** dashboard-root-fix-review  
**Parent Task:** t_0b501c7f (Rebuild clean Phase 6 Dashboard)  
**Assigned To:** code-reviewer  
**Date:** 2026-05-17

### Objective
Diagnose why updating the root route in serve_dashboard.py is not taking effect on ports 8501 and 8502.

### Context & Background
Multiple attempts to change the root (/) handler from serving the old Phase 4b dashboard.html to the new phase6_dashboard.html have failed. The code appears correct after edits, but the legacy dashboard is still being served.

### Scope & Boundaries

**Must Do:**
- Review the current serve_dashboard.py file
- Check how the HTTP server is initialized and which file is actually being executed
- Identify why route changes are not reflected at runtime
- Provide concrete, actionable fixes

**Must Not Do:**
- Do not modify production files without explicit approval
- Do not assume the services are using the file being edited

**Files to Examine:**
- /home/brad/projects/crypto-trading-bot/serve_dashboard.py
- Running processes on ports 8501 and 8502
- Systemd service definitions for phase6-paper-dashboard and phase6-live-dashboard

### Expected Deliverables
- Clear diagnosis of the root cause
- Specific recommended fixes (file paths, service restarts, code changes)
- Verification steps

### Success Criteria
- Root cause identified
- Actionable fix provided that can be applied immediately

### Notes & Warnings
- The user has already manually verified that the legacy Phase 4b HTML is still being returned.
- Multiple direct edits by the orchestrator have not taken effect.
