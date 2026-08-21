# Proceed plan — Bear ladder in the trade-opt portfolio

**Date:** 2026-08-20  
**Status:** Active — shadow + P2 done; **no live**  
**Edge class:** `LESS_LOSS_VS_SL` (not HIT_10 absolute)

---

## Why this is in the portfolio

Today in bear we mostly **ride to SL**. That path is **lossy** (~−1.9% mean R on the CF sample).

The **winning path** is a real opt candidate:

> residual long × bounce tags ≥2 ladder slices × cash stays cash × SL when no bounce

| | |
|--|--|
| Mean vs ride-SL | **~+0.94% ΔR** (less loss) |
| Win rate | **~30%** green paths (vs ~7% ride-SL) |
| When 3 slices fill | **~+4.6% mean** |
| When 0 slices | **~−3%** (stop — same pain class as now) |

**Portfolio role:** reduce **give-back / stop bleed** on residual risk in down markets — not a bear long-entry engine.

---

## How we proceed (ordered)

| Step | Action | Live money | Owner |
|------|--------|------------|--------|
| **0 Now** | Keep P1 shadow on runner; park new buys in bear still | No | Done |
| **1 Portfolio** | Scoreboard lane `bear_ladder_scale_out` + winning path in spec/config | No | Done |
| **2 Collect** | Wait for **real bear** calendar; count multi-slice would-fire episodes | No | Automatic |
| **3 Optional P3** | Relief detector only if bounce timing looks late on live shadow | No | Later |
| **4 Re-CF** | Re-run path CF after live bear legs exist (ledger > 0) | No | Auto / cron ok |
| **5 Review** | Gates: path CF + ≥10 ladder episodes + ≥30 bear days + **Brad OK ASAP** | No until OK | Brad + watch cron |
| **6 Live** | One flip: partial sells + 72h rebuy block + stables park | **Yes** | Explicit Brad go (intent: don't sit on it) |

**Forget-proofing:** Hermes cron `bear-ladder-promote-watch` pings Telegram on regime→bear, episode milestones, and gates ready. Memory + MASTER flag Brad intent.

**Never:** auto-promote without Brad, short, FOMO re-entry, market as “bear money printer.”

---

## What we do *not* do next

- Flip `live_apply` because P2 looked good  
- Replace SL (SL stays floor)  
- Force full +6% TP in bear (map prior still separate)  
- Open new risk *to* feed the ladder  

---

## Success when live (later)

- Fewer full give-backs on names that bounce +3–8% before dying  
- Trader copy: “we took some profit on a bounce; cash is sitting out” (script only)  
- Moon bag optional; most of the win is **slices 1–3 + no rebuy**

## Kill criteria

- Live shadow episodes worse than ride-SL after fees  
- Multi-slice almost never fires in real bear  
- Ops complexity > less-loss value  

---

## Commands

```bash
# Path CF (anytime)
PYTHONPATH=. python3 phase6/research/run_bear_ladder_path_cf.py

# Shadow once
PYTHONPATH=. python3 phase6/research/run_bear_profit_take_shadow.py

# Scoreboard (includes bear ladder lane)
PYTHONPATH=. python3 phase6/research/run_exit_promote_scoreboard.py --no-sl-cf
```

Artifacts: `reports/BEAR_LADDER_PATH_CF_LATEST.md`, `reports/EXIT_PROMOTE_SCOREBOARD_LATEST.md`
