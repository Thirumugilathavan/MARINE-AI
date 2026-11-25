"""
Database initialization utilities.

Safely initializes database tables using SQLAlchemy's checkfirst=True policy,
ensuring that existing tables and data are never dropped or damaged.
"""

import logging
from sqlalchemy import Engine
from app.database.connection import engine
from app.database.models import Base

logger = logging.getLogger(__name__)


def init_db(target_engine: Engine = engine) -> None:
    """
    Creates database tables if they do not already exist.
    Never drops or modifies existing tables.
    """
    try:
        logger.info("Initializing database tables (checkfirst=True)...")
        Base.metadata.create_all(bind=target_engine, checkfirst=True)
        logger.info("Database tables verified/initialized successfully.")
    except Exception as exc:
        logger.warning(f"Database initialization could not complete: {exc}")
        raise
