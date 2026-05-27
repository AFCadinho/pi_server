#!/usr/bin/env bash
set -euo pipefail

APP_NAME="deploy-api"
APP_MODULE="main:app"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${ROOT_DIR}/${APP_NAME}.pid"
LOG_FILE="${ROOT_DIR}/${APP_NAME}.log"
SERVICE_NAME="${SERVICE_NAME:-deploy-api.service}"

usage() {
  cat <<EOF
Usage: $(basename "$0") {start|stop|restart|status|logs}

Environment overrides:
  HOST          Bind host for local mode. Default: ${HOST}
  PORT          Bind port for local mode. Default: ${PORT}
  SERVICE_NAME  systemd service name. Default: ${SERVICE_NAME}
EOF
}

has_systemd_service() {
  command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files "${SERVICE_NAME}" >/dev/null 2>&1
}

is_local_running() {
  [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" >/dev/null 2>&1
}

is_port_open() {
  local python_bin="python3"
  if ! command -v "${python_bin}" >/dev/null 2>&1; then
    python_bin="python"
  fi
  if ! command -v "${python_bin}" >/dev/null 2>&1; then
    return 1
  fi

  "${python_bin}" - "${HOST}" "${PORT}" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.5)
    try:
        sys.exit(0 if sock.connect_ex((host, port)) == 0 else 1)
    except OSError:
        sys.exit(1)
PY
}

print_recent_logs() {
  if [[ -f "${LOG_FILE}" ]]; then
    echo
    echo "Recent logs:"
    tail -40 "${LOG_FILE}"
  fi
}

start_local() {
  if is_local_running; then
    echo "${APP_NAME} is already running locally with PID $(cat "${PID_FILE}")"
    return
  fi
  rm -f "${PID_FILE}"

  cd "${ROOT_DIR}"
  if [[ ! -f ".env" ]]; then
    echo "Warning: .env not found in ${ROOT_DIR}" >&2
  fi

  if is_port_open; then
    echo "Cannot start ${APP_NAME}: ${HOST}:${PORT} is already in use." >&2
    echo "Try: PORT=8081 $0 start" >&2
    exit 1
  fi

  {
    echo
    echo "----- $(date '+%Y-%m-%d %H:%M:%S') starting ${APP_NAME} on ${HOST}:${PORT} -----"
  } >>"${LOG_FILE}"

  nohup poetry run uvicorn "${APP_MODULE}" --host "${HOST}" --port "${PORT}" >>"${LOG_FILE}" 2>&1 &
  echo "$!" >"${PID_FILE}"

  sleep 1
  if ! is_local_running; then
    rm -f "${PID_FILE}"
    echo "Failed to start ${APP_NAME} locally on ${HOST}:${PORT}" >&2
    print_recent_logs >&2
    exit 1
  fi

  echo "Started ${APP_NAME} locally on ${HOST}:${PORT} with PID $(cat "${PID_FILE}")"
  echo "Logs: ${LOG_FILE}"
}

stop_local() {
  if ! is_local_running; then
    rm -f "${PID_FILE}"
    echo "${APP_NAME} is not running locally"
    return
  fi

  local pid
  pid="$(cat "${PID_FILE}")"
  kill "${pid}"

  for _ in {1..20}; do
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      rm -f "${PID_FILE}"
      echo "Stopped ${APP_NAME}"
      return
    fi
    sleep 0.25
  done

  echo "Process ${pid} did not stop gracefully; sending SIGKILL" >&2
  kill -9 "${pid}" >/dev/null 2>&1 || true
  rm -f "${PID_FILE}"
  echo "Stopped ${APP_NAME}"
}

start() {
  if has_systemd_service; then
    sudo systemctl start "${SERVICE_NAME}"
    sudo systemctl status "${SERVICE_NAME}" --no-pager
  else
    start_local
  fi
}

stop() {
  if has_systemd_service; then
    sudo systemctl stop "${SERVICE_NAME}"
    echo "Stopped ${SERVICE_NAME}"
  else
    stop_local
  fi
}

status() {
  if has_systemd_service; then
    systemctl status "${SERVICE_NAME}" --no-pager
  elif is_local_running; then
    echo "${APP_NAME} is running locally with PID $(cat "${PID_FILE}")"
  else
    echo "${APP_NAME} is not running"
  fi
}

logs() {
  if has_systemd_service; then
    journalctl -u "${SERVICE_NAME}" -f
  else
    touch "${LOG_FILE}"
    tail -f "${LOG_FILE}"
  fi
}

case "${1:-}" in
  start)
    start
    ;;
  stop)
    stop
    ;;
  restart)
    stop
    start
    ;;
  status)
    status
    ;;
  logs)
    logs
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: $1" >&2
    usage >&2
    exit 1
    ;;
esac
