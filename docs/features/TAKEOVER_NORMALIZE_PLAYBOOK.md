# Takeover normalize playbook

| Field | Value |
|-------|--------|
| **ID** | `FEAT-TAKEOVER-NORMALIZE-2026-09` |
| **Status** | `DRAFT` · ops playbook (partially implementable today; not a one-call product) |
| **Parent** | [`CRYPTO_PROCESS_LIFECYCLE.md`](./CRYPTO_PROCESS_LIFECYCLE.md) |
| **Trader voice** | [`CRYPTO_PROCESS_TRADER_VOICE.md`](./CRYPTO_PROCESS_TRADER_VOICE.md) |
| **Updated** | 2026-09-19 |
| **Default posture** | **Respect holdings → protect → classify → slow normalize.** Never silent full dump on connect. |

---

## 0. Purpose

When a trader (or this operator book) already holds **allocated crypto on Coinbase**, the platform must:

1. **Not** pretend it is a Fresh start  
2. **Not** fire-sale the book to match a model portfolio on day one  
3. **Do** attach protectives, classify risk, and only then move toward a process-controlled book  

**Fresh remains the preferred economics path** when the user can choose cash-first. Takeover is the **honest path for real bags**.

This playbook is **operator law**. Multi-tenant self-serve takeover UX is **OUT** until Scaling-1000 onboarding is in scope.

---

## 1. Definitions

| Term | Meaning |
|------|---------|
| **Inherited bag** | Position present at connect / first live cycle; not opened by current process Open path |
| **Process open** | Lot opened under Qualify→Open (tryout or graduated) with SL + bag_id |
| **Ballast** | Intentional hold outside normal tryout churn (e.g. PAXG micro / Preserve) |
| **Non-process name** | Outside basket / hard-block / novelty jail / user “do not touch” |
| **Normalize** | Move book composition and lot hygiene toward Fresh-like process control **without** requiring day-one parity |
| **Violent normalize** | Large liquidations / full flatten — **Brad or trader GO only** |

---

## 2. Hard rules (non-negotiable)

1. **Day-1 default = Care, not Open.** Protect first.  
2. **No auto scale-up (Grow) on inherited bags** until classified **process-eligible** and packet rules allow.  
3. **No auto membership dump/fill** (`live_membership_swaps` stays OFF). Roster changes = GO tools.  
4. **No claiming Takeover edge = Fresh backtest edge.** Tag results `inherited` vs `process_open`.  
5. **Naked bag = P0.** Fail-closed reattach / block new risk if protectives cannot attach.  
6. **Manual user sells** follow capital-events policy (cash hold / rebuy cooldown) — see `docs/CAPITAL_AND_PORTFOLIO_EVENTS.md`.  
7. **Door package / tryout thaw / size shells** apply to **new** risk only; they do not rewrite inherited size overnight.  
8. **Kill / Close Down** is explicit — not a side effect of “running the model.”

---

## 3. Phase plan

### Phase T0 — Connect & snapshot (same day)

| Step | Action | Done when | Status today |
|------|--------|-----------|--------------|
| T0.1 | Connect exchange / confirm account id | Balances readable | **LIVE** |
| T0.2 | Snapshot cash, positions, open orders, existing stops | Written to live state / ops note | **LIVE** |
| T0.3 | Detect scenario: Fresh vs Takeover (holdings-respecting path) | Runner does not invent zero-position Fresh if bags exist | **PARTIAL** |
| T0.4 | Plain-English card: “Takeover — holdings respected” | Operator/trader sees mode | **PARTIAL** |

**Abort if:** balances unreadable, auth broken, or snapshot contradicts UI — fix connect before any normalize GO.

---

### Phase T1 — Protect (hours, not days)

| Step | Action | Done when | Status today |
|------|--------|-----------|--------------|
| T1.1 | Inventory exchange stop orders vs positions | Gap list of naked / mismatched | **PARTIAL** |
| T1.2 | Reattach protectives (CR-03 discipline); preserve pairs keep deep policy (e.g. PAXG E1) | No intentional naked process risk | **LIVE** (code) · prove per book |
| T1.3 | Cancel orphan stops on dust / sold legs if policy says so | Registry coherent | **PARTIAL** |
| T1.4 | If attach fails → **fail closed**: no new tryout buys until resolved | Gate or operator halt | **LIVE** A1 spirit · ops still manual |

**Do not:** rebalance to target weights, scale-up, or dual_agree churn during T1 unless protecting requires a GO flatten of a broken name.

---

### Phase T2 — Classify (same day / next morning)

Assign every holding a **bucket** (write to ops note or future state file):

| Bucket | Criteria (start simple) | Default next action |
|--------|-------------------------|---------------------|
| **B0 Ballast** | PAXG / Preserve / explicit user hold | Care only; micro policy; no tryout logic |
| **B1 Process roster** | In current basket, not hard-blocked | Care; exits per stack; no Grow until packet |
| **B2 Tryout-eligible orphan** | Not seated but would pass doors if cash Fresh | Prefer: seat via GO **or** slow exit — don’t leave forever limbo |
| **B3 Non-process / toxic** | Hard block, missfire lock, meme novelty, user reject | Trim schedule or GO liquidate; block rebuy |
| **B4 Unknown / data poor** | No reliable mark, dust, delist risk | Treat as B3 until proven |

**Outputs:**

- `classify_table` (pair, qty, usd, bucket, stop?, notes)  
- `normalize_speed`: `hold` | `slow_trim` | `active_normalize` | `wind_down`  

Speed is **human-chosen**. Default if unspecified: **`slow_trim`** for B3, **`hold`** for B0/B1.

---

### Phase T3 — Stabilize (days 1–7)

| Step | Action | Guardrails |
|------|--------|------------|
| T3.1 | Run normal **Care** only on B0/B1 | SL/TP/trail; no forced redeploy of cash from inherited sells unless policy clears hold |
| T3.2 | Start B3 exits per speed | Prefer limit-aware exits; respect fee tax; no market panic unless risk event |
| T3.3 | Seat decisions for B2 | `basket_swap` / dual_agree **GO**; novelty override only with eyes open |
| T3.4 | Cash from trims | Smart Park / powder OK; **not** automatic full re-risk into alts |
| T3.5 | New Open risk | Same Qualify→Open as Fresh; tryout shell; seats/day; **inherited size does not consume “graduation”** |

**Success metric (stabilize):** zero naked bags; every name bucketed; no surprise full liquidation; capital events coherent.

---

### Phase T4 — Normalize toward Fresh-like (weeks)

Goal: increase **share of NAV in process_open lots + cash/park**, decrease **unclassified inherited entropy**.

| Lever | How | GO needed? |
|-------|-----|------------|
| Exit remaining B3 | Scheduled trims | Speed GO once; not per fill |
| Convert B1 inherited → process hygiene | On full exit+reopen only if intentional; else keep Care until natural exit | Reopen = normal Open gates |
| Roster hygiene | Remove names you will never process-trade | dual_agree / swap GO |
| Grow (R5 scale-up) | **Only** on process_open (or explicit exception list) | Approval path / Brad GO |
| Size graduation | first_fill / shell rules | Existing GO doctrine |

**Anti-patterns:**

- “Average down” inherited losers to “meet weight”  
- Scale-up because takeover NAV is large  
- Treating basket membership as a buy order  
- Wiping ledger pain to force eligibility  

---

### Phase T5 — Steady state or Close

| Path | When | Action |
|------|------|--------|
| **Steady Manage** | Buckets stable; new risk only process_open | Lifecycle Care/Grow/Rotate/Learn |
| **Close Down** | User exits product or full risk-off | Flatten alts per GO → cash/park; cancel tryout minting; leave ballast if requested |

**Close Down checklist (manual until one-call exists):**

1. Kill new buys / scale-up armed paths as needed  
2. Flatten B1–B3 trading risk (order + confirm fills)  
3. Confirm stops cancelled on flat names  
4. Park or withdraw cash per user  
5. Snapshot final book + mode `closed` in ops note  

---

## 4. Grow / Graduate rules under Takeover

| Lot type | Grow (add) | Name graduation | Size graduation |
|----------|------------|-----------------|-----------------|
| Inherited B1 | **Default NO** | N/A (already held) | NO until process_open history or explicit GO exception |
| Process tryout | Approval / armed path | Ledger + doors | R5 / first_fill rules |
| Process graduated | Per shell | — | Packet + GO doctrine |
| B3 | NO | Demote / block | NO |

**Exception template (rare):**  
`Brad GO · pair · max_add_usd · reason · expires` — logged; not a standing knob.

---

## 5. Operator checklist (copy/paste)

```text
TAKEOVER NORMALIZE
[ ] T0 snapshot cash/positions/stops/orders
[ ] T0 mode = Takeover (not Fresh)
[ ] T1 naked-bag scan + reattach
[ ] T1 fail-closed if attach broken
[ ] T2 classify table B0–B4
[ ] T2 normalize_speed chosen
[ ] T3 no Grow on inherited
[ ] T3 new buys only via tryout/grad gates
[ ] T3 B3 trim started if speed ≠ hold
[ ] T4 weekly: % NAV process_open + cash/park vs inherited
[ ] Learn: tag exits inherited vs process_open
[ ] Close path documented if user wants out
```

---

## 6. Code / ops hooks (current, not exhaustive)

| Need | Where to look |
|------|----------------|
| Fresh path | `phase6_runner` `_handle_fresh_start` · ARCH-4 parity tests |
| Holdings respected | Live runner takeover messaging / init lineage |
| Protectives / naked bag | `stop_loss_manager` A1 · CR-03 reattach · preserve/PAXG policy |
| Capital / manual sells | `docs/CAPITAL_AND_PORTFOLIO_EVENTS.md` · capital controls CLI |
| Roster GO | `phase6/scripts/basket_swap.sh` · dual_agree skill |
| Tryout doors / size | `regime_cash_policy` · recovery tryout · first_fill |
| Scale-up | `tryout_scale_up_live` + approval cron (process lots only) |
| Park | Smart Park / Preserve specs under `docs/features/` |

**GAP:** single state artifact `data/state/takeover_normalize_{account}.json` (classify table + speed + phase). Spec’d here; not required to start manual ops.

---

## 7. Suggested state shape (future)

```json
{
  "account_id": "...",
  "mode": "takeover",
  "phase": "T3",
  "normalize_speed": "slow_trim",
  "asof": "2026-09-19T00:00:00Z",
  "buckets": {
    "PAXG-USD": {"bucket": "B0", "inherited": true, "usd": 0},
    "LINK-USD": {"bucket": "B1", "inherited": true, "usd": 0}
  },
  "rules": {
    "grow_inherited": false,
    "new_risk": "process_gates_only"
  },
  "notes": ""
}
```

Measure-only until Brad GO to wire writes into runner.

---

## 8. Success criteria (playbook, not alpha)

| Gate | Pass |
|------|------|
| Safety | No naked inherited bags after T1 |
| Honesty | Mode + buckets visible; Fresh edge not claimed |
| Control | New risk only through process gates |
| Progress | Inherited entropy down over T4 **or** explicit hold/wind_down choice |
| Exit | User can Close Down without archaeology |

---

## 9. Staff-next (implementation order when prioritized)

1. Manual ops using this checklist on next real Takeover-shaped book  
2. `takeover_normalize` state JSON + CLI `status` (read-only)  
3. Dashboard tile: mode + naked count + bucket counts  
4. Block Grow paths when `inherited=true` unless exception  
5. One-call Close Down (shared with Fresh wind-down)  
6. Only then: SaaS onboarding copy pointing at trader voice + this speed choice  

---

## 10. Revision log

| Date | Change |
|------|--------|
| 2026-09-19 | Initial playbook from lifecycle FEAT + Fresh-vs-Takeover product decision. |
