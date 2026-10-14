"""Módulo de persistencia local e idempotencia de retiros (SQLite).

Garantiza que peticiones repetidas con el mismo requestId no dupliquen
la operación y devuelvan el código esperado de idempotencia.
NOTA: Ningún identificador legacy debe escribirse en este archivo.
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any

DB_PATH = os.environ.get("RESILIENCE_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "resilience.db"))


def get_sqlite_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_resilience_db():
    """Inicializa las tablas para idempotencia y outbox."""
    with get_sqlite_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS retirement_requests (
                request_id TEXT PRIMARY KEY,
                document TEXT NOT NULL,
                retirement_date TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL,
                movement_id INTEGER,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS retirement_outbox (
                request_id TEXT PRIMARY KEY,
                document TEXT NOT NULL,
                retirement_date TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()


def check_idempotency(request_id: str) -> Optional[Dict[str, Any]]:
    """Verifica si un requestId ya fue procesado o registrado."""
    init_resilience_db()
    with get_sqlite_conn() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM retirement_requests WHERE request_id = ?", (request_id,))
        row = cur.fetchone()
        if row:
            return dict(row)
    return None


def save_retirement_record(
    request_id: str,
    document: str,
    retirement_date: str,
    reason: str,
    status: str = "COMPLETED",
    movement_id: Optional[int] = None,
):
    """Registra la solicitud procesada para evitar duplicidad."""
    init_resilience_db()
    with get_sqlite_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO retirement_requests 
            (request_id, document, retirement_date, reason, status, movement_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            request_id,
            document,
            retirement_date,
            reason,
            status,
            movement_id,
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
