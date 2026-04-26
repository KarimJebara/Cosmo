"""SQLAlchemy engine and session factory.

The engine is process-global; sessions are short-lived and obtained via
``get_session()``. SQLite gets ``foreign_keys=ON`` via a connect-time pragma
so FK constraints actually fire.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from cosmo.config import CONFIG


def _make_engine(url: str) -> Engine:
    connect_args = {"timeout": 10} if url.startswith("sqlite") else {}
    engine = create_engine(url, future=True, connect_args=connect_args)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_fk(dbapi_conn, _conn_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.close()

    return engine


engine: Engine = _make_engine(CONFIG.database_url)
SessionFactory: sessionmaker[Session] = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, future=True
)


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a session and commit on success, rollback on error."""
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
