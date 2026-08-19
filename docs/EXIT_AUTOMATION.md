# Exit automation — big picture

**Goal:** Automated trading platform. End-users change **few settings**. The bot runs.

## End-user knobs (short list)

| Knob | Where | Default now |
|------|--------|-------------|
| `take_profit.mode` | `config/exit_automation.json` | **`shadow`** |
| `take_profit.fixed_tp_pct` | same | `0.06` |
| `take_profit.trail.*` | same | arm 4% / trail 2% / BE 0.5% |
| SL % / adaptive | `trading_config` risk_management | live |
| Regime park / hard-exit thresholds | `regime_cash_policy.json` | live |
| `hard_exit.operator_approve` | regime_cash_policy | **true** (temporary human loop) |

**Not the product:** approving every sell forever. Operator loop is a **safety exception** while we prove exits.

## Layers

1. **Regime exit map (primary policy shadow)** — Bull/Flat/Bear knobs for TP/trail/RSI would-fire. Telegram **off** (weekly review). Doc: `docs/REGIME_EXIT_POLICY_MAP.md`. State: `regime_exit_shadow_status.json`.
2. **Global Shadow TP (legacy instrumentation)** — fixed ~6% + trail on all regimes; still logs to `shadow_tp_status.json`. Telegram **muted** (`notify_on_would_fire: false`). Superseded for *policy* by the regime map; optional backup log until map is trusted, then `mode: off`.
3. **One-time promote** — only after multi-regime gates + Brad OK. Prefer promoting via regime map design, not a blind global 6% flip.
4. **Hard exit** — thresholds already knobs; human loop **for now** (`operator_approve: true`). Off the loop: `operator_approve: false` + `live_apply: true` after review.
5. **Trail market exits** — `live_market_exit` stays **false** until quality is good.

## Promotion (settings, not chats)

Global TP hints in `exit_automation.promotion` are legacy. Prefer:

- Regime map collection ~**60d** + per-regime episodes  
- Offline study re-run  
- Brad OK  

`auto_promote: false`. Not five Telegrams a day.

## Commands

```bash
# status
cat data/state/shadow_tp_status.json | head -80

# isolation
PYTHONPATH=. python3 phase6/core/test_isolation_shadow_tp.py

# one-shot eval (no runner)
PYTHONPATH=. python3 -c "from phase6.core.shadow_tp import apply_shadow_tp_from_runner; from types import SimpleNamespace as S; print(apply_shadow_tp_from_runner(S()))"
```

## Related

- Path study: `reports/TP_TRAIL_PATH_STUDY_2026-07-29.md` / `…_2026-08-05.md`
- **TP + RSI vs SL by regime (offline):** `reports/EXIT_THRESHOLD_REGIME_STUDY_2026-08-06.md`  
  Runner: `phase6/research/run_exit_threshold_regime_study.py`  
  State: `data/state/exit_threshold_regime_study_latest.json`  
  Read: thresholds are **regime-dependent** (bear → ride/SL; bull/flat → TP ~5–6% class). Not a live flip.
- **Regime exit policy map (live shadow):** `docs/REGIME_EXIT_POLICY_MAP.md` · `config/regime_exit_policy_map.json` · `phase6/core/regime_exit_shadow.py`  
  Collects would-fires by regime for ~60d; no orders until gates + Brad OK.
- Hard-exit loop (exception mode): `docs/HARD_EXIT_OPERATOR_LOOP.md`
- Code: `phase6/core/shadow_tp.py`
