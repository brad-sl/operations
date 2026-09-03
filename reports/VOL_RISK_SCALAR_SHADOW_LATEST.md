# Vol + velocity risk scalar (Tier 1 shadow)
As of `2026-09-03T18:16:04.177470+00:00`

**No live size change. No orders. No config mutate.**

## Plain English

BTC daily vol ≈ 2.92% (EWMA 36h). Vol regime **high** → s_vol=0.78. Velocity stress=0.2727 → s_vel=0.87. **Combined s=0.68** Shadow would **cut** size vs baseline this cycle. Live book unchanged.

## Scalars

- **s_vol** (BTC EWMA): `0.7835` · regime `high`
- **s_vel** (velocity dampen): `0.8696` · stress `0.2727`
- **s_combined**: `0.6813`

## BTC / ETH vol

- `BTC-USD`: daily σ̂=0.02923360223732191 · ann≈55.9% · median_lr=0.013439626175418174 · ok=True
- `ETH-USD`: daily σ̂=0.03397767976628656 · ann≈64.9% · median_lr=0.018620752479019502 · ok=True

## Shadow size CF

```json
{
  "s_combined": 0.6813,
  "would_reduce": true,
  "would_fatten": false,
  "internal_cap_usd": 75.0,
  "would_cap_usd": 51.1,
  "note": "Internal engine budget \u00d7 scalar only. Not a trader-facing cycle ceiling; ARCH-2/rotation paths can still exceed on live until separately gated."
}
```

## Velocity bridge

```json
{
  "stress": 0.2727,
  "source": "volume_velocity_shadow_latest",
  "n_noms": 1,
  "max_rvol": 2.3553,
  "btc_rvol": null,
  "heat_n": 0.0833,
  "heat_r": 0.4277
}
```

## Doctrine

- Directional signals propose side; this scalar proposes relative size.
- RVOL/velocity → risk tolerance dampener + scout nominator (separate jobs).
- See `docs/research/VOL_CLUSTERING_RISK_SIZING_TIER1.md`.

