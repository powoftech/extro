from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from extro.core.paths import database_path

if TYPE_CHECKING:
    from collections.abc import Iterator


def sqlite_url(path: Path | None = None) -> str:
    db_path = (path or database_path()).resolve()
    return str(URL.create("sqlite", database=str(db_path)))


def create_db_engine(path: Path | None = None) -> Engine:
    return create_engine(sqlite_url(path), future=True)


def create_session_factory(path: Path | None = None) -> sessionmaker[Session]:
    return sessionmaker(create_db_engine(path), expire_on_commit=False)


def alembic_config(path: Path | None = None) -> Config:
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", sqlite_url(path))
    return cfg


def upgrade_database(path: Path | None = None) -> None:
    db_path = (path or database_path()).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(db_path), "head")


@contextmanager
def session_scope(path: Path | None = None) -> Iterator[Session]:
    factory = create_session_factory(path)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
