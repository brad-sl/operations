# Basket select arms (shadow parallel)
As of `2026-09-03T18:30:25.521702+00:00`

No arm is pre-certified as high-probability. Priors are medium at best until CF N matures.

## `baseline_hybrid` — Current discovery + hybrid RSI/sent/mom cycler
Prior: Live scorer. Recent CF mean excess negative — control to beat.
- CF 3d: N=35 excess=11.451171428571428 | 7d: N=27 excess=-0.04592592592592455
- Latest paper swap: ICP-USD → ADA-USD (replace low-potential ICP-USD (score=0.202, held=$0) with ADA-USD (score=0.610); Δ=0.408 | membership_gate=ok(potential_)

## `anti_pump` — Anti-pump / de-chase
Prior: Medium prior vs baseline for less loss: block hot 24h/3d extensions (RAVE-class). Not proven; may miss real breakouts.
- CF 3d: N=25 excess=4.17896 | 7d: N=23 excess=11.74295652173913
- Latest paper swap: ARB-USD → STX-USD (anti_pump: add=STX-USD score=0.0593 eject=ARB-USD score=-999.0 | membership_gate=M3:M3:delta_missing_scores)

## `risk_adj_mom` — Risk-adjusted momentum (ret/vol)
Prior: Literature-aligned TSMOM-ish sleeve pick. Medium prior on longer horizons; weak on 1–3d crypto noise. Not high-confidence.
- CF 3d: N=27 excess=2.616629629629629 | 7d: N=24 excess=14.589458333333335
- Latest paper swap: ARB-USD → ADA-USD (risk_adj_mom: add=ADA-USD score=14.4816 eject=ARB-USD score=-999.0 | membership_gate=M3:M3:delta_missing_scores)

## `rel_btc_stable` — Beat BTC + stability gate
Prior: Only add if 7d excess vs BTC > 0 and not extended. Conservative; may propose fewer swaps. Medium-low activity prior.
- CF 3d: N=31 excess=0.5549032258064512 | 7d: N=25 excess=6.43612
- Latest paper swap: SOL-USD → STX-USD (rel_btc_stable: add=STX-USD score=0.0705 eject=SOL-USD score=-999.0 | membership_gate=M3:M3:delta_missing_scores)

## `control_no_swap` — Never swap (hold membership)
Prior: Structural control. Recent window beat baseline sleeve — default until another arm wins.
- CF 3d: N=0 excess=None | 7d: N=0 excess=None
- Latest paper swap: *(none)*

## `dual_agree` — Dual agree (anti_pump ∩ risk_adj_mom)
Prior: Intersection of co-leaders: only paper swaps where both anti_pump and risk_adj_mom nominate the same remove→add on the same day. Higher bar, fewer swaps. Shadow only until HC gates clear.
- CF 3d: N=10 excess=1.6202 | 7d: N=10 excess=11.231799999999996

