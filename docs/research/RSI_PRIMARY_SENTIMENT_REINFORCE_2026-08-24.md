# RSI Primary / Sentiment Reinforce — Deploy Structure Spec

**Date:** 2026-08-24  
**Status:** Implementing (P0 live hard gates; P1 sentiment-fade **shadow**)  
**Trigger:** LINK 09:00 full-wallet deploy on flat RSI (~47) + hot X sentiment (~0.89); ~80% NAV single name; no wired exit when sentiment cools.  
**Principle (Brad):** *RSI is grounded fact. Sentiment is transient timing reinforcement and can flip on a dime.*

---

## 1. Problem (asymmetric structure)

| Stage | Behavior before fix | Failure mode |
|-------|---------------------|--------------|
| Signal | Weighted: RSI extreme ±0.4, sentiment ±0.3; BUY if score > 0.25 | Sentiment alone (RSI 30–70) → score 0.30 → legal BUY |
| Allocator | Emergency Recovery (≤2 seats) drops min_buy 0.55→0.30; splits **all free cash** across top strong | One ticket can be entire free cash |
| Caps | `rebalance_cap_usd` / REGIME-CASH often soft on ARCH-4 recovery | Log “cap $100”, fill ~$1.9k |
| Exit | Live TP = price (+4% arm / +6% fixed); hard prefer_exit = operator shadow; sent hold only at ≤−0.35 | Sentiment fade does nothing until clock / SL |

**Result:** Sentiment opens the door; nothing closes it on the same axis. Concentration risk + 12h wait.

---

## 2. Design principles

1. **RSI structure first** for *full* deploy size. Neutral/chop RSI is not a full-wallet thesis.
2. **Sentiment reinforces timing**, never substitutes for structure on large tickets.
3. **Hard money ceilings bind on every BUY path**, including Emergency Recovery and light_tilt.
4. **Entry drivers are durable tags** on the lot (ledger / state) so exits can match the entry thesis.
5. **Sentiment fade is shadow-first** (notify + log). Live trim only after Brad promote (Trust SOP).
6. **Expectation honesty:** if a number is not a hard bind, UI/logs must not present it as one.

---

## 3. Classification: entry drivers

Pure function on `(rsi, sentiment, reason_text?)` → drivers + flags.

| Driver | Condition (defaults) |
|--------|----------------------|
| `rsi_oversold` | RSI < 35 |
| `rsi_structure` | RSI in [35, 55) with reason/score implying RSI contributed, **or** RSI < 40 |
| `rsi_continuation` | RSI in [40, 68] **and** momentum_pct ≥ +1.5 (when available) |
| `sentiment` | sentiment ≥ 0.20 |

Derived flags:

- `sentiment_only` = has `sentiment` and **no** RSI driver (`rsi_oversold` | `rsi_structure` | `rsi_continuation`)
- `sentiment_led` = `sentiment_only` **or** (has sentiment and strongest structural driver is absent and RSI in dead band [40, 60])
- `full_size_ok` = has at least one RSI driver (not sentiment-only)

Defaults live in config key `rsi_primary_deploy` (see §6). Tunable via OPT later; not magic constants buried only in code.

---

## 4. P0 — Hard deploy gates (LIVE)

Applied to every BUY action in TradePlan **after** allocator, **before** execute (same filter chain as add_risk / regime_cash).

### 4.1 Sentiment-only size haircut

```
if sentiment_only:
    usd *= sentiment_only_size_frac   # default 0.35
    reason += "|sent_only_haircut"
```

If after haircut `usd < min_move_usd` → **drop** BUY (do not dust-deploy).

### 4.2 Hard ticket ceiling

```
ticket_cap = rebalance_cap_usd   # from runtime_knobs / regime snap (must be numeric ≥ 0)
if ticket_cap > 0:
    usd = min(usd, ticket_cap)
```

**Hard bind:** this is not advisory. Recovery mode does not bypass.

### 4.3 Hard max pair weight after buy

```
room = max(0, max_pair_weight * equity - current_pair_usd)
usd = min(usd, room)
```

Defaults:

- `max_pair_weight`: 0.30 (recovery-safe; tighter than “all cash in one name”; looser than add_risk bull 0.22 so empty-seat re-entry still works)
- Emergency recovery may use `max_pair_weight_recovery` default **0.35** (still far from 80%)

If room < min_move → drop BUY.

### 4.4 Multi-buy diversification nudge (recovery)

When Emergency Recovery and ≥2 BUY candidates survive gates: prefer split already in allocator; **additionally** refuse any single action > `max_single_share_of_free_cash` (default 0.50 of free cash available to the plan).

### 4.5 What P0 does *not* do

- Does not auto-sell existing LINK/book.
- Does not change live TP / hard_exit promote.
- Does not enable mid-cycle *buys*.

---

## 5. P1 — Entry tags + sentiment-fade shadow

### 5.1 Entry tags (on successful BUY)

Persist on trade ledger row + `data/state/entry_driver_lots.json`:

```json
{
  "pair": "LINK-USD",
  "ts": "...",
  "entry_price": 11.60,
  "usd": 665.0,
  "drivers": ["sentiment"],
  "sentiment_only": true,
  "sentiment_led": true,
  "entry_rsi": 46.6,
  "entry_sentiment": 0.89,
  "order_id": "..."
}
```

Also copy into `indicators_at_trade` / trade JSON fields when present.

### 5.2 Sentiment-fade shadow (no live sell)

Each monitor tick / optional rebalance preflight:

For each open lot with `sentiment_led` or `sentiment_only`:

```
fade = entry_sentiment - current_sentiment
if fade >= sentiment_fade_delta          # default 0.40
   OR current_sentiment <= sentiment_fade_floor  # default 0.15
AND peak_return_from_entry < tp_arm_pct  # default 0.04 (not yet in trail profit zone)
AND position_usd >= min_position_usd
→ emit SHADOW would_trim (fraction default 0.50), Telegram deduped, JSONL audit
```

**Live apply:** blocked until `sentiment_fade.mode = live` **and** Brad go (same pattern as hard_exit / TP promote). Default mode = `shadow`.

### 5.3 Optional time-stop shadow (same module, off by default)

`time_stop_hours` default null/0. If set (e.g. 12) and MFE < 1% and sentiment_led → shadow prefer_reduce. Not enabled day-1.

---

## 6. Config shape

`config/trading_config_phase6.json` → `rsi_primary_deploy`:

```json
{
  "enabled": true,
  "rsi_oversold_max": 35.0,
  "rsi_structure_max": 40.0,
  "rsi_deadband_low": 40.0,
  "rsi_deadband_high": 60.0,
  "rsi_continuation_max": 68.0,
  "mom_continuation_pct": 1.5,
  "sentiment_reinforce_min": 0.20,
  "sentiment_only_size_frac": 0.35,
  "max_pair_weight": 0.30,
  "max_pair_weight_recovery": 0.35,
  "max_single_share_of_free_cash": 0.50,
  "enforce_rebalance_cap": true,
  "sentiment_fade": {
    "mode": "shadow",
    "fade_delta": 0.40,
    "fade_floor": 0.15,
    "trim_fraction": 0.50,
    "min_position_usd": 25.0,
    "notify_telegram": true,
    "notify_dedupe_hours": 6,
    "time_stop_hours": 0
  }
}
```

---

## 7. Code map

| Piece | Path |
|-------|------|
| Pure rules | `phase6/core/rsi_primary_deploy.py` |
| Filter on plan | `filter_trade_plan_rsi_primary_deploy(runner, plan, ...)` |
| Wire | `phase6/core/rebalance_coordinator.py` after regime_cash / add_risk |
| Entry lot store | `data/state/entry_driver_lots.json` via module helpers |
| Fade shadow eval | same module + `scripts/phase6/run_sentiment_fade_shadow.py` |
| Isolation | `scripts/phase6/test_isolation_rsi_primary_deploy.py` |
| Counterfactual BT | `scripts/phase6/backtest_rsi_primary_deploy_cf.py` |
| Spec (this doc) | `docs/research/RSI_PRIMARY_SENTIMENT_REINFORCE_2026-08-24.md` |

---

## 8. Validation

### 8.1 Isolation (mandatory)

- Sentiment-only BUY $2000 → haircut to 0.35× then ticket/pair caps.
- RSI oversold + sent → full size subject only to hard caps.
- Pair already 25% equity, max_weight 30% → room 5% only.
- Cap $100 binds on recovery $1925 proposal → $100.
- Fade: entry sent 0.89 → 0.40, no TP arm → would_trim shadow.
- Fade: price already +5% (armed) → no fade trim (TP owns exit).

### 8.2 Counterfactual backtest

Replay `trades/phase6_trades.jsonl` BUY legs (and rebalance logs when RSI/sent available):

- Baseline: historical notional / max single ticket / max pair weight proxy.
- CF: apply P0 gates with recorded or reconstructed rsi/sent.
- Report: tickets clipped, $ not deployed, max ticket reduction, LINK-2026-08-24 case study.

### 8.3 Live verify (post-wire)

- Next dry allocate with current book: no path proposes >cap or full cash sentiment-only.
- Fade shadow dry-run on LINK lot if tagged (or backfill tag from 09:00 buy + caches).

---

## 9. Promotion ladder

| Step | Gate |
|------|------|
| P0 live | Isolation green + CF case study shows LINK would have been ≤ cap×haircut |
| P1 shadow | Events JSONL + optional TG; 0 live sells |
| P1 live trim | Brad explicit go after shadow sample ≥ N or clear poster-child |
| Mid-cycle de-risk buys | Out of scope this change |

---

## 10. Non-goals (this change)

- Selling current LINK without Brad order.
- Flipping hard_exit to live_apply.
- Rewriting SignalGenerator weights (classification + size gates first; weight retune can follow OPT).
- Reddit path (already off).

---

## 11. Success criteria

1. Impossible for ARCH-4 recovery to place a single BUY > `rebalance_cap` when cap > 0 and enforce on.
2. Sentiment-only tickets size ≤ `sentiment_only_size_frac` of unconstrained proposal before caps.
3. Entry drivers recorded on new BUYs.
4. Sentiment fade produces shadow audit when led lots cool before TP arm.
5. Isolation + CF scripts exit 0 with printed evidence.
6. Spec + MASTER note updated.
