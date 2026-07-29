"""Database connection helper for the local Postgres+pgvector instance."""

import psycopg

from observatory.config import get_settings


def get_conn() -> psycopg.Connection:
    """Open a new connection to Postgres. Use inside a ``with`` block."""
    return psycopg.connect(get_settings().database_url)
