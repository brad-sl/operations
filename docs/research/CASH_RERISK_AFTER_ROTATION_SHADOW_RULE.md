# Shadow rule — cash re-risk after rotation / breadth day

**Status:** PAPER / SHADOW ONLY — no live orders, no config mutate  
**Opened:** 2026-08-19  
**Parent research:** `docs/research/MARKET_BREADTH_MOMENTUM_BREAKOUT_RESEARCH.md`  
**Code (pure):** `phase6/research/market_breadth_breakout.py`  
**Align size with:** flat B / layered re-entry **$75** first pass  

---

## Plain English

**If we just rotated majors into cash (or we’re already very cash-heavy), and the market is running across many big names at once, the bot should at least *notice* and paper-simulate putting a small slice back to work** — into names we are already allowed to buy — instead of waking up after a +5–9% beta day with only LINK on.

This is **not** “FOMO buy everything.” It is a **cash-idle alarm + small re-risk checklist**.

---

## When the rule wakes up (all must hold)

| # | Gate | Default (v0 paper) |
|---|------|---------------------|
| 1 | **Cash heavy** | `cash_usd / total_usd ≥ 0.60` (case was ~0.83) |
| 2 | **Breadth ON** | Candidate B1: ≥ **4** of liquid set with 24h ret ≥ **+3%** (set frozen in code) |
| 3 | **Not bear** | BTC 30d ret > **−10%** (same veto family as layered) |
| 4 | **Deploy allowed** | At least one **in-basket** name with no active 72h/manual buy block |
| 5 | **Recent de-risk** (optional strengthen) | BTC or SOL (or any sticky) had `rotation_exchange` / de-risk SELL within **7d** — flags “we chose cash recently” |

If breadth ON but cash &lt; 60%: log **breadth_only** (no cash-idle fault).  
If cash heavy but breadth OFF: log **cash_idle_no_breadth** (not this rule’s fire).

---

## What paper does when it fires

1. **Would-fire** record only (`data/state/cash_rerisk_breadth_shadow.jsonl`).  
2. **Paper sleeve:** up to **$75** notional (or `min(75, 0.25 * cash)`), split across up to **2** in-basket names:  
   - Prefer sticky core with free block (BTC/ETH) if breadth includes them green; else top cycler score among unblocked actives.  
3. **Mode:** paper **rebalance add**, not membership swap.  
4. **Never** override 72h block; never touch PAXG preserve; never auto-promote ZEC/HYPE here (that’s Path B).

---

## Coil → expansion (M2 link to squeeze research)

Optional context flag (2026-08-19): `coil_recent` from squeeze compression detector.

| State | Tag | Fire? |
|-------|-----|-------|
| Cash heavy, breadth OFF, coil recent | `coil_ready_wait_breadth` | No — waiting for expansion |
| Cash heavy, breadth ON, coil recent | `fire_coil_expansion` | Yes — preferred quality fire |
| Cash heavy, breadth ON, no coil | `fire` | Yes — plain breadth path |

Coil alone never deploys. See `docs/research/SQUEEZE_REGIME_BREAKOUT_RESEARCH.md`.

---

## What success means (before any live talk)

| Horizon | Metric | Bar (draft) |
|---------|--------|-------------|
| 1d / 3d / 7d | Paper sleeve MTM − fees vs **stay cash** | Mean excess ≥ 0 and hit rate ≥ 45% after N≥12 episodes |
| Chop | Max DD of sleeve | Not worse than “always $75 long basket” control by much |
| Process | Would-fire on 2026-08-19 case | **Must** fire given reconstructed cash/breadth |

Kill or redesign if fires constantly in sideways weeks with negative excess.

---

## Relation to other systems

| System | Relationship |
|--------|----------------|
| Layered bull re-entry | Breadth can **confirm** BTC breakout; cash rule can fire even if BTC RSI &gt; 70 **only in paper v0 with explicit flag** — default paper still respects chase caution (optional: require BTC RSI ≤ 75) |
| 72h post-SL block | Hard filter on targets |
| Pool cycling / discovery | Separate Path B; this rule does **not** change `global_settings.pairs` |
| ARCH-4 rotation | This rule is the **aftercare** when rotation left cash dominant into a risk-on tape |

---

## Implementation phases

| Phase | Work | Live risk |
|-------|------|-----------|
| 0 | Spec + case study JSON | None |
| 1 | Pure detector + isolation tests | None |
| 2 | Offline bake-off B1–B4 on long tape | None |
| 3 | Paper cron would-fire (no_agent quiet) | None |
| 4 | Brad review → optional live shadow cap $75 | Gated |

---

## Anti-patterns

- Treating Coinbase top-gainers list as a buy list  
- Full-book FOMO when breadth ON  
- Using this to skip SL / cooldown  
- Claiming one green day validates the rule  

---

## Case hook

`scripts/phase6/run_breadth_cash_rerisk_case_20260819.py` →  
`data/state/breadth_cash_rerisk_case_20260819.json`
