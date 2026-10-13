#!/usr/bin/env bash
# Devuelve el entorno al estado inicial: borra contenedores y volúmenes (la base legacy
# se recarga desde db/init, sin el cambio de esquema). No modifica su código ni su .env.
set -euo pipefail
cd "$(dirname "$0")"
docker compose --profile "*" down -v --remove-orphans
[ -f .env ] || cp .env.example .env
mkdir -p logs
docker compose up -d --build
docker compose ps
