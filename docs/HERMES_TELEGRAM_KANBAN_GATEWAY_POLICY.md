# Hermes Telegram + Kanban / sub-agent gateway policy

**Problem:** Telegram allows one `getUpdates` long-poll per bot token. Multiple Hermes `gateway run` processes (or OpenClaw + Hermes on the same token) cause HTTP 409, outbound `sendMessage` still works, but **inbound replies vanish**.

## How Kanban workers run (no extra gateway required)

- The dispatcher lives in the **default** gateway (`kanban.dispatch_in_gateway: true` in `~/.hermes/config.yaml`).
- Ready cards spawn **`hermes -p <assignee> chat -q`** subprocesses — **not** `hermes -p <assignee> gateway run`.
- Parallel Kanban workers (crypto-engineer, code-reviewer, etc.) do **not** need profile gateway services for board execution.

## Do

| Action | Why |
|--------|-----|
| Keep **only** `hermes-gateway.service` (default profile) for Telegram | Single poller |
| Use Kanban assignees as **profiles** for worker chat subprocesses | Standard Hermes Kanban path |
| After **`hermes update`**, run `~/.hermes/scripts/ensure-telegram-gateway-singleton.sh` | Update restarts all installed profile gateways |
| Keep OpenClaw Telegram **disabled** if Hermes owns the home bot | Same-token conflict |

## Do not

| Action | Risk |
|--------|------|
| `hermes -p <profile> gateway install` on profiles sharing `TELEGRAM_BOT_TOKEN` | Respawns competing pollers on every update |
| `hermes -p <profile> gateway start` for Kanban “to wake workers” | Unnecessary; dispatcher uses default gateway |
| Enable `channels.telegram` on OpenClaw with the Hermes bot token | Steals inbound updates |

## Recovery (one command)

```bash
bash ~/.hermes/scripts/ensure-telegram-gateway-singleton.sh
```

Verify: user reply on Telegram starts an agent run within a few seconds; `grep -i conflict ~/.hermes/logs/gateway.log | tail -3` should be quiet after cooldown.

## References

- `~/.hermes/TELEGRAM_GATEWAY_SINGLETON.md`
- `hermes-operations` skill → `references/telegram-gateway-multi-profile-conflicts.md`
- Kanban: `kanban-orchestrator` skill → gateway startup gotchas (main gateway only)

**MASTER:** append verification when this policy is exercised.