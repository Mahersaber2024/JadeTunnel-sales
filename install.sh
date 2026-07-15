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
press_enter(){ read -rp "برای ادامه Enter را بزنید..." _ || true; }

require_root(){
  if [[ $EUID -ne 0 ]]; then
    err "این اسکریپت باید با دسترسی root اجرا شود (با sudo یا کاربر root)."
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
  read -rp "مسیر نصب [${DEFAULT_INSTALL_DIR}]: " INSTALL_DIR
  INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}
}

detect_python(){
  if command -v python3 &>/dev/null; then
    PY_BIN=python3
  else
    err "پایتون ۳ روی سرور یافت نشد."
    exit 1
  fi
}

install_system_packages(){
  info "در حال نصب پیش‌نیازهای سیستمی..."
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip git curl build-essential libpq-dev
  ok "پیش‌نیازهای سیستمی نصب شدند."
}

install_postgresql(){
  info "در حال نصب PostgreSQL..."
  apt-get install -y postgresql postgresql-contrib
  systemctl enable postgresql
  systemctl start postgresql
  ok "PostgreSQL نصب و فعال شد."
}

setup_database(){
  echo
  echo "======================================"
  echo "          تنظیمات دیتابیس"
  echo "======================================"
  read -rp "آیا می‌خواهید PostgreSQL روی همین سرور نصب و تنظیم شود؟ (y/n) [y]: " INSTALL_DB
  INSTALL_DB=${INSTALL_DB:-y}

  if [[ "$INSTALL_DB" =~ ^[Yy]$ ]]; then
    if ! command -v psql &>/dev/null; then
      install_postgresql
    else
      info "PostgreSQL از قبل روی سرور نصب است."
      systemctl enable postgresql &>/dev/null || true
      systemctl start postgresql &>/dev/null || true
    fi

    read -rp "نام دیتابیس [jadetunnel_base]: " DB_NAME
    DB_NAME=${DB_NAME:-jadetunnel_base}
    read -rp "نام کاربری دیتابیس [cbu_user]: " DB_USER
    DB_USER=${DB_USER:-cbu_user}

    DB_PASS=""
    while [[ -z "$DB_PASS" ]]; do
      read -rsp "رمز عبور برای کاربر دیتابیس (اجباری): " DB_PASS
      echo
    done

    DB_HOST="localhost"
    DB_PORT="5432"

    info "در حال ساخت یوزر و دیتابیس در PostgreSQL..."
    sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 \
      || sudo -u postgres psql -c "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';"
    sudo -u postgres psql -c "ALTER ROLE ${DB_USER} WITH PASSWORD '${DB_PASS}';" >/dev/null

    sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 \
      || sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};" >/dev/null

    ok "دیتابیس «${DB_NAME}» و کاربر «${DB_USER}» آماده شدند."
  else
    info "لطفاً اطلاعات دیتابیس از قبل موجود (روی سرور دیگر یا همین سرور) را وارد کنید:"
    read -rp "آدرس هاست دیتابیس: " DB_HOST
    read -rp "پورت دیتابیس [5432]: " DB_PORT
    DB_PORT=${DB_PORT:-5432}
    read -rp "نام دیتابیس: " DB_NAME
    read -rp "نام کاربری دیتابیس: " DB_USER
    read -rsp "رمز عبور دیتابیس: " DB_PASS
    echo
  fi
}

collect_bot_config(){
  echo
  echo "======================================"
  echo "        تنظیمات ربات تلگرام"
  echo "======================================"
  BOT_TOKEN=""
  while [[ -z "$BOT_TOKEN" ]]; do
    read -rp "توکن ربات (از @BotFather): " BOT_TOKEN
  done

  read -rp "آیدی‌های عددی ادمین‌ها (با کاما جدا کنید، مثل 111,222): " ADMIN_IDS_RAW
  read -rp "آیدی گروه لاگ (عدد منفی، مثل -1001234567890) [اختیاری - Enter برای رد شدن]: " LOG_GROUP_ID

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
  ok "فایل config.json ساخته شد (دسترسی محدود به root)."
}

clone_or_update_repo(){
  if [[ -d "${INSTALL_DIR}/.git" ]]; then
    info "پروژه از قبل موجود است، در حال به‌روزرسانی..."
    git -C "${INSTALL_DIR}" pull
  else
    info "در حال دریافت پروژه از گیت‌هاب..."
    mkdir -p "${INSTALL_DIR}"
    git clone "${REPO_URL}" "${INSTALL_DIR}"
  fi
  ok "کد پروژه آماده شد."
}

setup_venv(){
  info "در حال ساخت محیط مجازی پایتون و نصب پکیج‌ها..."
  cd "${INSTALL_DIR}"
  ${PY_BIN} -m venv venv
  # shellcheck disable=SC1091
  source venv/bin/activate
  pip install --upgrade pip -q
  pip install -r requirements.txt -q
  deactivate
  ok "پکیج‌های پایتون نصب شدند."
}

run_db_setup_script(){
  if [[ -f "${INSTALL_DIR}/setup_db.py" ]]; then
    info "در حال ساخت جداول دیتابیس..."
    cd "${INSTALL_DIR}"
    # shellcheck disable=SC1091
    source venv/bin/activate
    python3 setup_db.py --auto || warn "ساخت خودکار جداول با خطا مواجه شد؛ می‌توانید بعداً دستی اجرا کنید: cd ${INSTALL_DIR} && source venv/bin/activate && python3 setup_db.py"
    deactivate
  else
    warn "فایل setup_db.py یافت نشد؛ ساخت جداول را باید دستی انجام دهید."
  fi
}

create_systemd_service(){
  info "در حال ساخت سرویس systemd با نام ${SERVICE_NAME}..."
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
  ok "سرویس ${SERVICE_NAME} فعال و اجرا شد."
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
  ok "نصب با موفقیت کامل شد! 🎉"
  echo "  📂 مسیر نصب      : ${INSTALL_DIR}"
  echo "  🔧 نام سرویس      : ${SERVICE_NAME}"
  echo "  📜 مشاهده لاگ زنده : journalctl -u ${SERVICE_NAME} -f"
  echo "  ℹ️  وضعیت سرویس    : systemctl status ${SERVICE_NAME}"
}

update_bot(){
  require_root
  load_install_dir
  if [[ ! -d "${INSTALL_DIR}" ]]; then
    read -rp "مسیر نصب فعلی را وارد کنید: " INSTALL_DIR
  fi
  detect_python
  clone_or_update_repo
  setup_venv
  systemctl restart "${SERVICE_NAME}"
  save_install_dir
  ok "به‌روزرسانی انجام شد و سرویس ری‌استارت شد."
}

restart_service(){
  require_root
  systemctl restart "${SERVICE_NAME}"
  ok "سرویس ری‌استارت شد."
}

view_logs(){
  journalctl -u "${SERVICE_NAME}" -f --no-pager -n 100
}

show_status(){
  systemctl status "${SERVICE_NAME}" --no-pager || true
}

uninstall_bot(){
  require_root
  warn "این کار سرویس و فایل‌های ربات را حذف می‌کند."
  read -rp "آیا مطمئن هستید؟ (yes/no): " CONFIRM
  if [[ "$CONFIRM" != "yes" ]]; then
    info "لغو شد."
    return
  fi

  systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
  systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
  rm -f "${SERVICE_FILE}"
  systemctl daemon-reload

  load_install_dir
  read -rp "مسیر نصب برای حذف [${INSTALL_DIR}]: " DEL_DIR
  DEL_DIR=${DEL_DIR:-$INSTALL_DIR}

  read -rp "آیا دیتابیس PostgreSQL هم حذف شود؟ (y/n) [n]: " DROP_DB
  DROP_DB=${DROP_DB:-n}
  if [[ "$DROP_DB" =~ ^[Yy]$ ]]; then
    read -rp "نام دیتابیس برای حذف: " DB_NAME_DEL
    read -rp "نام کاربری دیتابیس برای حذف: " DB_USER_DEL
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${DB_NAME_DEL};" || true
    sudo -u postgres psql -c "DROP ROLE IF EXISTS ${DB_USER_DEL};" || true
    ok "دیتابیس حذف شد."
  fi

  if [[ -d "$DEL_DIR" ]]; then
    rm -rf "$DEL_DIR"
    ok "فایل‌های نصب حذف شدند."
  fi
  rm -f "${STATE_FILE}"

  ok "حذف ربات کامل شد."
}

main_menu(){
  while true; do
    echo
    echo "======================================"
    echo "     🚀 Jade Tunnel Bot - Installer"
    echo "======================================"
    echo "1) نصب کامل ربات (Install)"
    echo "2) به‌روزرسانی ربات (Update)"
    echo "3) ری‌استارت سرویس"
    echo "4) مشاهده لاگ زنده"
    echo "5) وضعیت سرویس"
    echo "6) حذف کامل ربات (Uninstall)"
    echo "0) خروج"
    echo "======================================"
    read -rp "شماره گزینه را وارد کنید: " CHOICE
    case "$CHOICE" in
      1) full_install; press_enter ;;
      2) update_bot; press_enter ;;
      3) restart_service; press_enter ;;
      4) view_logs ;;
      5) show_status; press_enter ;;
      6) uninstall_bot; press_enter ;;
      0) exit 0 ;;
      *) warn "گزینه نامعتبر است." ;;
    esac
  done
}

main_menu
