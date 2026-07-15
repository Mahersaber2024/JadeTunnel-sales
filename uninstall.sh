#!/usr/bin/env bash
# =============================================================
#  Jade Tunnel Bot - Uninstaller
#  Usage:
#    bash <(curl -fsSL https://raw.githubusercontent.com/Mahersaber2024/JadeTunnel-sales/main/uninstall.sh)
# =============================================================

set -euo pipefail

SERVICE_NAME="sell-bot"
DEFAULT_INSTALL_DIR="/opt/sell-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
STATE_FILE="/etc/${SERVICE_NAME}.install_dir"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info(){ echo -e "${CYAN}ℹ️  $1${NC}"; }
ok(){ echo -e "${GREEN}✅ $1${NC}"; }
warn(){ echo -e "${YELLOW}⚠️  $1${NC}"; }
err(){ echo -e "${RED}❌ $1${NC}"; }

require_root(){
  if [[ $EUID -ne 0 ]]; then
    err "This script must be run with root privileges (using sudo or as root user)."
    exit 1
  fi
}

load_install_dir(){
  if [[ -f "${STATE_FILE}" ]]; then
    cat "${STATE_FILE}"
  else
    echo "${DEFAULT_INSTALL_DIR}"
  fi
}

stop_and_remove_service(){
  info "Stopping service..."
  systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
  systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
  rm -f "${SERVICE_FILE}"
  systemctl daemon-reload
  ok "Service ${SERVICE_NAME} has been stopped and removed."
}

remove_files(){
  local dir
  dir=$(load_install_dir)
  read -rp "Installation path to remove [${dir}]: " DEL_DIR
  DEL_DIR=${DEL_DIR:-$dir}

  if [[ -d "$DEL_DIR" ]]; then
    rm -rf "$DEL_DIR"
    ok "Project files have been removed from ${DEL_DIR}."
  else
    warn "Path ${DEL_DIR} not found."
  fi
  rm -f "${STATE_FILE}"
}

remove_database(){
  read -rp "Database name to delete: " DB_NAME_DEL
  read -rp "Database username to delete: " DB_USER_DEL

  if ! command -v psql &>/dev/null; then
    warn "PostgreSQL not found on this server; skipping this step."
    return
  fi

  warn "Database «${DB_NAME_DEL}» and user «${DB_USER_DEL}» will be permanently deleted."
  read -rp "Are you sure? (yes/no): " CONFIRM_DB
  if [[ "$CONFIRM_DB" != "yes" ]]; then
    info "Database deletion cancelled."
    return
  fi

  sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${DB_NAME_DEL};" || true
  sudo -u postgres psql -c "DROP ROLE IF EXISTS ${DB_USER_DEL};" || true
  ok "Database and related user have been deleted."
}

main_menu(){
  require_root
  echo "======================================"
  echo "     🗑  Jade Tunnel Bot - Uninstaller"
  echo "======================================"
  echo "1) Stop and remove service only (files and database will remain)"
  echo "2) Remove service + project files (database will remain)"
  echo "3) Complete removal: service + files + database"
  echo "0) Cancel and exit"
  echo "======================================"
  read -rp "Enter option number: " CHOICE

  case "$CHOICE" in
    1)
      stop_and_remove_service
      ;;
    2)
      stop_and_remove_service
      remove_files
      ;;
    3)
      stop_and_remove_service
      remove_files
      remove_database
      ;;
    0)
      info "Cancelled."
      exit 0
      ;;
    *)
      err "Invalid option."
      exit 1
      ;;
  esac

  echo
  ok "Uninstallation completed successfully."
}

main_menu
