from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import Base


def upgrade_schema() -> None:
    """Create the current schema for local development only.

    Production schema changes should be managed with Alembic migrations.
    """
    Base.metadata.create_all(bind=get_engine())


def enable_pgvector(session: Session) -> None:
    session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    session.commit()
