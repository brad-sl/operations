# Ladder path CF by regime (bull / flat / bear / transition)

**As of:** 2026-08-21T01:15:54.860590Z
**Schema:** `ladder_path_cf_by_regime_v1`

## Portfolio read

- **Bull:** `no_clear_exit_upgrade`
- **Flat:** `no_clear_exit_upgrade`
- **Bear:** `pursue_ladder_shadow`
- **Transition:** `park_priority_exits_secondary`

On synthetic enter-while-in-regime paths (same method as bear P2): ladder helps vs SL only in **bear** (less-loss). Bull/flat: both ladder and full TP lose to ride-SL on this sample — do not promote ladder there; map full-TP still rests on the separate ledger EXIT_THRESHOLD study (prefer_tp bull/flat). No live flips from this report.

## Per regime

| Regime | N | SL mean | Full TP mean | Ladder mean | Δ lad−SL | Δ lad−TP | Δ TP−SL | Call | Edge |
|--------|---|---------|--------------|-------------|----------|----------|---------|------|-------|
| bull | 230 | 0.51% | -0.73% | -0.35% | -0.86% | 0.39% | -1.25% | `no_clear_exit_upgrade` | `NO_CLEAR_EDGE` |
| flat | 552 | 0.61% | -0.44% | -0.15% | -0.75% | 0.30% | -1.05% | `no_clear_exit_upgrade` | `NO_CLEAR_EDGE` |
| bear | 276 | -1.91% | -0.88% | -0.96% | 0.94% | -0.08% | 1.02% | `pursue_ladder_shadow` | `LESS_LOSS_VS_SL` |
| transition | 441 | 0.82% | -0.53% | -0.13% | -0.95% | 0.40% | -1.35% | `park_priority_exits_secondary` | `NO_CLEAR_EDGE` |

## Plain English by regime

### bull

bull: no_clear_exit_upgrade. full_tp loses to SL by ~1.25% mean ΔR (ride-SL preferred for full exit); ladder worse than SL ~0.86%; ladder beats full_tp by ~0.39% — multi-slice product edge. Means: SL=0.51% TP=-0.73% ladder=-0.35% (N=230). Edge class: NO_CLEAR_EDGE.

- Ladder beats SL rate: **0.9217** · Full TP beats SL: **0.1957** · Ladder beats full TP: **0.8**
- Green path rate — SL **0.0826** · TP **0.2739** · ladder **0.2957**

### flat

flat: no_clear_exit_upgrade. full_tp loses to SL by ~1.05% mean ΔR (ride-SL preferred for full exit); ladder worse than SL ~0.75%; ladder beats full_tp by ~0.30% — multi-slice product edge. Means: SL=0.61% TP=-0.44% ladder=-0.15% (N=552). Edge class: NO_CLEAR_EDGE.

- Ladder beats SL rate: **0.9366** · Full TP beats SL: **0.279** · Ladder beats full TP: **0.7228**
- Green path rate — SL **0.0725** · TP **0.346** · ladder **0.346**

### bear

bear: pursue_ladder_shadow. full_tp beats SL by ~1.02% mean ΔR (supports map TP); ladder less-loss vs SL ~0.94% mean ΔR; ladder ≈ full_tp. Means: SL=-1.91% TP=-0.88% ladder=-0.96% (N=276). Edge class: LESS_LOSS_VS_SL.

- Ladder beats SL rate: **0.942** · Full TP beats SL: **0.2029** · Ladder beats full TP: **0.7935**
- Green path rate — SL **0.0688** · TP **0.2572** · ladder **0.3043**

### transition

transition: park_priority_exits_secondary. full_tp loses to SL by ~1.35% mean ΔR (ride-SL preferred for full exit); ladder worse than SL ~0.95%; ladder beats full_tp by ~0.40% — multi-slice product edge. Means: SL=0.82% TP=-0.53% ladder=-0.13% (N=441). Edge class: NO_CLEAR_EDGE.

- Ladder beats SL rate: **0.9206** · Full TP beats SL: **0.22** · Ladder beats full TP: **0.7778**
- Green path rate — SL **0.0816** · TP **0.2971** · ladder **0.3356**

## Takeaways (honest)

### Sample

- **This run:** synthetic entries on real daily OHLCV while BTC already in that regime (same construction as bear P2). **Ledger legs matched here: 0** (FIFO rounds lacked usable bar paths / regime tags in this harness).
- **Different study:** `EXIT_THRESHOLD_REGIME_STUDY` used closed ledger legs and found bull `prefer_tp_06` / flat `prefer_tp_05` / bear `prefer_sl_ride` for **full** exits. That still stands for the **map**. This report only answers: *does the bear ladder recipe help in bull/flat too?*

### What the ladder recipe does by regime

1. **Bear — yes (less-loss):** ladder ≈ full TP, both beat ride-SL (~+0.9–1.0% mean ΔR). Keep **ladder FEAT** as bear specialty; map still leaves full TP off (ledger prior).
2. **Bull / flat — no ladder promote:** on this sample both ladder and full TP **lose to ride-SL**. Ladder slightly softens full-TP pain but is **not** an upgrade over SL. **Do not** extend bear ladder live intent to bull/flat.
3. **Transition — no:** same pattern as bull/flat; park/cash stance stays primary.
4. **Why bull/flat disagree with EXIT_THRESHOLD:** entering *after* BTC is already labeled bull/flat is a late/synthetic path; ledger legs that caught earlier moves can still favor TP. Map TP shadow collection remains the right bull/flat opt lane — not this ladder.
5. No live config writes.

Artifacts: `/home/brad/projects/crypto-trading-bot/data/state/ladder_path_cf_by_regime_latest.json` · `reports/LADDER_PATH_CF_BY_REGIME_LATEST.md`
