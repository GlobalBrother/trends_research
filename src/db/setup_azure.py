"""
Azure SQL Server schema setup.

Creates all tables from ORM metadata and then runs the idempotent migration
to add any missing indexes.

Usage::

    $env:PYTHONPATH="."
    python src/db/setup_azure.py
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv

load_dotenv(os.path.join(project_root, ".env"))

from src.db.models import Base
from src.db.connection import get_engine
from src.db.migrate import run_migration


def run_schema() -> None:
    """Create all tables from ORM metadata on Azure SQL, then add indexes."""
    engine = get_engine()

    db_url = str(engine.url)
    logger.info("Database : %s", db_url)
    logger.info("Models   : src/db/models.py")

    # Step 1: Create tables (checkfirst=True prevents errors on existing tables)
    Base.metadata.create_all(engine, checkfirst=True)
    logger.info("Tables created / verified via ORM metadata.")

    # Step 2: Run migration to add any missing indexes
    result = run_migration(dry_run=False)
    s = result.summary()
    logger.info(
        "Migration: %d tables created, %d indexes created, %d errors.",
        s["tables_created_count"], s["indexes_created_count"], s["error_count"],
    )
    if s["errors"]:
        for err in s["errors"]:
            logger.error("  Migration error: %s", err)

    logger.info("Azure SQL schema setup completed successfully.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_schema()
