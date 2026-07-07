# Opportunity Score Expansion Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Extend `score_opportunity` to support multiple modes ("oversold", "bullish", "hybrid") with configurable settings for toggling.

**Architecture:**
- Update `score_opportunity` signature to include `mode` parameter.
- Implement conditional scoring logic based on `mode`.
- Move weights to config or constant dictionary accessible via settings.
- Ensure backcompat for existing calls.

**Tech Stack:** Python 3.11

---

### Task 1: Update Constants and Config Structure
**Objective:** Define mode-specific weights.

**Files:**
- Modify: `projects/crypto-trading-bot/phase6/core/opportunity_scanner.py`

**Step 1: Define Scoring Modes**
Add dictionary definitions for weights at the top level or load them from config.

```python
SCORING_MODES = {
    "oversold": {
        "rsi_weight": 0.50,
        "sent_weight": 0.15,
        "edge_weight": 0.20,
        "div_weight": 0.15,
    },
    "bullish": {
        "rsi_weight": 0.20,
        "sent_weight": 0.30,
        "edge_weight": 0.40,
        "div_weight": 0.10,
    },
    "hybrid": {
        "rsi_weight": 0.35,
        "sent_weight": 0.25,
        "edge_weight": 0.25,
        "div_weight": 0.15,
    }
}
```

### Task 2: Refactor `score_opportunity`
**Objective:** Update signature and logic.

**Files:**
- Modify: `projects/crypto-trading-bot/phase6/core/opportunity_scanner.py`

**Step 1: Update Signature**
```python
def score_opportunity(
    pair: str,
    rsi: float,
    sentiment: float,
    vol: float,
    momentum_pct: float,
    is_current: bool,
    mode: str = "oversold"
) -> Tuple[float, str]:
```

**Step 2: Update Logic**
Use selection from `SCORING_MODES` and apply weights dynamically.

### Task 3: Update Callers
**Objective:** Propagate changes to callers.

**Files:**
- Modify: `projects/crypto-trading-bot/phase6/core/opportunity_scanner.py`
- Modify: `projects/crypto-trading-bot/phase6/tests/test_isolation_bullish_entry_scorer.py` (ensure tests cover new modes)

### Task 4: Verify and Backtest
**Objective:** Validate via isolation test, then offer backtest script.

**Files:**
- Test: `projects/crypto-trading-bot/phase6/core/test_isolation_opportunity_scanner.py`

**Step 1: Run verification**
Run: `python3 -m unittest projects/crypto-trading-bot/phase6/core/test_isolation_opportunity_scanner.py`

---

Plan complete. Ready to execute using `subagent-driven-development` — I'll dispatch a fresh subagent per task with two-stage review. Shall I proceed?
