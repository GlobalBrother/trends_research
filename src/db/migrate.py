"""
Database migration - bring existing Azure SQL tables in sync with models.py.

This script is idempotent: it can be run multiple times safely. It creates
missing tables and indexes using SQLAlchemy metadata rather than raw SQL.

Usage
-----
From the project root::

    python -m src.db.migrate          # run the migration
    python -m src.db.migrate --dry    # preview actions without executing
"""

import argparse
import logging
import os
import sys
from datetime import datetime

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from src.runtime.secrets import init_runtime_secrets

init_runtime_secrets()

from sqlalchemy import inspect

from src.db.connection import get_engine
from src.db.models import Base

logger = logging.getLogger(__name__)


class MigrationResult:
    """Collects migration actions for reporting."""

    def __init__(self):
        self.tables_created: list[str] = []
        self.indexes_created: list[str] = []
        self.indexes_skipped: list[str] = []
        self.errors: list[str] = []
        self.started_at = datetime.utcnow()
        self.finished_at: datetime | None = None

    def summary(self) -> dict:
        self.finished_at = self.finished_at or datetime.utcnow()
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "tables_created": self.tables_created,
            "tables_created_count": len(self.tables_created),
            "indexes_created": self.indexes_created,
            "indexes_created_count": len(self.indexes_created),
            "indexes_skipped_count": len(self.indexes_skipped),
            "errors": self.errors,
            "error_count": len(self.errors),
            "success": len(self.errors) == 0,
        }


def _get_existing_tables(engine) -> set[str]:
    insp = inspect(engine)
    return set(insp.get_table_names())


def _get_existing_indexes(engine) -> set[str]:
    insp = inspect(engine)
    existing: set[str] = set()
    for table_name in insp.get_table_names():
        for idx in insp.get_indexes(table_name):
            if idx.get("name"):
                existing.add(idx["name"])
    return existing


def _iter_model_indexes():
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            if index.name:
                yield table.name, index


def run_migration(dry_run: bool = False) -> MigrationResult:
    """Run the full migration: create missing tables, then add missing indexes."""
    result = MigrationResult()
    engine = get_engine()

    logger.info("Step 1: Checking for missing tables...")
    existing_tables_before = _get_existing_tables(engine)
    model_tables = set(Base.metadata.tables.keys())
    missing_tables = model_tables - existing_tables_before

    if missing_tables:
        logger.info("  Missing tables to create: %s", ", ".join(sorted(missing_tables)))
        if not dry_run:
            Base.metadata.create_all(engine, checkfirst=True)
        for table_name in sorted(missing_tables):
            result.tables_created.append(table_name)
            logger.info("  [%s] CREATE TABLE %s", "DRY-RUN" if dry_run else "OK", table_name)
    else:
        logger.info("  All %d tables already exist.", len(model_tables))

    logger.info("Step 2: Checking for missing indexes...")
    existing_indexes = _get_existing_indexes(engine)
    logger.info("  Found %d existing indexes in the database.", len(existing_indexes))

    for table_name, index in _iter_model_indexes():
        idx_name = index.name
        if idx_name in existing_indexes:
            result.indexes_skipped.append(idx_name)
            logger.debug("  [SKIP] %s already exists on %s", idx_name, table_name)
            continue

        columns = ", ".join(column.name for column in index.columns)
        logger.info("  [%s] %s ON %s (%s)", "DRY-RUN" if dry_run else "CREATE", idx_name, table_name, columns)

        if dry_run:
            result.indexes_created.append(f"{idx_name} (dry-run)")
            continue

        try:
            index.create(bind=engine, checkfirst=True)
            result.indexes_created.append(idx_name)
        except Exception as exc:
            err_msg = f"Failed to create index {idx_name}: {exc}"
            logger.error("  [ERROR] %s", err_msg)
            result.errors.append(err_msg)

    result.finished_at = datetime.utcnow()
    logger.info(
        "Migration complete: %d tables created, %d indexes created, %d indexes skipped, %d errors.",
        len(result.tables_created),
        len(result.indexes_created),
        len(result.indexes_skipped),
        len(result.errors),
    )
    return result


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Migrate Azure SQL schema to match models.py")
    parser.add_argument("--dry", action="store_true", help="Preview actions without executing")
    args = parser.parse_args()

    result = run_migration(dry_run=args.dry)
    summary = result.summary()

    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"  Started at:       {summary['started_at']}")
    print(f"  Finished at:      {summary['finished_at']}")
    print(f"  Tables created:   {summary['tables_created_count']}")
    print(f"  Indexes created:  {summary['indexes_created_count']}")
    print(f"  Indexes skipped:  {summary['indexes_skipped_count']}")
    print(f"  Errors:           {summary['error_count']}")
    print(f"  Success:          {summary['success']}")
    print("=" * 60)

    if summary["tables_created"]:
        print("\nNew tables:")
        for table_name in summary["tables_created"]:
            print(f"  + {table_name}")

    if summary["indexes_created"]:
        print("\nNew indexes:")
        for index_name in summary["indexes_created"]:
            print(f"  + {index_name}")

    if summary["errors"]:
        print("\nErrors:")
        for error in summary["errors"]:
            print(f"  ! {error}")
