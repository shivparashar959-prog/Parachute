"""SQLAlchemy engine and request-scoped database session dependency."""

from functools import lru_cache
from typing import Generator

from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import ConfigurationError, require_database_url


@lru_cache(maxsize=4)
def _session_factory(database_url: str) -> sessionmaker[Session]:
    engine_options = {"pool_pre_ping": True}
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        engine_options.update(
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    engine = create_engine(database_url, **engine_options)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    try:
        database_url = require_database_url()
        factory = _session_factory(database_url)
    except ConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured.",
        ) from exc

    db = factory()
    try:
        yield db
    finally:
        db.close()
