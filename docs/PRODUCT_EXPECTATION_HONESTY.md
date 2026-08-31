# Product expectation honesty (universal rule)

**Status:** STANDING · applies to all Phase 6 / platform surfaces  
**Origin:** Brad 2026-08-22 — Signals BUY vs REGIME-CASH new-seat gate; CS 101  
**Class:** same severity as **wrong dashboard numbers = bug**

---

## Rule (one line)

> **If a gate, floor, cooldown, cap, or mode can stop or change an outcome, any UI, API, alert, brief, or cron copy that implies that outcome must surface the gate.**

Setting proper expectations up front prevents false confidence and future escalations.

---

## What this means

| Do | Don't |
|----|--------|
| Show **signal** and **deploy** as separate facts when they differ | Paint a green BUY that cannot clear entry |
| Label strength honestly (mild sent ≠ strong bull color) | Vanity-green weak values |
| Name the floor in hover/badge (`new≥0.15`, `·gated`, reason text) | Leave knobs “under the table” |
| Prefer `·ready` / `·gated` / `·blocked` over a single misleading status | Coerce Status to hide the gate |
| Treat missing telegraph as a **product bug** (fix + verify) | Explain only in chat after Brad asks |

---

## Canonical examples

1. **Signals pane** — Status = SignalGenerator; deploy = REGIME-CASH + cooldown + size.  
   `·gated` (pair column) when BUY fails entry (e.g. empty seat sent &lt; `min_sentiment_new_pair`).
   Status column stays plain `BUY`/`HOLD`/`SELL` — gate state is the flag, not `BUY·gate`.  
   Sent. colors strength-scaled to live floors. See skill `phase6-dashboard-signals`.

2. **Wrong dash numbers** — any KPI that disagrees with ledger/exchange truth is a bug, not a footnote.

3. **Shadow vs live** — never imply live promote from shadow-only arms (TP, velocity, swap CF).

4. **Regime bull ≠ basket all BUY** — macro open ≠ pair trigger; copy/UI must not fuse them.

4b. **House / size / reaction (Brad 2026-08-30)** — client copy must not imply we remove exchange fees or “outsmart whales.” Prefer: fees always exist; extreme tape → stand down; gates visible. SSOT discussion: `docs/discussions/MACRO_HOUSE_SIZE_REACTION_ONGOING.md`. FAQ: External § *Who gets paid when you trade*.

5. **Soft internal budgets ≠ hard trader promises (Brad 2026-08-22)** —  
   `rebalance_cap_usd` is an internal soft budget on *some* deploy paths. ARCH-2 recovery / rotation can spend far more.  
   **Do not** show `cap $N` (or “up to $N this cycle”) on the Regime tile or trader copy.  
   Prefer stance truth only: `DEPLOY` / `PARK` · `buys gated` / `no new buys` · BTC window.  
   Corollary: **if a number is not a hard guarantee, do not print it as if it were.** Silence beats a false ceiling.

---

## Build checklist (every new surface)

Before shipping a status, badge, alert, or “will buy/sell/park” claim:

1. List gates that can veto or resize the action.  
2. For each gate: is it visible on the same surface (flag, color, hover, reason)?  
3. Would a non-expert operator form a false expectation from the default glance?  
4. If yes → change the default glance, not the docs after the fact.

---

## Non-goals

- Dumping every internal score into the main row (hover/detail is fine).  
- Removing gates to make the UI simpler.  
- Auto-trading because the UI looks “ready” — `·ready` still subject to size/cap at execution.

---

## Related

- **Skill (load this):** `ui-expectation-honesty` — checklist + when to apply  
- `phase6-dashboard-signals` — `·gated` / `·ready` / sent strength (reference impl)  
- `phase6-capital-and-dashboard-kpis` — KPI truth  
- USER memory stays light: pointer to skill only  
