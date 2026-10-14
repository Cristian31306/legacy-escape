"""Módulo de Outbox persistente para tolerancia a caídas de la base de datos.

Cuando la base de datos no está disponible, los retiros se encolan
en SQLite y un worker en segundo plano los procesa al recuperarse.
NOTA: Ningún identificador legacy debe escribirse en este archivo.
"""

import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import List, Dict, Any

from src.idempotency import get_sqlite_conn, init_resilience_db, save_retirement_record
from src.adapter import check_legacy_health, retire_member

logger = logging.getLogger(__name__)


def queue_retirement(request_id: str, document: str, retirement_date: str, reason: str):
    """Encola un retiro para procesamiento asíncrono diferido."""
    init_resilience_db()
    with get_sqlite_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO retirement_outbox 
            (request_id, document, retirement_date, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            request_id,
            document,
            retirement_date,
            reason,
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
    # Marcamos en requests como ACCEPTED
    save_retirement_record(
        request_id=request_id,
        document=document,
        retirement_date=retirement_date,
        reason=reason,
        status="ACCEPTED",
        movement_id=None,
    )
    logger.info(f"Retiro encolado en outbox: request_id={request_id}")


def get_pending_outbox() -> List[Dict[str, Any]]:
    init_resilience_db()
    with get_sqlite_conn() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM retirement_outbox ORDER BY created_at ASC")
        return [dict(r) for r in cur.fetchall()]


def remove_from_outbox(request_id: str):
    with get_sqlite_conn() as conn:
        conn.execute("DELETE FROM retirement_outbox WHERE request_id = ?", (request_id,))
        conn.commit()


def process_outbox_queue():
    """Intenta procesar todos los retiros pendientes si la base está arriba."""
    if not check_legacy_health():
        return

    items = get_pending_outbox()
    for item in items:
        try:
            mov_id = retire_member(
                document=item["document"],
                date=item["retirement_date"],
                reason=item["reason"],
            )
            save_retirement_record(
                request_id=item["request_id"],
                document=item["document"],
                retirement_date=item["retirement_date"],
                reason=item["reason"],
                status="COMPLETED",
                movement_id=mov_id,
            )
            remove_from_outbox(item["request_id"])
            logger.info(f"Retiro de outbox aplicado con éxito: request_id={item['request_id']} mov_id={mov_id}")
        except Exception as exc:
            logger.error(f"Fallo al procesar item de outbox {item['request_id']}: {exc}")


def start_outbox_worker(interval_seconds: int = 2):
    """Inicia hilo de segundo plano para procesar la cola outbox."""
    def _worker():
        while True:
            time.sleep(interval_seconds)
            try:
                process_outbox_queue()
            except Exception as e:
                logger.warning(f"Excepción en outbox worker: {e}")

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread
