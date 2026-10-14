"""subsidios-app — registra retiros de afiliados (SÍ se puede modificar).

Hoy llama directamente al procedimiento legacy sp_registrar_retiro.
El reto pide que pase a usar el servicio nuevo (gateway) sin perder el camino legacy.

POST /retiros  {"documento": "...", "fecha": "YYYY-MM-DD", "motivo": "..."}  (puerto 8091)
"""

import json
import os
import uuid
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg2

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:8082")
SUBSIDIOS_TOKEN = os.environ.get("SUBSIDIOS_TOKEN", "subsidios-token")
STATUS_FILE = os.environ.get("STATUS_FILE", "/app/data/migration_status.json")


def connect():
    return psycopg2.connect(
        host=os.environ.get("LEGACY_DB_HOST", "legacy-db"),
        port=int(os.environ.get("LEGACY_DB_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "legacy"),
        user=os.environ.get("POSTGRES_USER", "legacy"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        connect_timeout=2,
    )


def registrar_retiro_legacy(documento, fecha, motivo):
    """Procedimiento original directo a PostgreSQL para camino legacy / rollback."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT sp_registrar_retiro(%s, %s, %s, %s)", (documento, fecha, motivo, "SUBSIDIOS"))
            movimiento = cur.fetchone()[0]
        conn.commit()
        return movimiento
    finally:
        conn.close()


def is_affiliations_legacy() -> bool:
    """Verifica si el dominio Afiliaciones fue devuelto a estado LEGACY por rollback.sh."""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("domains", {}).get("affiliations") == "LEGACY"
        except Exception:
            pass
    return False


def registrar_retiro_gateway(documento, fecha, motivo, request_id):
    """Envía el retiro a través del Gateway REST con SUBSIDIOS_TOKEN (G15)."""
    url = f"{GATEWAY_URL.rstrip('/')}/api/v1/members/{documento}/retirements"
    payload = json.dumps({
        "requestId": request_id,
        "date": fecha,
        "reason": motivo,
    }).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SUBSIDIOS_TOKEN}",
    }
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=3) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        return body.get("movimiento", 1)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            modo = "legacy" if is_affiliations_legacy() else "gateway"
            return self._send(200, {"status": "UP", "modo": modo})
        return self._send(404, {"error": "ruta no encontrada"})

    def do_POST(self):
        if self.path != "/retiros":
            return self._send(404, {"error": "ruta no encontrada"})
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length) or b"{}")
        
        doc = str(data.get("documento", "")).strip()
        fecha = str(data.get("fecha", "")).strip()
        motivo = str(data.get("motivo", "RETIRO")).strip()
        req_id = str(data.get("requestId", f"subsidios-{doc}-{uuid.uuid4().hex[:8]}"))

        # 1. Si el dominio está en LEGACY (por rollback.sh), usar el camino directo
        if is_affiliations_legacy():
            try:
                movimiento = registrar_retiro_legacy(doc, fecha, motivo)
                return self._send(201, {"movimiento": movimiento, "via": "legacy_rollback"})
            except psycopg2.Error as exc:
                return self._send(500, {"error": str(exc).strip()})

        # 2. Modo normal: Registrar vía Gateway API (G15)
        try:
            movimiento = registrar_retiro_gateway(doc, fecha, motivo, req_id)
            return self._send(201, {"movimiento": movimiento, "via": "gateway"})
        except Exception:
            # 3. Fallback de resiliencia: Si el gateway no responde, ejecutar camino legacy
            try:
                movimiento = registrar_retiro_legacy(doc, fecha, motivo)
                return self._send(201, {"movimiento": movimiento, "via": "fallback"})
            except psycopg2.Error as exc:
                return self._send(500, {"error": str(exc).strip()})

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8091), Handler).serve_forever()
