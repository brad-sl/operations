# Crypto Trading Bot VPS Migration Playbook

## Infrastructure Strategy
### DigitalOcean Droplet Specification
- **Tier**: Basic $24/mo
- **Specs**: 
  - 4GB RAM
  - 2 vCPU
  - 80GB SSD
- **OS**: Ubuntu 24.04 LTS
- **Region**: Recommended: London (low latency)

## Deployment Architecture
### Docker Compose Services
```yaml
services:
  bot:
    image: python:3.12-slim
    volumes: ['./bot:/app']
    command: python3 phase5_multi_pair.py
    restart: unless-stopped
    networks:
      - trading_network
    ports:
      - "8502:8502"  # Expose Prometheus metrics port

  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports: ["9090:9090"]
    networks:
      - trading_network

  grafana:
    image: grafana/grafana-oss
    ports: ["3000:3000"]
    networks:
      - trading_network

  redis:
    image: redis:alpine
    networks:
      - trading_network

  celery:
    command: celery -A tasks worker
    networks:
      - trading_network

networks:
  trading_network:
    driver: bridge
```

### Prometheus Configuration (prometheus.yml)
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'trading_bot'
    static_configs:
      - targets: ['bot:8502']
```

## Deployment Steps
1. Provision DigitalOcean Droplet
   ```bash
   doctl compute droplet create crypto-bot \
     --image ubuntu-24-04-x64 \
     --size s-2vcpu-4gb \
     --region lon1 \
     --ssh-keys YOUR_SSH_KEY_FINGERPRINT
   ```

2. Initial Setup
   ```bash
   # SSH into droplet
   ssh root@DROPLET_IP

   # Install dependencies
   apt update && apt upgrade -y
   apt install -y docker docker-compose tailscale git

   # Authenticate Tailscale
   tailscale up --authkey=YOUR_TAILSCALE_AUTHKEY
   ```

3. Deploy Trading Bot
   ```bash
   git clone YOUR_REPO_URL
   cd crypto-bot
   docker-compose up -d
   ```

## Monitoring & Resilience
- **Grafana Alerts**: Configure PromQL alerts
- **Backup**: Hourly rsync to offsite storage
- **Update Strategy**: Blue-green Docker deployment

## Hermes Agent + Git Resilience (Phase 4 Addition - 2026-06-14)

Hermes (v0.16.0) runs on legacy hardware as the orchestration layer. Git (operations.git) is now the durable source of truth for Hermes state via the `hermes/` mirror.

### Key Components
- `hermes/` mirror in repo: profiles (crypto-orchestrator etc.), cron yamls, skills inventory, hardware snapshots, PHASE_GOALS.md, sanitized config.
- Sync script: `scripts/hermes/sync-hermes-state.sh` (selective rsync from ~/.hermes, excludes secrets, atomic git commit/push).
- Restore script: `scripts/hermes/restore-hermes.sh` (applies mirror to ~/.hermes with timestamped backup).
- Git workflows (Phase 3): Standardized branching, handoffs with git commands, pre-commit example.

### Migration Steps for Hermes
1. On new VPS (after base bot deploy):
   ```
   git clone https://github.com/brad-sl/operations.git
   cd operations
   git checkout phase-6.1
   ./scripts/hermes/restore-hermes.sh
   # Then start Hermes gateway and profiles as needed
   hermes gateway start
   hermes -p crypto-orchestrator profile use
   ```

2. For full Hermes + bot:
   - Clone repo.
   - Restore Hermes state with the script.
   - Restore trading config/.env (separate secret handling).
   - Launch Phase 6 runner and Hermes crons.

3. Hybrid resilience (legacy + cloud):
   - Keep legacy as primary/hot spare.
   - Mirror critical profiles/crons to VPS via git clone + restore.
   - Use Tailscale for access.
   - Daily sync via cron: add to ~/.hermes/cron/ or system crontab `0 * * * * cd /path/to/operations && ./scripts/hermes/sync-hermes-state.sh`

### Git Health & Monitoring Integration
- Run sync script regularly for push of state changes.
- In ops-engineer or crypto-monitor: check `git status`, last sync age, unpushed changes in hermes/.
- Add to reports: "Hermes git mirror age: X hours, clean: yes/no".
- Pre-commit hook example: scripts/hermes/git/pre-commit-example.sh (isolation tests + handoff validation).

### Backup & Restore Drills
- Full restore test: `mkdir -p /tmp/hermes-test; HERMES_HOME=/tmp/hermes-test ./scripts/hermes/restore-hermes.sh --dry` (adapt for real).
- Verify with `hermes cron list`, `ls /target/profiles/`.
- Store recovery packets in git under .hermes/resume-packets/.

### Update Strategy
- Blue-green for bot (Docker).
- For Hermes: git pull + restore script (fast, versioned).
- Tag stable "Hermes + Phase 6" releases.

See:
- hermes/git-workflows/AGENT_GIT_WORKFLOWS.md
- scripts/hermes/sync-hermes-state.sh and restore-hermes.sh
- GIT_HERMES_OPERATIONALIZATION_PLAN.md (Phases 2-4)
- hermes-state/ for baseline exports
- **Scaling**: Horizontal scaling via Docker Swarm

## Security Considerations
- Tailscale VPN for secure access
- Minimal exposed ports
- Regular security updates
- Encrypted volumes

## Troubleshooting
### Prometheus Metrics Endpoint
- Ensure bot exposes metrics on :8502
- Verify Docker network configuration
- Check firewall rules
- Validate prometheus.yml configuration