#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${ROOT_DIR}/deploy-api-restart.log"

(
  sleep 2
  cd "${ROOT_DIR}"
  ./server.sh start >>"${LOG_FILE}" 2>&1
) >/dev/null 2>&1 &

echo "Scheduled deploy-api restart"
