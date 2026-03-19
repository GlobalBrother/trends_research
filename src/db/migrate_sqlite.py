"""
Migrate the existing SQLite database from the old schema (platform TEXT)
to the new normalised schema (platform_id INTEGER FK → platforms).

Safe to run multiple times – it checks whether migration is needed first.

Usage::

    PYTHONPATH="." python src/db/migrate_sqlite.py
"""

import logging
import os
import sqlite3
import sys

logger = logging.getLogger(__name__)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def _get_db_path() -> str:
    from dotenv import load_dotenv
    load_dotenv()
    return os.getenv("DB_PATH", os.path.join(project_root, "src", "collector", "trends.db"))


def _column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def migrate():
    db_path = _get_db_path()
    if not os.path.exists(db_path):
        logger.info("Database does not exist yet – nothing to migrate.")
        return

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA journal_mode = WAL")

    try:
        # Check if migration is needed
        trends_cols = _column_names(conn, "trends")
        if "platform_id" in trends_cols:
            logger.info("trends table already has platform_id – migration not needed.")
            return
        if "platform" not in trends_cols:
            logger.info("trends table has neither platform nor platform_id – skipping.")
            return

        logger.info("Starting migration: platform TEXT → platform_id INTEGER FK")

        # 1. Create platforms table if it doesn't exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS platforms (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT    NOT NULL UNIQUE
            )
        """)

        # 2. Populate platforms from existing data
        conn.execute("""
            INSERT OR IGNORE INTO platforms (name)
            SELECT DISTINCT platform FROM trends WHERE platform IS NOT NULL
        """)

        # 3. Recreate trends table with new schema
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trends_new (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                platform_id  INTEGER REFERENCES platforms(id),
                topic        TEXT,
                growth       REAL,
                keyword      TEXT,
                geo          TEXT,
                extracted_at NUMERIC,
                extra_data   TEXT
            )
        """)

        # 4. Copy data, mapping platform name → platform_id
        conn.execute("""
            INSERT INTO trends_new (id, platform_id, topic, growth, keyword, geo, extracted_at, extra_data)
            SELECT t.id, p.id, t.topic, t.growth, t.keyword, t.geo, t.extracted_at, t.extra_data
            FROM trends t
            LEFT JOIN platforms p ON p.name = t.platform
        """)

        # 5. Swap tables
        conn.execute("DROP TABLE trends")
        conn.execute("ALTER TABLE trends_new RENAME TO trends")

        # 6. Recreate indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trends_platform_id ON trends(platform_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trends_keyword ON trends(keyword)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trends_geo ON trends(geo)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trends_extracted_at ON trends(extracted_at)")

        conn.commit()
        logger.info("Migration completed successfully.")

    except Exception:
        conn.rollback()
        logger.exception("Migration failed – rolled back.")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate()
