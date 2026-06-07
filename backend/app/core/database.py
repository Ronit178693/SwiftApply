"""
Database configuration module for AutoIntern.

Handles:
- Lazy engine initialization (after .env is loaded)
- SSL support for Supabase PostgreSQL connections
- Connection pooling tuned for SaaS workloads
- Automatic SQLite fallback when PostgreSQL is unreachable
- Connection retry with exponential backoff
- Health check utility
"""

import os
import ssl
import time
import logging
from typing import Optional

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import OperationalError, InterfaceError

logger = logging.getLogger(__name__)

Base = declarative_base()

# Module-level state (populated lazily)
_engine = None
_SessionLocal = None
_db_mode: str = "uninitialized"  # "postgresql", "sqlite", or "uninitialized"

# Path for the local SQLite fallback database
SQLITE_FALLBACK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "autointern_local.db"
)


def _build_pg_url(raw_url: str) -> str:
    """Normalize a PostgreSQL URL to use the pg8000 driver."""
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+pg8000://", 1)
    elif raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+pg8000://", 1)
    return raw_url


def _try_connect_pg(url: str, max_retries: int = 3) -> Optional[object]:
    """
    Attempt to create a PostgreSQL engine and verify connectivity.
    Tries with SSL first (required by Supabase), then without.
    Returns the engine on success, or None on failure.
    """
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    # Try SSL first, then no-SSL
    connect_configs = [
        {"ssl_context": ssl_context},  # SSL (Supabase standard)
        {},                             # No SSL (local PostgreSQL)
    ]

    for connect_args in connect_configs:
        for attempt in range(1, max_retries + 1):
            try:
                engine = create_engine(
                    url,
                    connect_args=connect_args,
                    pool_size=5,
                    max_overflow=10,
                    pool_timeout=30,
                    pool_recycle=1800,  # Recycle connections every 30 min
                    pool_pre_ping=True,  # Verify connections before use
                    poolclass=QueuePool,
                )
                # Test the connection
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                
                ssl_label = "with SSL" if connect_args else "without SSL"
                logger.info(f"PostgreSQL connection established {ssl_label} (attempt {attempt})")
                return engine
            except (OperationalError, InterfaceError, Exception) as e:
                ssl_label = "with SSL" if connect_args else "without SSL"
                logger.debug(f"PostgreSQL connection attempt {attempt} {ssl_label} failed: {str(e)[:100]}")
                if attempt < max_retries:
                    wait = 2 ** attempt  # Exponential backoff: 2s, 4s, 8s
                    time.sleep(wait)

    return None


def _create_sqlite_engine():
    """Create a SQLite engine as a fallback."""
    url = f"sqlite:///{SQLITE_FALLBACK_PATH}"
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    
    # Enable WAL mode for better concurrent access
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_engine(force_reinit: bool = False):
    """
    Initialize the database engine lazily.

    Call this AFTER environment variables have been loaded (i.e., after dotenv).
    If PostgreSQL is unreachable, automatically falls back to local SQLite.

    This function is idempotent — calling it multiple times is safe.
    """
    global _engine, _SessionLocal, _db_mode

    if _engine is not None and not force_reinit:
        return _engine

    raw_url = os.environ.get("DATABASE_URL", "")

    # Check if DATABASE_URL is configured with real values
    has_real_url = (
        raw_url
        and "your_password" not in raw_url
        and "your_project_id" not in raw_url
        and raw_url.startswith(("postgresql://", "postgres://"))
    )

    if has_real_url:
        pg_url = _build_pg_url(raw_url)
        host_info = pg_url.split("@")[-1] if "@" in pg_url else pg_url
        logger.info(f"Attempting PostgreSQL connection to: {host_info}")

        _engine = _try_connect_pg(pg_url, max_retries=2)

        if _engine is not None:
            _db_mode = "postgresql"
            logger.info("Using PostgreSQL database (Supabase)")
        else:
            logger.warning(
                "PostgreSQL connection FAILED after retries. "
                "Your Supabase project may be paused or unreachable. "
                f"Falling back to local SQLite: {SQLITE_FALLBACK_PATH}"
            )
            _engine = _create_sqlite_engine()
            _db_mode = "sqlite"
    else:
        if not raw_url:
            logger.warning("DATABASE_URL is not set. Using local SQLite database.")
        else:
            logger.warning("DATABASE_URL has placeholder values. Using local SQLite database.")
        _engine = _create_sqlite_engine()
        _db_mode = "sqlite"

    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

    logger.info(f"Database engine initialized in '{_db_mode}' mode.")
    return _engine


def get_engine():
    """Get the current database engine, initializing if needed."""
    if _engine is None:
        init_engine()
    return _engine


def get_session_factory():
    """Get the session factory, initializing if needed."""
    if _SessionLocal is None:
        init_engine()
    return _SessionLocal


def get_db_mode() -> str:
    """Return the current database mode: 'postgresql', 'sqlite', or 'uninitialized'."""
    return _db_mode


def get_db():
    """
    FastAPI Dependency that provides a database session per request,
    closing it automatically when the request completes.
    """
    SessionFactory = get_session_factory()
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """
    Create all tables defined in models if they don't already exist.
    Safe to call multiple times (idempotent).
    """
    engine = get_engine()
    # Import models to ensure they are registered with Base
    from app.models import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info(f"Database tables ensured (mode={_db_mode})")


def check_db_health() -> dict:
    """
    Perform a health check on the database connection.
    Returns a dict with status, mode, and latency.
    """
    engine = get_engine()
    start = time.time()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency_ms = round((time.time() - start) * 1000, 1)
        return {
            "status": "healthy",
            "mode": _db_mode,
            "latency_ms": latency_ms,
            "sqlite_fallback_path": SQLITE_FALLBACK_PATH if _db_mode == "sqlite" else None,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "mode": _db_mode,
            "error": str(e)[:200],
        }


# Backwards compatibility aliases
# (So existing imports like `from app.core.database import engine` still work)
class _LazyEngineProxy:
    """Proxy that lazily initializes the engine on first attribute access."""
    def __getattr__(self, name):
        return getattr(get_engine(), name)

    def __repr__(self):
        return repr(get_engine())


class _LazySessionProxy:
    """Proxy that lazily initializes SessionLocal on first call."""
    def __call__(self, *args, **kwargs):
        return get_session_factory()(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(get_session_factory(), name)


engine = _LazyEngineProxy()
SessionLocal = _LazySessionProxy()
