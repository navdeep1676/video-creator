#!/usr/bin/env bash
# Start stack with live reload (API --reload, Vite HMR, Celery watchfiles).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/docker"

export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml:docker-compose.dev.yml}"
# Load repo-root .env for FAL_KEY / REPLICATE_API_TOKEN / etc.
ENV_FILE_ARGS=()
if [[ -f "$ROOT/.env" ]]; then
  ENV_FILE_ARGS=(--env-file "$ROOT/.env")
fi

echo "Starting Docker with hot reload (COMPOSE_FILE=$COMPOSE_FILE)"
docker compose "${ENV_FILE_ARGS[@]}" up --build "$@"
