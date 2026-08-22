# Floor ratchet after multi-bagger / large-spread adds

**Status:** PLATFORM REQUIREMENT — **SHIPPED 2026-08-21** (`phase6/core/sl_floor_ratchet.py` + `stop_loss_manager` wire + isolation PASS)  
**ID:** `P6-SL-RATCHET-AFTER-ADDS`  
**Date captured:** 2026-08-21  
**Owner:** crypto risk product  
**Related:** `P6-ADD-RISK-SIZER-20260821`, `P6-ARMED-STOP-GAP-ALLOW-20260821`, CR-03 SL reattach, `P6-EXIT-WR-IMPROVE-STACK-20260821`

---

## Why this exists

Brad history: large BTC crash with **no SL** → ~**80%** value loss. Floor is non-negotiable.

Current Phase 6 behavior after long-runner **adds**:

- SL reattach often keeps **original / early lot entry** as anchor (e.g. LINK add @ ~$11.63 still floored ~$8.03 on genesis entry).
- That is a **catastrophe floor** for the old runner, but for **new capital** it leaves a huge air pocket (20–60%+) before exit.
- Add-risk sizer (2026-08-21) limits **how much** you can add into that pocket. It does **not** raise the floor.

**Product gap:** after a large mark-vs-entry **spread**, especially when topping off, the platform must be able to **ratchet the floor up** so hitting it is painful-but-bounded (slice of open win), not a round-trip of a multi-bagger plus fresh cash.

Brad example (intent test):

| | |
|--|--|
| Pitch / entry | XLM **$0.54** |
| Later / top-off zone | **$1.35** (~1 month) |
| Multiple | **~2.5× (+150%)** |

Genesis−3% floor under a $1.35 top-off ≈ financing a full giveback. **New floor required** before/with fat adds on that spread.

---

## Problem statement (exact)

> Something doubles or triples between initial purchase and top-off → you definitely want a new floor.  
> Floor adjustment “ratchet after adds” depends on **total spread**, not “we added ⇒ always move stop.”  
> Bounce risk remains under any floor; goal is bound pain to a **slice of earned gains**, not open-ended crash or genesis round-trip.

“Missing a bounce” = stopped out, then price recovers (support snapback, relief rally, resistance reclaim, macro reverse) — not only textbook resistance.

---

## Two floor jobs (both required on platform)

| Job | Intent | Failure mode if missing |
|-----|--------|-------------------------|
| **Catastrophe cap** | Never again ~80% open drawdown | No SL / SL never arms |
| **Pain budget** | Hitting floor shouldn’t feel like a second crash after a multi-bagger | Genesis floor under double/triple + fat add |

Ratchet serves **pain budget** after large spread; catastrophe cap remains via always-on SL.

---

## Simple solution (agreed direction)

**Spread is the switch** — not arbitrary $ caps.

### When to ratchet (triggers — draft)

Ratchet (or require ratchet before allowing add) when **any** of:

1. **Open multiple** `mark / original_entry ≥ M` (start band **1.5×**; hard expect at **2.0–2.5×** — XLM-class).  
2. **Add would leave new-money stop-gap** `(add_px − stop) / add_px ≥ G_max` (e.g. **15–25%**) under current floor.  
3. **Operator/policy:** after successful add above M, always re-anchor floor per policy below.

Near entry / small R → keep structure / original-style floor (no nervous ratchet on noise).

### Where the new floor goes (draft ladder)

Prefer **lock a slice of open profit**, not knife-edge under last print:

| Stage | Example floor idea | Notes |
|-------|-------------------|--------|
| Modest runner | Trail or BE + small buffer | Optional |
| Strong runner (≥1.5–2×) | Floor at **max(old_stop, entry × 1.0+, mark − trail%)** | Never lower stop |
| Double/triple + add | Floor under **recent structure** or **% of open gain locked** (e.g. keep ≥50% of run from entry) | Must run before/with large add |
| Post-add | CR-03 reattach uses **ratcheted anchor**, full bag qty | Same atomic suspend/reattach path |

**Hard rule:** ratchet only **raises** protective stop (never loosens).

### Interaction with add-risk sizer (already shipped)

Order of concerns:

```text
1. Gap / armed gates          → may we add at all?
2. Add-risk factor sizer      → how many $ notional?
3. Floor ratchet (THIS GAP)   → where does the bag’s floor live after / before add?
4. CR-03 full-bag reattach    → exchange orders match policy
```

- Sizer without ratchet → small adds into still-wrong floor (better, incomplete).  
- Ratchet without sizer → can still dump cash under a higher floor (also incomplete).  
- **Both required** for long-runner platform quality.

### Regime awareness (draft)

| Regime | Ratchet posture |
|--------|-----------------|
| Bull | Allow pyramid + ratchet on spread triggers |
| Flat | Tighter trail / earlier ratchet; smaller adds |
| Bear / park | Prefer no pyramid; ratchet existing winners toward cash preservation if still held |

Factors live next to `regime_cash_policy.add_risk` when implemented.

---

## Non-goals

- Not a substitute for **having** a stop (catastrophe).  
- Not discretionary “AI picks the bottom.”  
- Not force-selling overweight bags (add-risk sizer already no forced sell).  
- Not Preserve/PAXG E1 (−32%) — different sleeve (`preserve-mode-and-ballast`).

---

## Acceptance criteria (when built)

1. Spec + knobs in config (multiples, lock fraction, never-loosen).  
2. Isolation: XLM-shaped 0.54→1.35 top-off **must** raise floor vs genesis−3%.  
3. Isolation: small R add does **not** yank floor to last print without trigger.  
4. Live path: ratchet + CR-03 reattach; registry/verify show new stop ≥ old stop.  
5. LINK-shaped regression: large add with wide genesis gap either **blocked/clipped by sizer** and/or **ratchet required** before size applies.  
6. MASTER card closed only after isolation PASS + runner deploy note.  
7. Skill `phase6-sl-exits-and-dust` documents ratchet + points here.

---

## Implementation sketch (not started)

| Piece | Likely home |
|-------|-------------|
| Pure policy | `phase6/core/sl_floor_ratchet.py` (or extend stop_loss_manager anchor selection) |
| Triggers | open multiple, projected add gap, regime table |
| Wire | before/after add in rebalance execute + CR-03 reattach anchor resolution |
| Config | `risk_management.sl_ratchet_*` + `regime_cash_policy` optional by_regime |
| Tests | `scripts/phase6/test_isolation_sl_floor_ratchet.py` |
| Observability | `[SL-RATCHET] pair old→new reason=multiple|add_gap|post_add` |

---

## Capture provenance

- Conversation 2026-08-21: LINK pile-in under genesis SL; add-risk sizer shipped; Brad confirmed ratchet-after-adds on large spread as **platform must-have**; XLM 0.54→1.35 cited.  
- Do not drop this when compacting sessions — functional gap until DONE.
