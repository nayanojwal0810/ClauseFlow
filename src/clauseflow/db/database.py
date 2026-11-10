"""Database connection and session management."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from typing import Generator, Optional
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import Session, sessionmaker

# Load environment variables from .env if present
load_dotenv()


def get_db_url(
    host: Optional[str] = None,
    port: Optional[int | str] = None,
    name: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> URL:
    """Construct a PostgreSQL URL using psycopg3 driver.
    
    Reads from environment variables if arguments are omitted.
    Fails clearly if required variables (especially password) are missing.
    """
    db_host = host or os.getenv("CF_DB_HOST", "127.0.0.1")
    db_port = int(port or os.getenv("CF_DB_PORT", "5433"))
    db_name = name or os.getenv("CF_DB_NAME", "clauseflow")
    db_user = user or os.getenv("CF_DB_USER", "clauseflow")
    db_password = password or os.getenv("CF_DB_PASSWORD")

    if not db_password:
        raise ValueError(
            "Database password is required. Please set CF_DB_PASSWORD in .env or pass it explicitly."
        )

    return URL.create(
        drivername="postgresql+psycopg",
        username=db_user,
        password=db_password,
        host=db_host,
        port=db_port,
        database=db_name,
    )


def get_engine(
    url: Optional[URL] = None,
    echo: bool = False,
    connect_args: Optional[dict] = None,
) -> Engine:
    """Create a SQLAlchemy engine with connection pool pre-ping enabled."""
    db_url = url or get_db_url()
    extra_args = connect_args or {}
    return create_engine(db_url, pool_pre_ping=True, echo=echo, connect_args=extra_args)


@contextmanager
def get_session(engine: Optional[Engine] = None) -> Generator[Session, None, None]:
    """Provide a transactional session context.
    
    The caller is responsible for committing transactions.
    Rolls back automatically on unhandled exceptions.
    """
    eng = engine or get_engine()
    session_factory = sessionmaker(bind=eng, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
