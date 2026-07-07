# Stop-Loss Emergency Audit and Enforcement Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan.

**Goal:** Audit all current positions for active stop-loss (SL) protections and enforce them for the upcoming "triple witching" event.

**Architecture:**
- Use `StopLossManager` to verify active SL protections on all open positions.
- Automate re-attachment for any positions identified without an active SL.
- Log findings for user review.

---

### Task 1: Audit Active Positions
**Objective:** Verify which positions currently have active server-side SL protections.

**Files:**
- Use: `projects/crypto-trading-bot/scripts/phase6/attach_sl_to_current_positions.py` or `set_stop_loss_utility.py`

**Step 1: Execute Audit**
```bash
python3 projects/crypto-trading-bot/set_stop_loss_utility.py --list-positions
# Verify status for each pair
```

### Task 2: Enforce SL Protection
**Objective:** Attach a 3% trailing/fixed stop-loss to any unprotected positions.

**Files:**
- Script: `projects/crypto-trading-bot/scripts/phase6/attach_sl_to_current_positions.py`

**Step 1: Execute Enforcement**
```bash
python3 projects/crypto-trading-bot/scripts/phase6/attach_sl_to_current_positions.py --confirm-live
```

---

Plan complete. Ready to execute using `subagent-driven-development` — I'll dispatch a fresh subagent per task with two-stage review. Shall I proceed?
