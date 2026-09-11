# Platform mission (agent SSOT)

**Owner:** Brad  
**Updated:** 2026-09-09  
**Audience:** every Hermes/coding agent touching this repo

## Why this exists

Brad has been building this trading platform for months (primarily with Grok-assisted agents) to create a **reliable automated environment** that decides **when**, **what**, and **how** to invest — with code and evidence, not vibes.

Trial-and-error is **R&D for that system**. It is **not** gambling the book for a quick cash patch or spending money. Do not reframe the operator as impatient degen capital. Do not optimize for “one hot seat this afternoon.”

## North-star sequence (do not skip steps)

1. **Reliable environment**  
   Runner, ledger, stops, cooldowns, dashboard, and agent quality gates tell the truth. Process tax (manufactured SLs, post-SL/TP reseats, ratchet ghosts, config≠path) dies first. Wrong numbers = product bugs.

2. **Intelligent when / what / how**  
   Automated decisions with enforceable gates. Shadow and isolation before live. `dual_agree` ≠ promote. Discovery/CF contenders ≠ buy permission.

3. **Net profitability (honest)**  
   Deposit-adjusted NAV on the process book. Scoreboard: `reports/MONTH_PATH_SCOREBOARD_LATEST.md` and `docs/AGENT_5PCT_MONTH_PATH.md`.  
   ~5%/mo take-home is a **path meter**, not an SLA or lifestyle promise. Edge class until proven: **`ATTENTION_ONLY_less_loss_path`**.

4. **Scale only after proof**  
   Once net profitability is **real and repeatable**, scale capital and multi-book / large-AUM operation **deliberately**.  
   Do **not** scale complexity, util, or pair count to “feel closer” to scale. Scaling a leaky engine multiplies tax.

## Standing operator rules

- Leave the live book as-is unless Brad **go**.  
- Trust and reliability are the product (boring correct cycles &gt; hype).  
- Plain-English go/no-go first; expand SL/TP/shadow/WR on ask.  
- Idle yield (e.g. cash/USDC / external ~APY control arms) may hold stub capital during the lab phase — that is **allocation hygiene**, not abandoning the mission.  
- Barbell is allowed: boring yield on the stub + small leak-free tryout sleeve. Full-NAV “beat 4% APY” is a **later** milestone after edge is proven, not a reason to force util under soft_down.

## What agents must not do

- Treat closed red months as proof “Coinbase can never work” **or** as proof we should YOLO util.  
- Add alts / widen tryout / live-promote paper arms to manufacture activity.  
- Bypass `evaluate_buy_entry` lockouts, ratchet continuity, or quality gates.  
- Auto-promote, silent knob changes, or fake fills/prices.  
- Stuff MEMORY.md with playbooks — procedures live in skills/docs; memory stays thin facts.

## Canonical pointers

| Doc | Role |
|-----|------|
| This file | Mission / intent SSOT |
| `docs/AGENT_5PCT_MONTH_PATH.md` | Profitability path + live stance |
| `docs/AGENT_QUALITY_GATES.md` | Pre-ship / money-path quality |
| `docs/MASTER_TASK_TRACKING.md` | Durable work cards |
| `.hermes.md` | Session load rules (preflight, BoN, leave-book) |
| `reports/MONTH_PATH_SCOREBOARD_LATEST.md` | Hit/miss meter |

## One-line sticky

> Build a trustworthy decision engine → prove net edge → then scale. Less-loss and truth first; candidates are not capital.
