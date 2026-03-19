"""
Azure SQL Server schema setup.

Uses SQLAlchemy ORM metadata to create all tables.

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
from src.db.connection import get_engine, switch_backend


def run_schema() -> None:
    """Switch to MSSQL backend and create all tables from ORM metadata."""
    switch_backend("mssql")
    engine = get_engine()

    db_url = str(engine.url)
    logger.info("Database : %s", db_url)
    logger.info("Models   : src/db/models.py")

    Base.metadata.create_all(engine)

    logger.info("Azure SQL schema setup completed successfully (from ORM models).")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_schema()
