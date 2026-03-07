#!/bin/bash
# Factory server setup — runs ON the GCP VM.
# Called by deploy-gcp.sh via gcloud compute ssh.
#
# Installs Docker, clones the repo, generates secrets, starts everything.
# Idempotent — safe to run multiple times.

set -euo pipefail

REPO_URL="https://github.com/ygdotcom/antzilla.git"
INSTALL_DIR="/home/factory/antzilla"
FACTORY_USER="factory"

echo "=== Factory Server Setup ==="
echo "$(date)"

# ── 1. System packages ───────────────────────────────────────────────────────

echo ""
echo "[1/7] Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq docker.io docker-compose-v2 git ufw fail2ban curl jq

systemctl enable docker
systemctl start docker

# ── 2. Firewall (UFW) ────────────────────────────────────────────────────────

echo "[2/7] Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw allow 9000/tcp  # CEO Dashboard
ufw allow 8080/tcp  # Hatchet Dashboard
ufw --force enable
echo "  UFW enabled."

# ── 3. Create factory user ───────────────────────────────────────────────────

echo "[3/7] Setting up factory user..."
if ! id "$FACTORY_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$FACTORY_USER"
    usermod -aG docker "$FACTORY_USER"
    echo "  User '$FACTORY_USER' created."
else
    usermod -aG docker "$FACTORY_USER"
    echo "  User '$FACTORY_USER' already exists."
fi

# ── 4. Clone or update repo ──────────────────────────────────────────────────

echo "[4/7] Setting up repository..."
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "  Repo exists, pulling latest..."
    cd "$INSTALL_DIR"
    git pull --ff-only
else
    echo "  Cloning repo..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi
chown -R "$FACTORY_USER":"$FACTORY_USER" "$INSTALL_DIR"

# ── 5. Generate .env ─────────────────────────────────────────────────────────

echo "[5/7] Generating secrets..."
cd "$INSTALL_DIR"

POSTGRES_PW=$(openssl rand -hex 16)
ENCRYPTION_KEY=$(openssl rand -hex 32)
DASHBOARD_PW=$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9' | head -c 16)

if [ ! -f .env ] || [ ! -s .env ]; then
    cat > .env << ENVEOF
# Factory boot variables — generated $(date +%Y-%m-%d)
POSTGRES_PASSWORD=$POSTGRES_PW
ENCRYPTION_KEY=$ENCRYPTION_KEY
DASHBOARD_USER=ceo
DASHBOARD_PASSWORD=$DASHBOARD_PW
DAILY_BUDGET_LIMIT_USD=50.00
AGENT_DEFAULT_DAILY_LIMIT_USD=5.00
DRY_RUN=true
ENVEOF
    echo "  .env created with generated secrets."
else
    echo "  .env already exists, preserving."
    # Read existing password for display
    DASHBOARD_PW=$(grep DASHBOARD_PASSWORD .env | cut -d= -f2)
fi

chown "$FACTORY_USER":"$FACTORY_USER" .env
chmod 600 .env

# ── 6. Start services ────────────────────────────────────────────────────────

echo "[6/7] Starting Docker services..."
cd "$INSTALL_DIR"

docker compose pull --quiet 2>/dev/null || true
docker compose up -d postgres

echo "  Waiting for Postgres to be healthy..."
for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U factory &>/dev/null; then
        break
    fi
    sleep 2
done
echo "  Postgres ready."

# Start remaining services
docker compose up -d --build
echo "  All services starting..."

# Wait for dashboard
for i in $(seq 1 30); do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/setup 2>/dev/null | grep -q "401\|200"; then
        break
    fi
    sleep 3
done

# ── 7. Auto-start on reboot ──────────────────────────────────────────────────

echo "[7/7] Setting up auto-start..."
CRON_CMD="@reboot cd $INSTALL_DIR && /usr/bin/docker compose up -d"
(crontab -u "$FACTORY_USER" -l 2>/dev/null | grep -v "docker compose up" ; echo "$CRON_CMD") | crontab -u "$FACTORY_USER" -
echo "  Crontab configured for auto-start on reboot."

# ── Done ──────────────────────────────────────────────────────────────────────

EXTERNAL_IP=$(curl -s http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip -H "Metadata-Flavor: Google" 2>/dev/null || echo "unknown")

echo ""
echo "============================================="
echo "  Server setup complete!"
echo "============================================="
echo ""
echo "  Dashboard:  http://$EXTERNAL_IP:9000"
echo "  Hatchet:    http://$EXTERNAL_IP:8080"
echo ""
echo "  Login:      ceo / $DASHBOARD_PW"
echo ""
echo "  DRY_RUN is ON. The factory will not make"
echo "  real API calls until you turn it off in"
echo "  Dashboard → Settings."
echo ""
echo "  Next: open the dashboard and complete"
echo "  the Setup Wizard to add your API keys."
echo "============================================="
