#!/bin/bash
# ============================================================
#  SMS API — automatinis diegimo skriptas
#  ZTE modemo HTTP API integracija su Flask
#  Veikia: Ubuntu 20.04+ / Debian 11+
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

INSTALL_DIR="/opt/sms-api"
SERVICE_FILE="/etc/systemd/system/sms-api.service"
LOG_FILE="/var/log/sms-api.log"

print_header() {
  echo ""
  echo -e "${BLUE}${BOLD}╔══════════════════════════════════════╗${NC}"
  echo -e "${BLUE}${BOLD}║        SMS API — Diegimas v1.0       ║${NC}"
  echo -e "${BLUE}${BOLD}╚══════════════════════════════════════╝${NC}"
  echo ""
}

print_step() {
  echo -e "\n${YELLOW}▶ $1${NC}"
}

print_ok() {
  echo -e "  ${GREEN}✓ $1${NC}"
}

print_error() {
  echo -e "  ${RED}✗ $1${NC}"
  exit 1
}

# ── Root patikrinimas ──────────────────────────────────────
check_root() {
  if [ "$EUID" -ne 0 ]; then
    print_error "Paleiskite kaip root: sudo bash install.sh"
  fi
}

# ── OS patikrinimas ────────────────────────────────────────
check_os() {
  print_step "Tikrinamas OS..."
  if [ -f /etc/os-release ]; then
    . /etc/os-release
    print_ok "OS: $PRETTY_NAME"
  else
    echo -e "  ${YELLOW}⚠ Nepavyko nustatyti OS — tęsiama${NC}"
  fi
}

# ── Priklausomybės ─────────────────────────────────────────
install_deps() {
  print_step "Diegiamos priklausomybės..."
  apt-get update -qq
  apt-get install -y -qq python3 python3-pip > /dev/null 2>&1
  print_ok "python3 ir pip įdiegti"
}

# ── Failų kopijavimas ──────────────────────────────────────
copy_files() {
  print_step "Kopijuojami failai į ${INSTALL_DIR}..."

  mkdir -p "${INSTALL_DIR}/templates"

  cp app.py            "${INSTALL_DIR}/"
  cp manage-tokens.py  "${INSTALL_DIR}/"
  cp requirements.txt  "${INSTALL_DIR}/"
  cp -r templates/     "${INSTALL_DIR}/templates/"

  chmod +x "${INSTALL_DIR}/app.py"
  chmod +x "${INSTALL_DIR}/manage-tokens.py"

  print_ok "Failai nukopijuoti į ${INSTALL_DIR}"
}

# ── Python paketai ─────────────────────────────────────────
install_python_packages() {
  print_step "Diegiami Python paketai..."
  pip3 install -q -r "${INSTALL_DIR}/requirements.txt"
  print_ok "Flask ir Werkzeug įdiegti"
}

# ── Log failas ─────────────────────────────────────────────
setup_log() {
  touch "${LOG_FILE}"
  chmod 640 "${LOG_FILE}"
  print_ok "Log failas: ${LOG_FILE}"
}

# ── Systemd servisas ───────────────────────────────────────
setup_service() {
  print_step "Konfigūruojamas systemd servisas..."
  cp systemd/sms-api.service "${SERVICE_FILE}"
  systemctl daemon-reload
  systemctl enable sms-api.service > /dev/null 2>&1
  systemctl start sms-api.service
  sleep 2

  if systemctl is-active --quiet sms-api; then
    print_ok "Servisas paleistas ir įjungtas"
  else
    print_error "Servisas nepasileido — patikrinkite: journalctl -u sms-api"
  fi
}

# ── Admin slaptažodis ──────────────────────────────────────
show_credentials() {
  ADMIN_PWD=$(cat "${INSTALL_DIR}/admin.conf" 2>/dev/null || echo "generuojamas pirmą kartą")
  SERVER_IP=$(hostname -I | awk '{print $1}')

  echo ""
  echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}${BOLD}║           DIEGIMAS SĖKMINGAS ✓               ║${NC}"
  echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  ${BOLD}API URL:${NC}        http://${SERVER_IP}:5000"
  echo -e "  ${BOLD}Admin panel:${NC}    http://${SERVER_IP}:5000/admin"
  echo -e "  ${BOLD}Admin slaptaž.:${NC} ${YELLOW}${ADMIN_PWD}${NC}"
  echo -e "  ${BOLD}Admin conf:${NC}     ${INSTALL_DIR}/admin.conf"
  echo ""
  echo -e "  ${BOLD}Tokenų valdymas:${NC}"
  echo -e "    cd ${INSTALL_DIR} && python3 manage-tokens.py list"
  echo -e "    cd ${INSTALL_DIR} && python3 manage-tokens.py create \"Vardas\""
  echo ""
  echo -e "  ${BOLD}Servisų komandos:${NC}"
  echo -e "    systemctl status sms-api"
  echo -e "    systemctl restart sms-api"
  echo -e "    journalctl -u sms-api -f"
  echo ""
  echo -e "  ${YELLOW}⚠  Atidarykite port 5000 firewall'e jei reikia:${NC}"
  echo -e "     ufw allow 5000/tcp"
  echo ""
}

# ── ZTE tinklo patikrinimas ────────────────────────────────
check_modem() {
  print_step "Tikrinamas ZTE modemas (192.168.0.1)..."
  if curl -s --connect-timeout 3 http://192.168.0.1/goform/goform_get_cmd_process?cmd=modem_main_state > /dev/null 2>&1; then
    print_ok "ZTE modemas pasiekiamas"
  else
    echo -e "  ${YELLOW}⚠ ZTE modemas nepasiekiamas — patikrinkite tinklo konfigūraciją${NC}"
    echo -e "    Modemas turi būti prieinamas adresu 192.168.0.1"
    echo -e "    Daugiau: žr. INSTALL.md skyrius 'Modemo konfigūracija'"
  fi
}

# ── Uninstall ──────────────────────────────────────────────
uninstall() {
  echo -e "${RED}${BOLD}Šalinamas SMS API...${NC}"
  systemctl stop sms-api 2>/dev/null || true
  systemctl disable sms-api 2>/dev/null || true
  rm -f "${SERVICE_FILE}"
  systemctl daemon-reload
  rm -rf "${INSTALL_DIR}"
  rm -f "${LOG_FILE}"
  echo -e "${GREEN}✓ SMS API pašalintas${NC}"
  exit 0
}

# ── Main ───────────────────────────────────────────────────
print_header

case "${1}" in
  uninstall|remove)
    uninstall
    ;;
  *)
    check_root
    check_os
    install_deps
    copy_files
    install_python_packages
    setup_log
    check_modem
    setup_service
    show_credentials
    ;;
esac
