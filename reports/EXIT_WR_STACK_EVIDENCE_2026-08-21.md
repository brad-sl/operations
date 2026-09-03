# Exit WR stack evidence — 2026-08-21

## Path study (60d OHLCV counterfactual)
- **Enum:** `design_shadow` · live writes: false
- Usable path legs: **52** · losses: 45
- Hit rate path ≥+6%: **57.7%**
- Losses that still touched +6%: **27** (rescue rate **60.0%**)
- Rescue CF Δr vs baseline: **2.402452**

## Open-book shadow TP
- mode=shadow signals=3 would_fire_total=476
- promotion_hint={'shadow_days': 0.19, 'days_needed': 7, 'would_fire_count_total': 476, 'events_needed': 5, 'ready_for_settings_flip_review': False, 'action_if_ready': 'Set take_profit.mode=live and live_attach_on_buy=true (one-time knob). Not per-trade approve.'}

## Open-book ratchet what-if
```json
[
  {
    "pair": "LINK-USD",
    "entry": 8.277302,
    "mark": 12.1515,
    "mult": 1.468,
    "stop_now": 8.028,
    "ratchet_to": 9.7212,
    "applied": true,
    "reasons": [
      "air_pocket_gap>0.2"
    ]
  },
  {
    "pair": "PAXG-USD",
    "entry": 4055.92,
    "mark": 4617.475,
    "mult": 1.138,
    "stop_now": 3937.48,
    "ratchet_to": 3937.48,
    "applied": false,
    "reasons": [
      "no_raise"
    ]
  }
]
```

## Go/no-go
| Item | Call |
|------|------|
| Live take-profit | **NO** (design_shadow; promotion gates) |
| Keep shadow TP | **YES** |
| SL floor ratchet | **SHIPPED** (next attach applies) |
