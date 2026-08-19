# Hermes + Phase 6 host — vulnerability review & patch plan

**Date:** 2026-08-08  
**Scope:** Hermes Agent (gateway/Telegram/dashboard), host exposure, crypto-trading-bot secrets/ops  
**Not in scope:** Full app pentest, legal counsel, third-party SaaS TOS  
**Verdict:** **PASS-WITH-RISKS** for private single-operator use on trusted LAN/Tailscale — **FAIL for “internet-open admin”** until P0 items addressed  

## 0. Exposure map

| Surface | Bind / reach | Auth today | Power |
|--------|----------------|------------|--------|
| Hermes gateway | process active | Telegram allowlist (env may be set at unit level; config `telegram.allowed_chats` empty) | Full agent tools on Telegram |
| Dashboard :9119 | `0.0.0.0:9119` | basic_auth present in config; `gateway.auth.enabled: false` | Admin / agent control plane |
| Dashboard :8080 | `0.0.0.0:8080 --insecure` | “insecure” mode | Admin UI |
| OpenClaw gateway | `:18789` | separate stack | Parallel agent surface |
| Terminal backend | **local** (host) | approvals.mode=smart + large allowlist | Shell as `brad` |
| Browser / web | on CLI + Telegram toolsets | private URLs blocked by default | SSRF/injection surface |
| computer_use | enabled on Telegram | — | Desktop control |
| Trading bot `.env` | file mode **664** | N/A | Exchange / API secrets |
| Discovery/cron | no_agent scripts | no live basket apply | Low money risk if apply stays gated |

**Network:** LAN `192.168.0.0/24` + Tailscale `100.x` + docker bridges. Anything on `0.0.0.0` is reachable from LAN and often Tailscale peers.

## 1. Critical clarification (UX vs security)

Hermes **does not** route normal `read_file` / `write_file` through the approval prompt.  
Approvals apply primarily to **flagged shell commands** (and a few destructive slash/MCP paths).

If the last lockdown felt like “permission for every file read/write,” that was almost certainly one of:

1. **`approvals.mode: manual`** (or YOLO off + over-triggering patterns), or  
2. **`HERMES_EXEC_ASK=1`** (currently set) pushing exec prompts, or  
3. **Tirith / security scan** on piped shell (`curl | python` style), or  
4. A different product surface / profile — **not** “file tool requires allow every time.”

**Design goal for this plan:** raise **money, secrets, and network-admin** bars; keep **project file R/W and normal coding shell** fluid.

## 2. Findings (priority order)

### P0 — fix soon (real blast radius)

| ID | Finding | Evidence | Why it matters | UX impact if fixed |
|----|---------|----------|----------------|--------------------|
| P0-1 | **Gateway/dashboard bound to all interfaces** | `gateway.host: 0.0.0.0`, dashboards on `0.0.0.0:9119` and `0.0.0.0:8080` | LAN/Tailscale peers can hit admin UI | None for local use if bind `127.0.0.1` or require Tailscale ACL + auth |
| P0-2 | **`gateway.auth.enabled: false`** | config | Unauthenticated gateway API surface if reachable | Login once; not per file op |
| P0-3 | **Second dashboard `--insecure` on :8080** | process list | Explicit insecure admin on LAN | Remove or bind localhost only |
| P0-4 | **Fat `command_allowlist`** | includes `execute_code`, recursive delete, overwrite env/config, `shell -c`, kill gateway, stop system services | “Always allow” on the dangerous patterns = smart mode hollowed out | Remove 5–8 entries; keep none-of-the-above for day-to-day files |
| P0-5 | **Trading `.env` mode 664** | `stat` → 664 group-readable | Any same-group local user/process can read exchange keys | One `chmod 600` |
| P0-6 | **Telegram has `terminal` + `computer_use` + `browser`** | `platform_toolsets.telegram` | Compromised chat session = host shell + desktop | Optional tool trim; not constant prompts |

### P1 — high (defense in depth)

| ID | Finding | Evidence | Fix direction |
|----|---------|----------|---------------|
| P1-1 | `delegation.subagent_auto_approve: true` | config | Set `false` so child shell still hits smart approvals |
| P1-2 | `security.tirith_fail_open: true` | config | Prefer fail-closed on unknown high-risk scans, or keep fail-open but don’t allowlist kill/rm |
| P1-3 | `website_blocklist.enabled: false` | config | Enable minimal deny list (pastebins, raw IP URL shortener abuse, known junk) — optional |
| P1-4 | OpenClaw still running | port 18789 | Confirm Telegram single-owner; disable OpenClaw TG if Hermes owns bot |
| P1-5 | `privacy.redact_pii: false` | config | Enable if logs leave machine |
| P1-6 | `security.allow_lazy_installs: true` | config | Disable or constrain if supply-chain worry |
| P1-7 | `HERMES_EXEC_ASK=1` | env | Likely major UX pain source — set `0` if smart mode is enough |
| P1-8 | Media trust recent files + non-strict delivery | env/config | OK for home; tighten if multi-user |

### P2 — medium (trading / agent traps)

| ID | Finding | Fix direction |
|----|---------|---------------|
| P2-1 | No automated gate that **web-derived instructions cannot `apply_config` / place live orders** | Keep apply-config human-only; document; optional wrapper deny list in runner |
| P2-2 | Agent traps / prompt injection via browser/web | Keep private URL block; treat web as data (already); don’t expand computer_use |
| P2-3 | Cron can run powerful scripts | Already `approvals.cron_mode: deny` for agent approvals; audit `no_agent` scripts (good pattern) |
| P2-4 | Dual dashboard ports drift after updates | One dashboard service; pin bind + auth in unit file |

### P3 — low / hygiene

- Config backups under `~/.hermes/*.bak*` — ensure 600  
- `acked_advisories: []` — review Hermes security advisories when present  
- Rotate any key that may have lived in chat logs historically  

## 3. What we will **not** do (learned from last lockdown)

| Anti-pattern | Why avoid |
|--------------|-----------|
| Approve every file read/write | Not how Hermes works; destroys velocity |
| `approvals.mode: manual` for all shell | Painful; use smart + thin allowlist |
| YOLO / `approvals.mode: off` | Wrong direction |
| Dockerize entire trading stack “for security” in this pass | Huge UX/ops cost; optional later |
| Strip Telegram of `file` tools | Breaks your workflow; file tools are the point |

## 4. Target security model (balanced)

```
TRUSTED (no prompt):
  - file read/write under project + ~/.hermes skills/memory (as today)
  - routine shell: pytest, git status/diff/commit, python scripts, ls, rg
  - smart auto-approve low-risk shell

PROMPT / DENY (high value):
  - rm -rf, chmod secrets, curl|sh, dd, mkfs
  - overwrite .env / trading_config apply
  - systemctl stop hermes-gateway, kill -9 gateway
  - package install broad (optional)
  - live order / apply-config paths (human only)

NETWORK:
  - Admin UIs: localhost OR Tailscale + auth (not open LAN insecure)
  - browser: no private URL SSRF (already false)
  - Telegram: only your chat IDs

MONEY:
  - discovery/pool cycle shadow only until explicit Brad promote
  - no web content can authorize live trades
```

## 5. Patch plan (phased)

### Phase A — same day, low friction (recommend do now)

1. **`chmod 600`** project `.env` (and any other key files found 664).  
2. **Trim `command_allowlist`** to empty or only 1–2 proven nuisances — **remove** at least:  
   - recursive delete  
   - overwrite project env/config  
   - delete in root path  
   - kill hermes/gateway / stop system service  
   - shell `-c` / script `-e` blanket entries  
   - `execute_code` if it bypasses smart checks  
3. **Set `HERMES_EXEC_ASK=0`** in gateway environment if prompts were exec-related (keep `approvals.mode: smart`).  
4. **Dashboard hygiene:** stop or rebind **:8080 --insecure**; prefer single dashboard with basic_auth; bind `127.0.0.1` unless Tailscale-only access is intentional.  
5. **Enable `gateway.auth`** if any non-loopback bind remains.  
6. **`delegation.subagent_auto_approve: false`**.

**Expected UX:** coding + file ops stay smooth; only true destructive shell pings you again.

### Phase B — this week

1. Confirm **Telegram allowed chat IDs** in unit env (not empty in effective runtime).  
2. Consider removing **`computer_use`** from Telegram toolset (keep on CLI if needed).  
3. `tirith_fail_open: false` **or** keep true but rely on thin allowlist.  
4. OpenClaw: verify no dual Telegram poll; disable TG on OpenClaw if Hermes owns the bot.  
5. Document “live config apply / live orders = human only” in ops runbook (already informal).

### Phase C — optional hardening (only if threat model grows)

1. Terminal backend **docker** for untrusted web-research sessions (profile split: `trading-ops` local vs `web-research` container).  
2. Website blocklist for known junk.  
3. Separate low-privilege OS user for agent terminal (heavy).  
4. Formal public-exposure review if dashboards leave private network.

## 6. Verification checklist

After Phase A:

- [ ] `stat -c '%a' projects/crypto-trading-bot/.env` → `600`  
- [ ] `hermes config get approvals.mode` → `smart`  
- [ ] `hermes config get command_allowlist` → short or `[]`  
- [ ] `ss -lntp` → no unexpected `0.0.0.0:8080` insecure  
- [ ] Gateway/dashboard requires auth if not localhost  
- [ ] Telegram DM still works for Brad only  
- [ ] Agent can `read_file` / `write_file` project files **without** approval spam  
- [ ] `rm -rf` / kill gateway still prompts or denies  

## 7. Residual risk (accepted for private ops)

- Local full-host terminal as your user (by design for productivity)  
- Model can still be socially engineered; mitigations are scope + money gates  
- Tailscale peer compromise = host compromise if UI bound there without auth  
- Trading keys on disk (standard); protect with 600 + disk encryption  

## Phase A status (2026-08-08) — **COMPLETE**

Verified after `bash ~/.hermes/scripts/phase_a_security_finish.sh`:

| Check | Result |
|------|--------|
| `:8080` insecure | **gone** (no listener) |
| System `hermes-dashboard.service` | **disabled / inactive** |
| User dashboard | **`127.0.0.1:9119` only**, HTTP 200 |
| User gateway | **active**, `HERMES_EXEC_ASK=0` |
| `approvals.mode` | **smart** |
| `command_allowlist` | **[]** |
| `subagent_auto_approve` | **false** |
| Trading `.env` | **600** |

UX intent preserved: no per-file approval spam; smart shell gates with empty always-allow.
