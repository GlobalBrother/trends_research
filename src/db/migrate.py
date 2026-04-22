"""
Database migration — bring existing Azure SQL tables in sync with models.py.

This script is **idempotent**: it can be run multiple times safely.  It will
only create indexes, columns, or tables that do not already exist.

It handles two categories of changes:

1. **New tables** — created via ``Base.metadata.create_all(checkfirst=True)``.
2. **New indexes on existing tables** — created via raw ``CREATE INDEX`` with
   ``IF NOT EXISTS`` guards (T-SQL compatible).
3. **New columns on existing tables** — added via ``ALTER TABLE ... ADD`` with
   existence checks.

Usage
-----
From the project root::

    python -m src.db.migrate          # run the migration
    python -m src.db.migrate --dry    # preview SQL without executing

Or via the API::

    POST /admin/azure/migrate
"""

import argparse
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

load_dotenv(os.path.join(project_root, ".env"))

from sqlalchemy import text, inspect

from src.db.connection import get_engine, session_scope
from src.db.models import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Index definitions — every index declared in models.py
#
# Format: (index_name, table_name, column_list_csv)
#
# These are written as raw SQL so we can use T-SQL's conditional syntax
# which is not supported by SQLAlchemy's DDL layer for existing tables.
# ---------------------------------------------------------------------------

_INDEXES = [
    # Authors
    ("idx_authors_platform",            "authors",          "platform_id"),
    ("idx_authors_external",            "authors",          "platform_id, external_author_id"),

    # Content
    ("idx_content_platform",            "content",          "platform_id"),
    ("idx_content_keyword",             "content",          "keyword"),
    ("idx_content_external",            "content",          "platform_id, external_id"),
    ("idx_content_created",             "content",          "created_at"),
    ("idx_content_author",              "content",          "author_id"),

    # Content Metrics
    ("idx_metrics_content",             "content_metrics",  "content_id"),

    # Trends
    ("idx_trends_platform_id",          "trends",           "platform_id"),
    ("idx_trends_keyword",              "trends",           "keyword"),
    ("idx_trends_geo",                  "trends",           "geo"),
    ("idx_trends_extracted_at",         "trends",           "extracted_at"),
    ("idx_trends_dedup",                "trends",           "platform_id, keyword, geo, extracted_at"),

    # Scrape Errors
    ("idx_error_platform",              "scrape_errors",    "platform"),
    ("idx_error_extracted_at",          "scrape_errors",    "extracted_at"),

    # Scrape Log
    ("idx_log_platform_id",             "scrape_log",       "platform, identifier"),
    ("idx_log_extracted",               "scrape_log",       "platform, identifier, status, extracted_at"),

    # OTP Codes
    ("idx_otp_user",                    "otp_codes",        "user_id"),
    ("idx_otp_lookup",                  "otp_codes",        "user_id, code, used, created_at"),

    # Auth Tokens
    ("idx_authtoken_token",             "auth_tokens",      "token"),
    ("idx_authtoken_user_expires",      "auth_tokens",      "user_id, expires_at"),

    # Token Usage
    ("idx_tokenusage_platform",         "token_usage",      "platform"),
    ("idx_tokenusage_created",          "token_usage",      "created_at"),
    ("idx_tokenusage_platform_created", "token_usage",      "platform, created_at"),

    # Raw Data Archive
    ("idx_raw_source",                  "raw_data_archive", "source_table, source_id"),

    # Niches
    ("idx_niches_name",                 "niches",           "niche_name"),

    # Ads Insight
    ("idx_ads_keyword",                 "ads_insight",      "search_keyword"),
    ("idx_ads_extracted",               "ads_insight",      "extracted_at"),
    ("idx_ads_hookd_id",                "ads_insight",      "hookd_id"),
]


# ---------------------------------------------------------------------------
# Column additions — new columns to add to existing tables
#
# Format: (table_name, column_name, mssql_column_def, sqlite_column_def)
#
# Each entry is applied with an existence guard so the migration is safe
# to re-run.  ``mssql_column_def`` is the T-SQL fragment that follows
# ``ADD`` (column name + type + constraints + default).  ``sqlite_column_def``
# is the equivalent for SQLite (used in tests).
# ---------------------------------------------------------------------------

_COLUMN_ADDITIONS = [
    (
        "niches",
        "is_seed",
        "is_seed BIT NOT NULL CONSTRAINT DF_niches_is_seed DEFAULT 0",
        "is_seed BOOLEAN NOT NULL DEFAULT 0",
    ),
]


# ---------------------------------------------------------------------------
# Migration logic
# ---------------------------------------------------------------------------

class MigrationResult:
    """Collects migration actions for reporting."""

    def __init__(self):
        self.tables_created: list[str] = []
        self.indexes_created: list[str] = []
        self.indexes_skipped: list[str] = []
        self.columns_added: list[str] = []
        self.columns_skipped: list[str] = []
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
            "columns_added": self.columns_added,
            "columns_added_count": len(self.columns_added),
            "columns_skipped_count": len(self.columns_skipped),
            "errors": self.errors,
            "error_count": len(self.errors),
            "success": len(self.errors) == 0,
        }


def _get_existing_indexes(engine) -> set[str]:
    """Return a set of all index names that already exist in the database.

    Works for both Azure SQL (MSSQL) and SQLite (for testing).
    """
    dialect = engine.dialect.name
    existing = set()

    try:
        insp = inspect(engine)
        for table_name in insp.get_table_names():
            for idx in insp.get_indexes(table_name):
                existing.add(idx["name"])
    except Exception:
        # Fallback: query sys.indexes directly (MSSQL-specific)
        if dialect in ("mssql", "mssql+pyodbc"):
            try:
                with engine.connect() as conn:
                    rows = conn.execute(text(
                        "SELECT name FROM sys.indexes WHERE name IS NOT NULL"
                    )).fetchall()
                    existing = {r[0] for r in rows}
            except Exception as e:
                logger.warning("Could not query sys.indexes: %s", e)

    return existing


def _get_existing_tables(engine) -> set[str]:
    """Return a set of all table names that already exist in the database."""
    try:
        insp = inspect(engine)
        return set(insp.get_table_names())
    except Exception:
        return set()


def _column_exists(engine, table_name: str, column_name: str) -> bool:
    """Return True if ``table_name.column_name`` already exists in the DB.

    Uses SQLAlchemy's inspector first (works for both MSSQL and SQLite),
    falling back to a dialect-specific query for MSSQL when inspection
    fails.
    """
    try:
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns(table_name)}
        if cols:
            return column_name in cols
    except Exception:
        pass

    dialect = engine.dialect.name
    if dialect in ("mssql", "mssql+pyodbc"):
        try:
            with engine.connect() as conn:
                res = conn.execute(text(
                    f"SELECT COL_LENGTH('{table_name}', '{column_name}')"
                )).scalar()
                return res is not None
        except Exception as e:
            logger.warning("Could not check column existence for %s.%s: %s",
                           table_name, column_name, e)
    return False


def run_migration(dry_run: bool = False) -> MigrationResult:
    """Run the full migration: create missing tables, then add missing indexes.

    Parameters
    ----------
    dry_run : bool
        If True, log all SQL statements but do not execute them.

    Returns
    -------
    MigrationResult
        A summary of all actions taken.
    """
    result = MigrationResult()
    engine = get_engine()
    dialect = engine.dialect.name

    # ------------------------------------------------------------------
    # Step 1: Create any tables that don't exist yet
    # ------------------------------------------------------------------
    logger.info("Step 1: Checking for missing tables...")
    existing_tables_before = _get_existing_tables(engine)
    model_tables = set(Base.metadata.tables.keys())
    missing_tables = model_tables - existing_tables_before

    if missing_tables:
        logger.info("  Missing tables to create: %s", ", ".join(sorted(missing_tables)))
        if not dry_run:
            Base.metadata.create_all(engine, checkfirst=True)
        for t in sorted(missing_tables):
            result.tables_created.append(t)
            logger.info("  [%s] CREATE TABLE %s", "DRY-RUN" if dry_run else "OK", t)
    else:
        logger.info("  All %d tables already exist.", len(model_tables))

    # ------------------------------------------------------------------
    # Step 2: Create missing indexes on existing tables
    # ------------------------------------------------------------------
    logger.info("Step 2: Checking for missing indexes...")
    existing_indexes = _get_existing_indexes(engine)
    logger.info("  Found %d existing indexes in the database.", len(existing_indexes))

    for idx_name, table_name, columns in _INDEXES:
        if idx_name in existing_indexes:
            result.indexes_skipped.append(idx_name)
            logger.debug("  [SKIP] %s already exists on %s", idx_name, table_name)
            continue

        # Build the CREATE INDEX statement with T-SQL conditional guard
        if dialect in ("mssql", "mssql+pyodbc"):
            # T-SQL: Use IF NOT EXISTS guard for safety
            sql = (
                f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = '{idx_name}') "
                f"CREATE NONCLUSTERED INDEX [{idx_name}] ON [{table_name}] ({columns})"
            )
        else:
            # SQLite / PostgreSQL: Use IF NOT EXISTS syntax
            sql = f"CREATE INDEX IF NOT EXISTS [{idx_name}] ON [{table_name}] ({columns})"

        logger.info("  [%s] %s ON %s (%s)",
                     "DRY-RUN" if dry_run else "CREATE", idx_name, table_name, columns)

        if not dry_run:
            try:
                with engine.connect() as conn:
                    conn.execute(text(sql))
                    conn.commit()
                result.indexes_created.append(idx_name)
            except Exception as e:
                err_msg = f"Failed to create index {idx_name}: {e}"
                logger.error("  [ERROR] %s", err_msg)
                result.errors.append(err_msg)
        else:
            result.indexes_created.append(f"{idx_name} (dry-run)")

    # ------------------------------------------------------------------
    # Step 3: Add missing columns to existing tables (idempotent)
    # ------------------------------------------------------------------
    logger.info("Step 3: Checking for missing columns...")
    existing_tables_after = _get_existing_tables(engine)

    for table_name, column_name, mssql_def, sqlite_def in _COLUMN_ADDITIONS:
        if table_name not in existing_tables_after:
            # Table doesn't exist yet (would have been created in step 1
            # with the column already present via the ORM model).
            result.columns_skipped.append(f"{table_name}.{column_name}")
            logger.debug("  [SKIP] table %s does not exist", table_name)
            continue

        if _column_exists(engine, table_name, column_name):
            result.columns_skipped.append(f"{table_name}.{column_name}")
            logger.debug("  [SKIP] column %s.%s already exists", table_name, column_name)
            continue

        if dialect in ("mssql", "mssql+pyodbc"):
            # T-SQL idempotent guard, mirroring the index pattern above.
            sql = (
                f"IF COL_LENGTH('{table_name}', '{column_name}') IS NULL "
                f"ALTER TABLE [{table_name}] ADD {mssql_def}"
            )
        else:
            sql = f"ALTER TABLE [{table_name}] ADD COLUMN {sqlite_def}"

        logger.info("  [%s] ALTER TABLE %s ADD %s",
                     "DRY-RUN" if dry_run else "ADD", table_name, column_name)

        if not dry_run:
            try:
                with engine.connect() as conn:
                    conn.execute(text(sql))
                    conn.commit()
                result.columns_added.append(f"{table_name}.{column_name}")
            except Exception as e:
                err_msg = f"Failed to add column {table_name}.{column_name}: {e}"
                logger.error("  [ERROR] %s", err_msg)
                result.errors.append(err_msg)
        else:
            result.columns_added.append(f"{table_name}.{column_name} (dry-run)")

    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------
    result.finished_at = datetime.utcnow()
    logger.info(
        "Migration complete: %d tables created, %d indexes created, "
        "%d indexes skipped, %d columns added, %d errors.",
        len(result.tables_created),
        len(result.indexes_created),
        len(result.indexes_skipped),
        len(result.columns_added),
        len(result.errors),
    )
    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Migrate Azure SQL schema to match models.py")
    parser.add_argument("--dry", action="store_true", help="Preview SQL without executing")
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
    print(f"  Columns added:    {summary['columns_added_count']}")
    print(f"  Errors:           {summary['error_count']}")
    print(f"  Success:          {summary['success']}")
    print("=" * 60)

    if summary["tables_created"]:
        print("\nNew tables:")
        for t in summary["tables_created"]:
            print(f"  + {t}")

    if summary["indexes_created"]:
        print("\nNew indexes:")
        for i in summary["indexes_created"]:
            print(f"  + {i}")

    if summary["errors"]:
        print("\nErrors:")
        for e in summary["errors"]:
            print(f"  ! {e}")
