#!/usr/bin/env bash
# =============================================================
#  Jade Tunnel Bot - Installer
#  Usage:
#    bash <(curl -fsSL https://raw.githubusercontent.com/Mahersaber2024/JadeTunnel-sales/main/install.sh)
# =============================================================

set -euo pipefail

REPO_URL="https://github.com/Mahersaber2024/JadeTunnel-sales.git"
SERVICE_NAME="sell-bot"
SUB_SERVICE_NAME="sub-api"
DEFAULT_INSTALL_DIR="/opt/sell-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SUB_SERVICE_FILE="/etc/systemd/system/${SUB_SERVICE_NAME}.service"
STATE_FILE="/etc/${SERVICE_NAME}.install_dir"

# ------------------ Colors ------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info(){ echo -e "${CYAN}ℹ️  $1${NC}"; }
ok(){ echo -e "${GREEN}✅ $1${NC}"; }
warn(){ echo -e "${YELLOW}⚠️  $1${NC}"; }
err(){ echo -e "${RED}❌ $1${NC}"; }
press_enter(){ read -rp "Press Enter to continue..." _ || true; }

require_root(){
  if [[ $EUID -ne 0 ]]; then
    err "This script must be run with root privileges (using sudo or as root user)."
    exit 1
  fi
}

save_install_dir(){ echo "${INSTALL_DIR}" > "${STATE_FILE}"; }
load_install_dir(){
  if [[ -f "${STATE_FILE}" ]]; then
    INSTALL_DIR=$(cat "${STATE_FILE}")
  else
    INSTALL_DIR="${DEFAULT_INSTALL_DIR}"
  fi
}

# ------------------ Steps ------------------
install_dir_prompt(){
  read -rp "Installation path [${DEFAULT_INSTALL_DIR}]: " INSTALL_DIR
  INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}
}

detect_python(){
  if command -v python3 &>/dev/null; then
    PY_BIN=python3
  else
    err "Python 3 not found on the server."
    exit 1
  fi
}

install_system_packages(){
  info "Installing system dependencies..."
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip git curl build-essential libpq-dev
  ok "System dependencies installed."
}

install_postgresql(){
  info "Installing PostgreSQL..."
  apt-get install -y postgresql postgresql-contrib
  systemctl enable postgresql
  systemctl start postgresql
  ok "PostgreSQL installed and started."
}

setup_database(){
  echo
  echo "======================================"
  echo "          Database Setup"
  echo "======================================"
  read -rp "Do you want to install and configure PostgreSQL on this server? (y/n) [y]: " INSTALL_DB
  INSTALL_DB=${INSTALL_DB:-y}

  if [[ "$INSTALL_DB" =~ ^[Yy]$ ]]; then
    if ! command -v psql &>/dev/null; then
      install_postgresql
    else
      info "PostgreSQL is already installed on the server."
      systemctl enable postgresql &>/dev/null || true
      systemctl start postgresql &>/dev/null || true
    fi

    read -rp "Database name [jadetunnel_base]: " DB_NAME
    DB_NAME=${DB_NAME:-jadetunnel_base}
    read -rp "Database username [cbu_user]: " DB_USER
    DB_USER=${DB_USER:-cbu_user}

    DB_PASS=""
    while [[ -z "$DB_PASS" ]]; do
      read -rsp "Password for database user (required): " DB_PASS
      echo
    done

    DB_HOST="localhost"
    DB_PORT="5432"

    info "Creating user and database in PostgreSQL..."
    sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 \
      || sudo -u postgres psql -c "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';"
    sudo -u postgres psql -c "ALTER ROLE ${DB_USER} WITH PASSWORD '${DB_PASS}';" >/dev/null

    sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 \
      || sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};" >/dev/null

    ok "Database «${DB_NAME}» and user «${DB_USER}» have been created."
  else
    info "Please enter existing database connection details:"
    read -rp "Database host: " DB_HOST
    read -rp "Database port [5432]: " DB_PORT
    DB_PORT=${DB_PORT:-5432}
    read -rp "Database name: " DB_NAME
    read -rp "Database username: " DB_USER
    read -rsp "Database password: " DB_PASS
    echo
  fi
}

collect_bot_config(){
  echo
  echo "======================================"
  echo "        Telegram Bot Settings"
  echo "======================================"
  BOT_TOKEN=""
  while [[ -z "$BOT_TOKEN" ]]; do
    read -rp "Bot token (from @BotFather): " BOT_TOKEN
  done

  read -rp "Admin numeric IDs (comma separated, e.g. 111,222): " ADMIN_IDS_RAW
  read -rp "Log group ID (negative number, e.g. -1001234567890) [optional - Enter to skip]: " LOG_GROUP_ID

  ADMIN_IDS_JSON="[]"
  if [[ -n "$ADMIN_IDS_RAW" ]]; then
    ADMIN_IDS_JSON=$(python3 - "$ADMIN_IDS_RAW" <<'PYEOF'
import sys
raw = sys.argv[1]
ids = [x.strip() for x in raw.split(",") if x.strip().lstrip("-").isdigit()]
print("[" + ", ".join(ids) + "]")
PYEOF
)
  fi
}

collect_iran_host_config(){
  echo
  echo "======================================"
  echo "     Iran Host (Subscription Proxy) Settings"
  echo "======================================"
  echo "The subscription proxy will run on port 2053."
  echo "You need to place index.php on your Iran host to forward requests."
  echo ""
  
  read -rp "Your Iran host domain (e.g. https://heysolo.ir): " IRAN_HOST_URL
  IRAN_HOST_URL=${IRAN_HOST_URL:-https://heysolo.ir}
  IRAN_HOST_URL=$(echo "$IRAN_HOST_URL" | sed 's:/*$::')
  
  read -rp "Absolute path where index.php is placed on Iran host [default: /home/heysolo/public_html/sub/]: " IRAN_HOST_PATH
  IRAN_HOST_PATH=${IRAN_HOST_PATH:-/home/heysolo/public_html/sub/}
  
  read -rp "Server IP for sub_api.py (this server's public IP): " SERVER_IP
  SERVER_IP=$(curl -s ifconfig.me || curl -s icanhazip.com || echo "127.0.0.1")
  
  ok "Iran host config collected."
}

write_config_json(){
  local target="$1"
  local log_group_value="null"
  if [[ -n "${LOG_GROUP_ID:-}" ]]; then
    log_group_value="$LOG_GROUP_ID"
  fi

  cat > "${target}/config.json" <<EOF
{
    "bot_token": "${BOT_TOKEN}",
    "db_host": "${DB_HOST}",
    "db_port": ${DB_PORT},
    "db_name": "${DB_NAME}",
    "db_user": "${DB_USER}",
    "db_password": "${DB_PASS}",
    "admin_ids": ${ADMIN_IDS_JSON},
    "LOG_GROUP_ID": ${log_group_value}
}
EOF
  chmod 600 "${target}/config.json"
  ok "config.json file created (restricted access)."
}

write_bot_settings(){
  local target="$1"
  local combined_base_url="${IRAN_HOST_URL}"
  
  # Update bot_settings.py with combined_sub_base_url
  cat > "${target}/bot_settings.py" <<'EOF'
import json
import os
import logging
import json as _json
import os as _os

_EMERGENCY_PROXY_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "emergency_proxies.json")
logger = logging.getLogger(__name__)

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_settings.json")

DEFAULT_SETTINGS = {
    "sponsor_channel": "@jadetunnell",
    "sponsor_channel_title": "Jade Tunnel",
    "membership_required": True,
    "support_username": "@jadetunnel",
    "signup_bonus": 30000,
    "referral_bonus_inviter": 20000,
    "referral_bonus_invitee": 30000,
    "special_panel_id": None,
    "special_panel_commission_percent": 50,
    "hybrid_payment_enabled": False,
    "card_number": "6219861065685272",
    "card_holder": "وحید صابر",
    "card_bank": "سامان",
    "combined_sub_base_url": "https://heysolo.ir",
}

_settings_cache = None

def _load():
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache
    data = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading bot_settings.json: {e}")
            data = {}
    merged = {**DEFAULT_SETTINGS, **data}
    _settings_cache = merged
    return merged

def _save(data):
    global _settings_cache
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _settings_cache = data

def get_sponsor_channel() -> str:
    channel = _load().get("sponsor_channel", DEFAULT_SETTINGS["sponsor_channel"])
    channel = channel.strip()
    if not channel.startswith("@"):
        channel = "@" + channel.lstrip("@")
    return channel

def set_sponsor_channel(channel: str):
    channel = channel.strip()
    if "t.me/" in channel:
        channel = channel.split("t.me/")[-1].split("?")[0].strip("/")
    if not channel.startswith("@"):
        channel = "@" + channel.lstrip("@")
    data = _load()
    data["sponsor_channel"] = channel
    _save(data)

def get_sponsor_channel_title() -> str:
    title = _load().get("sponsor_channel_title", DEFAULT_SETTINGS["sponsor_channel_title"])
    return title.strip() or DEFAULT_SETTINGS["sponsor_channel_title"]

def set_sponsor_channel_title(title: str):
    title = title.strip()
    if not title:
        return
    data = _load()
    data["sponsor_channel_title"] = title
    _save(data)

def is_membership_required() -> bool:
    return bool(_load().get("membership_required", True))

def set_membership_required(value: bool):
    data = _load()
    data["membership_required"] = bool(value)
    _save(data)

def get_support_username() -> str:
    username = _load().get("support_username", DEFAULT_SETTINGS["support_username"])
    username = username.strip()
    if not username.startswith("@"):
        username = "@" + username.lstrip("@")
    return username

def set_support_username(username: str):
    username = username.strip()
    if "t.me/" in username:
        username = username.split("t.me/")[-1].split("?")[0].strip("/")
    if not username.startswith("@"):
        username = "@" + username.lstrip("@")
    data = _load()
    data["support_username"] = username
    _save(data)

def get_signup_bonus() -> int:
    try:
        return int(_load().get("signup_bonus", DEFAULT_SETTINGS["signup_bonus"]))
    except (TypeError, ValueError):
        return DEFAULT_SETTINGS["signup_bonus"]

def set_signup_bonus(amount: int):
    data = _load()
    data["signup_bonus"] = int(amount)
    _save(data)

def get_referral_bonus_inviter() -> int:
    try:
        return int(_load().get("referral_bonus_inviter", DEFAULT_SETTINGS["referral_bonus_inviter"]))
    except (TypeError, ValueError):
        return DEFAULT_SETTINGS["referral_bonus_inviter"]

def set_referral_bonus_inviter(amount: int):
    data = _load()
    data["referral_bonus_inviter"] = int(amount)
    _save(data)

def get_referral_bonus_invitee() -> int:
    try:
        return int(_load().get("referral_bonus_invitee", DEFAULT_SETTINGS["referral_bonus_invitee"]))
    except (TypeError, ValueError):
        return DEFAULT_SETTINGS["referral_bonus_invitee"]

def set_referral_bonus_invitee(amount: int):
    data = _load()
    data["referral_bonus_invitee"] = int(amount)
    _save(data)

def get_special_panel_id():
    return _load().get("special_panel_id", DEFAULT_SETTINGS["special_panel_id"])

def set_special_panel_id(panel_id):
    data = _load()
    data["special_panel_id"] = panel_id
    _save(data)

def get_special_panel_commission_percent() -> int:
    try:
        return int(_load().get("special_panel_commission_percent", DEFAULT_SETTINGS["special_panel_commission_percent"]))
    except (TypeError, ValueError):
        return DEFAULT_SETTINGS["special_panel_commission_percent"]

def set_special_panel_commission_percent(percent: int):
    data = _load()
    data["special_panel_commission_percent"] = int(percent)
    _save(data)

def is_hybrid_payment_enabled() -> bool:
    return bool(_load().get("hybrid_payment_enabled", False))

def set_hybrid_payment_enabled(value: bool):
    data = _load()
    data["hybrid_payment_enabled"] = bool(value)
    _save(data)

def get_card_number() -> str:
    return str(_load().get("card_number", DEFAULT_SETTINGS["card_number"])).strip()

def set_card_number(value: str):
    data = _load()
    data["card_number"] = value.strip()
    _save(data)

def get_card_holder() -> str:
    return str(_load().get("card_holder", DEFAULT_SETTINGS["card_holder"])).strip()

def set_card_holder(value: str):
    data = _load()
    data["card_holder"] = value.strip()
    _save(data)

def get_card_bank() -> str:
    return str(_load().get("card_bank", DEFAULT_SETTINGS["card_bank"])).strip()

def set_card_bank(value: str):
    data = _load()
    data["card_bank"] = value.strip()
    _save(data)

_COMBINED_SUB_BASE_URL = None

def set_combined_sub_base_url(url: str):
    global _COMBINED_SUB_BASE_URL
    _COMBINED_SUB_BASE_URL = url.rstrip('/')
    data = _load()
    data["combined_sub_base_url"] = _COMBINED_SUB_BASE_URL
    _save(data)

def get_combined_sub_base_url() -> str:
    global _COMBINED_SUB_BASE_URL
    if _COMBINED_SUB_BASE_URL:
        return _COMBINED_SUB_BASE_URL
    data = _load()
    url = data.get("combined_sub_base_url")
    if url:
        _COMBINED_SUB_BASE_URL = url.rstrip('/')
        return _COMBINED_SUB_BASE_URL
    default_url = "https://heysolo.ir"
    _COMBINED_SUB_BASE_URL = default_url
    return default_url

def get_emergency_proxy_links() -> list:
    if not _os.path.exists(_EMERGENCY_PROXY_FILE):
        return []
    try:
        with open(_EMERGENCY_PROXY_FILE, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return []

def set_emergency_proxy_links(links: list):
    try:
        with open(_EMERGENCY_PROXY_FILE, "w", encoding="utf-8") as f:
            _json.dump(links, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.getLogger(__name__).error(f"Error saving emergency proxies: {e}")
EOF

  # Update the combined_sub_base_url in the settings file
  cat > "${target}/bot_settings.json" <<EOF
{
    "combined_sub_base_url": "${IRAN_HOST_URL}"
}
EOF
  
  ok "bot_settings.py and bot_settings.json configured with Iran host URL."
}

clone_or_update_repo(){
  if [[ -d "${INSTALL_DIR}/.git" ]]; then
    info "Project already exists, updating..."
    git -C "${INSTALL_DIR}" pull
  else
    info "Cloning project from GitHub..."
    mkdir -p "${INSTALL_DIR}"
    git clone "${REPO_URL}" "${INSTALL_DIR}"
  fi
  ok "Project code is ready."
}

setup_venv(){
  info "Creating Python virtual environment and installing packages..."
  cd "${INSTALL_DIR}"
  ${PY_BIN} -m venv venv
  # shellcheck disable=SC1091
  source venv/bin/activate
  pip install --upgrade pip -q
  pip install -r requirements.txt -q
  deactivate
  ok "Python packages installed."
}

run_db_setup_script(){
  if [[ -f "${INSTALL_DIR}/setup_db.py" ]]; then
    info "Creating database tables..."
    cd "${INSTALL_DIR}"
    # shellcheck disable=SC1091
    source venv/bin/activate
    python3 setup_db.py --auto || warn "Automatic table creation failed; you can run it manually later"
    deactivate
  else
    warn "setup_db.py not found; you need to create tables manually."
  fi
}

create_systemd_services(){
  info "Creating systemd services..."
  
  # Main bot service
  cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Jade Tunnel Sales Bot
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  # Sub API service
  cat > "${SUB_SERVICE_FILE}" <<EOF
[Unit]
Description=Subscription API Service
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
Environment="SUB_HOST=0.0.0.0"
Environment="SUB_PORT=2053"
Environment="ENV_FILE=${INSTALL_DIR}/.env"
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/sub_api.py
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}" >/dev/null
  systemctl enable "${SUB_SERVICE_NAME}" >/dev/null
  systemctl restart "${SERVICE_NAME}"
  systemctl restart "${SUB_SERVICE_NAME}"
  
  ok "Services created and started."
}

generate_index_php(){
  cat > "${INSTALL_DIR}/index.php" <<EOF
<?php
// ==================================================
// Subscription Proxy - Iran Host
// Place this file on your Iran host at /sub/index.php
// ==================================================

// ---- Settings ----
const API_BASE = 'http://${SERVER_IP}:2053';
const API_KEY  = '';
const SPONSOR_HTML = '
<div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 0.9rem;">
    🌟 Sponsored by <a href="https://t.me/HeySoloATM" target="_blank" style="color:#1a73e8; text-decoration:none; font-weight:bold;">@HeySoloATM</a> – Subscription link costs covered.
</div>';

function fetch_api(string $path) {
    \$url = API_BASE . \$path;
    \$ch = curl_init();
    \$headers = ['Accept: application/json'];
    if (API_KEY !== '') {
        \$headers[] = 'X-API-Key: ' . API_KEY;
    }
    curl_setopt(\$ch, CURLOPT_URL, \$url);
    curl_setopt(\$ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt(\$ch, CURLOPT_HTTPHEADER, \$headers);
    curl_setopt(\$ch, CURLOPT_TIMEOUT, 20);
    curl_setopt(\$ch, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt(\$ch, CURLOPT_SSL_VERIFYHOST, false);
    \$response = curl_exec(\$ch);
    \$httpCode = curl_getinfo(\$ch, CURLINFO_HTTP_CODE);
    \$err = curl_error(\$ch);
    curl_close(\$ch);
    return [\$httpCode, \$response, \$err];
}

\$requestUri = \$_SERVER['REQUEST_URI'];
\$userAgent  = \$_SERVER['HTTP_USER_AGENT'] ?? '';

if (preg_match('#^/sub/([A-Za-z0-9]+)#', \$requestUri, \$matches)) {
    \$token = \$matches[1];
    \$isBrowser = (bool) preg_match('/(Chrome|Firefox|Safari|Opera|Edge|MSIE|Trident)/i', \$userAgent);

    if (\$isBrowser) {
        [\$httpCode, \$body, \$err] = fetch_api('/api/sub/' . urlencode(\$token) . '?details=1');
        if (\$err || \$httpCode !== 200) {
            http_response_code(\$httpCode ?: 502);
            echo "❌ خطا در دریافت اطلاعات اشتراک" . (\$err ? ": \$err" : " (HTTP \$httpCode)");
            exit;
        }
        \$data = json_decode(\$body, true);
        if (!\$data) {
            http_response_code(502);
            echo "❌ پاسخ نامعتبر از سرویس اشتراک";
            exit;
        }
        header('Content-Type: text/html; charset=utf-8');
        \$subs = \$data['subscriptions'] ?? [];
        \$count = \$data['count'] ?? 0;
        
        echo '<!DOCTYPE html><html lang="fa" dir="rtl"><head><meta charset="utf-8">';
        echo '<meta name="viewport" content="width=device-width, initial-scale=1">';
        echo '<title>اشتراک شما | جاده تونل</title>';
        echo '<style>
            body{font-family:Tahoma,Arial,sans-serif;background:#f5f6fa;margin:0;padding:20px;direction:rtl;}
            .card{background:#fff;border-radius:12px;padding:16px 20px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,.08);}
            .card h3{margin:0 0 8px;font-size:16px;color:#222;}
            .meta{font-size:13px;color:#666;margin-bottom:10px;}
            .config{background:#f0f2f5;border-radius:8px;padding:10px;font-size:12px;word-break:break-all;margin-bottom:8px;position:relative;}
            .copy-btn{display:inline-block;margin-top:6px;padding:4px 10px;font-size:12px;border-radius:6px;background:#1a73e8;color:#fff;text-decoration:none;cursor:pointer;border:none;}
            h2{text-align:center;color:#222;}
            .empty{text-align:center;color:#888;margin-top:40px;}
        </style></head><body>';
        echo '<h2>🔑 اشتراک‌های فعال شما (' . (int)\$count . ' اشتراک)</h2>';
        if (empty(\$subs)) {
            echo '<div class="empty">هیچ اشتراک فعالی یافت نشد.</div>';
        } else {
            foreach (\$subs as \$sub) {
                \$planName = htmlspecialchars(\$sub['plan_name'] ?? 'پلن', ENT_QUOTES, 'UTF-8');
                \$endDate  = htmlspecialchars(\$sub['end_date'] ?? '-', ENT_QUOTES, 'UTF-8');
                \$volume   = \$sub['remaining_volume'] ?? null;
                echo '<div class="card">';
                echo "<h3>📦 {\$planName}</h3>";
                echo '<div class="meta">📅 انقضا: ' . \$endDate;
                if (\$volume !== null) {
                    echo ' | 📊 حجم باقیمانده: ' . (int)\$volume . ' گیگ';
                }
                echo '</div>';
                \$links = \$sub['links'] ?? [];
                foreach (\$links as \$i => \$link) {
                    \$safeLink = htmlspecialchars(\$link, ENT_QUOTES, 'UTF-8');
                    \$idAttr = 'cfg_' . uniqid();
                    echo "<div class=\"config\"><span id=\"{\$idAttr}\">{\$safeLink}</span><br>";
                    echo "<button class=\"copy-btn\" onclick=\"copyText('{\$idAttr}', this)\">📋 کپی کانفیگ " . (\$i + 1) . '</button></div>';
                }
                echo '</div>';
            }
        }
        echo '<script>
        function copyText(id, btn){
            var text = document.getElementById(id).innerText;
            navigator.clipboard.writeText(text).then(function(){
                var old = btn.innerText;
                btn.innerText = "✅ کپی شد";
                setTimeout(function(){ btn.innerText = old; }, 1500);
            });
        }
        </script>';
        echo SPONSOR_HTML;
        echo '</body></html>';
        exit;
    }

    // ---- VPN Client Mode ----
    [\$httpCode, \$body, \$err] = fetch_api('/api/sub/' . urlencode(\$token));
    if (\$err || \$httpCode !== 200) {
        http_response_code(\$httpCode ?: 502);
        echo "Subscription error" . (\$err ? ": \$err" : " (HTTP \$httpCode)");
        exit;
    }
    header('Content-Type: text/plain; charset=utf-8');
    header('Content-Disposition: inline; filename="subscribe.txt"');
    echo \$body;
    exit;
}

echo "✅ Subscription proxy is active. Use /sub/YOUR_TOKEN to get your subscription.";
EOF

  ok "index.php generated at ${INSTALL_DIR}/index.php"
  echo ""
  echo "📝 To complete the setup, upload index.php to your Iran host:"
  echo "   scp ${INSTALL_DIR}/index.php root@YOUR_IRAN_HOST:${IRAN_HOST_PATH}/index.php"
  echo ""
  echo "   Or copy the content and save it as index.php on your Iran host."
  echo ""
}

full_install(){
  require_root
  detect_python
  install_dir_prompt
  install_system_packages
  setup_database
  collect_bot_config
  collect_iran_host_config
  clone_or_update_repo
  write_config_json "${INSTALL_DIR}"
  write_bot_settings "${INSTALL_DIR}"
  setup_venv
  run_db_setup_script
  create_systemd_services
  generate_index_php
  save_install_dir
  
  echo
  ok "✅ Installation completed successfully! 🎉"
  echo "  📂 Install path     : ${INSTALL_DIR}"
  echo "  🔧 Bot service      : ${SERVICE_NAME}"
  echo "  🔧 Sub API service  : ${SUB_SERVICE_NAME}"
  echo "  🌐 Sub API URL      : http://${SERVER_IP}:2053"
  echo "  📜 Live logs        : journalctl -u ${SERVICE_NAME} -f"
  echo "  📜 Sub API logs     : journalctl -u ${SUB_SERVICE_NAME} -f"
  echo ""
  echo "  ⚠️  IMPORTANT:"
  echo "  1. Upload index.php to your Iran host:"
  echo "     ${INSTALL_DIR}/index.php → ${IRAN_HOST_PATH}/index.php"
  echo "  2. Make sure the Iran host can access http://${SERVER_IP}:2053"
  echo "  3. Your subscription links will be: ${IRAN_HOST_URL}/sub/USER_TOKEN"
}

update_bot(){
  require_root
  load_install_dir
  if [[ ! -d "${INSTALL_DIR}" ]]; then
    read -rp "Enter current installation path: " INSTALL_DIR
  fi
  detect_python
  clone_or_update_repo
  setup_venv
  systemctl restart "${SERVICE_NAME}"
  systemctl restart "${SUB_SERVICE_NAME}"
  save_install_dir
  ok "Update completed and services restarted."
}

restart_service(){
  require_root
  systemctl restart "${SERVICE_NAME}"
  systemctl restart "${SUB_SERVICE_NAME}"
  ok "Services restarted."
}

view_logs(){
  journalctl -u "${SERVICE_NAME}" -f --no-pager -n 100
}

view_sub_logs(){
  journalctl -u "${SUB_SERVICE_NAME}" -f --no-pager -n 100
}

show_status(){
  systemctl status "${SERVICE_NAME}" --no-pager || true
  echo ""
  systemctl status "${SUB_SERVICE_NAME}" --no-pager || true
}

uninstall_bot(){
  require_root
  warn "This will remove the service and bot files."
  read -rp "Are you sure? (yes/no): " CONFIRM
  if [[ "$CONFIRM" != "yes" ]]; then
    info "Cancelled."
    return
  fi

  systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
  systemctl stop "${SUB_SERVICE_NAME}" 2>/dev/null || true
  systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
  systemctl disable "${SUB_SERVICE_NAME}" 2>/dev/null || true
  rm -f "${SERVICE_FILE}"
  rm -f "${SUB_SERVICE_FILE}"
  systemctl daemon-reload

  load_install_dir
  read -rp "Installation path to remove [${INSTALL_DIR}]: " DEL_DIR
  DEL_DIR=${DEL_DIR:-$INSTALL_DIR}

  read -rp "Also drop the PostgreSQL database? (y/n) [n]: " DROP_DB
  DROP_DB=${DROP_DB:-n}
  if [[ "$DROP_DB" =~ ^[Yy]$ ]]; then
    read -rp "Database name to delete: " DB_NAME_DEL
    read -rp "Database username to delete: " DB_USER_DEL
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${DB_NAME_DEL};" || true
    sudo -u postgres psql -c "DROP ROLE IF EXISTS ${DB_USER_DEL};" || true
    ok "Database deleted."
  fi

  if [[ -d "$DEL_DIR" ]]; then
    rm -rf "$DEL_DIR"
    ok "Installation files removed."
  fi
  rm -f "${STATE_FILE}"

  ok "Bot uninstallation completed."
}

main_menu(){
  while true; do
    echo
    echo "======================================"
    echo "     🚀 Jade Tunnel Bot - Installer"
    echo "======================================"
    echo "1) Full installation"
    echo "2) Update bot"
    echo "3) Restart services"
    echo "4) View bot logs"
    echo "5) View sub API logs"
    echo "6) Service status"
    echo "7) Complete uninstall"
    echo "0) Exit"
    echo "======================================"
    read -rp "Enter option number: " CHOICE
    case "$CHOICE" in
      1) full_install; press_enter ;;
      2) update_bot; press_enter ;;
      3) restart_service; press_enter ;;
      4) view_logs ;;
      5) view_sub_logs ;;
      6) show_status; press_enter ;;
      7) uninstall_bot; press_enter ;;
      0) exit 0 ;;
      *) warn "Invalid option." ;;
    esac
  done
}

main_menu
