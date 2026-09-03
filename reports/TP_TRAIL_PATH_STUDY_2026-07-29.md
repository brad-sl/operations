# TP / Trail Path Study — 2026-07-29

**Enum:** `design_shadow` · live writes: false
- Matched rounds: 82 · usable path legs: **50** · losses: 43
- Baseline sum r: -2.302264 · mean r: -0.046045
- CF TP+6% (always bank TP if touched) sum r: -0.206333 (Δ 2.095931)
- CF **rescue** (TP only if realized loss + path hit): sum r -0.304284 (Δ 1.99798)
- CF trail sum r: 1.070636 (Δ 3.3729)
- Hit rate path≥+6%: 0.54
- Losses that still touched +6% on path: **23** (rescue rate 0.5349)
- Skipped: {'no_ohlcv': 28, 'no_price': 4, 'no_bars': 0}

## Read
- **Rescue rate** is the decision metric: losses that had a path TP opportunity.
- Full fixed-TP sum can look worse because it caps winners — do not drop on that alone.
- Daily bars slightly overstate TP ease.

## Next
- If design_shadow: shadow TP / trail research + same operator notify loop as hard exit.
- Do not set live take_profit_pct without Brad + shadow days.
