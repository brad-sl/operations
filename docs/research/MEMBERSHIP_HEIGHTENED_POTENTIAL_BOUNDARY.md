# Membership boundary — heightened potential (optimize bag, not expand)

**Status:** SPEC + CODE (paper/shadow)  
**Frozen intent:** Brad 2026-08-19  
**Code:** `phase6/core/membership_potential_gate.py`  
**Related:** Path B ladder, pair discovery, basket swap CF, promote semantics  

---

## Plain English

We **optimize a fixed-size bag** (swap one weak name for a stronger contender).  
We do **not** grow the list.  
We do **not** require the new name to be **ready to buy today** (RSI + sentiment).

What we **do** require on the way in:

> **Heightened potential** — structural reason this name deserves a seat in the bag  
> (energy / quality / momentum-vol structure), so future capital *can* work when deploy gates trip.

Membership = **eligibility for future buys**.  
Deploy gates = **whether we buy on this cycle**.  
Those are different layers. This doc owns **membership only**.

---

## Bag constraint (M0) — always on

| Rule | Default |
|------|---------|
| Mode | **Optimize**, not expand |
| Size | Fixed active count (no net +1) |
| Action | At most **1** swap per cycle: remove A, add B |
| Sticky | BTC/ETH never auto-ejected |
| Residual | Open size on removed name may remain until runner/SL/dust — promote does not liquidate |
| Apply | Shadow / human promote only — no auto config from this gate |

---

## Membership layers (this boundary)

| ID | Name | Question | RSI/sent? |
|----|------|----------|-----------|
| **M0** | Bag | Fixed size 1:1 swap? | No |
| **M1** | Inbound heightened potential | Does ADD deserve a seat? | **No** |
| **M2** | Outbound weak seat | Is REMOVE a fair eject (flat/weak, not sticky)? | No |
| **M3** | Potential delta | Is ADD clearly better seat than REMOVE? | No |

**Explicit non-gate for membership:**

| ID | Name | Role |
|----|------|------|
| **D0 Deploy** | Pair RSI / sentiment / 72h block / cash | Decides **buy now**, never blocks **seat** alone |

So L3 in older notes is **redefined**: not “near-buy,” but **M1+M2+M3 potential**.  
L2 deploy replay stays optional research for “would book PnL have realized,” not the promote bar.

---

## M1 — Inbound heightened potential (code defaults)

All evaluated on **public market structure** (candles/stats/discovery quality). No X/Reddit.

| Check | Default | Fail reason |
|-------|---------|-------------|
| Data | Enough candles / features present | `no_data` |
| Liquidity | 24h quote vol ≥ **$1.5M** (arm floor family) | `thin_liquidity` |
| Quality / score | `potential_score ≥ 0.35` **or** arm score present and finite | `low_potential` |
| Upside structure | 3d mom ≥ **0** **or** 7d mom ≥ **+2%** **or** discovery upside impulse already set | `no_upside_structure` |
| Pump brake | \|ret24h\| ≤ **80%** and not anti-pump extended melt-up | `pump_brake` |
| Not active | ADD ∉ active basket (optimize-in only) | `already_active` |

`potential_score` may come from discovery `quality_score` or a local feature composite; both are **seat quality**, not buy signals.

---

## M2 — Outbound weak seat

| Check | Default | Fail reason |
|-------|---------|-------------|
| Sticky | REMOVE ∉ {BTC-USD, ETH-USD} | `sticky_core` |
| In active | REMOVE ∈ active | `not_active` |
| Prefer flat | held_usd &lt; **$40** preferred (soft); hard block only if policy says protect large holds | `protect_held` (optional hard) |
| Weak vs book | outbound potential ≤ inbound (enforced in M3) | — |

---

## M3 — Potential delta (why this swap)

| Check | Default |
|-------|---------|
| Margin | `inbound_potential − outbound_potential ≥ 0.05` (score units) **or** arm-specific Δ already positive |
| Equal seat | Reject pure noise swaps where scores tie |

---

## Verdict object (API)

```text
MembershipSwapVerdict
  ok: bool                 # M0∧M1∧M2∧M3
  optimize_bag: true       # always for this path
  require_deploy_ready: false   # FROZEN — never true for membership
  inbound_ok / outbound_ok / delta_ok
  inbound_potential / outbound_potential / delta
  reasons: list[str]
  layer_failed: M0|M1|M2|M3|null
```

Arm proposals and discovery promote paths should **attach** this verdict.  
Shadow may still **log** failed proposals for research; **live promote** must require `ok=True`.

---

## What this is not

- Not a buy order  
- Not “RSI ≤ 55 and sent ≥ 0.25”  
- Not bag expansion  
- Not proof of PnL (that’s CF L1 path + optional D0 replay)  
- Not silent live apply  

---

## Wiring map

| Surface | Use of gate |
|---------|-------------|
| `pair_discovery` promote_eligible | ≈ M1 (+ discovery upside); no D0 |
| `pool_cycling` / arm `propose_arm_swaps` | Full M0–M3 on paper swap |
| `basket_swap_shadow_cf` | Tag proposals; CF still prices L1 path |
| `promote_basket_proposal.py` | Refuse apply if verdict.ok is false (when wired) |
| ARCH-4 buy path | **D0 only** — unchanged |

---

## Tests

`phase6/research/test_isolation_membership_potential_gate.py`

---

## Decision language

| Say | Don’t say |
|-----|-----------|
| “Inbound clears heightened potential for a seat” | “Ready to trade / would buy today” |
| “Optimize bag 1:1” | “Add a 12th name” |
| “Deploy gates still apply later” | “Promote = we are long” |
