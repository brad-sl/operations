# Volume velocity shadow — 2026-08-29T05:45:26

**Live orders: false** · RVOL nominator → evaluate queue research

- Stats universe: 48 · candles scanned: 65
- Nominations this run: **1**
- Open tracks: **40** · by bucket: {'dual_tf': 3, 'early_trend': 19, 'early_coil': 18}
- LQHV (high velocity, weak legacy gates): **33**
- Ever promote-eligible: 10 · never selected: 27

## Paper performance (equal $100 from nomination)
- All open: mean mark -4.39% · hit 0.25
- LQHV: mean mark -4.08% · hit 0.2727272727272727 · mean MFE +9.71%
- Never selected: mean mark -3.83% · hit 0.2222222222222222
- Ever promote: mean mark -5.75%

## Top open by mark_r
- CVX-USD [early_trend] r=+12.33% MFE=+24.66% rvol0=2.5356556062058138 promote_ever=False lqhv=True
- ASTER-USD [early_coil] r=+8.03% MFE=+14.96% rvol0=2.2780605623773535 promote_ever=False lqhv=True
- O-USD [early_trend] r=+6.74% MFE=+10.64% rvol0=2.4382938798605522 promote_ever=False lqhv=True
- TAO-USD [early_coil] r=+4.62% MFE=+11.40% rvol0=2.0566764802964337 promote_ever=True lqhv=True
- PENGU-USD [early_coil] r=+3.63% MFE=+12.99% rvol0=4.974649961088678 promote_ever=True lqhv=True
- S-USD [early_trend] r=+3.07% MFE=+15.58% rvol0=1.497107125545003 promote_ever=False lqhv=True
- DRIFT-USD [early_trend] r=+2.95% MFE=+5.57% rvol0=1.8660150434460028 promote_ever=False lqhv=False
- ICP-USD [early_coil] r=+1.88% MFE=+4.23% rvol0=2.150018496729638 promote_ever=False lqhv=True
- SPX-USD [early_coil] r=+1.27% MFE=+21.37% rvol0=2.5043899080742973 promote_ever=False lqhv=True
- WIF-USD [early_coil] r=+0.95% MFE=+18.19% rvol0=2.1881723686578924 promote_ever=True lqhv=True
- ETH-USD [early_coil] r=-0.15% MFE=+5.03% rvol0=2.3072807814560434 promote_ever=False lqhv=True
- SEI-USD [early_coil] r=-1.29% MFE=+5.17% rvol0=2.062390236571097 promote_ever=False lqhv=True

## Hypothesis
RVOL nominates early movers into evaluate queue. LQHV = high velocity but fails legacy discovery/promote gates — track if they outperform selected names (different filter set).

Artifacts: `data/state/volume_velocity_shadow_latest.json`, `volume_velocity_tracks.json`, `volume_velocity_nominations.jsonl`
