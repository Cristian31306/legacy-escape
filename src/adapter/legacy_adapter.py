"""Adapter legacy para desacoplar el acceso a la base de datos PostgreSQL heredada.

REGLA ESTRICTA DE ARQUITECTURA (GE01):
Este archivo es el ÚNICO lugar del repositorio donde pueden residir los identificadores
del esquema heredado (AFI_MAE, NRO_DOC, EST_AFI, LOGMOV, sp_registrar_retiro, COD_EMP, etc.).
Todos los métodos retornan o reciben el Modelo Canónico del sistema.
"""

import os
import logging
from contextlib import contextmanager
from typing import Optional, Dict, List, Any
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.environ.get("LEGACY_DB_HOST", "localhost"),
    "port": int(os.environ.get("LEGACY_DB_PORT", 5432)),
    "dbname": os.environ.get("POSTGRES_DB", "legacy"),
    "user": os.environ.get("POSTGRES_USER", "legacy"),
    "password": os.environ.get("POSTGRES_PASSWORD", "legacy"),
    "connect_timeout": 2,
}


@contextmanager
def get_db_connection():
    """Context manager para obtener conexiones seguras con timeout."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def check_legacy_health() -> bool:
    """Verifica si la base de datos legacy responde en menos de 2 segundos."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone() is not None
    except Exception as exc:
        logger.warning(f"Error de salud contra legacy-db: {exc}")
        return False


def resolve_schema() -> Dict[str, str]:
    """Detecta dinámicamente si el esquema fue migrado por schema-change.sh.
    
    Soporta tanto el esquema inicial (AFI_MAE) como el renombrado (PERSON_MASTER).
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = {row[0].lower() for row in cur.fetchall()}

    if "person_master" in tables:
        return {
            "member_table": "person_master",
            "doc_column": "document_number",
            "status_column": "status_code",
            "ben_table": "afi_ben",
            "ben_doc_column": "nro_doc",
            "ben_id_column": "nro_doc_ben",
            "ben_relation_column": "cod_par",
            "company_table": "empresa",
            "company_id_column": "cod_emp",
            "company_name_column": "nom_emp",
        }
    else:
        return {
            "member_table": "afi_mae",
            "doc_column": "nro_doc",
            "status_column": "est_afi",
            "ben_table": "afi_ben",
            "ben_doc_column": "nro_doc",
            "ben_id_column": "nro_doc_ben",
            "ben_relation_column": "cod_par",
            "company_table": "empresa",
            "company_id_column": "cod_emp",
            "company_name_column": "nom_emp",
        }


def get_member(document: str) -> Optional[Dict[str, Any]]:
    """Consulta un afiliado por documento y lo traduce al modelo canónico."""
    s = resolve_schema()
    query = f"""
        SELECT 
            m.{s['doc_column']} AS doc,
            m.nom1, m.nom2, m.ape1, m.ape2,
            m.{s['status_column']} AS est,
            m.cod_emp,
            e.{s['company_name_column']} AS nom_emp
        FROM {s['member_table']} m
        LEFT JOIN {s['company_table']} e ON e.{s['company_id_column']} = m.cod_emp
        WHERE m.{s['doc_column']} = %s
    """
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (document,))
            row = cur.fetchone()

    if not row:
        return None

    status_raw = str(row["est"]).strip().upper()
    status_map = {
        "A": "ACTIVE",
        "ACTIVE": "ACTIVE",
        "R": "RETIRED",
        "RETIRED": "RETIRED",
        "S": "SUSPENDED",
        "SUSPENDED": "SUSPENDED",
    }
    status = status_map.get(status_raw, "ACTIVE")

    names = [row["nom1"], row["nom2"], row["ape1"], row["ape2"]]
    full_name = " ".join(part.strip() for part in names if part and str(part).strip())

    return {
        "document": str(row["doc"]),
        "fullName": full_name,
        "status": status,
        "company": {
            "id": str(row["cod_emp"] or ""),
            "name": str(row["nom_emp"] or ""),
        },
    }


def get_beneficiaries(document: str) -> List[Dict[str, str]]:
    """Consulta los beneficiarios de un afiliado y traduce los parentescos."""
    s = resolve_schema()
    query = f"""
        SELECT 
            b.{s['ben_id_column']} AS doc_ben,
            b.nom1, b.nom2, b.ape1, b.ape2,
            b.{s['ben_relation_column']} AS rel
        FROM {s['ben_table']} b
        WHERE b.{s['ben_doc_column']} = %s
        ORDER BY b.{s['ben_id_column']} ASC
    """
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (document,))
            rows = cur.fetchall()

    rel_map = {
        "C": "CONYUGE",
        "H": "HIJO",
        "P": "PADRE",
        "M": "MADRE",
        "CONYUGE": "CONYUGE",
        "HIJO": "HIJO",
        "PADRE": "PADRE",
        "MADRE": "MADRE",
    }

    result = []
    for r in rows:
        names = [r["nom1"], r["nom2"], r["ape1"], r["ape2"]]
        full_name = " ".join(part.strip() for part in names if part and str(part).strip())
        rel_raw = str(r["rel"]).strip().upper()
        result.append({
            "document": str(r["doc_ben"]),
            "fullName": full_name,
            "relationship": rel_map.get(rel_raw, "HIJO"),
        })
    return result


def get_company(company_id: str) -> Optional[Dict[str, Any]]:
    """Consulta una empresa y calcula el conteo de miembros activos."""
    s = resolve_schema()
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"""
                SELECT {s['company_id_column']} AS id, {s['company_name_column']} AS name
                FROM {s['company_table']}
                WHERE {s['company_id_column']} = %s
            """, (company_id,))
            company_row = cur.fetchone()

            if not company_row:
                return None

            cur.execute(f"""
                SELECT COUNT(*) AS total
                FROM {s['member_table']}
                WHERE cod_emp = %s 
                  AND ({s['status_column']} = 'A' OR UPPER({s['status_column']}) = 'ACTIVE')
            """, (company_id,))
            count_row = cur.fetchone()
            active_members = int(count_row["total"]) if count_row else 0

    return {
        "id": str(company_row["id"]),
        "name": str(company_row["name"]),
        "activeMembers": active_members,
    }


def retire_member(document: str, date: str, reason: str, user: str = "SUBSIDIOS") -> int:
    """Registra el retiro invocando el procedimiento almacenado legacy."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sp_registrar_retiro(%s, %s, %s, %s)",
                (document, date, reason, user),
            )
            row = cur.fetchone()
            mov_id = row[0] if row else 0
        conn.commit()
    return mov_id
