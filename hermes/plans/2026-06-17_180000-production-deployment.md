# Production Deployment Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan.

**Goal:** Promote all fixes (SL precision, API wrappers, Smoke Test) to the production environment and activate the robust protection system.

**Architecture:**
- Sync changes to the production branch if applicable.
- Restart production services (`phase5.service`, `crypto-dashboard.service`).
- Set up a cron-based health-check monitor using the new `RobustSmokeTest.py`.

---

### Task 1: Deployment & Service Restart
**Objective:** Apply changes and cycle production services.

**Files:**
- Commands: `systemctl` (for service management)

**Step 1: Restart services**
```bash
sudo systemctl restart phase5
sudo systemctl restart crypto-dashboard
```

### Task 2: Implement Persistent Diagnostic Health Check
**Objective:** Maintain protection via recurring smoke tests.

**Step 1: Setup Cron**
```bash
# Every hour, run smoke test to ensure protections haven't dropped
0 * * * * /usr/bin/python3 /home/brad/projects/crypto-trading-bot/RobustSmokeTest.py >> /var/log/smoke_test.log 2>&1
```

---

Plan complete. Ready to execute using `subagent-driven-development` — I'll dispatch a fresh subagent to promote to prod. Shall I proceed?
