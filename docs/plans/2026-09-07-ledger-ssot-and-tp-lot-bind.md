# Ledger SSOT + Live-TP Lot Bind Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task after Brad **go**.

**Goal:** Make the trade journal the reliable source of truth for fills/holdings/cost basis, stop live TP from firing on ghost/stale lots, document the ledger system, and run an independent design/execution review.

**Architecture:** Three hard layers, no time-buffer bandaid.  
(1) **Write path** — every successful live BUY/SELL hits TradeLedger before any exit cycle can see the bag.  
(2) **Read path** — FIFO inventory never drops SELL qty; open-lot cost only when layers match exchange qty; refuse `last_buy_flat` / phantom LIFO for live TP.  
(3) **Exit gate** — live TP resolves entry as verified fill → matching FIFO lot only; otherwise no live exit (keep mode=live, fail closed).  
Scheduled later: ghost-layer repair (D). Separate track: ledger system doc + independent review report.

**Tech Stack:** Python Phase 6 (`phase6/core/*`, `trading/executor.py`), JSONL TradeLedger, isolation tests under `phase6/core/test_isolation_*` / `scripts/phase6/`.

**Incident trigger (2026-09-07 ~21:01 PT):** Daily rebalance bought LINK 5.92 @ ~$12.658 (order `328bd360`); buy never ledgered; FIFO still held ~44 phantom LINK from Aug 24 operator trim SELL missing exit_price; live fixed TP used entry $11.641 → fake +8.7% → sold ~15s later. Real PnL ≈ −0.06%.

---

## Decisions locked (Brad 2026-09-07)

| Q | Lock |
|---|------|
| Fix shape | **A + B + C now**; **schedule D** (ghost repair) after |
| Entry authority | **(1) verified exchange fill for current bag → (2) FIFO open layers if qty matches**; no last-buy forever for live TP |
| Live TP | **Stay ON**; good data + fail-closed C |
| Ghost inventory | **A+B first**; no auto-rebuild on boot in this card |
| Extra | Reliable journal SSOT; **document ledger system**; **independent design+execution review** |

## Must not touch

- Live book discretionary orders / manual sells
- `exit_automation.json` mode flip off
- TP % / trail knobs / post-TP 24h duration
- Capital holds / seat sizing / pair allowlists
- Auto ghost rebuild on runner boot (D is scheduled, not this ship)

## Proof of done (acceptance)

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. python3 phase6/core/test_isolation_ledger_write_path.py
PYTHONPATH=. python3 phase6/core/test_isolation_position_cost_basis_sell_qty.py
PYTHONPATH=. python3 phase6/core/test_isolation_live_tp_lot_bind_entry.py
# Expected: all PASS
# Replay fixture: fresh buy @ mark, phantom last_buy lower → live TP must NOT fire
# Replay fixture: buy ledgered, mark +6.1% on that entry → fixed TP may fire
```

Docs on disk:

- `docs/LEDGER_SYSTEM_SSOT.md` (writers, readers, authority order, failure modes)
- `reports/LEDGER_INDEPENDENT_REVIEW_2026-09-07.md` (design + execution findings; pre- and post-fix notes)

---

### Task 1: Isolation — missing BUY write reproduces LINK class

**Objective:** Failing test that TradeExecutor / OrderExecutor path without ledger wire leaves no BUY row.

**Files:**

- Create: `phase6/core/test_isolation_ledger_write_path.py`

**Step 1:** Write test that constructs OrderExecutor **with** `trade_ledger=TradeLedger(path=tmp)` and one **without**; successful `execute_buy` mock must append BUY only when ledger wired.

**Step 2:** Assert TradeExecutor rebalance BUY either writes via injected ledger hook or documents required runner post-hook (test the contract we will implement in Task 2).

**Step 3:** Run — expect FAIL until Task 2.

---

### Task 2: Wire ledger on all live execution paths (A)

**Objective:** Every successful live BUY/SELL appends a TradeLedger row with pair, side, qty, fill px, order_id, signal_source, timestamp.

**Files:**

- Modify: `phase6/core/phase6_runner.py` (~290) — pass `trade_ledger=self.trade_ledger` into `OrderExecutor(...)`
- Modify: `trading/executor.py` — accept optional `trade_ledger`; after successful buy/sell call `log_execution_result` (or thin wrapper)
- Modify: `phase6/core/phase6_runner.py` `_execute_trade_plan` — **defense in depth**: after results, for each successful BUY/SELL, if order_id not already in recent ledger, `log_execution_result` / `log_trade` (idempotent by order_id)
- Modify: `phase6/core/order_executor.py` — keep `_record_to_ledger`; ensure limit-first path still records when `record_ledger=True` (default)

**Rules:**

- Prefer fill-verified `average_filled_price` + `filled_size` when present
- Idempotent: same `order_id` must not double-count inventory (dedupe in ledger write or cost basis already dedupes by order_id — verify)
- Never block the exchange fill on ledger failure — log **ERROR** + optional TG ops page; fill already happened
- SELL rows must carry `exit_price` (fill) even for operator trims

**Step:** Re-run Task 1 tests → PASS.

---

### Task 3: Isolation — FIFO must apply SELL qty without price (B)

**Objective:** Operator-trim style SELL with qty + entry_price but no exit_price still reduces layers.

**Files:**

- Create: `phase6/core/test_isolation_position_cost_basis_sell_qty.py`

**Fixture:** BUY 164.59 @ 11.60; SELL 32.34 with only `entry_price=11.57` (no exit); remaining layers qty ≈ 132.25, not 164.59.

**Also:** When `expected_qty>0` and `ledger_qty≈0`, must **not** return `last_buy_flat` as a trusted open-lot cost (return `None, "flat_or_unknown"` or equivalent).

---

### Task 4: Fix FIFO / average_cost (B)

**Objective:** Inventory accounting is qty-first; price is for cost, not for whether the SELL happened.

**Files:**

- Modify: `phase6/core/position_cost_basis.py` `_fifo_layers_from_trades` and `average_cost_from_trades`

**Behavior:**

```text
SELL with qty>0:
  reduce layers even if fill px missing
  cost reduction uses exit_price or average_filled_price or price or entry_price (last resort)
  if still no px: reduce qty only (inventory truth > perfect cost)

When ledger_qty ~ 0:
  if expected_qty > 0: return None, "ledger_flat_exchange_open"  # NOT last_buy_flat
  else: return None, "flat"

When drift > tol and LIFO cannot cover expected_qty:
  return None, "ledger_exchange_qty_mismatch"  # do not invent last_buy
```

**Step:** Task 3 tests PASS. Re-check live LINK: `average_cost_for_pair(..., expected_qty=5.92)` must not return 11.641 from ghosts once repair optional; with current ghosts after B alone, mismatch path should refuse not invent.

---

### Task 5: Isolation — live TP fail-closed on bad basis (C)

**Objective:** LINK 2026-09-07 class cannot live-exit.

**Files:**

- Create: `phase6/core/test_isolation_live_tp_lot_bind_entry.py`
- Extend patterns from: `phase6/core/test_isolation_shadow_tp.py`, live TP exit tests

**Cases:**

1. Position held, entry resolves `last_buy_flat` or `ledger_flat_exchange_open` or `unknown` → **no** live fixed_tp/trail execute
2. Fresh fill lot: entry_px = fill, mark = fill * 1.061 → fixed_tp **may** signal
3. Phantom LIFO vs exchange qty mismatch source → no live execute
4. Peak-lot bind still resets on new entry (UNI regression stays green)

---

### Task 6: Implement TP entry authority + gate (C)

**Objective:** Live exits only on trusted lot-bound entry.

**Files:**

- Modify: `phase6/core/shadow_tp.py` `resolve_entry`, `evaluate_signals` / live execute path

**Authority order (locked):**

1. Verified fill / position with `entry_basis` from this bag (incl. protective registry **only if** qty matches open stop size for current bag within tol)
2. FIFO `average_cost_for_pair` when basis in `{ledger_avg_cost, ledger_lifo_exchange_qty}` **and** ledger open qty within ~5% of exchange qty
3. Else `entry=None` → **skip live exit** (still may log shadow would-fire with `blocked_reason=untrusted_entry`)

**Do not use for live execute:** `last_buy_flat`, `last_buy_ledger_drift`, bare `entry_from_ledger_last_buy` when FIFO flat, lifetime averages.

**Logging:** `[LIVE-TP] blocked LINK-USD reason=untrusted_entry src=...`

**Step:** Task 5 PASS; existing shadow_tp isolations still PASS.

---

### Task 7: Document ledger system SSOT

**Objective:** One doc traders/agents can trust.

**Files:**

- Create: `docs/LEDGER_SYSTEM_SSOT.md`

**Contents:**

1. Purpose (journal for traders: timing, holdings, fills, basis, exits)
2. Writers table (OrderExecutor, TradeExecutor, fill reconciler, dust sweep, protected exit, operator scripts) + required fields
3. Readers table (dashboard trades, cost basis, shadow TP, buy blocks, performance)
4. Authority order for entry (same as C)
5. File paths (`trades/phase6_trades.jsonl`, exchange fills, protective registry, qty_ssot)
6. Failure modes (this incident) + how each layer prevents recurrence
7. How to verify a fill is journaled (rg order_id; isolation cmds)
8. What is **not** SSOT (capital_events mis-tags, recovery_state.json alone, UI slice bugs)

Cross-link: `docs/DATA_FLOW_AND_LOCATIONS.md`, `docs/PHASE6_DASHBOARD_DATA_SPEC.md`.

---

### Task 8: Independent design + execution review

**Objective:** Second-pass critique not written by the implementer of Tasks 2–6 (delegate or separate pass).

**Files:**

- Create: `reports/LEDGER_INDEPENDENT_REVIEW_2026-09-07.md`

**Review must cover:**

- Design: single vs dual executor ledger responsibility; idempotency; crash between fill and ledger write; multi-lot average vs tryout lots
- Execution: scan for other writers that omit exit_price; other readers that call `entry_from_ledger_last_buy` for live risk; TradeExecutor sell path; paper/shadow pollution
- Residual risks after A+B+C; whether D is still needed and how big
- Explicit **go/no-go** on restarting runner with live TP still on

**Method:** `delegate_task` with read-only mandate after code lands, **or** same session second pass with fresh file reads only — no rubber stamp.

---

### Task 9: Schedule D (ghost repair) — plan only artifact

**Objective:** Do not run destructive repair in this ship; schedule clearly.

**Files:**

- Create: `docs/plans/2026-09-07-ledger-ghost-repair-D-scheduled.md` (short)

**D outline (future go):**

- Script: list pairs where FIFO open qty ≫ exchange qty
- Emit proposed compensating ledger rows or ops_correction events (no silent rewrite of history without audit trail)
- Dry-run default; `--execute` needs Brad go
- LINK: account for skipped 32.34 operator trim

---

### Task 10: Deploy verification (post-go ops)

**Objective:** Prove production path after runner restart.

**Steps (ops, after Brad go on deploy):**

1. Restart phase6 live runner so wired executor loads
2. Confirm no open crypto bag needs emergency action (book leave-as-is)
3. On next successful micro BUY (or paper fixture in shadow): ledger contains BUY order_id before next shadow_tp cycle
4. `rg "LIVE-TP. blocked|untrusted_entry" logs/phase6_runner.log` after a cycle with any mismatch
5. Dashboard Trades newest-first shows BUY then SELL when both exist

---

## Out of scope

- Buffer/min-hold time as primary fix
- Turning live TP off
- Full Coinbase history rebuild on boot
- Changing fixed_tp 6% / trail 4/2
- Dashboard UI redesign (honesty only if a number is wrong due to basis)

## Rollback

- Revert PR / git revert on `shadow_tp.py` + cost_basis + executor wires
- Live TP fail-closed is safe-fail (fewer exits), not more risk
- Ledger writes are additive; worst case duplicate order_id — dedupe must be in place before ship

## Commit strategy

Feature branch: `fix/ledger-ssot-tp-lot-bind`  
Commits per task cluster: tests → impl → docs → review.

---

## Preflight summary

- **Objective:** Reliable trade journal + fail-closed live TP lot identity; docs + independent review
- **IN scope:** A, B, C, schedule D, LEDGER_SYSTEM_SSOT.md, independent review report, isolation proofs
- **OUT of scope:** buffer-only, TP off, auto ghost rebuild, knob changes, live discretionary trades
- **Must not touch:** live book / exit mode off / capital holds without separate go
- **Decisions locked:** A+B+C; entry 1→2; TP on; D scheduled after A+B
- **BoN:** skipped (single locked path)
- **Plan path:** `docs/plans/2026-09-07-ledger-ssot-and-tp-lot-bind.md`
- **Proof of done:** three isolation modules PASS + docs/report on disk
- **Awaiting:** Brad **go** to implement
