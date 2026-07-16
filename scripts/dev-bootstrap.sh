#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

cp -n .env.example .env 2>/dev/null || true

echo "Starting stack with docker compose..."
cd docker
docker compose up --build -d
echo "API:      http://localhost:8000/docs"
echo "Frontend: http://localhost:3000"
