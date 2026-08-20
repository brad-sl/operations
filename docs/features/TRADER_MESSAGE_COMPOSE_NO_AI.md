# Trader messages — script-only composition (no AI)

**Status:** platform rule (2026-08-20)  
**Code:** `phase6/core/trader_message_compose.py`  
**Facts:** `phase6/core/market_posture_explain.py` → `why_idle` + `messages`

## Rule

Any message a trader sees on **dashboard**, **IM** (Telegram/etc.), or **email** about
cash posture / why not fully invested must be:

| Property | Requirement |
|----------|-------------|
| **Composed by script** | Fixed templates + structured facts |
| **No AI in live path** | No LLM/API call to generate the text at send time |
| **Deterministic** | Same facts → same output bytes |
| **Performant** | Pure CPU; no network inside compose |
| **Scalable** | Per-account facts overlay + shared market heat cache |
| **Reliable** | Fail closed to a short safe headline; never block trading |
| **Accurate** | Format only supplied facts — never invent pairs/PnL/regime |

AI may edit templates in git offline. AI must not author live trader copy.

## Pipeline

```
facts (heat, posture, book, basket, gates)
        │
        ▼
build_why_idle()          # structure + plain-English title/detail strings
        │
        ▼
compose_why_cash_channels()  # dashboard | telegram | email | push | sms
        │
        ├── /api/metrics → UI
        ├── hermes/cron IM send (future wire)
        └── email multipart (future wire)
```

## Channels (`why_idle.messages`)

- `dashboard` — headline + reason lines  
- `telegram.text` — plain IM body  
- `email.subject` / `.text` / `.html`  
- `push` / `sms` — short body  

## Tests

```bash
PYTHONPATH=. python3 phase6/core/test_isolation_trader_message_compose.py
PYTHONPATH=. python3 phase6/core/test_isolation_market_posture_explain.py
```

## Multi-tenant

Shared: market heat + default posture.  
Personal: book, basket, cooldowns, holds → pass as facts into the same composer.
