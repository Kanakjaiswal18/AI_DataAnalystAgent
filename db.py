"""
db.py
PostgreSQL connection handling and schema introspection for Neon PostgreSQL.
"""

import logging
import time
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from config import PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD, QUERY_TIMEOUT_MS

log = logging.getLogger(__name__)

_schema_cache = {"text": None, "loaded_at": 0.0}
SCHEMA_CACHE_TTL_SECONDS = 60


def init_pool():
    """
    Kept only for compatibility with main.py.
    We no longer use a persistent connection pool because Neon may close
    idle SSL connections.
    """
    log.info(f"Using Neon PostgreSQL ({PG_HOST}:{PG_PORT}/{PG_DB})")


@contextmanager
def get_conn():
    """
    Create a fresh SSL connection for every database operation.
    This is much more reliable with Neon than keeping long-lived pooled
    connections.
    """
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD,
        sslmode="require",
    )

    try:
        yield conn
    finally:
        conn.close()


def get_schema_text(force_refresh: bool = False) -> str:
    """
    Return a compact schema description for the LLM.
    Cached briefly to avoid querying information_schema repeatedly.
    """
    now = time.time()

    if (
        not force_refresh
        and _schema_cache["text"]
        and (now - _schema_cache["loaded_at"] < SCHEMA_CACHE_TTL_SECONDS)
    ):
        return _schema_cache["text"]

    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cur.execute("""
            SELECT
                table_name,
                column_name,
                data_type,
                is_nullable
            FROM information_schema.columns
            WHERE table_schema='public'
            ORDER BY table_name, ordinal_position
        """)

        columns = cur.fetchall()

        cur.execute("""
            SELECT
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
            WHERE
                tc.constraint_type='FOREIGN KEY'
                AND tc.table_schema='public'
        """)

        fks = cur.fetchall()

        cur.close()

    tables = {}

    for row in columns:
        nullable = "" if row["is_nullable"] == "YES" else ", not null"

        tables.setdefault(row["table_name"], []).append(
            f'{row["column_name"]} ({row["data_type"]}{nullable})'
    )

    fk_lines = [
        f'{r["table_name"]}.{r["column_name"]} -> '
        f'{r["foreign_table_name"]}.{r["foreign_column_name"]}'
        for r in fks
    ]

    lines = ["TABLES:"]

    for table, cols in tables.items():
        lines.append(f"- {table}({', '.join(cols)})")

    if fk_lines:
        lines.append("")
        lines.append("FOREIGN KEYS:")
        for fk in fk_lines:
            lines.append(f"- {fk}")

    text = "\n".join(lines)

    _schema_cache["text"] = text
    _schema_cache["loaded_at"] = now

    return text


def run_select(sql: str, max_rows: int):
    """
    Execute a validated SELECT query.
    """

    with get_conn() as conn:
        cur = conn.cursor()

        try:
            cur.execute(f"SET statement_timeout = {QUERY_TIMEOUT_MS}")
            cur.execute(sql)

            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(max_rows)

            conn.commit()

            return columns, rows

        except Exception:
            conn.rollback()
            raise

        finally:
            cur.close()