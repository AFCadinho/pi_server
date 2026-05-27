#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${ROOT_DIR}/deploy-api-restart.log"

nohup bash -c '
  set -euo pipefail
  sleep 3
  cd "$1"
  ./server.sh start >>"$2" 2>&1
' bash "${ROOT_DIR}" "${LOG_FILE}" >/dev/null 2>&1 &

echo "Scheduled deploy-api restart"
