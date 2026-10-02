"""Lightweight schema versioning / migrations."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import Base, SchemaVersion
from src.utils.logging import get_logger

CURRENT_SCHEMA_VERSION = 2

logger = get_logger("migrations")


def make_engine(database_path: Path) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(url, future=True)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def get_schema_version(session: Session) -> int:
    if not _table_exists(session, "schema_version"):
        return 0
    row = (
        session.execute(select(SchemaVersion).order_by(SchemaVersion.version.desc()))
        .scalars()
        .first()
    )
    return int(row.version) if row else 0


def _table_exists(session: Session, name: str) -> bool:
    result = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": name},
    ).scalar_one_or_none()
    return result is not None


def run_migrations(engine: Engine) -> int:
    """Create or upgrade the schema. Returns the applied version."""
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        version = get_schema_version(session)
        if version < 1:
            session.merge(SchemaVersion(version=1))
            session.commit()
            version = 1
            logger.info("Applied schema version 1")
        if version < 2:
            # Additive: existing track IDs, playlists and download history stay intact.
            columns = {column["name"] for column in inspect(engine).get_columns("tracks")}
            if "bpm" not in columns:
                session.execute(text("ALTER TABLE tracks ADD COLUMN bpm FLOAT"))
            session.merge(SchemaVersion(version=2))
            session.commit()
            version = 2
            logger.info("Applied schema version 2 (BPM)")
        return version
