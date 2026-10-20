from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.models import Base
from app.settings import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = get_settings().database_url.get_secret_value()
    return create_engine(
        database_url,
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 8, "prepare_threshold": None},
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def test_database_connection() -> bool:
    """Run a read-only connectivity check without exposing connection details."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise RuntimeError("PostgreSQL connectivity check failed; verify DATABASE_URL and network access") from None
    return True


def create_database_tables() -> None:
    """Verify connectivity, enable pgvector, and create missing ORM tables.

    Use Alembic migrations for ongoing production schema changes. This initializer
    is intended for the first Supabase setup and development environments.
    """
    test_database_connection()
    engine = get_engine()
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(bind=engine)
        return

    test_tables = [table for table in Base.metadata.sorted_tables if table.name != "content_chunks"]
    Base.metadata.create_all(bind=engine, tables=test_tables)


if __name__ == "__main__":
    create_database_tables()
    print("Supabase PostgreSQL schema is ready.")
