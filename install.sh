#!/usr/bin/env bash
# =============================================================
#  Jade Tunnel Bot - Installer
#  Usage:
#    bash <(curl -fsSL https://raw.githubusercontent.com/Mahersaber2024/JadeTunnel-sales/main/install.sh)
# =============================================================

set -euo pipefail

REPO_URL="https://github.com/Mahersaber2024/JadeTunnel-sales.git"
SERVICE_NAME="sell-bot"
DEFAULT_INSTALL_DIR="/opt/sell-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
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
    python3 setup_db.py --auto || warn "Automatic table creation failed; you can run it manually later: cd ${INSTALL_DIR} && source venv/bin/activate && python3 setup_db.py"
    deactivate
  else
    warn "setup_db.py not found; you need to create tables manually."
  fi
}

create_systemd_service(){
  info "Creating systemd service with name ${SERVICE_NAME}..."
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

  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}" >/dev/null
  systemctl restart "${SERVICE_NAME}"
  ok "Service ${SERVICE_NAME} has been enabled and started."
}

full_install(){
  require_root
  detect_python
  install_dir_prompt
  install_system_packages
  setup_database
  collect_bot_config
  clone_or_update_repo
  write_config_json "${INSTALL_DIR}"
  setup_venv
  run_db_setup_script
  create_systemd_service
  save_install_dir
  echo
  ok "Installation completed successfully! 🎉"
  echo "  📂 Install path     : ${INSTALL_DIR}"
  echo "  🔧 Service name     : ${SERVICE_NAME}"
  echo "  📜 Live logs        : journalctl -u ${SERVICE_NAME} -f"
  echo "  ℹ️  Service status   : systemctl status ${SERVICE_NAME}"
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
  save_install_dir
  ok "Update completed and service restarted."
}

restart_service(){
  require_root
  systemctl restart "${SERVICE_NAME}"
  ok "Service restarted."
}

view_logs(){
  journalctl -u "${SERVICE_NAME}" -f --no-pager -n 100
}

show_status(){
  systemctl status "${SERVICE_NAME}" --no-pager || true
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
  systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
  rm -f "${SERVICE_FILE}"
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
    echo "3) Restart service"
    echo "4) View live logs"
    echo "5) Service status"
    echo "6) Complete uninstall"
    echo "0) Exit"
    echo "======================================"
    read -rp "Enter option number: " CHOICE
    case "$CHOICE" in
      1) full_install; press_enter ;;
      2) update_bot; press_enter ;;
      3) restart_service; press_enter ;;
      4) view_logs ;;
      5) show_status; press_enter ;;
      6) uninstall_bot; press_enter ;;
      0) exit 0 ;;
      *) warn "Invalid option." ;;
    esac
  done
}

main_menu
