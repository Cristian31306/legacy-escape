"""Middleware de auditoría para registrar cada petición en logs/audit.log.

Regla G12:
- Formato: una línea JSON por cada petición HTTP recibida.
- Campos obligatorios: timestamp, consumer, endpoint, status, latency_ms.
- El documento del afiliado en la URL DEBE quedar enmascarado (máximo 4 dígitos visibles).
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

LOG_DIR = os.environ.get("LOG_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"))
AUDIT_LOG_FILE = os.path.join(LOG_DIR, "audit.log")


def mask_endpoint(path: str) -> str:
    """Enmascara cualquier número de documento presente en la ruta HTTP.
    
    Por ejemplo: /api/v1/members/1019282447 -> /api/v1/members/******2447
    Garantiza que ninguna cédula completa quede expuesta en logs/audit.log.
    """
    def _mask_doc(match):
        digits = match.group(1)
        if len(digits) > 4:
            return f"/members/{'*' * (len(digits) - 4)}{digits[-4:]}"
        return f"/members/{'*' * len(digits)}"

    # Enmascara documento en /members/<documento>
    masked = re.sub(r"/members/(\d+)", _mask_doc, path)
    return masked


def write_audit_log(entry: dict):
    """Escribe de manera segura una línea JSON en logs/audit.log."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
    except Exception as exc:
        pass


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Procesar la petición
        response = await call_next(request)
        
        latency_ms = round((time.time() - start_time) * 1000.0, 2)
        
        # Determinar el consumidor
        consumer = getattr(request.state, "consumer", None)
        if not consumer:
            auth_header = request.headers.get("Authorization", "")
            if "Bearer " in auth_header:
                token = auth_header.split(" ", 1)[1].strip()
                tokens = {
                    os.environ.get("PORTAL_TOKEN", "portal-token"): "portal",
                    os.environ.get("SUBSIDIOS_TOKEN", "subsidios-token"): "subsidios",
                    os.environ.get("MOBILE_TOKEN", "mobile-token"): "mobile",
                }
                consumer = tokens.get(token, "unknown")
            else:
                consumer = "portal" if request.url.path.startswith("/api/v1/companies") else "anonymous"

        # Registrar la entrada en audit.log
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "consumer": consumer,
            "endpoint": mask_endpoint(request.url.path),
            "status": response.status_code,
            "latency_ms": latency_ms,
        }
        write_audit_log(audit_entry)
        
        return response
