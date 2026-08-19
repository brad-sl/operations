#!/bin/bash
# Hetzner VPS Provisioning Script for Crypto Trading Bot + GHL Webhook Gateway
# Usage: Run as root on fresh Ubuntu 24.04 VPS from Hetzner
# After: ssh-copy-id or add key, then sudo ./hetzner-provision.sh
# Then configure domain in Caddyfile, run docker, point DNS A record.
set -euo pipefail

echo "=== Hetzner Provision for ARCH Automation / Crypto Bot ==="
echo "Updating system..."
apt-get update -y
apt-get upgrade -y

echo "Installing essentials: curl, git, ufw, fail2ban, docker, docker-compose, unattended-upgrades..."
apt-get install -y curl git ufw fail2ban unattended-upgrades ca-certificates gnupg lsb-release

# Docker install (official)
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker $SUDO_USER || true
rm get-docker.sh

# Docker Compose (plugin)
apt-get install -y docker-compose-plugin

# Create deploy user (non-root)
if ! id deploy >/dev/null 2>&1; then
  useradd -m -s /bin/bash deploy
  usermod -aG docker deploy
  echo "Created deploy user. Set password or use SSH keys."
fi

# SSH hardening (assume key auth already)
echo "Hardening SSH (disable password auth, root login)..."
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config || true
sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config || true
systemctl restart sshd || true

# Firewall
echo "Configuring UFW firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
# Optional: internal only for monitoring if needed
# ufw allow from <your-ip> to any port 22
ufw --force enable

# Fail2ban for SSH
systemctl enable fail2ban
systemctl start fail2ban

# Unattended upgrades
dpkg-reconfigure -plow unattended-upgrades || true

# Create app dir
mkdir -p /opt/crypto-bot
chown -R deploy:deploy /opt/crypto-bot

echo "Base system ready. Next: copy configs, set up Caddy + app."
echo "Run as deploy: cd /opt/crypto-bot && docker compose up -d"
echo "=== Provision complete. Reboot recommended for kernel updates. ==="

# Post: manual steps
# 1. Add your SSH pubkey to /home/deploy/.ssh/authorized_keys
# 2. Set domain DNS A record to this VPS IP
# 3. Edit Caddyfile with your domain
# 4. docker compose
