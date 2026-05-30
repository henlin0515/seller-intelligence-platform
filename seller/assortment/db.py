from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "assortment.db"


class Base(DeclarativeBase):
    pass


def get_database_url() -> str:
    explicit = os.getenv("ASSORTMENT_DATABASE_URL", "").strip()
    if explicit:
        return explicit
    path = Path(os.getenv("ASSORTMENT_DB_PATH", str(DEFAULT_DB_PATH)))
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


_engine = None
SessionLocal = None


def get_engine():
    global _engine, SessionLocal
    if _engine is None:
        _engine = create_engine(
            get_database_url(),
            connect_args={"check_same_thread": False} if get_database_url().startswith("sqlite") else {},
        )

        @event.listens_for(_engine, "connect")
        def _sqlite_pragma(dbapi_conn, _):
            if get_database_url().startswith("sqlite"):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def init_assortment_db() -> None:
    """Create tables if missing. Safe to call on app startup."""
    from seller.assortment import models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def get_session():
    get_engine()
    return SessionLocal()
