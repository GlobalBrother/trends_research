"""
Azure SQL Server Schema Setup
Reads azure_schema.sql and executes it against the configured Azure SQL Server.

Usage:
    $env:PYTHONPATH="."
    python src/db/setup_azure.py
"""
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

from sqlalchemy import text
from src.db.connection import get_engine


def run_schema():
    schema_path = os.path.join(os.path.dirname(__file__), "azure_schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()

    engine = get_engine()

    # Split on GO-like boundaries: each statement separated by blank lines
    # For T-SQL, we split on semicolons at statement boundaries
    # But our schema uses IF NOT EXISTS blocks without semicolons between them
    # Split on double newlines before IF/CREATE/PRINT
    import re
    statements = re.split(r'\n(?=IF NOT EXISTS|CREATE INDEX|PRINT)', sql)

    with engine.connect() as conn:
        for stmt in statements:
            stmt = stmt.strip()
            if not stmt or stmt.startswith("--"):
                # skip pure comments
                lines = [l for l in stmt.split("\n") if l.strip() and not l.strip().startswith("--")]
                if not lines:
                    continue
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception as e:
                print(f"ERROR executing statement:\n{stmt[:120]}...\n{e}\n")
                conn.rollback()
                continue

    print("Schema setup complete.")


if __name__ == "__main__":
    run_schema()
