#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:-affiliations}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATUS_FILE="${HERE}/data/migration_status.json"

echo "Iniciando rollback para el dominio: ${DOMAIN}"

if [ "${DOMAIN}" = "affiliations" ] || [ "${DOMAIN}" = "afiliaciones" ]; then
    mkdir -p "${HERE}/data"
    cat > "${STATUS_FILE}" << 'EOF'
{
  "domains": {
    "affiliations": "LEGACY",
    "retirements": "LEGACY",
    "companies": "LEGACY"
  }
}
EOF
    echo "Dominio ${DOMAIN} devuelto a LEGACY exitosamente."
    exit 0
else
    echo "Dominio desconocido: ${DOMAIN}" >&2
    exit 1
fi
