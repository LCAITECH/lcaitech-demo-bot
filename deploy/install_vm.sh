#!/usr/bin/env bash
# Instala o actualiza el bot demo de LCA ITECH en una VM Debian/Ubuntu con systemd (sin Docker).
#
#   sudo bash install_vm.sh                 # instalar o actualizar (no vuelve a pedir el token si ya está guardado)
#   sudo bash install_vm.sh --change-token  # reemplazar el token guardado
#
# Qué hace: instala git y python3-venv si faltan, clona/actualiza el repo en /opt/lcaitech-demo-bot,
# crea el venv, crea el usuario de sistema 'demobot', guarda el token en /etc/lcaitech-demo-bot.env
# (root, chmod 600) y crea/habilita/reinicia el servicio systemd 'lcaitech-demo-bot'.
# El token se pide con `read -rs` (no se muestra ni queda en el historial) y nunca se imprime.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/LCAITECH/lcaitech-demo-bot.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/lcaitech-demo-bot}"
ENV_FILE="${ENV_FILE:-/etc/lcaitech-demo-bot.env}"
SERVICE="lcaitech-demo-bot"
UNIT_FILE="${UNIT_FILE:-/etc/systemd/system/${SERVICE}.service}"
BOT_USER="demobot"
SKIP_TOKEN_CHECK="${SKIP_TOKEN_CHECK:-0}"   # solo para pruebas
SIMULATE="${SIMULATE:-0}"                   # solo para pruebas (permite correr sin root)

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '    \033[33m⚠\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

usage() { sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; }

CHANGE_TOKEN=0
for arg in "$@"; do
  case "$arg" in
    --change-token) CHANGE_TOKEN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Opción desconocida: $arg (usá --help)" ;;
  esac
done

# ---------- 0. chequeos ----------
step "0/7 Chequeos"
if [ "$SIMULATE" != "1" ] && [ "$(id -u)" -ne 0 ]; then
  die "Correlo con sudo: sudo bash $0"
fi
command -v apt-get >/dev/null 2>&1 || die "Este instalador es para Debian/Ubuntu (apt-get)."
command -v systemctl >/dev/null 2>&1 || die "No encontré systemd (systemctl)."
ok "Debian/Ubuntu con systemd"

# ---------- 1. paquetes ----------
step "1/7 Paquetes del sistema (git, python3-venv)"
need=()
command -v git >/dev/null 2>&1 || need+=(git)
command -v python3 >/dev/null 2>&1 || need+=(python3)
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import ensurepip, venv' >/dev/null 2>&1; then
  need+=(python3-venv)
fi
if [ "${#need[@]}" -gt 0 ]; then
  echo "    Instalando: ${need[*]} (puede tardar un minuto)…"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates "${need[@]}" >/dev/null
  ok "Instalado: ${need[*]}"
else
  ok "git y python3-venv ya estaban"
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || die "Se necesita Python 3.10 o más nuevo (hay $(python3 -V 2>&1)). Usá Debian 12+ o Ubuntu 22.04+."
ok "$(python3 -V)"

# ---------- 2. usuario ----------
step "2/7 Usuario de sistema '$BOT_USER'"
if id "$BOT_USER" >/dev/null 2>&1; then
  ok "ya existe"
else
  useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$BOT_USER"
  ok "creado (sin login, sin home)"
fi

# ---------- 3. código ----------
step "3/7 Código en $APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
  git -C "$APP_DIR" checkout --quiet "$BRANCH"
  git -C "$APP_DIR" reset --quiet --hard "origin/$BRANCH"
  ok "actualizado a $(git -C "$APP_DIR" log -1 --format='%h %s')"
elif [ -e "$APP_DIR" ] && [ -n "$(ls -A "$APP_DIR" 2>/dev/null)" ]; then
  die "$APP_DIR existe y no es un repo git. Movelo o borralo y volvé a correr el script."
else
  git clone --quiet --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
  ok "clonado $(git -C "$APP_DIR" log -1 --format='%h %s')"
fi

# ---------- 4. venv ----------
step "4/7 Entorno Python (venv + dependencias)"
if [ ! -x "$APP_DIR/.venv/bin/pip" ]; then
  rm -rf "$APP_DIR/.venv"
  if ! python3 -m venv "$APP_DIR/.venv" >/dev/null 2>&1; then
    # algunas imágenes necesitan el paquete versionado (ej. python3.11-venv)
    pyver="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
    echo "    Instalando python3-venv / python${pyver}-venv…"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3-venv "python${pyver}-venv" >/dev/null 2>&1 || apt-get install -y -qq python3-venv >/dev/null
    rm -rf "$APP_DIR/.venv"
    python3 -m venv "$APP_DIR/.venv"
  fi
fi
"$APP_DIR/.venv/bin/pip" install --quiet --disable-pip-version-check -r "$APP_DIR/requirements.txt"
ok "dependencias instaladas"

# ---------- 5. token ----------
step "5/7 Token del bot ($ENV_FILE)"
token_saved() { [ -f "$ENV_FILE" ] && grep -qE '^TELEGRAM_BOT_TOKEN=.+' "$ENV_FILE"; }

# Valida el token con getMe. El token viaja por variable de entorno (nunca por argumentos ni pantalla).
check_token() {
  [ "$SKIP_TOKEN_CHECK" = "1" ] && { echo "skip"; return 0; }
  BOT_TOKEN_CHECK="$1" "$APP_DIR/.venv/bin/python" - <<'PY'
import json, os, sys, urllib.error, urllib.request
t = os.environ["BOT_TOKEN_CHECK"]
try:
    with urllib.request.urlopen(f"https://api.telegram.org/bot{t}/getMe", timeout=15) as r:
        print("@" + json.load(r)["result"]["username"])
except urllib.error.HTTPError as e:
    print("rejected" if e.code in (401, 404) else f"http{e.code}")
except Exception:
    print("network")
PY
}

read_secret() {  # lee sin eco desde la terminal (o stdin si no hay terminal)
  local __v=""
  if { exec 3</dev/tty; } 2>/dev/null; then
    IFS= read -rs __v <&3 || true
    exec 3<&-
  else
    IFS= read -rs __v || true
  fi
  printf '%s' "$__v"
}

if token_saved && [ "$CHANGE_TOKEN" != "1" ]; then
  ok "ya hay un token guardado; no lo pido de nuevo (para cambiarlo: --change-token)"
else
  echo "    Pegá el token que te dio @BotFather y apretá Enter."
  echo "    (No se va a ver nada mientras pegás: es a propósito.)"
  TOKEN=""
  for attempt in 1 2 3; do
    printf '    Token: '
    TOKEN="$(read_secret)"
    echo
    TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"
    if ! printf '%s' "$TOKEN" | grep -qE '^[0-9]{6,12}:[A-Za-z0-9_-]{30,}$'; then
      warn "Eso no tiene forma de token (números:letras). Intento $attempt de 3."
      TOKEN=""; continue
    fi
    res="$(check_token "$TOKEN")"
    case "$res" in
      @*) ok "Telegram aceptó el token: bot $res"; break ;;
      skip) ok "formato OK (validación salteada)"; break ;;
      rejected) warn "Telegram rechazó ese token. Intento $attempt de 3."; TOKEN="" ;;
      *) warn "No pude validar con Telegram ($res); lo guardo igual."; break ;;
    esac
  done
  [ -n "$TOKEN" ] || die "No se guardó ningún token. Volvé a correr el script."
  tmp="$(mktemp "${ENV_FILE}.XXXXXX")"
  chmod 600 "$tmp"
  if [ -f "$ENV_FILE" ]; then grep -v '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" > "$tmp" || true; fi
  printf 'TELEGRAM_BOT_TOKEN=%s\n' "$TOKEN" >> "$tmp"
  unset TOKEN
  [ "$SIMULATE" = "1" ] || chown root:root "$tmp"
  mv -f "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  ok "guardado en $ENV_FILE (dueño root, permisos 600)"
fi

# ---------- 6. servicio ----------
step "6/7 Servicio systemd '$SERVICE'"
cat > "$UNIT_FILE" <<UNIT
[Unit]
Description=LCA ITECH demo bot (Telegram)
Documentation=https://github.com/LCAITECH/lcaitech-demo-bot
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$BOT_USER
Group=$BOT_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
Environment=PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ExecStart=$APP_DIR/.venv/bin/python -u bot.py
Restart=always
RestartSec=10
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryMax=300M

[Install]
WantedBy=multi-user.target
UNIT
chmod 644 "$UNIT_FILE"
systemctl daemon-reload
systemctl enable --quiet "$SERVICE"
systemctl restart "$SERVICE"
ok "habilitado (arranca solo con la VM) y (re)iniciado"

# ---------- 7. verificación ----------
step "7/7 Verificación"
echo "    Esperando que arranque…"
sleep 8
systemctl --no-pager --lines=0 status "$SERVICE" || true
echo
echo "    Últimas líneas del log:"
journalctl -u "$SERVICE" -n 15 --no-pager -o short-iso 2>/dev/null \
  | sed -E 's/[0-9]{6,}:[A-Za-z0-9_-]{30,}/[REDACTED]/g' || true
logs="$(journalctl -u "$SERVICE" -n 300 --no-pager -o cat 2>/dev/null || true)"
if grep -q '^TELEGRAM_BOT_TOKEN=.' "$ENV_FILE" 2>/dev/null \
   && printf '%s' "$logs" | grep -qF -f <(sed -n 's/^TELEGRAM_BOT_TOKEN=//p' "$ENV_FILE"); then
  warn "¡El token aparece en el log! Avisá a Leandro/soporte y regenerá el token en @BotFather."
else
  ok "el token no aparece en el log"
fi
echo
if systemctl is-active --quiet "$SERVICE" && printf '%s' "$logs" | grep -q 'Application started'; then
  ok "Bot corriendo. Probalo en Telegram con /start."
else
  warn "El bot todavía no reporta 'Application started'. Mirá: journalctl -u $SERVICE -f"
fi
if printf '%s' "$logs" | grep -qi 'conflict'; then
  warn "Telegram reporta otra instancia usando el mismo token: apagá el bot viejo (box) y reiniciá: sudo systemctl restart $SERVICE"
fi
cat <<HELP

Comandos útiles:
  Ver log en vivo:   sudo journalctl -u $SERVICE -f
  Estado:            systemctl status $SERVICE
  Reiniciar:         sudo systemctl restart $SERVICE
  Parar:             sudo systemctl stop $SERVICE
  Actualizar:        sudo bash $APP_DIR/deploy/install_vm.sh
  Cambiar token:     sudo bash $APP_DIR/deploy/install_vm.sh --change-token
HELP
