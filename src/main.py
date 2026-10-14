"""Gateway API principal para desacoplamiento y transición del sistema legacy.

Toda la lógica de integración con la base de datos reside estrictamente en src.adapter.
"""

import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.auth import authenticate_consumer
from src.audit import AuditMiddleware
from src.adapter import (
    check_legacy_health,
    get_member,
    get_beneficiaries,
    get_company,
    retire_member,
)
from src.idempotency import init_resilience_db, check_idempotency, save_retirement_record
from src.outbox import queue_retirement, start_outbox_worker


STATUS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "migration_status.json",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base SQLite de resiliencia y el worker de fondo del outbox."""
    init_resilience_db()
    start_outbox_worker(interval_seconds=2)
    yield


app = FastAPI(
    title="Legacy Escape Gateway API",
    version="1.0.0",
    lifespan=lifespan,
)

# Registrar middleware de auditoría
app.add_middleware(AuditMiddleware)


# ---------------------------------------------------------
# Manejo Global de Errores (G06: Sin SQL ni trazas de código)
# ---------------------------------------------------------
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        content = exc.detail
        if "error_id" not in content:
            content["error_id"] = str(uuid.uuid4())
        if "message" not in content:
            content["message"] = "Ocurrió un error en la solicitud"
    else:
        content = {
            "message": str(exc.detail),
            "error_id": str(uuid.uuid4()),
        }
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={
            "message": "Parámetros o cuerpo de la petición inválidos",
            "error_id": str(uuid.uuid4()),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "message": "Error interno del servidor",
            "error_id": str(uuid.uuid4()),
        },
    )


# ---------------------------------------------------------
# Modelos de entrada canónicos
# ---------------------------------------------------------
class RetirementPayload(BaseModel):
    requestId: str = Field(..., description="Identificador único para idempotencia")
    date: str = Field(..., description="Fecha de retiro en formato YYYY-MM-DD")
    reason: Optional[str] = Field("RETIRO", description="Motivo del retiro")


# ---------------------------------------------------------
# Rutas del Contrato Oficial
# ---------------------------------------------------------

@app.get("/health")
def health_check():
    """Ruta pública de verificación de salud del gateway y del legacy (G01)."""
    legacy_up = check_legacy_health()
    return {
        "status": "UP",
        "legacy": "UP" if legacy_up else "DOWN",
    }


@app.get("/api/v1/members/{document}")
def get_member_endpoint(
    document: str,
    consumer: str = Depends(authenticate_consumer),
):
    """Consulta canónica de afiliado por número de documento (G02, G05, G06)."""
    try:
        member = get_member(document)
    except Exception:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LEGACY_UNAVAILABLE",
                "message": "Base de datos legacy no disponible",
                "error_id": str(uuid.uuid4()),
            },
        )

    if not member:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Afiliado no encontrado",
                "error_id": str(uuid.uuid4()),
            },
        )
    return member


@app.get("/api/v1/members/{document}/beneficiaries")
def get_beneficiaries_endpoint(
    document: str,
    consumer: str = Depends(authenticate_consumer),
):
    """Lista canónica de beneficiarios asociados a un afiliado (G03, G05)."""
    try:
        beneficiaries = get_beneficiaries(document)
    except Exception:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LEGACY_UNAVAILABLE",
                "message": "Base de datos legacy no disponible",
                "error_id": str(uuid.uuid4()),
            },
        )
    return beneficiaries


@app.get("/api/v1/companies/{id}")
def get_company_endpoint(
    id: str,
    consumer: str = Depends(authenticate_consumer),
):
    """Consulta de empresa y conteo de afiliados activos (G04, G05)."""
    try:
        company = get_company(id)
    except Exception:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LEGACY_UNAVAILABLE",
                "message": "Base de datos legacy no disponible",
                "error_id": str(uuid.uuid4()),
            },
        )

    if not company:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Empresa no encontrada",
                "error_id": str(uuid.uuid4()),
            },
        )
    return company


@app.post("/api/v1/members/{document}/retirements", status_code=status.HTTP_201_CREATED)
def register_retirement_endpoint(
    document: str,
    body: RetirementPayload,
    consumer: str = Depends(authenticate_consumer),
):
    """Registra un retiro aplicando idempotencia y tolerancia a caídas (G07, G08, G10, G11)."""
    # 1. Idempotencia: Verificar si el requestId ya fue procesado
    existing = check_idempotency(body.requestId)
    if existing:
        return JSONResponse(
            status_code=200,
            content={
                "message": "Petición ya procesada con anterioridad",
                "requestId": body.requestId,
            },
        )

    # 2. Intentar aplicar directamente en PostgreSQL legacy
    try:
        movement_id = retire_member(
            document=document,
            date=body.date,
            reason=body.reason,
            user=consumer.upper(),
        )
        save_retirement_record(
            request_id=body.requestId,
            document=document,
            retirement_date=body.date,
            reason=body.reason,
            status="COMPLETED",
            movement_id=movement_id,
        )
        return JSONResponse(
            status_code=201,
            content={
                "message": "Retiro registrado exitosamente",
                "requestId": body.requestId,
                "movimiento": movement_id,
            },
        )
    except Exception:
        # 3. Tolerancia a caídas: Si PostgreSQL no responde, encolar en Outbox SQLite (G11)
        queue_retirement(
            request_id=body.requestId,
            document=document,
            retirement_date=body.date,
            reason=body.reason,
        )
        return JSONResponse(
            status_code=202,
            content={
                "message": "Base de datos legacy no disponible; solicitud encolada en outbox",
                "requestId": body.requestId,
            },
        )


@app.get("/api/v1/migration/status")
def migration_status_endpoint():
    """Estado de la migración por dominio (G14)."""
    default_state = {
        "domains": {
            "affiliations": "DUAL",
            "retirements": "LEGACY",
            "companies": "LEGACY",
        }
    }
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception:
            pass
    return default_state
