"""
Fintelligence — Shared Database + Redis Utilities
==================================================
SINGLE SOURCE OF TRUTH for engine creation.
Mounted read-only into all 4 backend containers via docker-compose volume.

Usage in each backend:
    from db_utils import make_engine, make_redis, get_db
"""
import os
import logging
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
import redis as _redis

log = logging.getLogger("fintelligence.db_utils")


def make_engine(schema_prefix: str = ""):
    """
    Create a PostgreSQL SQLAlchemy engine from DATABASE_URL env var.
    Falls back to SQLite for local dev if DATABASE_URL starts with 'sqlite'.

    Args:
        schema_prefix: reserved for future schema-per-tenant migration path
    """
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Expected: postgresql://user:pass@host:5432/dbname"
        )

    is_sqlite = url.startswith("sqlite")

    if is_sqlite:
        # Local dev fallback — warn loudly
        log.warning(
            "DATABASE_URL points to SQLite. "
            "This is fine for local dev but NOT for production. "
            "Set DATABASE_URL to a PostgreSQL connection string."
        )
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30},
            pool_pre_ping=True,
        )
        # Enable WAL mode for SQLite
        from sqlalchemy import event as _sa_event

        @_sa_event.listens_for(engine, "connect")
        def _set_sqlite_wal(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()
    else:
        # PostgreSQL — proper connection pool
        engine = create_engine(
            url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,  # recycle connections every hour
            connect_args={
                "connect_timeout": 10,
                "application_name": f"fintelligence_{schema_prefix}" if schema_prefix else "fintelligence",
            },
        )
        log.info(f"PostgreSQL engine created (schema_prefix={schema_prefix!r})")

    return engine


def make_session_factory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db_dependency(SessionLocal):
    """
    Returns a FastAPI dependency function for database sessions.
    Usage:
        SessionLocal = make_session_factory(engine)
        get_db = get_db_dependency(SessionLocal)
        ...
        @router.get("/endpoint")
        def endpoint(db: Session = Depends(get_db)):
    """
    def get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    return get_db


def make_redis(db: int = 0) -> "_redis.Redis":
    """
    Create a Redis client from REDIS_URL env var.
    Each backend uses a separate DB index to avoid key collisions.
    """
    url = os.getenv("REDIS_URL", "")
    if not url:
        log.warning("REDIS_URL not set — Redis caching disabled")
        return None  # type: ignore

    try:
        client = _redis.from_url(
            url,
            db=db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        client.ping()
        log.info(f"Redis connected (db={db})")
        return client
    except Exception as e:
        log.warning(f"Redis unavailable ({e}) — caching disabled")
        return None  # type: ignore
