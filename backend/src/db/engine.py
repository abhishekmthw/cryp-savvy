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
    return create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,   # detect dropped connections (Supabase pooler closes idle ones)
        pool_size=5,
        max_overflow=10,
        future=True,
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
