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