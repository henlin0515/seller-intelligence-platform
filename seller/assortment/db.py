from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
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


def _migrate_sqlite_columns(engine) -> None:
    """Add shop-level columns to existing SQLite DBs (non-destructive)."""
    if not get_database_url().startswith("sqlite"):
        return
    migrations = [
        ("assortment_competitor_products", "platform", "VARCHAR(16) DEFAULT 'tiktok'"),
        ("assortment_competitor_products", "competitor_shop_name", "VARCHAR(255)"),
        ("assortment_competitor_products", "listed_at", "DATETIME"),
        ("assortment_product_matches", "competitor_shop_id", "VARCHAR(64)"),
        ("assortment_product_matches", "shopee_product_id", "INTEGER"),
        ("assortment_product_matches", "tiktok_product_id", "INTEGER"),
    ]
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, col, col_type in migrations:
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            if col in existing:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))


def init_assortment_db() -> None:
    """Create tables if missing. Safe to call on app startup."""
    from seller.assortment import models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_columns(engine)


def get_session():
    get_engine()
    return SessionLocal()
