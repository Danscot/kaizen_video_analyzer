#!/bin/bash
# deploy.sh — one-shot setup on Ubuntu 22.04 / 24.04
# Usage: sudo bash deploy.sh YOUR_GEMINI_API_KEY YOUR_DOMAIN_OR_IP
set -e

API_KEY="${1:?Usage: sudo bash deploy.sh GEMINI_KEY DOMAIN}"
DOMAIN="${2:-localhost}"
APP_DIR="/opt/kaizen"
LOG_DIR="/var/log/kaizen"

echo "==> System packages"
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv ffmpeg nginx certbot python3-certbot-nginx curl

echo "==> App directory"
mkdir -p "$APP_DIR" "$LOG_DIR"
chown www-data:www-data "$LOG_DIR"
cp -r . "$APP_DIR/"
chown -R www-data:www-data "$APP_DIR"

echo "==> Python venv"
python3 -m venv "$APP_DIR/venv"
source "$APP_DIR/venv/bin/activate"
pip install -q --upgrade pip
pip install -q -r "$APP_DIR/requirements.txt"

echo "==> Media directories"
mkdir -p "$APP_DIR/media/uploads" "$APP_DIR/media/output"
chown -R www-data:www-data "$APP_DIR/media"

echo "==> Secret key"
SECRET=$(python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(64)))")

echo "==> Systemd service"
sed -i "s/YOUR_KEY_HERE/$API_KEY/"       "$APP_DIR/kaizen.service"
sed -i "s/yourdomain.com/$DOMAIN/"        "$APP_DIR/kaizen.service"
sed -i "s/CHANGE_THIS_TO_A_LONG_RANDOM_STRING/$SECRET/" "$APP_DIR/kaizen.service"
cp "$APP_DIR/kaizen.service" /etc/systemd/system/kaizen.service
systemctl daemon-reload
systemctl enable kaizen
systemctl start kaizen

echo "==> Nginx"
sed -i "s/YOUR_DOMAIN_OR_IP/$DOMAIN/" "$APP_DIR/nginx.conf"
cp "$APP_DIR/nginx.conf" /etc/nginx/sites-available/kaizen
ln -sf /etc/nginx/sites-available/kaizen /etc/nginx/sites-enabled/kaizen
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo ""
echo "==> Done. Live at http://$(curl -s ifconfig.me)"
echo "    HTTPS: certbot --nginx -d $DOMAIN"
echo "    Logs:  journalctl -u kaizen -f"
