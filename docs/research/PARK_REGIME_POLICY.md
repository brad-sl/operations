# Park regime — simple policy for traders

**Status:** LIVE POLICY (optional tiny gold when turned on)  
**Date:** 2026-08-02 · voice update 2026-08-07  
**Audience:** Any trader onboarding this platform  
**Product name:** **Smart Park** — `docs/features/PARK_SMART_IDLE_CASH.md`  
**Related:** package spec, Preserve MVP, platform pause rules

---

## One sentence

**When crypto isn’t a good buy, most money stays in calm cash (dollars or USDC); a small optional gold sleeve can sit as ballast — not as a second day-trading bot.**

---

## Three jars (learn these first)

| Jar | Everyday name | What it is | Default job |
|-----|----------------|------------|-------------|
| **1 · Calm cash** | Parking lot | USDC / USD | Safety + dry powder (+ optional exchange yield on USDC) |
| **2 · Gold sleeve** | Optional ballast | PAXG (gold on the exchange) | Small diversifier while you wait — **Hold**, not gold day-trading |
| **3 · Crypto book** | Active trades | BTC/ETH/alts | Only when rules allow new risk |

```
Markets say “wait”     →  mostly cash, optional tiny gold
Rules open for crypto  →  calm gold if needed, then crypto under limits
Gold crashes hard      →  deep exchange stop may sell gold; stay in cash — don’t revenge-buy alts
```

---

## Rules a new trader can recite

1. **Pause first.** If the platform says no new buys, don’t force alt entries.  
2. **Cash is the default park.** 100% calm cash is always valid.  
3. **Gold is optional ballast, not “safe.”** Gold can drop hard (−15% to −28% on the path is real). **Size** is your airbag.  
4. **Hold gold, don’t ladder-trade it** in a crash (no staged “sell into the hole” robot).  
5. **One deep emergency stop on gold** lives **on the exchange** so it can still work if the bot is offline.  
6. **Don’t turn on gold on top of a full bag of alts** unless you really mean a dual stack. Prefer: pause alts → then tiny gold.  
7. **Tiny before large.** First gold size is small for learning — not a big % until you choose.  
8. **Coming back to crypto is separate.** Don’t accidentally run max alts + large gold without noticing.

---

## Platform defaults (this book; posture 2026-08-07)

| Setting | Value | Why |
|---------|--------|-----|
| Pause crypto | Platform regime rules | Already the control plane |
| Cash park | **USD primary today**; **USDC yield path** optional (off on primary) | Smart Park “cash + yield” is opt-in |
| Gold style | **Hold** only | Evidence favored static hold over staged gold exits |
| Larger gold later | Up to **20%** of cash+gold only if you scale | Not automatic |
| **Tiny gold now** | Small learning size if already on | Not the whole Smart Park story alone |
| Deep gold stop | Far below entry (by design) | Beyond measured ugly paths |
| Soft “don’t add more gold” | After a moderate drop from entry | Stops topping up a loser |
| Crash ladder on gold | **OFF** | Harmful in crash sims |

**Smart Park:** full product voice + choices → `docs/features/PARK_SMART_IDLE_CASH.md`.  
Technical enable → package checklist. Don’t market “guaranteed yield %.”

---

## What we log / monitor (micro phase)

Every cycle while armed:

- Badge: `Preserve · ARMED` (or `ARMED·NO-ADD`)
- Sleeve MTM $ and % vs arm
- E1 order id / stop price / still open?
- Append-only sleeve log for returns

**Success for micro phase is not “PAXG went up.”**  
Success = clean logs, E1 stays attached, no naked inventory, dash truthful, optional E1 path understood.

---

## How to operate (commands)

```bash
# Status
PYTHONPATH=. .venv/bin/python scripts/phase6/arm_preserve_hold.py status

# Micro arm (~$75) — uses config micro_live
PYTHONPATH=. .venv/bin/python scripts/phase6/arm_preserve_hold.py arm --micro --set-enabled --i-understand

# Full 20% later (only when you decide)
PYTHONPATH=. .venv/bin/python scripts/phase6/arm_preserve_hold.py arm --set-enabled --i-understand

# Disarm (cancel stops + sell PAXG)
PYTHONPATH=. .venv/bin/python scripts/phase6/arm_preserve_hold.py disarm --i-understand
```

---

## Onboarding script (30 seconds)

1. Crypto gated by REGIME-CASH? → you’re in **Park**.  
2. Want only cash? → leave Preserve **OFF**.  
3. Want cash + gold ballast? → arm Preserve **Hold** (start **micro**).  
4. Gold is **not** a 3% crypto stop — E1 is deep emergency only.  
5. When crypto deploys again → know whether gold stays or gets trimmed.

---

## Explicit non-goals

- Not a gold day-trading bot  
- Not “beat every bear with alpha”  
- Not replacing layered bull re-entry  
- Not wishful “gold is smooth”

---

## Scale-up gate (when to leave micro)

Only after:

1. ≥1 week clean micro logs (or operator satisfied)  
2. E1 observed healthy on dash / exchange  
3. You accept full ~20% gold path DD on the book  
4. Explicit arm at full target (not auto)

Until then: **Park = A + small B**.

---

## Canonical decision matrix

**Full initiate / size / de-scale / deploy / Keep-Hold (PAXG outperforming) rules:**  
→ `docs/research/PARK_BALLAST_DECISION_MATRIX.md`
