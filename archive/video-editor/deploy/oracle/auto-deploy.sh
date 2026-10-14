#!/usr/bin/env bash

set -Eeuo pipefail

REPO_DIR="${COLORCHECK_REPO_DIR:-/home/ubuntu/colorcheck}"
BRANCH="${COLORCHECK_DEPLOY_BRANCH:-main}"
GITHUB_REPOSITORY="${COLORCHECK_GITHUB_REPOSITORY:-adeshp32/colorcheck}"
STATE_DIR="${COLORCHECK_DEPLOY_STATE_DIR:-${REPO_DIR}/.deploy-state}"
DEPLOYED_FILE="${STATE_DIR}/deployed-commit"

log() {
  printf '[colorcheck-deploy] %s\n' "$*"
}

container_health() {
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1" 2>/dev/null || true
}

wait_for_healthy() {
  local container_id="$1"
  local attempts="${2:-60}"
  local status
  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    status="$(container_health "${container_id}")"
    if [[ "${status}" == "healthy" ]]; then
      return 0
    fi
    if [[ "${status}" == "unhealthy" || "${status}" == "exited" || "${status}" == "dead" ]]; then
      return 1
    fi
    sleep 2
  done
  return 1
}

ci_passed() {
  local commit="$1"
  local payload
  if ! payload="$(curl -fsSL \
    -H 'Accept: application/vnd.github+json' \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    "https://api.github.com/repos/${GITHUB_REPOSITORY}/commits/${commit}/check-runs")"; then
    log "GitHub CI status is unavailable; deployment will be retried."
    return 1
  fi
  CHECK_RUNS_PAYLOAD="${payload}" python3 - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["CHECK_RUNS_PAYLOAD"])
runs = [run for run in payload.get("check_runs", []) if run.get("name") == "test"]
if not runs:
    sys.exit(1)
if any(run.get("status") != "completed" for run in runs):
    sys.exit(1)
if any(run.get("conclusion") != "success" for run in runs):
    sys.exit(2)
PY
}

mkdir -p "${STATE_DIR}"
exec 9>"${STATE_DIR}/deploy.lock"
if ! flock -n 9; then
  log "Another deployment is already running."
  exit 0
fi

cd "${REPO_DIR}"
if ! git diff --quiet || ! git diff --cached --quiet; then
  log "Working tree has tracked changes; automatic deployment was skipped."
  exit 0
fi

current_commit="$(git rev-parse HEAD)"
git fetch --quiet origin "${BRANCH}"
remote_commit="$(git rev-parse "origin/${BRANCH}")"
deployed_commit="$(cat "${DEPLOYED_FILE}" 2>/dev/null || true)"
if [[ "${remote_commit}" == "${deployed_commit}" ]]; then
  exit 0
fi

if ! ci_passed "${remote_commit}"; then
  log "Commit ${remote_commit:0:12} is waiting for successful CI."
  exit 0
fi

if ! git merge-base --is-ancestor "${current_commit}" "${remote_commit}"; then
  log "Local history cannot fast-forward to origin/${BRANCH}; deployment was skipped."
  exit 0
fi

log "Preparing commit ${remote_commit:0:12}."
if [[ "${current_commit}" != "${remote_commit}" ]]; then
  git merge --ff-only "origin/${BRANCH}"
fi

candidate_image="colorcheck:${remote_commit:0:12}"
smoke_name="colorcheck-smoke-${remote_commit:0:12}"
VCC_IMAGE="${candidate_image}" docker compose --profile public build app

docker rm -f "${smoke_name}" >/dev/null 2>&1 || true
smoke_id="$(docker run --detach \
  --name "${smoke_name}" \
  --network none \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=32m,mode=1777 \
  --tmpfs /app/storage:rw,noexec,nosuid,size=32m,mode=1777 \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  "${candidate_image}")"

cleanup_smoke() {
  docker rm -f "${smoke_name}" >/dev/null 2>&1 || true
}
trap cleanup_smoke EXIT

if ! wait_for_healthy "${smoke_id}" 60; then
  log "Candidate health check failed."
  docker logs --tail 40 "${smoke_name}" || true
  exit 1
fi
cleanup_smoke
trap - EXIT

live_id="$(docker compose --profile public ps -q app)"
previous_image=""
if [[ -n "${live_id}" ]]; then
  previous_image="$(docker inspect --format '{{.Image}}' "${live_id}")"
  docker tag "${previous_image}" colorcheck:rollback
fi

docker tag "${candidate_image}" colorcheck:local
if ! docker compose --profile public up --detach --no-deps app; then
  log "Container replacement failed; restoring the previous image tag."
  if [[ -n "${previous_image}" ]]; then
    docker tag "${previous_image}" colorcheck:local
    docker compose --profile public up --detach --no-deps app || true
  fi
  exit 1
fi
new_live_id="$(docker compose --profile public ps -q app)"
if [[ -z "${new_live_id}" ]] || ! wait_for_healthy "${new_live_id}" 60; then
  log "Live health check failed; restoring the previous image."
  if [[ -n "${previous_image}" ]]; then
    docker tag "${previous_image}" colorcheck:local
    docker compose --profile public up --detach --no-deps app
  fi
  exit 1
fi

printf '%s\n' "${remote_commit}" >"${DEPLOYED_FILE}"
docker image rm "${candidate_image}" >/dev/null 2>&1 || true
log "Commit ${remote_commit:0:12} is live and healthy."
