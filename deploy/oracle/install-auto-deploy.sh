#!/usr/bin/env bash

set -Eeuo pipefail

REPO_DIR="$(git rev-parse --show-toplevel)"
RUN_USER="$(id -un)"
RUN_GROUP="$(id -gn)"
TEMPLATE="${REPO_DIR}/deploy/oracle/colorcheck-auto-deploy.service.in"
SERVICE_NAME="colorcheck-auto-deploy.service"
TIMER_NAME="colorcheck-auto-deploy.timer"
TEMP_SERVICE="$(mktemp)"

cleanup() {
  rm -f "${TEMP_SERVICE}"
}
trap cleanup EXIT

escape_sed() {
  printf '%s' "$1" | sed 's/[&|]/\\&/g'
}

sed \
  -e "s|__USER__|$(escape_sed "${RUN_USER}")|g" \
  -e "s|__GROUP__|$(escape_sed "${RUN_GROUP}")|g" \
  -e "s|__REPO_DIR__|$(escape_sed "${REPO_DIR}")|g" \
  "${TEMPLATE}" >"${TEMP_SERVICE}"

chmod +x "${REPO_DIR}/deploy/oracle/auto-deploy.sh"
sudo install -m 0644 "${TEMP_SERVICE}" "/etc/systemd/system/${SERVICE_NAME}"
sudo install -m 0644 \
  "${REPO_DIR}/deploy/oracle/${TIMER_NAME}" \
  "/etc/systemd/system/${TIMER_NAME}"
sudo systemctl daemon-reload
sudo systemctl enable --now "${TIMER_NAME}"

printf 'Automatic deployment installed. Timer status:\n'
sudo systemctl status "${TIMER_NAME}" --no-pager
