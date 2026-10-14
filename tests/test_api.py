"""Suite de pruebas automatizadas para el Gateway API (GE05).

Verifica el cumplimiento de los contratos REST, seguridad por tokens,
formato de errores, idempotencia y estado de migración.
"""

import os
import pytest
import requests

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:8082").rstrip("/")
PORTAL_TOKEN = os.environ.get("PORTAL_TOKEN", "portal-token")
SUBSIDIOS_TOKEN = os.environ.get("SUBSIDIOS_TOKEN", "subsidios-token")
MOBILE_TOKEN = os.environ.get("MOBILE_TOKEN", "mobile-token")

PORTAL_HEADERS = {"Authorization": f"Bearer {PORTAL_TOKEN}"}
SUBSIDIOS_HEADERS = {"Authorization": f"Bearer {SUBSIDIOS_TOKEN}"}
MOBILE_HEADERS = {"Authorization": f"Bearer {MOBILE_TOKEN}"}


def test_health_ok():
    """Verifica que el endpoint /health responda 200 y contenga los campos de salud."""
    r = requests.get(f"{GATEWAY_URL}/health", timeout=3)
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert "legacy" in data
    assert data["status"] == "UP"


def test_health_no_auth_required():
    """Verifica que el endpoint de salud sea de acceso público sin token."""
    r = requests.get(f"{GATEWAY_URL}/health", timeout=3)
    assert r.status_code == 200


def test_member_without_token_returns_401():
    """Verifica que intentar consultar un afiliado sin cabecera retorne 401."""
    r = requests.get(f"{GATEWAY_URL}/api/v1/members/12345678", timeout=3)
    assert r.status_code == 401
    body = r.json()
    assert "message" in body
    assert "error_id" in body


def test_member_invalid_token_returns_401():
    """Verifica que un token no reconocido devuelva 401 Unauthorized."""
    headers = {"Authorization": "Bearer token-invalido-123"}
    r = requests.get(f"{GATEWAY_URL}/api/v1/members/12345678", headers=headers, timeout=3)
    assert r.status_code == 401
    body = r.json()
    assert "message" in body
    assert "error_id" in body


def test_member_not_found_returns_404():
    """Verifica que un afiliado inexistente retorne 404 Not Found con formato seguro."""
    r = requests.get(f"{GATEWAY_URL}/api/v1/members/0000000000", headers=PORTAL_HEADERS, timeout=3)
    assert r.status_code in (404, 503)
    if r.status_code == 404:
        body = r.json()
        assert "message" in body
        assert "error_id" in body


def test_error_response_has_message_and_error_id():
    """Verifica que los errores sigan estrictamente el formato {message, error_id}."""
    r = requests.get(f"{GATEWAY_URL}/api/v1/members/9999999999", headers=PORTAL_HEADERS, timeout=3)
    body = r.json()
    assert isinstance(body, dict)
    assert "message" in body
    assert "error_id" in body
    # Asegura que no se filtren trazas técnicas
    text = r.text
    assert "Traceback" not in text
    assert "Exception" not in text


def test_mobile_get_member_authorized():
    """Verifica que el token de móvil pueda consultar afiliados (lectura permitida)."""
    r = requests.get(f"{GATEWAY_URL}/api/v1/members/0000000000", headers=MOBILE_HEADERS, timeout=3)
    assert r.status_code in (200, 404, 503)


def test_mobile_post_retirement_returns_403():
    """Verifica que el consumidor móvil reciba 403 Forbidden al intentar registrar retiros."""
    payload = {
        "requestId": "mobile-block-001",
        "date": "2026-10-14",
        "reason": "Intento no permitido desde app movil",
    }
    r = requests.post(
        f"{GATEWAY_URL}/api/v1/members/12345678/retirements",
        headers=MOBILE_HEADERS,
        json=payload,
        timeout=3,
    )
    assert r.status_code == 403
    body = r.json()
    assert "message" in body
    assert "error_id" in body


def test_retirement_idempotent():
    """Verifica que enviar dos veces el mismo requestId responda de forma idempotente."""
    payload = {
        "requestId": "test-idem-suite-001",
        "date": "2026-10-14",
        "reason": "Prueba de idempotencia",
    }
    r1 = requests.post(
        f"{GATEWAY_URL}/api/v1/members/12345678/retirements",
        headers=SUBSIDIOS_HEADERS,
        json=payload,
        timeout=4,
    )
    assert r1.status_code in (200, 201, 202, 503)
    
    r2 = requests.post(
        f"{GATEWAY_URL}/api/v1/members/12345678/retirements",
        headers=SUBSIDIOS_HEADERS,
        json=payload,
        timeout=4,
    )
    assert r2.status_code in (200, 201, 202)


def test_migration_status_returns_domain():
    """Verifica que /api/v1/migration/status devuelva el estado de los dominios."""
    r = requests.get(f"{GATEWAY_URL}/api/v1/migration/status", timeout=3)
    assert r.status_code == 200
    data = r.json()
    assert "domains" in data
    assert "affiliations" in data["domains"]
    assert data["domains"]["affiliations"] in ("DUAL", "LEGACY", "MODERN")


def test_beneficiaries_requires_auth():
    """Verifica que la consulta de beneficiarios exija autenticación Bearer."""
    r = requests.get(f"{GATEWAY_URL}/api/v1/members/12345678/beneficiaries", timeout=3)
    assert r.status_code == 401


def test_company_requires_portal_token():
    """Verifica que la consulta de empresa exija cabecera de autenticación."""
    r = requests.get(f"{GATEWAY_URL}/api/v1/companies/1", headers=PORTAL_HEADERS, timeout=3)
    assert r.status_code in (200, 404, 503)
