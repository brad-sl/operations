# Dedicated Host Provisioning Guide (SCALING-1000-PHASE-A-02)

**Objective:** Provision stable VPS for prod webhooks, public HTTPS, basic monitoring. NOT on personal laptop.

**Recommended Provider:** Hetzner Cloud (best value per research + existing playbook). Alternatives: DigitalOcean, AWS Lightsail.

**Target URL example (post-brand):** https://api.arch-automation.com/ghl/webhook

**Status:** Scripts + docs prepared (2026-07-16). Manual execution required (no cloud creds in env). Research posture: do not point prod GHL webhooks yet.

## 1. Provider Selection & Cost Estimate

- **Hetzner Cloud (primary rec):**
  - Staging/small: CPX11 or CX22 (~€5.99–€19.49/mo incl. traffic 1-20TB)
  - Recommended starter: CPX21 (3 vCPU, 4GB, 80GB SSD) ~ €19.49/mo or cheaper shared.
  - Location: EU (Germany/Finland) for low latency to Coinbase/US? Or US if needed. Traffic generous (20TB/mo standard).
  - Pros: Cheap, good perf, easy API/CLI (hcloud), GDPR.
  - Cons: EU focus (latency if US heavy), no US East cheap sometimes.

- **DigitalOcean:** ~$12-24/mo for comparable (s-2vcpu-4gb). Good UX, doctl CLI. Higher egress.

- **AWS Lightsail:** ~$12-20/mo. Integrated but egress costly long term.

**Total monthly estimate (staging/prod minimal):** $6–25 USD + domain $10-15/yr.
Add: monitoring free tier (UptimeRobot), basic backup snapshots (~extra € few).

See current pricing: https://www.hetzner.com/cloud (use calculator).

**Access for team:** Share root or deploy user SSH + 1Password or vault for secrets. Hetzner console for console access.

## 2. Prerequisites (local)

- Hetzner account + API token (create at console.hetzner.cloud)
- SSH keypair: `ssh-keygen -t ed25519 -C "deploy@arch"`
- (Optional) hcloud CLI: `curl -s https://api.github.com/repos/hetznercloud/cli/releases/latest | ...` or apt.
- Domain: pending brand (t_cff262a8). Use placeholder `arch-automation.com` or buy cheap .com via Namecheap/Cloudflare.
- Git clone of repo for configs.

## 3. Provision VPS (Hetzner Console or CLI)

**Console (easiest for first):**
1. Login https://console.hetzner.cloud
2. Create project or use existing.
3. Servers > Add server
   - Location: nbg1 (Nuremberg) or fsn1 (Falkenstein) or US if avail.
   - Image: Ubuntu 24.04 LTS
   - Type: CPX21 or CX32 (shared ok for start)
   - SSH key: add your pubkey
   - Firewall: allow 22,80,443 (or create Cloud Firewall later)
   - Name: crypto-bot-prod or staging
   - No volume/snapshot yet.
4. Create. Note public IPv4 (and IPv6).
5. Wait ~1min for ready. SSH as root@IP

**CLI (hcloud):**
```bash
hcloud server create --name crypto-bot --type cpx21 --image ubuntu-24.04 --ssh-key yourkey --location nbg1
```

Post-create: `hcloud server list` for IP.

## 4. Initial Setup on VPS (run as root)

```bash
# Copy this script or cat it
scp provisioning/scripts/hetzner-provision.sh root@<IP>:/root/
ssh root@<IP>
chmod +x /root/hetzner-provision.sh
/root/hetzner-provision.sh
reboot   # for good measure
```

- Add your SSH key for deploy user:
  ```bash
  ssh-copy-id -i ~/.ssh/id_ed25519.pub deploy@<IP>
  # or manually: cat pubkey >> /home/deploy/.ssh/authorized_keys
  ```

- Disable root SSH if not already.

## 5. Domain + DNS

1. Buy/register domain (e.g. arch-automation.com) if not done.
2. At registrar (or Cloudflare for DNS): create A record:
   - api.arch-automation.com -> VPS_IP (TTL 300 or low for test)
   - Optional: @ or www for marketing site later.
3. Wait propagation (use `dig api.arch-automation.com` or whatsmyip tools).
4. On VPS, update Caddyfile with correct domain.

**Note:** Brand decision pending parallel task. Use IP temporarily for testing (http), but task requires HTTPS.

## 6. Deploy Gateway Stub + HTTPS

On VPS (as deploy):
```bash
sudo su - deploy
mkdir -p /opt/crypto-bot
cd /opt/crypto-bot
# Copy files from local (git clone or scp)
git clone <repo> .   # or rsync configs
cp provisioning/config/* .   # adjust
cp provisioning/config/Dockerfile.gateway .

# Build/run
docker compose -f docker-compose.host.yml build
docker compose -f docker-compose.host.yml up -d

# Test local
curl http://localhost:8000/health
curl -X POST http://localhost:8000/ghl/webhook -d '{"type":"test"}' -H "Content-Type: application/json"

# With Caddy running: test HTTPS once DNS live
curl https://api.arch-automation.com/health
# Should return JSON healthy
```

Caddy auto-provisions Let's Encrypt cert on first HTTPS hit (port 80/443 open).

## 7. Basic Monitoring

- **Health endpoint:** /health returns JSON status. Use for:
  - UptimeRobot.com (free): add HTTPS monitor to api.../health , alert email/Telegram.
  - Or self: simple cron curl + log.
- **Logs:** `docker logs ghl-gateway -f`
- **System:** Install node-exporter or use Hetzner metrics (console has CPU/RAM/net).
- **Stub Prometheus:** extend compose with prom + grafana (see old playbook).
- **Uptime target:** >99%. Alerts for down >5min.

Add later: full gateway logging, request metrics.

## 8. Secrets & Config

- `.env` : GHL_WEBHOOK_SECRET=real-from-ghl (never git)
- Later: Coinbase keys per account (vault/encrypted).
- SSH keys only; no passwords.

## 9. Firewall / Security (already in script)

- UFW: only 22,80,443
- Fail2ban
- Docker network isolation
- Non-root deploy user
- Auto updates

## 10. Test Webhook Receipt

Once HTTPS live:
```bash
# From anywhere (GHL test or curl)
curl -X POST https://api.arch-automation.com/ghl/webhook \
  -H "Content-Type: application/json" \
  -H "X-GHL-Signature: test-sig" \
  -d '{"webhookId":"test-123", "type":"contact.create"}'

# Expect 200 + "stub-ok"
```

Verify in docker logs. Idempotency stub (use real in impl).

**Do not** configure real GHL webhook target yet.

## 11. Next / Migration

- Migrate Phase 6 runner later (use existing playbook + docker).
- Full gateway impl in GHL-01 (T0).
- Update GHL_INTEGRATION.md with actual IP/domain.
- Add to MASTER.
- Staging vs prod: duplicate VPS or use subdomains + separate compose.

## 12. Troubleshooting

- Cert issues: ensure 80/443 open, DNS correct, Caddy logs `docker logs caddy`
- Connection refused: ufw status, docker ps, port 8000 listening.
- Hetzner firewall: console > Firewall > assign to server if used.
- From Reddit/ guides: common is missing firewall allow in Hetzner cloud firewall.

## Artifacts Delivered

- hetzner-provision.sh
- Caddyfile
- health_gateway.py + Dockerfile.gateway
- docker-compose.host.yml
- This guide

**Cost + Access:** Documented. Team share via secure channel (not here).

**Success check:** HTTPS reachable, /health 200, test webhook logs 200. Uptime monitor configured.

Update docs:
- GHL_INTEGRATION.md (prereq #2)
- MASTER_TASK_TRACKING.md
- VPS_MIGRATION_PLAYBOOK.md (reference this)

References: IMPL §8, GHL_INTEGRATION prereqs, unified roadmap.

**Phase A complete for host when scripts run + tested on real VPS + docs updated.**
