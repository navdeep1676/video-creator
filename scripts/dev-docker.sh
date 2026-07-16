#!/usr/bin/env bash
# Start stack with live reload (API --reload, Vite HMR, Celery watchfiles).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/docker"

export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml:docker-compose.dev.yml}"

echo "Starting Docker with hot reload (COMPOSE_FILE=$COMPOSE_FILE)"
docker compose up --build "$@"
