# Streamlined Action Architecture — RSI Event · Book Rebalance · Multi-Tenant Scale

> **For Hermes:** Architecture-first. Implement only after Brad GO on this plan. Prefer subagent-driven-development + agentic-architecture (ports first, isolation tests, thin orchestrators). Do **not** live-cutover knobs or kill 2× X from this doc alone.

**Status:** PARTIAL SHIP — Brad GO 2026-09-18 Tasks 1+6 vertical slice  
**Date:** 2026-09-18  
**Shipped:** `phase6/domain/` types + dispatcher + `BookRebalanceAction` dry_run (refuse new seats) + CLI  
**Not shipped:** live order path, X spend on book action, cron cutover, RSI probe action, runner bridge  
**Goal:** Replace clock-coupled, duplicate-laden Phase-6 paths with **clean action-based components** that scale to **~1000 concurrent trader tenants** hitting endpoints at different times of day — without copying eligibility / X / seat / SL logic into every module.

**Architecture (3 lines):**  
Domain core = pure **actions** (commands) + **policies** (rules) over shared **ports**.  
Ingress = thin HTTP/CLI/cron adapters that only auth → build command → dispatch → return receipt.  
One trader today is tenant_id=`default`; multi-tenant is the same code path with isolated state namespaces.

**Tech stack:** Existing `trading/` ports (`TradingClient`, `TradeExecutor`, factory) · Phase 6 domain under `phase6/domain/` (new) · adapters under `phase6/adapters/` · single process OK initially; horizontal scale via stateless API + shared store later.

**Related (do not fork meaning):**
- `docs/plans/2026-09-15-rsi-event-x-tryout-shadow.md` — R0 product behavior
- `docs/plans/2026-09-16-rebalance-book-vs-rsi-buy-x-split.md` — product split
- `docs/plans/2026-09-15-luck-ladder-platform-refine.md` — R0–R6
- `agentic-architecture` skill + existing `trading/` hexagonal layer
- Live validate bits already shipped: `x_query_budget`, `rebalance_x_candidates`, `rsi_event_x_probe` (keep as adapters into the new core; do not grow parallel gods)

---

## 0. Why this exists (pain → target)

### Current shape (honest)

| Smell | Evidence | Scale failure mode |
|-------|----------|--------------------|
| Fat orchestrators | `phase6_runner.py` ~72KB, `regime_cash_policy.py` ~58KB, `rebalance_coordinator.py` ~35KB | Every tenant change risks the whole process |
| Duplicate policy reads | Sentiment/eligibility loaded in runner, readiness, probe, shadow, dashboard helpers | 1000 traders → 1000 divergent copies of “can buy?” |
| Clock-coupled buys | New seats hitchhike on 09/21 rebalance + full-book X | N tenants ≠ same UTC slots; thundering herd on X |
| Script sprawl | Many `run_*.py` each re-open JSON state | No single action contract; ops re-dig every time |
| State as files | `data/state/*.json` global | No tenant partition; race-prone under concurrent writes |

### Target shape

```
                    ┌─────────────────────────────────────────┐
   Cron / CLI / API │              Ingress adapters            │
   Webhook / TG     │  (auth, rate-limit, serialize command)   │
                    └──────────────────┬──────────────────────┘
                                       │ Command DTO
                                       ▼
                    ┌─────────────────────────────────────────┐
                    │           ActionDispatcher               │
                    │  idempotency key · tenant · receipt      │
                    └──────────────────┬──────────────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              ▼                        ▼                        ▼
     ┌─────────────────┐    ┌─────────────────┐      ┌─────────────────┐
     │ BookRebalance   │    │ RsiEventProbe   │      │ TryoutSeatBuy   │
     │ Action          │    │ Action          │      │ Action          │
     └────────┬────────┘    └────────┬────────┘      └────────┬────────┘
              │                      │                        │
              └──────────────────────┼────────────────────────┘
                                     ▼
                    ┌─────────────────────────────────────────┐
                    │     Shared domain services (ONCE)        │
                    │  Eligibility · SeatLedger · XBudget ·    │
                    │  Indicators · Sentiment · Protectives    │
                    └──────────────────┬──────────────────────┘
                                       │ Ports only
              ┌────────────────────────┼────────────────────────┐
              ▼                        ▼                        ▼
         MarketDataPort          SentimentPort            ExecutionPort
         (OHLCV/RSI)             (X/cache/free)           (trading/*)
         StateStorePort          AlertPort                ClockPort
```

**Scale thesis:** 1000 traders do **not** mean 1000 bots with copied modules.  
They mean 1000 **tenant contexts** calling the **same** actions with isolated state + per-tenant rate limits + shared read-through caches for public market data.

---

## 1. Design principles (non-negotiable)

1. **Actions, not scripts** — Every operator/automation path is a named action with: input DTO, output **Receipt**, idempotency key, side-effect list.
2. **Ports inward** — Domain never imports Coinbase SDK, Hermes, Telegram, or `pathlib` state layout. Adapters implement ports.
3. **Policy once** — `evaluate_buy_entry`, seat counts, tryout caps, wash band, X budget live in **one** service each. Shadows/probes/dashboard **call** them; they do not reimplement.
4. **Book ≠ Buy** — `BookRebalanceAction` **cannot** open new tryout seats. `TryoutSeatBuyAction` **cannot** rebalance weights. `RsiEventProbeAction` **cannot** place orders unless explicitly composed with buy (feature flag + GO).
5. **Replace X, don’t stack** — Sentiment spend goes through `XBudgetService` only; full-book 2× becomes one optional adapter mode to delete after cutover.
6. **Tenant-ready from day one** — Every state key and receipt includes `tenant_id` (default `"default"`). No “we’ll add multi-user later” forks.
7. **Idempotent by default** — Concurrent hits with same `idempotency_key` return the same receipt; no double X spend, no double seat.
8. **Embed only for hot path** — Duplication allowed **only** inside tight loops where call overhead dominates (e.g. per-tick mark PnL). Everything else is a shared service. Document exceptions in-code with `HOTPATH_EMBED: reason`.
9. **Measure-only until GO** — New architecture can shadow-produce receipts beside live runner; cutover is a flag, not a rewrite day.
10. **Honest receipts** — Every action returns structured reasons (`blocked_by[]`, `spent_x_pairs[]`, `orders[]`) suitable for 1000-tenant audit, not log archaeology.

---

## 2. Bounded contexts (what owns what)

| Context | Owns | Does not own |
|---------|------|--------------|
| **Identity / Tenant** | `tenant_id`, API keys binding, risk budget envelope | Trade logic |
| **Market** | OHLCV, RSI, marks, regime tags (read models) | Buys |
| **Sentiment / X** | Cache, aging, budget lanes, provider adapters | Seat opens |
| **Eligibility / Policy** | Tryout doors, blocks, floors, thaw, run-phase | Exchange I/O |
| **Book** | Targets, drift, trims, powder, protectives reattach | New tryout seats |
| **Entry** | Tryout seat lifecycle ($75, max seats, bag_id) | Full-book rebalance |
| **Exit / Protect** | SL attach, TP/trail, Preserve/E1 | Sentiment refresh |
| **Ops / Observability** | Receipts, metrics spine hooks, alerts | Policy decisions |

---

## 3. Core types (contracts first)

```python
# phase6/domain/types.py  (sketch — implement in Task 1)

from dataclasses import dataclass, field
from typing import Any, Literal, Optional
from datetime import datetime

TenantId = str  # "default" today; uuid later
ActionName = Literal[
    "book_rebalance",
    "rsi_event_probe",
    "tryout_seat_buy",
    "x_refresh_candidates",
    "protective_reconcile",
    "status_plain",
    "funnel_why",
]

@dataclass(frozen=True)
class ActionRequest:
    action: ActionName
    tenant_id: TenantId
    idempotency_key: str
    requested_at: datetime
    params: dict[str, Any] = field(default_factory=dict)
    # e.g. dry_run=True, spend_x=False, pairs=[...], force=False
    actor: str = "system"  # cron | brad | api:user | agent

@dataclass(frozen=True)
class ActionReceipt:
    action: ActionName
    tenant_id: TenantId
    idempotency_key: str
    ok: bool
    status: Literal["ok", "noop", "blocked", "error", "dry_run"]
    reasons: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()   # machine tags: spent_x:ADA-USD, latch:ADA-USD
    artifacts: dict[str, Any] = field(default_factory=dict)  # paths, order ids
    duration_ms: int = 0
    # Multi-tenant audit
    correlation_id: str = ""
```

**Rule:** CLI, cron, dashboard, and future HTTP all produce `ActionRequest` and print/store `ActionReceipt`. No action returns “vibes only.”

---

## 4. Ports (shared adapters — implement once)

| Port | Methods (minimal) | Today’s concrete | Notes |
|------|-------------------|------------------|-------|
| `MarketDataPort` | `get_rsi(pair)`, `get_mark(pair)`, `get_ohlcv(pair, tf)` | exchange / cache | Read-through cache per pair; shared across tenants |
| `SentimentPort` | `get_eng(pair)`, `refresh_pairs(pairs, lane)` | `fetch_x_sentiment` + cache | **Only** place that spends X |
| `XBudgetPort` | `can_spend(lane, pair)`, `record(lane, pair)` | `x_query_budget.py` | Promote to port; lanes: `rsi`, `rebalance`, `ops` |
| `EligibilityPort` | `evaluate_buy(pair, ctx) -> Decision` | `regime_cash_policy.evaluate_buy_entry` | **SSOT**; strip dashboard/probe copies |
| `SeatLedgerPort` | `seats_used_today()`, `record_seat(pair)`, skip stables | part of regime_cash_policy | Extract; USDT fix stays here |
| `BookPort` | `current_positions()`, `target_weights()`, `plan_delta()` | allocator / hybrid | |
| `ExecutionPort` | `execute_buy/sell`, `attach_sl` | `trading.TradeExecutor` | Already hexagonal — reuse |
| `ProtectivePort` | `reconcile(pair)`, `skip_preserve` | stop_loss_* / preserve | PAXG E1 rules stay |
| `StateStorePort` | `get/put/cas(tenant, key, value)` | files today → sqlite/redis later | **Tenant prefix mandatory** |
| `IdempotencyPort` | `begin(key) / complete(key, receipt)` | new | Prevents double spend |
| `ClockPort` | `now()` | datetime | Testable |
| `AlertPort` | `emit(level, msg, tenant)` | TG / log | |

**Duplicate purge list (explicit):** after ports land, delete or thin:

- Parallel “load sentiment + age” blocks in probe, shadow, readiness, dashboard_serve_helpers → call `SentimentPort` + shared aging helper once (`phase6/domain/sentiment_view.py`).
- Parallel basket loaders → `paths.load_trading_basket` / `buy_eligibility.load_trading_basket_set` collapse behind `BookPort` or one `BasketPort`.
- Probe/shadow re-encoding of wash trigger → one `WashTriggerService` used by both shadow (measure) and probe (spend).
- Rebalance X candidate set → already `rebalance_x_candidates`; becomes method on `BookPort` or small domain fn imported by action only.

---

## 5. Actions (the product surface)

### 5.1 `BookRebalanceAction` — streamlined rebalance

**Intent:** Maintain the **held book** for one tenant at one moment (any TOD; not only 09/21).

**Params:** `dry_run`, `allow_trims`, `spend_x_for_candidates` (default true only if lane budget allows), `reattach_protectives`.

**Algorithm:**
1. Load positions + targets via `BookPort`.
2. `candidates = held ∪ plan_delta` (never full pool) via existing pure fn.
3. Optional: `SentimentPort.refresh_pairs(candidates, lane="rebalance")` under `XBudgetPort`.
4. Build plan: trims / weight fixes / cash / powder **only**.
5. **Hard refuse:** any leg classified `new_tryout_seat` or `opportunity_entry` → drop + reason `book_rebalance_refuses_new_seats`.
6. Execute via `ExecutionPort` if not dry_run.
7. `ProtectivePort.reconcile` (Preserve skip intact).
8. Receipt with plan hash + effects.

**Not in this action:** RSI wash scan, full-book X, dual_agree swaps, promote.

**Scale:** Per-tenant lock on `book_rebalance` (one in-flight). 1000 tenants = 1000 independent locks; shared market cache.

### 5.2 `RsiEventProbeAction` — RSI event sensor

**Intent:** When structure says “wash,” refresh scarce X for top-K doors; **measure or latch only**.

**Params:** `spend_x`, `top_k` (≤2), `wash_rsi_max` (default 40), `dry_run`.

**Algorithm:**
1. Universe = eligibility tryout/thaw doors only (`EligibilityPort` list).
2. For each: RSI via `MarketDataPort`; eng via `SentimentPort` (cache, no spend yet).
3. `WashTriggerService.match(...)` → ranked pool.
4. Top-K; for each: if `spend_x` and `XBudgetPort.can_spend("rsi", pair)` → refresh one pair; record budget; update cache; if clears floor → latch (shared latch service).
5. **Never** calls `ExecutionPort` place order.
6. Receipt: trigger_pool, top_k, spent, latch writes, budget remaining.

**Compose later (separate GO):** `RsiEventProbeAction` receipt with `cleared_floor` pairs may enqueue `TryoutSeatBuyAction` — composition in dispatcher/workflow, **not** inside probe module.

### 5.3 `TryoutSeatBuyAction` — new seats only

**Intent:** Open at most one tryout seat under full safety stack.

**Params:** `pair`, `max_notional` (default 75), `limit_first` prefs, `require_fresh_sent`.

**Algorithm:**
1. `EligibilityPort.evaluate_buy` + `SeatLedgerPort` + run-phase + blocks.
2. Refuse if seat full / stable / extension / buy_block / post-SL.
3. `ExecutionPort` limit-first buy; A1 SL attach; bag_id.
4. Record seat (non-stables only).
5. Receipt with order ids / block reasons.

**Not in this action:** Basket membership edits, rebalance drift, X spray.

### 5.4 Supporting actions (ops scale)

| Action | Replaces repeated chat work |
|--------|------------------------------|
| `XRefreshCandidatesAction` | Scoped refresh (rebalance or explicit pair list) |
| `ProtectiveReconcileAction` | SL truth / PAXG E1 health |
| `StatusPlainAction` | OPS-P0-1 |
| `FunnelWhyAction` | OPS-P0-2 |
| `ForceBookRebalanceAction` | OPS-P0-3 (wraps BookRebalance + wait + receipt) |

These are the **same** dispatcher surface as trading actions — so 1000-tenant admin APIs don’t grow a second brain.

---

## 6. Multi-tenant scale model (1000 traders)

### 6.1 What is shared vs isolated

| Layer | Shared (global) | Isolated (per tenant) |
|-------|-----------------|------------------------|
| Public market OHLCV/RSI | Yes (read-through cache) | — |
| X raw for a pair at time T | Optional shared cache with TTL | Budget + “may spend” is per tenant |
| Basket / positions / seats / SL | — | Yes |
| Policy knobs (floors, caps) | Defaults in code | Tenant overrides in StateStore |
| Execution credentials | — | Yes (secret port) |
| Idempotency keys | — | Yes (`tenant_id + key`) |

### 6.2 Concurrency

- **In-process (phase 1):** `asyncio` or thread pool + **per-tenant mutex** per action class (book vs probe can overlap; two books cannot).
- **Phase 2:** Stateless API pods + Redis/SQLite for `StateStorePort` + `IdempotencyPort`; market cache in Redis.
- **X provider:** global rate limiter **in front of** `SentimentPort` (tenant budgets cannot exceed vendor caps). Fair queue: weighted round-robin by tenant tier.

### 6.3 Endpoint sketch (future HTTP; CLI is adapter #1)

```
POST /v1/tenants/{tid}/actions/book_rebalance
POST /v1/tenants/{tid}/actions/rsi_event_probe
POST /v1/tenants/{tid}/actions/tryout_seat_buy
GET  /v1/tenants/{tid}/receipts/{idempotency_key}
GET  /v1/tenants/{tid}/funnel
```

Cron becomes: “emit ActionRequest for tenant=default on schedule” — not a special snowflake script.

### 6.4 Thundering herd controls

- Jitter scheduled book rebalances across tenants (hash(tenant_id) % window).
- RSI probe is **event/poll** with per-tenant cadence caps (e.g. max 4/day) — already fits budget lanes.
- Shared market WS later; never 1000 REST full-book pulls.

---

## 7. Package layout (target)

```
phase6/
  domain/                     # pure-ish core (no exchange SDK)
    types.py                  # ActionRequest, Receipt, Decision
    dispatcher.py             # route + idempotency
    actions/
      book_rebalance.py
      rsi_event_probe.py
      tryout_seat_buy.py
      x_refresh_candidates.py
      status_plain.py
      funnel_why.py
    services/
      wash_trigger.py         # ONE wash matcher
      eligibility.py          # facade over policy SSOT
      seat_ledger.py
      x_budget.py             # move from core/
      sentiment_view.py       # age + floor helpers ONCE
      rebalance_candidates.py # move pure fn
    ports/
      __init__.py             # Protocols only
  adapters/
    state_files.py            # StateStorePort for tenant=default files
    state_sqlite.py           # later
    sentiment_x.py            # wraps fetch_x_sentiment
    market_coinbase.py
    execution_trading.py      # wraps trading.factory
    alert_telegram.py
    idempotency_files.py
  ingress/
    cli.py                    # phase6ctl actions ...
    cron_bridge.py            # thin: build request → dispatch
    http_api.py               # later FastAPI
  core/                       # LEGACY shrink-only zone
    phase6_runner.py          # becomes thin loop calling dispatcher
    ...                       # freeze new features here
trading/                      # keep — ExecutionPort adapter target
```

**Rule for agents:** New behavior lands in `domain/actions` or `domain/services`. Touching `phase6/core/*.py` requires “legacy bridge” note + sunset ticket.

---

## 8. Mapping: today → target (no big-bang)

| Today | Becomes | Migration |
|-------|---------|-----------|
| `rsi_event_x_tryout_shadow.py` | `RsiEventProbeAction(spend_x=False)` + report adapter | Shadow remains measure receipt |
| `rsi_event_x_probe.py` | same action `spend_x=True` | Delete duplicate trigger once WashTriggerService exists |
| `rebalance_x_candidates.py` | `domain/services/rebalance_candidates.py` | Import shim 1 release |
| `x_query_budget.py` | `domain/services/x_budget.py` + port | Shim |
| `rebalance_coordinator.py` + hybrid | `BookRebalanceAction` | Coordinator becomes adapter calling action |
| `regime_cash_policy.evaluate_buy_entry` | `EligibilityPort` implementation | Keep function; facade only at first |
| `refresh_sentiment.py` full book | `XRefreshCandidatesAction` modes: `full` (deprecated), `candidates` | Cutover flag |
| `phase6_runner` mid-cycle | Dispatcher poll: due actions for tenant | Thin |
| OPS force rebalance chat | `ForceBookRebalanceAction` | P0 CLI |
| Dashboard pair-signals | Read models from last receipts + EligibilityPort | No second gate engine |

---

## 9. Deduping rules (enforcement)

1. **One wash definition** — `WashTriggerService`; shadow and probe must not diverge on RSI band / stale eng rules (config single key).
2. **One buy decision** — only `EligibilityPort` / `evaluate_buy_entry`.
3. **One seat counter** — `SeatLedgerPort` (stables excluded).
4. **One X spend gate** — `XBudgetPort` before any provider call.
5. **One candidate set for book X** — held ∪ plan_delta.
6. **CI/isolation guard (Task 8):** script fails if `fetch_x_sentiment` imported outside adapters/sentiment_x.py; fails if `evaluate_buy_entry` redefined outside regime_cash_policy/eligibility facade.

---

## 10. Security & safety at scale

- Per-tenant credentials never in domain.
- `dry_run` default on all ingress except production cron with signed config.
- Action allowlist per API key scope (`book_rebalance`, `probe`, `buy`, `admin`).
- Kill switches: global `spend_x=false`, per-tenant `entries_enabled=false`, lane disable — checked inside services, not only cron wrappers.
- Preserve/PAXG: protective rules in `ProtectivePort` only; book action must call it, not reimplement CR-03.

---

## 11. What we are **not** doing in this architecture pass

- Not claiming multi-tenant SaaS product launch.
- Not rewriting all of `phase6_runner` in one PR.
- Not enabling live RSI→auto-buy by default.
- Not deleting full-book 2× until cutover GO + spend CF evidence.
- Not building Kafka/event-sourcing unless StateStore proves insufficient.
- Not 1000 live Coinbase accounts from this repo without separate custody design.

---

## 12. Success metrics (architecture, not alpha)

| Metric | Bar |
|--------|-----|
| Actions reachable via one CLI | `phase6ctl action <name> ...` → Receipt JSON |
| Duplicate wash/eligibility paths | ≤1 implementation each (shim OK) |
| Book rebalance new-seat legs | Always 0 by construction (test) |
| X spend without budget record | 0 (test) |
| Tenant state collision | Impossible if tenant_id prefix enforced (test) |
| Idempotent double-submit | Same receipt, second X spend 0 (test) |
| Runner LOC owning policy | Trend down each slice; no new policy in runner |
| 100 synthetic tenants dry_run probe | Completes under budgeted wall time (bench Task 9) |

---

## 13. Implementation tasks (staff only after Brad GO)

> Bite-sized; each ends in isolation test + commit. No live knob cutover in Tasks 1–7.

### Task 1: Domain types + dispatcher skeleton — **SHIPPED 2026-09-18**
- Create: `phase6/domain/types.py`, `phase6/domain/dispatcher.py`, `phase6/domain/ports/__init__.py`
- Test: covered in `scripts/phase6/test_isolation_book_rebalance_action.py` (noop + idempotency + tenant ns)
- Commit: with Task 6 vertical slice

### Task 2: File StateStore + Idempotency adapters (tenant prefix)
- Create: `phase6/adapters/state_files.py`, `idempotency_files.py`
- Prove tenant_id namespacing; default tenant reads current `data/state` layout via compatibility map
- Commit: `feat(adapters): tenant state store + idempotency`

### Task 3: Promote X budget + rebalance candidates into domain/services (shim old imports)
- Move/wrap: `x_query_budget`, `rebalance_x_candidates`
- Test: existing isolation tests still pass via shim
- Commit: `refactor: domain services for x budget + rebalance candidates`

### Task 4: WashTriggerService + unify shadow/probe trigger
- Create: `phase6/domain/services/wash_trigger.py`
- Refactor probe + shadow to call it (behavior-neutral)
- Test: shared cases + prior probe/shadow tests green
- Commit: `refactor: single wash trigger service`

### Task 5: RsiEventProbeAction + CLI ingress
- Create: `phase6/domain/actions/rsi_event_probe.py`, `phase6/ingress/cli.py` (minimal)
- Wire spend path through Sentiment adapter + budget
- Cron bridge calls action (wrappers become 5-liners)
- Commit: `feat: RsiEventProbeAction`

### Task 6: BookRebalanceAction (dry_run first) + refuse new seats — **SHIPPED 2026-09-18**
- Create: `phase6/domain/actions/book_rebalance.py`, `phase6/ingress/cli.py`, `scripts/phase6/run_book_rebalance_action.py`
- Isolation test: `scripts/phase6/test_isolation_book_rebalance_action.py` (tryout leg stripped + reason)
- Dry_run against live snapshot; no orders; X spend forced off in v1
- CLI: `python3 -m phase6.ingress.cli action book_rebalance` / `run_book_rebalance_action.py`
- Commit: `feat(domain): BookRebalanceAction dry_run refuse new seats`

### Task 7: Eligibility + SeatLedger facades (no behavior change)
- Create: `phase6/domain/services/eligibility.py`, `seat_ledger.py`
- Dashboard/readiness import facade (optional thin)
- Commit: `refactor: eligibility/seat facades`

### Task 8: Import-boundary / dup guard script
- Create: `scripts/phase6/check_domain_boundaries.py`
- CI or pre-commit optional; isolation run in test
- Commit: `test: domain boundary guard`

### Task 9: Synthetic 100-tenant dry_run bench (probe + book)
- Create: `scripts/phase6/bench_action_scale_dry.py`
- Report wall time + lock behavior; no external X spend
- Commit: `chore: action scale dry bench`

### Task 10: Cutover design packet (not execute)
- Doc only: flags to point runner/cron at dispatcher; retire full-book X mode; compose probe→buy workflow under GO
- Update MASTER + luck ladder link
- **Stop for Brad GO** before any production cutover task

---

## 14. Cutover flags (future — do not set in Tasks 1–9)

```json
"action_architecture": {
  "enabled": false,
  "dispatcher_owns_cron": false,
  "book_rebalance_refuses_new_seats": true,
  "x_query_split": {
    "mode": "validate",
    "rebalance_candidates_only": false,
    "retire_full_book_2x": false
  },
  "rsi_event": {
    "probe_action": true,
    "compose_tryout_buy": false
  }
}
```

---

## 15. Plain-English summary for Brad

**We’re redesigning around verbs, not files.**  
Each verb (`book_rebalance`, `rsi_event_probe`, `tryout_seat_buy`) is one component with a clear receipt.  
Rules (can I buy? may I spend X? is this a wash?) live **once**.  
Scripts/cron/dashboard become thin doorbells.  
**1000 traders** = 1000 isolated bags of state calling the same verbs, with shared market data and a fair X queue — not 1000 copies of `phase6_runner`.

**Already built pieces** (budget, candidates, probe) plug in as the first adapters; we stop growing parallel gods.

**Next:** Your GO on this design → staff Task 1.  
No live money-path change until Task 10 + explicit cutover GO.

---

## 16. Open decisions (need Brad only if disagree)

| # | Default in this design | Alt |
|---|------------------------|-----|
| D1 | Single-process + file store first | Jump straight to Redis |
| D2 | HTTP API after CLI/cron green | HTTP in parallel |
| D3 | Compose probe→buy as workflow later | Never auto-compose (human/cron only) |
| D4 | Keep `regime_cash_policy.evaluate_buy_entry` as implementation behind facade | Full rewrite of policy |
| D5 | Tenant id string `"default"` | UUID from day one for default book |

Defaults favor **ship architecture without pausing live book**.
