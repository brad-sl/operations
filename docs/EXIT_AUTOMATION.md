# Exit automation — big picture (SSOT)

**Last verified:** 2026-08-26  
**Goal:** Automated platform. End-users change **few settings**. The bot runs.  
**Trust SOP:** `docs/sop/TRUST_FIRST_TRADING_ENGINE.md`

---

## Plain English first

| Term | Meaning |
|------|---------|
| **Stop-loss (SL)** | Exchange order that caps ~3% loss from bag entry. Always live floor. |
| **Take-profit / trail (TP)** | Software bank of gains: arm after ~+4%, trail 2% pullback; fixed +6% fallback. **LIVE** market sells (not exchange limit TP). |
| **Hard exit** | RSI overbought / weak sentiment reduce. Default = **operator approve**, not auto. |
| **Dual-peak / lifecycle** | Structure + sentiment fade trims on a run. Live half-trims only when **green** vs entry (P0 2026-08-26). |
| **Structure BOS** | Break of last higher-low after a real run. **Shadow only** (no sells yet). |
| **Bear ladder** | Partial +3/+5/+8% scale-out in **bear only**. Shadow; collect real bear days. |
| **Protected market exit** | Shared Coinbase dance: cancel stops → wait free size → market sell → reattach SL. |

Do **not** conflate would-fire Telegram / shadow ticks with live sells.

---

## End-user knobs (short list)

| Knob | Where | Live default now |
|------|--------|------------------|
| `take_profit.mode` | `config/exit_automation.json` | **`live`** (promoted 2026-08-23) |
| `take_profit.fixed_tp_pct` | same | `0.06` (software fallback) |
| `take_profit.trail.*` | same | arm **4%** / trail **2%** / BE 0.5% |
| `take_profit.live_market_exit` | same | **`true`** (primary) |
| `take_profit.live_attach_on_buy` | same | **`false`** (H2 wired, not flipped) |
| `take_profit.post_tp_block_rebuy_hours` | same | **24h** |
| `take_profit.post_tp_structure_aware` | same | **true** (EXIT-H4 early release) |
| SL % / adaptive | `trading_config` risk_management | live |
| Regime park / cash | `regime_cash_policy.json` | live |
| `hard_exit.operator_approve` | regime_cash_policy | **true** (+ cautious **flat** auto path) |
| Dual-peak mode | `trading_config.run_lifecycle.dual_peak_exit` | **live** (green-only gates) |
| Structure BOS | `config/structure_bos_exit.json` | **shadow** |
| Bear ladder | `config/bear_profit_take.json` | **shadow** |

**Not the product:** approving every sell forever. Operator loop is a **safety exception** while hard-exit / BOS prove out.

---

## Layers (stack order — decision vs execution)

```
DECISION (should we exit? how much?)
  1. Exchange SL                          — always on
  2. Global trail / fixed TP              — LIVE software market exit
  3. Dual-peak / lifecycle partials       — LIVE when green + gates
  4. Hard exit (RSI / sent)               — shadow + operator (flat cautious auto)
  5. Structure BOS                        — shadow only
  6. Bear profit ladder                   — shadow; bear regime only
  7. Regime exit policy map               — shadow collection by regime

EXECUTION (how we sell without stuck size)
  ★ protected_market_exit                 — SSOT cancel→poll→sell→reattach
```

### Layer details

| # | Layer | Live money? | Config / code | State |
|---|--------|-------------|---------------|--------|
| 1 | **Stop-loss** | **Yes** | trading_config risk_management · `stop_loss_manager` | exchange + ledger |
| 2 | **Global TP / trail** | **Yes** | `exit_automation.json` · `phase6/core/shadow_tp.py` | `shadow_tp_status.json`, `shadow_tp_live_exits.jsonl` |
| 3 | **Dual-peak / lifecycle** | **Yes** (trims) | `run_lifecycle` · monitor_reentry_sl_tp | dual_peak events / live_state lot counters |
| 4 | **Hard exit** | Operator / cautious flat | `regime_cash_policy.hard_exit` · `regime_cash_policy.py` | `regime_hard_exit_shadow.json`, pending inbox |
| 5 | **Structure BOS** | **No** | `structure_bos_exit.json` · `structure_bos_exit.py` | `structure_bos_exit_status.json` |
| 6 | **Bear ladder** | **No** | `bear_profit_take.json` | `bear_profit_take_shadow_status.json` |
| 7 | **Regime exit map** | **No** | `regime_exit_policy_map.json` | `regime_exit_shadow_status.json` |
| ★ | **Protected market exit** | mechanics | `phase6/core/protected_market_exit.py` | callers: shadow_tp, run_lifecycle |

---

## Take-profit (current product)

### Behavior

1. **Trail primary:** when mark return `r` arms at ≥ **+4%**, track `peak_r`; fire if pullback ≥ **2%** from peak (with breakeven lock).  
2. **Fixed +6% fallback:** software market exit if trail not the firer and `r ≥ 0.06`.  
3. **PAXG / preserve excluded** (`exclude_pairs`).  
4. **No exchange limit TP on buy** unless `live_attach_on_buy=true` (double-path risk).  
5. **Qty SSOT (EXIT-H5):** reads `position_qty` (`amount`/`qty`/`quantity`).  
6. **Execution:** `execute_live_tp_exits` → **`protected_market_exit`** (not raw market sell under a live stop).

### Gap / lot functionality (CRITICAL)

Old gap gate (`peak − r > 0.15`) **failed** UNI 2026-08-23 (gap ~0.115 → trail dump ~90s after rebal at −0.3%).

**SSOT:** `sanitize_peak_r_for_lots` in `shadow_tp.py`:

| Rule | Effect |
|------|--------|
| Drop peaks for pairs not held | No orphan trail on flat book |
| No `peak_lot` + leftover peak | Reset peak := current `r` (`unbound_peak_new_lot`) |
| `entry_px` moved > **0.5%** vs lot | Reset (`entry_changed`) — new lot |
| Same lot | Keep peak so real pullbacks still fire |
| Real live TP exit | Clear peak/lot (not dry_run) |

State: `peak_r` + `peak_lot` in `data/state/shadow_tp_status.json`.  
Regression: `phase6/core/test_isolation_live_tp_exit.py` · report `reports/INCIDENT_UNI_STALE_PEAK_TP_2026-08-23.md`.

**Related gaps (not trail peaks):**

| Gap | Where | Role |
|-----|--------|------|
| `near_stop_min_gap_pct` / `armed_stop_allow_add_min_gap_pct` | trading_config · runner_capital_events | Block adds when mark too close to stop |
| `add_risk.min_gap_pct` | regime_cash_policy | Pyramid add sizing gap |
| `min_structure_low_gap_pct` | structure_bos_exit | Ignore micro swing noise vs entry |
| SCALE **GAP-01…10** | `docs/testing/SCALE_TEST_LANES.md` | Platform scale backlog (exit scoreboard, post-SL, basket CF, …) — **not** trail peak math |

### Post-TP rebuy block (EXIT-H4)

| Setting | Value |
|---------|--------|
| Default block | **24h** `post_tp_rebuy_block` from ledger `take_profit_*` |
| Structure early release | After **≥4h**, if run phase ∈ **ignition/trend (1,2)** and `structure_ok` → drop block |
| Does **not** affect | SL 72h blocks, manual disposition cooldowns |
| Code | `runner_capital_events._apply_post_tp_structure_early_release` |

**Disposition honesty:** TP must **not** stamp 48h manual cash hold. Classify TP in disposition split. See skill ref `post-tp-block-and-disposition-20260823.md`.

### Dual-peak P0 (2026-08-26)

- No lifecycle half-trim while **mark < entry** (dicing red bags).  
- **Max 1 dual_peak trim per lot** until price makes a **new peak**.  
- Config under `run_lifecycle.dual_peak_exit`.  
- Monitor path can execute live when mode=live.

### Structure BOS (2026-08-26 shadow)

- Arm after ~+4% MFE; would-exit when close breaks last higher-low.  
- **No live sells** even if mode miss-set.  
- Collect vs trail TP + SL before promote talk.

### Protected market exit SSOT (2026-08-26)

Coinbase open stops **lock** base. Every profit path must:

1. cancel stops → 2. poll free (lag fallback) → 3. market sell → 4. reattach SL / full-exit cancel  

**Wired:** live TP, lifecycle dual-peak.  
**Follow-on OPEN:** operator_trim, dust sweep, order_executor sells (`P6-PROTECTED-EXIT-CALLERS-20260826`).

---

## Hard exit (unchanged product stance)

- Default: shadow + **operator_approve** inbox (`hard_exit_controls`).  
- Auto merge needs: `operator_approve=false` **and** `live_apply=true` **and** `shadow_only=false`.  
- **Cautious flat (2026-08-25):** flat-only auto when RSI cross-up + hold ≥24h + mark r≥0. Bull/bear/transition stay operator.  
- Never auto `park_prefer_reduce`.

---

## Promotion (settings, not chats)

| Surface | Gate |
|---------|------|
| Global TP | **Already live** (Brad 2026-08-23). `auto_promote: false` still. |
| Regime map | ~60d multi-regime shadow + Brad OK |
| Hard exit full auto | CF + FP review + Brad flip |
| Structure BOS | Episodes + scoreboard vs trail/SL + Brad |
| Bear ladder | Real bear calendar + episodes + Brad (`bear-ladder-promote-watch`) |
| Basket **swap-pair** | Separate product — see `docs/features/BASKET_SWAP_PAIR_PROMOTION.md` |

---

## Commands

```bash
cd /home/brad/projects/crypto-trading-bot

# TP status
python3 -c "import json;print(json.load(open('data/state/shadow_tp_status.json'))['mode'], json.load(open('data/state/shadow_tp_status.json')).get('live_market_exit'))"

# Isolation
PYTHONPATH=. python3 phase6/core/test_isolation_live_tp_exit.py
PYTHONPATH=. python3 scripts/phase6/test_isolation_protected_market_exit.py
PYTHONPATH=. python3 scripts/phase6/test_isolation_dual_peak_p0_gates.py
PYTHONPATH=. python3 scripts/phase6/test_isolation_structure_bos_exit.py
PYTHONPATH=. python3 scripts/phase6/test_isolation_exit_hardening_h2_h5.py

# Monitor (SL/TP/block hygiene + lifecycle hooks)
PYTHONPATH=. python3 scripts/phase6/monitor_reentry_sl_tp.py --json | head -80

# Hard exit CF
PYTHONPATH=. python3 phase6/research/run_h3_hard_exit_counterfactual.py --lookback-days 120
```

---

## Related docs

| Doc | Role |
|-----|------|
| `docs/REGIME_EXIT_POLICY_MAP.md` | Per-regime **shadow** map (global TP is live separately) |
| `docs/HARD_EXIT_OPERATOR_LOOP.md` | Operator approve path |
| `docs/research/EXIT_HARDENING_H2_H5_2026-08-24.md` | H2–H5 short notes |
| `docs/features/BEAR_PROFIT_TAKE_NO_SHORT_SPEC.md` | Bear ladder |
| `docs/features/BASKET_SWAP_PAIR_PROMOTION.md` | **Swap-pair promote + seat graduation** |
| `docs/BASKET_HOT_RELOAD.md` | Membership hot-reload after promote |
| `docs/testing/SCALE_TEST_LANES.md` | SCALE GAP-01…10 program |
| `docs/sop/TRUST_FIRST_TRADING_ENGINE.md` | Product trust standard |
| Skill | `phase6-exit-automation` (+ `phase6-sl-exits-and-dust`) |

## Code map

| Piece | Path |
|-------|------|
| Config | `config/exit_automation.json` |
| TP / trail | `phase6/core/shadow_tp.py` |
| Protected sell | `phase6/core/protected_market_exit.py` |
| Qty SSOT | `phase6/core/position_qty.py` |
| Post-TP blocks | `phase6/core/runner_capital_events.py` |
| Lifecycle / dual-peak | `phase6/core/run_lifecycle.py` |
| Structure BOS | `phase6/core/structure_bos_exit.py` |
| Monitor | `scripts/phase6/monitor_reentry_sl_tp.py` |
| Runner hooks | `phase6/core/phase6_runner.py` |
