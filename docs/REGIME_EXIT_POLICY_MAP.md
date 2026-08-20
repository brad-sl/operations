# Regime exit policy map (shadow)

**Status:** live **shadow only** — no orders  
**Config:** `config/regime_exit_policy_map.json`  
**Code:** `phase6/core/regime_exit_shadow.py`  
**State:** `data/state/regime_exit_shadow_status.json` · `…_collection.json` · events jsonl  

## Plain English

Stop-loss (~3%) already protects the downside on the exchange.

This map is the **profit-side playbook by market weather**:

| Market regime | What the map does in shadow | Why |
|---------------|----------------------------|-----|
| **Bull** | Watch for ~**+6%** take-profit + trail; RSI hard-exit only if very hot (≥75) | Offline study: TP beat ride-to-stop |
| **Flat** | Watch for ~**+5%** take-profit + trail; RSI ≥65 watch | Offline study: TP beat ride-to-stop |
| **Bear** | **No** full TP / trail / RSI exit shadows on the map. **Plus:** partial **ladder scale-out** shadow (`bear_profit_take`) when green vs entry | Offline: early *full* TP hurt; ladder is separate hypothesis |
| **Transition / unknown** | Conservative (mostly ride/SL; light RSI watch in transition) | No solid offline cell |

**Nothing here sells.** Evidence is written to disk for **weekly review** — Telegram pings for this map are **off** (`notify_on_would_fire: false`).

Your assumption: **1–2 months** to see bull, bear, and flat with enough points. Default promote gate is **60 calendar days** of shadow collection, plus per-regime episode counts — **not** auto-on.

## Knobs (few)

Edit only `config/regime_exit_policy_map.json`:

- `mode`: `shadow` (keep until Brad OK)
- `enabled`: true/false
- per-regime `fixed_tp.pct`, `trail.*`, `rsi_hard_exit.overbought`
- `promotion.*` gates (days, min episodes, regimes required)

**Still separate (unchanged by this map):**

- Exchange SL  
- `exit_automation.json` global shadow TP (still runs; map is regime-aware layer)  
- `regime_cash_policy.hard_exit.operator_approve` (human loop until you flip)

## Collection gates (before any live discussion)

From `promotion` block:

| Gate | Default |
|------|---------|
| Calendar | **60 days** shadow (early review flag at 45d if some regimes cooking) |
| Episodes / regime | ≥ **5** unique would-fire episodes (30m gap = 1 episode, not tick spam) |
| Closed legs / regime | ≥ **15** (filled when offline study re-run stamps collection — optional) |
| Regimes for global flip | **bull + bear + flat** all ready |
| Auto promote | **false** — Brad OK required |

**Partial live (one regime only)** is off by default (`allow_partial_regime_live: false`). Prefer full multi-regime confidence.

## Commands

```bash
cd /home/brad/projects/crypto-trading-bot

# isolation
PYTHONPATH=. python3 phase6/core/test_isolation_regime_exit_shadow.py

# one-shot status (uses live_state + regime_cash_status)
PYTHONPATH=. python3 -c "
from phase6.core.regime_exit_shadow import apply_regime_exit_shadow_from_runner
from types import SimpleNamespace
print(apply_regime_exit_shadow_from_runner(SimpleNamespace(rsi_values={}))['plain_english'])
"

# offline study refresh (path CF by regime)
PYTHONPATH=. python3 phase6/research/run_exit_threshold_regime_study.py 120

cat data/state/regime_exit_shadow_status.json | head -80
cat data/state/regime_exit_shadow_collection.json | head -80
```

Runner hooks each cycle next to shadow TP (`phase6_runner`).

## Promote later (not now)

1. Collection: 60d + episode gates on bull/bear/flat  
2. Re-run `run_exit_threshold_regime_study.py` — calls still support map  
3. Brad OK  
4. Then design **live** attach (per-regime or global) — separate change; map stays shadow until then  

## Related

- Offline study: `reports/EXIT_THRESHOLD_REGIME_STUDY_2026-08-06.md`  
- Global shadow TP: `docs/EXIT_AUTOMATION.md`  
- Hard-exit loop: `docs/HARD_EXIT_OPERATOR_LOOP.md`  
