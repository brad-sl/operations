# TP / Trail Path Study — 2026-08-21

**Enum:** `design_shadow` · live writes: false
- Matched rounds: 91 · usable path legs: **52** · losses: 45
- Baseline sum r: -1.276536 · mean r: -0.024549
- CF TP+6% (always bank TP if touched) sum r: 1.196814 (Δ 2.47335)
- CF **rescue** (TP only if realized loss + path hit): sum r 1.125916 (Δ 2.402452)
- CF trail sum r: 0.358541 (Δ 1.635077)
- Hit rate path≥+6%: 0.5769230769230769
- Losses that still touched +6% on path: **27** (rescue rate 0.6)
- Skipped: {'no_ohlcv': 33, 'no_price': 6, 'no_bars': 0}

## Read
- **Rescue rate** is the decision metric: losses that had a path TP opportunity.
- Full fixed-TP sum can look worse because it caps winners — do not drop on that alone.
- Daily bars slightly overstate TP ease.

## Next
- If design_shadow: shadow TP / trail research + same operator notify loop as hard exit.
- Do not set live take_profit_pct without Brad + shadow days.
