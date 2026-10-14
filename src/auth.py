"""Módulo de autenticación y autorización por roles para el Gateway API.

Valida tokens Bearer contra variables de entorno del sistema:
- PORTAL_TOKEN -> rol: portal
- SUBSIDIOS_TOKEN -> rol: subsidios
- MOBILE_TOKEN -> rol: mobile

Regla G05:
- Petición sin token o token inválido -> 401
- Rol 'mobile' intentando escribir (POST) -> 403
"""

import os
import uuid
from typing import Optional
from fastapi import Header, HTTPException, Request


def get_expected_tokens():
    return {
        os.environ.get("PORTAL_TOKEN", "portal-token"): "portal",
        os.environ.get("SUBSIDIOS_TOKEN", "subsidios-token"): "subsidios",
        os.environ.get("MOBILE_TOKEN", "mobile-token"): "mobile",
    }


def authenticate_consumer(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> str:
    """Valida la cabecera Authorization: Bearer <token> y retorna el rol del consumidor."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Cabecera de autenticación ausente o formato inválido",
                "error_id": str(uuid.uuid4()),
            },
        )

    token = authorization.split(" ", 1)[1].strip()
    valid_tokens = get_expected_tokens()

    consumer = valid_tokens.get(token)
    if not consumer:
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Token de autenticación inválido o no reconocido",
                "error_id": str(uuid.uuid4()),
            },
        )

    # Si es móvil e intenta escribir (POST), lanzar 403 Forbidden
    if consumer == "mobile" and request.method.upper() == "POST":
        raise HTTPException(
            status_code=403,
            detail={
                "message": "El consumidor móvil no tiene permisos para registrar retiros",
                "error_id": str(uuid.uuid4()),
            },
        )

    # Adjuntamos el consumidor al estado de la petición para el middleware de auditoría
    request.state.consumer = consumer
    return consumer
