#!/usr/bin/env bash
set -euo pipefail

APP_NAME="speech2text-net"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
DATA_DIR="${HOME}/.local/share/${APP_NAME}"
VENV_DIR="${DATA_DIR}/venv"
CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/${APP_NAME}"
STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/${APP_NAME}"
CONFIG_PATH="${CONFIG_DIR}/${APP_NAME}.conf"
TOKEN_DIR="${CONFIG_DIR}/.secrets"
TOKEN_FILE="${TOKEN_DIR}/${APP_NAME}.token"
GPU_SCRIPT_DST="${DATA_DIR}/gpu-cleanup.sh"

prompt() {
  local text="$1"
  local default="${2:-}"
  if [[ -n "$default" ]]; then
    read -r -p "${text} [${default}]: " answer
    printf '%s' "${answer:-$default}"
  else
    read -r -p "${text}: " answer
    printf '%s' "$answer"
  fi
}

choose_role() {
  local role="${1:-}"
  if [[ -n "$role" ]]; then
    printf '%s' "$role"
    return
  fi

  printf 'Install profile\n'
  printf '  1) client\n'
  printf '  2) server\n'
  printf '  3) all\n'
  local choice
  choice="$(prompt 'Choose profile' '1')"
  case "$choice" in
    1|client) printf 'client' ;;
    2|server) printf 'server' ;;
    3|all|workstation) printf 'all' ;;
    *) printf 'client' ;;
  esac
}

ensure_paths() {
  mkdir -p "$BIN_DIR" "$DATA_DIR" "$STATE_DIR" "$CONFIG_DIR" "$TOKEN_DIR" "${DATA_DIR}/output"
}

install_python_package() {
  python3 -m venv "$VENV_DIR"
  "${VENV_DIR}/bin/pip" install --upgrade pip setuptools wheel >/dev/null
  "${VENV_DIR}/bin/pip" install "$PROJECT_ROOT"
}

install_wrapper() {
  cat > "${BIN_DIR}/${APP_NAME}" <<EOF
#!/usr/bin/env bash
exec "${VENV_DIR}/bin/${APP_NAME}" "\$@"
EOF
  chmod 755 "${BIN_DIR}/${APP_NAME}"
}

install_cleanup_script() {
  install -m 755 "${PROJECT_ROOT}/gpu-cleanup.sh" "${GPU_SCRIPT_DST}"
}

random_token() {
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
}

write_client_config() {
  local server_url token_hint
  server_url="$(prompt 'Remote server URL' 'http://100.64.0.10:8765')"
  token_hint=''
  if [[ -f "$TOKEN_FILE" ]]; then
    token_hint='# API token file already exists and will be used.'
  fi
  cat > "$CONFIG_PATH" <<EOF
OUT_DIR=~/.local/share/${APP_NAME}/output
LOG_FILE=~/.local/state/${APP_NAME}/client.log
CLIENT_LOG_FILE=~/.local/state/${APP_NAME}/client.log

ENABLE_CLIPBOARD=1
ENABLE_COLOR=1
QUIET=0

ENABLE_MEDIA_MUTE=1
MUTE_ONLY=0
RECORD_BACKEND=auto
RECORD_DEVICE=

AUTO_DETECT_LOCAL_SERVER=1
SERVER_URL=${server_url}

API_TOKEN=
API_TOKEN_FILE=~/.config/${APP_NAME}/.secrets/${APP_NAME}.token
${token_hint}
EOF
}

write_server_config() {
  local bind_mode host model_dir clean_mode token
  bind_mode="$(prompt 'Bind mode (localhost/tailscale)' 'localhost')"
  host='127.0.0.1'
  if [[ "$bind_mode" == "tailscale" ]]; then
    host="$(prompt 'Tailscale IPv4/hostname to bind' '100.64.0.10')"
    if [[ ! -f "$TOKEN_FILE" ]]; then
      token="$(random_token)"
      printf '%s\n' "$token" > "$TOKEN_FILE"
      chmod 600 "$TOKEN_FILE"
      printf 'Created API token file: %s\n' "$TOKEN_FILE"
    fi
  fi
  model_dir="$(prompt 'Whisper model directory' '~/whisper-models')"
  clean_mode="$(prompt 'GPU cleanup mode (empty/safe/force)' '')"
  cat > "$CONFIG_PATH" <<EOF
MODEL=turbo
LANGUAGE=German
DEVICE=cuda
FP16=1

OUT_DIR=~/.local/share/${APP_NAME}/output
MODEL_DIR=${model_dir}
LOG_FILE=~/.local/state/${APP_NAME}/server.log
SERVER_LOG_FILE=~/.local/state/${APP_NAME}/server.log

TITLE_MODEL=
TITLE_MAXLEN=40
AUTO_TITLE=1

SERVER_HOST=${host}
SERVER_PORT=8765
SERVER_URL=http://${host}:8765

API_TOKEN=
API_TOKEN_FILE=~/.config/${APP_NAME}/.secrets/${APP_NAME}.token

CLEAN_MODE=${clean_mode}
GPU_CLEANUP_PATH=~/.local/share/${APP_NAME}/gpu-cleanup.sh
EOF
}

write_all_config() {
  local bind_mode host model_dir clean_mode token
  bind_mode="$(prompt 'Bind mode (localhost/tailscale)' 'localhost')"
  host='127.0.0.1'
  if [[ "$bind_mode" == "tailscale" ]]; then
    host="$(prompt 'Tailscale IPv4/hostname to bind' '100.64.0.10')"
    if [[ ! -f "$TOKEN_FILE" ]]; then
      token="$(random_token)"
      printf '%s\n' "$token" > "$TOKEN_FILE"
      chmod 600 "$TOKEN_FILE"
      printf 'Created API token file: %s\n' "$TOKEN_FILE"
    fi
  fi
  model_dir="$(prompt 'Whisper model directory' '~/whisper-models')"
  clean_mode="$(prompt 'GPU cleanup mode (empty/safe/force)' '')"
  cat > "$CONFIG_PATH" <<EOF
MODEL=turbo
LANGUAGE=German
DEVICE=cuda
FP16=1

OUT_DIR=~/.local/share/${APP_NAME}/output
MODEL_DIR=${model_dir}
LOG_FILE=~/.local/state/${APP_NAME}/${APP_NAME}.log
CLIENT_LOG_FILE=~/.local/state/${APP_NAME}/client.log
SERVER_LOG_FILE=~/.local/state/${APP_NAME}/server.log

TITLE_MODEL=
TITLE_MAXLEN=40
AUTO_TITLE=1

ENABLE_MEDIA_MUTE=1
MUTE_ONLY=0
ENABLE_COLOR=1
QUIET=0
ENABLE_CLIPBOARD=1
RECORD_BACKEND=auto
RECORD_DEVICE=

AUTO_DETECT_LOCAL_SERVER=1
SERVER_HOST=${host}
SERVER_PORT=8765
SERVER_URL=http://${host}:8765

API_TOKEN=
API_TOKEN_FILE=~/.config/${APP_NAME}/.secrets/${APP_NAME}.token

CLEAN_MODE=${clean_mode}
GPU_CLEANUP_PATH=~/.local/share/${APP_NAME}/gpu-cleanup.sh
EOF
}

main() {
  local role
  role="$(choose_role "${1:-}")"
  ensure_paths
  install_python_package
  install_wrapper
  install_cleanup_script

  if [[ -f "$CONFIG_PATH" ]]; then
    printf 'Config already exists: %s\n' "$CONFIG_PATH"
  else
    case "$role" in
      client) write_client_config ;;
      server) write_server_config ;;
      all) write_all_config ;;
      *) write_client_config ;;
    esac
    chmod 600 "$CONFIG_PATH"
    printf 'Wrote config: %s\n' "$CONFIG_PATH"
  fi

  printf '\nInstalled %s.\n' "$APP_NAME"
  printf 'Command: %s/%s\n' "$BIN_DIR" "$APP_NAME"
  printf 'Config : %s\n' "$CONFIG_PATH"
  printf '\nNext steps:\n'
  case "$role" in
    client)
      printf '  %s doctor\n' "$APP_NAME"
      printf '  %s client\n' "$APP_NAME"
      ;;
    server)
      printf '  %s doctor\n' "$APP_NAME"
      printf '  %s server --foreground\n' "$APP_NAME"
      ;;
    all)
      printf '  %s doctor\n' "$APP_NAME"
      printf '  %s server --foreground\n' "$APP_NAME"
      printf '  %s client\n' "$APP_NAME"
      ;;
  esac
}

main "${1:-}"
