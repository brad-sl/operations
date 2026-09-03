# Preserve kill-bot soak — 2026-08-02

**Core claim: PASS** — E1 stayed OPEN on Coinbase while the runner was dead.

## Sequence
1. Micro-arm ~$30 PAXG + E1 stop-limit at **$2757.98** (−32% from arm ~$4055.86)
2. Confirmed E1 OPEN on exchange
3. **SIGTERM** runner pid 1301820
4. Soaked ~20s with bot dead → E1 still **OPEN**
5. Restarted runner (pid 1373339)
6. E1 still OPEN after restart
7. Disarmed (cancel + sell); manual cleanup of residual stop hold race

## IDs
| Item | Value |
|------|--------|
| Buy | `eacee7ac-458b-4597-8eac-97b142379e4d` |
| E1 | `f60b1f32-25ac-4201-ab59-2865dd1a9381` |
| E1 stop / limit | $2757.98 / $2741.43 |

## Cleanup
First disarm left a tiny stop + inventory hold race (restart repair placed a second micro stop briefly).  
**Follow-up cancel-all + sell:** PAXG **0**, open PAXG stops **0**, `preserve_mode.enabled=false`, badge **OFF**.  
USD ~$2448.25 (fees from round-trip).

## Implication
Exchange-resting E1 is real for bot-down resilience. Disarm hardened to cancel **all** pair stops + retry sells.

## Artifacts
- `reports/PRESERVE_KILLBOT_SOAK_2026-08-02.json`
- Script: `scripts/phase6/preserve_killbot_soak.py`

## Dashboard
Preserve badge on live dash (`preserve_mode` in `/api/metrics`): OFF / STANDBY / ARMED.
