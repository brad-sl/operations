# Breadth vs cash-idle case — 2026-08-19

Generated: `2026-08-19T17:19:18.102315+00:00`

## Plain English

Breadth ON across majors while book was cash-heavy. Cash re-risk shadow would FIRE a small paper sleeve into unblocked basket names. Separately, rotation policy paper arms had named HYPE/ZEC — encouraging but unproven.

- Cash fraction: **0.8663**
- Breadth: **ON** (green=6/8 (have_data=6) threshold=3.00% k=4 → ON)
- Shadow cash re-risk: **fire** fire=True targets=['BTC-USD', 'ETH-USD'] sleeve=$75.0
- BTC rotation missed MTM (clip): **$158.55**

## Paper membership arms (not live)

```json
{
  "control_no_swap": [],
  "baseline_hybrid": [
    {
      "remove": "ARB-USD",
      "add": "VVV-USD",
      "delta": 0.24,
      "add_score": 0.451,
      "remove_score": 0.211,
      "reason": "replace low-potential ARB-USD (score=0.211, held=$0) with VVV-USD (score=0.451); \u0394=0.240"
    }
  ],
  "anti_pump": [
    {
      "remove": "RAVE-USD",
      "add": "HYPE-USD",
      "delta": null,
      "add_score": 0.0272,
      "remove_score": null,
      "reason": "anti_pump: add=HYPE-USD score=0.0272 eject=RAVE-USD score=-999.0",
      "remove_held_usd": 0.0
    }
  ],
  "risk_adj_mom": [
    {
      "remove": "RAVE-USD",
      "add": "ZEC-USD",
      "delta": null,
      "add_score": 4.4588,
      "remove_score": null,
      "reason": "risk_adj_mom: add=ZEC-USD score=4.4588 eject=RAVE-USD score=-999.0",
      "remove_held_usd": 0.0
    }
  ],
  "rel_btc_stable": [
    {
      "remove": "XRP-USD",
      "add": "HYPE-USD",
      "delta": null,
      "add_score": 0.0483,
      "remove_score": null,
      "reason": "rel_btc_stable: add=HYPE-USD score=0.0483 eject=XRP-USD score=-999.0",
      "remove_held_usd": 0.0
    }
  ]
}
```

Full JSON: `/home/brad/projects/crypto-trading-bot/data/state/breadth_cash_rerisk_case_20260819.json`
