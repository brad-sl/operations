# Phase 6 forward plan — trust the path, then fills

> **For Hermes:** Planning only. Do not implement, restart, or change knobs until Brad GO on a named wave.
>
> **Goal:** Stop losing live tryouts to process bugs, then get qualified fills under the *current* shell before any new loosen or shadow promote.
>
> **Architecture:** Python money path stays the owner (seats, SL, dust caps, floors). Shadows (knife, Jev CF, scale-up, RSI-event X) stay measure-only until their own N bars clear. One dated loosen package only if three natural X+rebalance slots still produce zero risk fills.
>
> **Tech stack:** Phase 6 runner, `tryout_readiness`, ledger `trades/phase6_trades.jsonl`, marketdata.db climate, Hermes crons (local/quiet unless a decision card).

**Status:** PLAN — awaiting Brad alignment. No execution in this document.

**As of:** 2026-09-24 ~17:10 PT. Runner PID `99848` (live). Grounded from readiness, ledger, shadow boards — not vibes.

---

## Preflight summary

- **Objective:** A forward plan after a month of process-tax bugs and an idle risk book. Not a new strategy.
- **IN scope:** Bug-class damage, why the door is closed *right now*, what current tests actually say, sequenced next moves with GO gates.
- **OUT of scope:** New scouts, Jev as strategy, auto-promote, permanent door-package codify, X bill cut, live scale-up money, knob writes.
- **Must not touch:** Live book, `config/trading_config_phase6.json` floors/RSI/thaw, runner restart, force-rebalance, membership swaps.
- **Decisions locked by evidence (not by this plan's GO):**
  - Idle risk book is real (PAXG preserve only).
  - Current choke is **aged engineering sentiment vs 0.30 floor**, plus LINK RSI > 55. Regime is **not** the choke (`flat` / `deploy` / allow_new_buys / cap $75 / park_blocked false).
  - Current tests are **not** an entry unlock. All are `ATTENTION_ONLY` or `N_INSUFFICIENT`. Scale-up CF excess is slightly **negative**.
  - Door package already proved a fill path, then was expired on purpose (2026-09-22). Re-opening it is a new GO, not a bugfix.
- **Open:** Wave 1 wait vs Wave 2 loosen — see grill at the bottom.
- **Proof of done (this plan):** Brad picks Wave 1 (default) or a named Wave 2 package. No code until that pick.

---

## 1. Plain verdict

**No-go** on “parameters are too tight, so loosen now” and **no-go** on “current tests found a better entry.”

**Go** on this order:

1. Keep the process-tax fixes that just landed (full-bag dust refuse). Do not stack a new loosen on top of an unwatched path.
2. Let the **next three natural slots** (21:00 X + ~21:05 rebalance) try the current shell: `$25 × ≤4` seats, sent floor **0.30**, RSI max **55**, thaw/latch/RSI65 **off**.
3. Only if those slots still produce **zero non-bug risk fills**, pick **one** dated loosen. Do not open three doors at once.
4. Leave every shadow where it is until its honesty bar is met. None are close.

North star stays ~5%/mo deposit-adjusted take-home. This month’s damage is **process tax and a closed sensor clock**, not a missing indicator.

---

## 2. Live book (2026-09-24 17:06 PT)

| Fact | Value |
|------|--------|
| Runner | Up, PID 99848, restarted today with dust-cap fix |
| Risk book | **Empty.** Only PAXG-USD ~$80 preserve (E1 stop on the held qty) |
| Cash (readiness) | ~$151 |
| Regime | `flat` / `flat`, BTC 30d **+7.4%**, source `marketdata.db` fresh |
| Policy | `deploy`, `allow_new_buys=true`, rebalance cap **$75**, park_blocked **false**, scenario `flat_cautious_deploy_b` |
| Tryout shell | cap **$25**, seats today **0/4** |
| Eligible doors | **ETH-USD, LINK-USD** only (parity with scoreboard) |
| ETH | eng **0.045** < 0.30, RSI 53 (ok) |
| LINK | eng **0.031** < 0.30, RSI **57.7 > 55** |
| Sensor | Not broken. X age ~8h → reddit bridge, eng expected low mid-cycle. Next X **21:00 PT** |
| `can_buy_before_next_rebalance` | **false** until that refresh |

Do not quote `phase6_live_state.total_usd` (~$2287) as NAV. It does not match cash + PAXG. Readiness cash + holdings is the operator number until that field is audited.

---

## 3. What actually hurt trading (last ~35 days)

Ledger window: 72 rows. This is not “the bot never entered.” It entered, then process bugs and rotations ate the sample.

| Class | Evidence | Still steering? |
|-------|----------|-----------------|
| Same-session LINK SL (2026-09-09) | 2 sells reclassed `process_bug_same_session_sl_void` (~−$4). Missfire cleared 2026-09-23 because the scar was bug-induced | Code lockout exists. Do not re-pin LINK to perma-block |
| CR-03 cancel + dust race (2026-09-19) | `process_bug_cr03_dust_race` on LINK | Partial fix shipped 2026-09-19; **recurred as a full-bag kill** |
| Full-bag “dust” exit (2026-09-24 04:00Z) | 2.04 LINK market-sold as `dust_sweep_orphan` because orphan cap was $50 and SL reattach saw avail≈0.05. Reclassed `process_bug_orphan_dust_full_bag` | **Fixed** `4a7b1f01` / dust commit: orphan max $5, refuse held-under-stop, holdings coerce. Runner restarted. **Watch 48h** — fix is not proven in a live cycle yet |
| Small orphan dust (2026-09-18, 09-20) | LINK residuals, one −$0.82 | Same cap fix |
| Rotation sells | 24 `rotation_exchange`, about −$1.30 | Real but small vs SL/bug class. Not the idle-book cause |
| Real TP | 2 fixed TP ~+$6, 1 trail ~+$0.62 | Path can pay. N is tiny |
| Door package | RSI65 + 180m latch + thaw, then **expired early 2026-09-22** on Brad GO | Intentional. Fewer moving pieces. Not a regression bug |
| Transition knob map $0 | `transition → usdc_hold` blocked buys until P1 restore | Restored. Current regime is `flat/deploy`, not that choke |
| Stale dashboard regime | Signals pane served old `bear/usdc_park` until dashboard restart | Display bug. Do not trade off a stale pane |

**Claim class:** process tax is a P&L liability. Fixing the path is primary. Voiding bug-induced ledger rows was correct. Do not launder honest stops the same way.

`stop_loss_exchange` pnl sums in a naive 35d group-by are **not** a clean tax number (one LINK row printed +$114 on an SL reason — lot-match noise). Use stamped RT boards, not raw reason sums, before any “SL made money” sentence.

---

## 4. Are parameters too restrictive?

**Partly, by design. Not the way the idle book feels.**

Closed right now:

- Sentiment floor **0.30** on tryout (B1). Both doors fail it because X is **8h old**, not because the floor is stacked on 0.35.
- RSI max **55**. Blocks LINK (57.7) even if sent cleared. Does **not** block ETH (53).
- Thaw / RSI65 / 180m latch **off** (door expired).
- Run-phase / missfire / buy_block are **not** the current ETH/LINK reasons.

Open right now:

- Regime deploy, cap $75, seats 0/4, cash enough for a $25 seat, park off.

So “too restrictive” is true **only if** we decide aged-mid-cycle silence should still buy, or RSI 55–60 should still buy. That is a product choice. It is not what the tests have earned.

**Tonight’s 21:00 X refresh is the honest test of the floor.** If fresh eng still prints &lt; 0.30 on ETH and LINK, the sensor is quiet — cutting the floor buys noise. If fresh eng clears 0.30 and only RSI 55 blocks LINK, the restrictiveness claim is real and narrow.

---

## 5. Do current tests offer a better entry?

**No. Not yet.** Honesty tags from disk:

| Test | Latest claim | What it does *not* say |
|------|----------------|------------------------|
| Knife filter | `ATTENTION_ONLY`, n_pairs=2, all arms allow=2, sl=0, mean_r ~0.29–0.37 | No SL separation. Do not block or prefer an arm |
| Jev select-few CF | `N_INSUFFICIENT`, paper buys **0**, n_closed **0**, 6 calls today | Jev has not tagged a buy. Weekly TG Sunday is a scoreboard, not a strategy |
| RSI-event X shadow | `ATTENTION_ONLY_sensor_clock`, trigger pool **0** | No RSI≤40 wash on the two doors. Clock path owns the window |
| Scale-up shadow | `INSUFFICIENT_N` (4 exits). Mean excess scale−tryout **−0.003** | Scale path did **not** beat tryout-only. Live apply false. Do not kindle |
| Limit-first pilot | Enabled, **0 attempts today** | Cost cut, not an entry unlock. Fill rate unknown |
| Luck ladder | R0/R1 running, R2–R4/R6 blocked or scheduled, R5 path armed but money off | No rung is promote-ready |
| Platform spine | Ops **GO**, money path **ATTENTION**, edge claim false, choke labeled `promote` | Do not auto-promote to “get active” |
| Break-even one-pager | `N_INSUFFICIENT_path_proof_only`. Illustrative gap vs $150/mo is large on a 1-day window | Not a reason to force trades |
| Attribution RT weekly | Last built **2026-09-12**, n=7, edge claim false | Stale. Rebuild before using it in a loosen argument |

**Rule:** a green isolation test or a quiet cron is not an opportunity. Opportunity requires a would-buy that also clears Python floors, then a fill that is not dust.

---

## 6. Forward sequence

### Wave 0 — Watch the fix (no GO required, no knobs)

**Objective:** Confirm the 2026-09-24 dust fix holds on the next runner cycles.

**Must not:** force rebalance, change floors, re-open thaw.

**Check after each 21:05 cycle for 48h:**

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. .venv/bin/python3 - <<'PY'
import json
from pathlib import Path
# last dust / bug sells
rows=[]
for line in Path("trades/phase6_trades.jsonl").read_text().splitlines()[-30:]:
    r=json.loads(line)
    if r.get("side")=="SELL" and "dust" in str(r.get("exit_reason") or r.get("reason") or ""):
        print(r.get("timestamp"), r.get("pair"), r.get("exit_reason") or r.get("reason"), r.get("pnl"))
print("--- readiness ---")
t=json.loads(Path("data/state/tryout_readiness_latest.json").read_text())
print(t.get("plain_english"))
print("can_buy", t.get("can_buy_before_next_rebalance"), "seats", t.get("seats_used_today"), "/", t.get("max_new_seats_per_day"))
for p in t.get("pairs") or []:
    print(p.get("pair"), p.get("allowed"), p.get("reasons"), "eng", p.get("eng_sent"), "rsi", p.get("rsi"))
PY
```

**Pass:** no new `dust_sweep_orphan` on a notional ≥ $10 bag. SL coverage on any new risk seat = 1.0 within one cycle.

**Fail:** any full-seat market sell tagged dust → stop Wave 2, file ops, do not loosen.

### Wave 1 — Prove the current shell (default, no knob GO)

**Window:** next **three** natural slots: 2026-09-24 21:00, 2026-09-25 21:00, 2026-09-26 21:00 PT (X at :00, rebalance ~:05). Do **not** force-rebalance to “validate.”

**Score each slot (disk, not Telegram dumps):**

| Question | Pass looks like |
|----------|-----------------|
| Did fresh X clear 0.30 on a door? | eng ≥ 0.30 after 21:00 refresh |
| Did RSI block a sent-clear door? | reason is only `rsi > 55` |
| Did a risk BUY fill? | ledger BUY, not stable, seat counter +1 |
| Did SL attach? | no naked bag, no CR-03 cancel+dust |
| Did it survive the session? | no same-session SL, no dust full-bag |

**Wave 1 success:** ≥1 risk fill with SL on, held past the same session, exit reason not `process_bug_*`. Then **stop**. Watch the exit stack. Do not scale. Do not add doors.

**Wave 1 empty after 3 slots:** go to Wave 2 **only with Brad GO**. Idle cash is an allowed outcome (control arm). It is not a failure of the mission by itself.

### Wave 2 — One dated loosen (requires explicit GO)

Pick **one** row. Do not combine.

| ID | Package | When it is the right pick | Kill |
|----|---------|---------------------------|------|
| **W2-A** | Dated 7-day door: tryout RSI max 55→65 **and** 180m sent latch, shell stays `$25×≤4`, no thaw of tier-C basket, no auto-promote | Fresh X **does** clear 0.30 sometimes, but RSI 55 or mid-cycle age still blocks the only liquid doors. This is the package that already produced a ZEC TP, then was expired to reduce moving pieces | Same-session SL, dust full-bag, or fee drag with no hold. Auto-expire. Do not codify |
| **W2-B** | Floor only: quality-tryout 0.30→0.20 for 7 days. RSI 55 stays | Fresh X on ETH/LINK lands in 0.20–0.29 and RSI is otherwise ok. **Not** if fresh eng is ~0.03 — that is a quiet sensor, not a tight floor | Any buy with eng &lt; 0.20, or WR/process-tax worse than the expired door window |
| **W2-C** | RSI only: 55→60 for 7 days. Floor stays 0.30 | A door is sent-clear and RSI is 55–60. **Useless alone tonight** — both doors fail sent | LINK-style chase into extension (`run_phase` still blocks late FOMO) |
| **W2-D** | No loosen. Keep shell. Treat idle USDC as the control vs the bot | Fresh X stays ≪ 0.30 and tests stay N-thin | Revisit only on a new dated GO |

**Recommendation if Wave 1 is empty:** do **not** default to W2-B or W2-C from today’s 17:00 board. Wait for the 21:00 print.

- If 21:00 eng ≥ 0.30 and the only block is RSI → **W2-C** (narrow) or **W2-A** (if age also bites between refreshes).
- If 21:00 eng still ~0.03–0.10 → **W2-D**. Cutting the floor would be buying a dead sensor.
- Do **not** re-open basket thaw. The expired package’s thaw was the piece most likely to seat junk. Shell + RSI/latch is enough if anything re-opens.

Rollback for any W2: set the dated flags false, rewrite readiness, restart runner only after the config write is verified. No force-rebalance as the rollback.

### Wave 3 — Tests: keep, don’t promote

| Arm | Next action | Promote bar (not now) |
|-----|-------------|------------------------|
| Jev select-few CF | Let 8:15/14:15/20:15 ticks run. Read Sunday 18:30 TG card | n_closed ≥ 20 **and** rank beats RSI+sent on forward R. Still paper |
| Knife | Keep local cron. Do not add a live block | n_allow ≥ 20 with SL join, one arm strictly lower SL rate after fees |
| RSI-event X | Keep shadow. Paid probe stays budgeted, `live_gate` off | Would-buy that matches a later clean fill, not a spray |
| Scale-up | **Do not apply.** CF excess is negative at n=4 | n≥8 and excess &gt; 0 after fees, then still Brad GO per step |
| Limit-first | Leave enabled as cost cut. Score fill rate when Wave 1 actually buys | ≥30 attempts or 14d before any “maker saved us” sentence |
| R2 exit geometry | Do not staff a new dig this week | ≥5 clean non-bug RTs to join |
| Attribution weekly | Rebuild the board (stale since 2026-09-12) as a **read** before any W2 memo | Edge claim stays false under n&lt;20 |

No new cron that posts JSON to Telegram. Measure jobs stay `deliver=local` + empty stdout.

### Wave 4 — Explicitly not this plan

- New pair-discovery digs, STAMPEDE, TV snipers, Brainstormity SDK
- `live_membership_swaps`, auto-promote, dual_agree as a live swap
- Jev `would_order`, Jev stops, Jev replacing eng floors
- Perma-block expansion (live scars stay RAVE/UNI only)
- Cutting paid X 2×/day this week (already held)
- Permanent door-package codify
- Quoting break-even $150/mo as a reason to force a seat

---

## 7. What “done” means

| Horizon | Done |
|---------|------|
| 48h | No full-bag dust sell. Runner still the post-fix PID lineage (or a documented restart) |
| 3 slots | Written slot card: eng after refresh, RSI block, fill or honest idle |
| If fill | SL on, not same-session bug exit, ledger reason is a real exit not `process_bug_*` |
| If no fill | Brad picks W2-A/B/C/D. Default recommendation computed from the 21:00 prints, not from this afternoon’s aged eng |
| Tests | Still measure-only. Sunday Jev card + BE one-pager are reads |

---

## 8. Grill (frontier — answer these, then GO)

Facts above are settled. These do not depend on each other.

**Q1 — Next 7 days, what is the job?**
- A) Prove the current shell on natural 21:00 slots (recommended)
- B) Loosen now so something fills before Sunday
- C) Q&A only, no further ops

Recommendation: **A.** A loosen tonight cannot see fresh X, and the dust fix has not survived a cycle yet.

**Q2 — If three slots are empty, which single package?**
- W2-A dated RSI65+latch, no thaw
- W2-B floor 0.20
- W2-C RSI 60 only
- W2-D stay idle (recommended **until** the 21:00 eng print exists; then pick from the rule in Wave 2)

Recommendation: **do not pre-commit B or C.** Pre-commit the *rule*: sent-clear + RSI block → C or A; quiet sensor → D.

**Q3 — Shadows**
- Keep all measure-only (recommended)
- Promote one arm anyway

Recommendation: **keep.** Knife n=2, Jev n_closed=0, scale-up excess negative. Promoting any of them is theater.

---

## 9. Files this plan will touch later (not now)

Only after a named GO:

- Wave 0/1: none (read `data/state/tryout_readiness_latest.json`, `trades/phase6_trades.jsonl`)
- W2-A/C: `config/trading_config_phase6.json` tryout RSI / latch flags + readiness rewrite + runner restart note
- W2-B: same file, `quality_tryout` floor only
- Wave 3 read: `scripts/phase6/run_attribution_rt_weekly.py` (rebuild report only, no knobs)

Isolation already covers dust refuse: `phase6/tests/test_isolation_sl_dust_sweep.py`. Re-run before any claim that the cap “held.”
