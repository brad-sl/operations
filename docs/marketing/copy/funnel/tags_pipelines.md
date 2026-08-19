# GHL Tags & Pipelines (copy/ops quick ref)

Source of truth for fields: `docs/integrations/ghl_t0/GHL_T0_FIELD_DICT.md`  
This file mirrors what lifecycle copy expects.

## Contact tags

| Tag | Meaning | Set by |
|-----|---------|--------|
| `pilot` | Invite cohort | Manual / import |
| `paid` | Active paid sub | W1 / SaaS |
| `coinbase_connected` | OAuth complete | Platform → GHL |
| `runner_healthy` | Green health | Platform / W3 |
| `needs_attention` | Ops / red-yellow | Platform / W6 |
| `priority_support` | Elite | Product map |
| `trader_tier_starter` | Tier | Checkout |
| `trader_tier_pro` | Tier | Checkout |
| `trader_tier_elite` | Tier | Checkout |
| `past_due` | Billing fail | W5 |
| `canceled` | Offboarded | W7 |

## Pipeline: Trader Onboarding

| Stage | Entry signal |
|-------|----------------|
| Invite / Waitlist | Not paid |
| Paid — Awaiting Connect | `paid`, not connected |
| Connecting | Connect link sent / W2 |
| Live — Healthy | connected + green |
| Needs Attention | `needs_attention` / red |
| Paused / Billing | past_due |
| Offboarded | canceled + disconnect guidance |

## Pipeline: Support Escalation (optional)

New → Investigating → Waiting on trader → Resolved

## Custom fields used in merge tags

`trader_tier`, `subscription_status`, `coinbase_status`, `runner_health`, `connect_link_sent_at`, `platform_account_id`, `pilot_cohort`
