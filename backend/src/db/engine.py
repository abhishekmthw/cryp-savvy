"""
SQLAlchemy engine + session factory.

Reads DATABASE_URL from settings (typically a Supabase pooler URL on port 6543).
Use ``with session_scope() as db:`` to get a session that auto-commits on
success and rolls back on exception.
"""

from __future__ import annotations

import sys
import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings


def _make_engine():
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set — refusing to start")

    connect_args: dict = {}
    # Supabase's transaction-mode pooler (Supavisor/PgBouncer, port 6543) routes
    # each transaction to a possibly-different Postgres backend. psycopg3 promotes
    # repeated queries to *server-side* prepared statements (_pg3_N), which then
    # collide or vanish across backends:
    #   "prepared statement _pg3_N already exists" / "... does not exist".
    # Disabling auto-prepare sends every statement inline, which is what the
    # transaction pooler requires. (Only valid for the psycopg v3 driver.)
    if "+psycopg" in settings.DATABASE_URL and "+psycopg2" not in settings.DATABASE_URL:
        connect_args["prepare_threshold"] = None

    return create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,   # detect dropped connections (Supabase pooler closes idle ones)
        pool_size=20,         # raised for multi-user concurrency (front Supabase with PgBouncer)
        max_overflow=20,
        pool_recycle=1800,    # recycle connections before Supabase's idle timeout
        future=True,
        connect_args=connect_args,
    )


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
