#!/usr/bin/env bash
set -euo pipefail

echo "=== tiktok-faceless VPS setup ==="

# System packages
apt-get update -qq
apt-get install -y -qq git python3.12 python3.12-venv curl sqlite3

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# Install Caddy
apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update -qq && apt-get install -y -qq caddy

# Create system user (idempotent)
useradd --system --create-home --shell /bin/bash tiktok 2>/dev/null || true

# Clone repo — update YOUR_USERNAME before running
REPO_URL="${REPO_URL:-https://github.com/YOUR_USERNAME/tiktok-faceless.git}"
INSTALL_DIR="/home/tiktok/tiktok-faceless"

if [ -d "$INSTALL_DIR" ]; then
  echo "Repo already cloned, pulling latest..."
  sudo -u tiktok git -C "$INSTALL_DIR" pull origin main
else
  sudo -u tiktok git clone "$REPO_URL" "$INSTALL_DIR"
fi

# Install Python dependencies (no dev extras)
sudo -u tiktok bash -c "cd $INSTALL_DIR && uv sync --no-dev"

echo ""
echo "=== Setup complete. Next steps ==="
echo ""
echo "1. Fill in credentials:"
echo "   cp $INSTALL_DIR/.env.example $INSTALL_DIR/.env"
echo "   nano $INSTALL_DIR/.env"
echo "   chown tiktok:tiktok $INSTALL_DIR/.env && chmod 600 $INSTALL_DIR/.env"
echo ""
echo "2. Run DB migrations:"
echo "   sudo -u tiktok bash -c 'cd $INSTALL_DIR && set -a && source .env && set +a && uv run alembic upgrade head'"
echo ""
echo "3. Provision first account:"
echo "   sudo -u tiktok bash -c 'cd $INSTALL_DIR && set -a && source .env && set +a && uv run python -m tiktok_faceless.main --provision-account acc1'"
echo ""
echo "4. Install systemd units:"
echo "   cp $INSTALL_DIR/deploy/pipeline.service /etc/systemd/system/tiktok-pipeline.service"
echo "   cp $INSTALL_DIR/deploy/pipeline.timer /etc/systemd/system/tiktok-pipeline.timer"
echo "   cp $INSTALL_DIR/deploy/dashboard.service /etc/systemd/system/tiktok-dashboard.service"
echo "   systemctl daemon-reload"
echo "   systemctl enable --now tiktok-pipeline.timer"
echo "   systemctl enable --now tiktok-dashboard"
echo ""
echo "5. Configure Caddy (edit Caddyfile domain first):"
echo "   nano $INSTALL_DIR/deploy/Caddyfile"
echo "   cp $INSTALL_DIR/deploy/Caddyfile /etc/caddy/Caddyfile"
echo "   systemctl reload caddy"
