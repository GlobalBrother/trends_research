"""
SQL compatibility layer for SQLite and Azure SQL Server.
Provides dialect-aware SQL fragments so the rest of the codebase
can work with both backends without inline if/else blocks.
"""

import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.db.connection import is_sqlite


# ---------------------------------------------------------------------------
# Schema-qualified table names
# ---------------------------------------------------------------------------

def tbl(table_name: str) -> str:
    """Return schema-qualified table name.

    SQLite  → ``table_name``  (no schema prefix)
    MSSQL   → ``dbo.table_name``
    """
    if is_sqlite():
        return table_name
    return f"dbo.{table_name}"


# ---------------------------------------------------------------------------
# Date / time helpers
# ---------------------------------------------------------------------------

def today_start():
    """SQL expression for the start of today (midnight)."""
    if is_sqlite():
        return "date('now')"
    return "CAST(GETDATE() AS DATE)"


def now():
    """SQL expression for current timestamp."""
    if is_sqlite():
        return "datetime('now')"
    return "GETDATE()"


def minutes_ago(col, minutes):
    """SQL expression: <col> + <minutes> minutes > now."""
    if is_sqlite():
        return f"datetime({col}, '+{minutes} minutes') > datetime('now')"
    return f"DATEADD(MINUTE, {minutes}, {col}) > GETDATE()"


def expires_check(col):
    """SQL expression: <col> > now (for token expiry)."""
    if is_sqlite():
        return f"{col} > datetime('now')"
    return f"{col} > GETDATE()"


# ---------------------------------------------------------------------------
# LIMIT / TOP
# ---------------------------------------------------------------------------

def limit_clause(order_by, limit):
    """Return ORDER BY ... LIMIT/OFFSET FETCH clause."""
    if is_sqlite():
        return f" ORDER BY {order_by} LIMIT {limit}"
    return f" ORDER BY {order_by} OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"


def top_clause(n):
    """Return TOP N or empty string (SQLite uses LIMIT instead)."""
    if is_sqlite():
        return ""
    return f"TOP {n} "


def top_limit_suffix(n):
    """Return LIMIT N for SQLite (appended at end) or empty for mssql (uses TOP)."""
    if is_sqlite():
        return f" LIMIT {n}"
    return ""


# ---------------------------------------------------------------------------
# UPSERT / MERGE for scrape_log
# ---------------------------------------------------------------------------

def upsert_scrape_log(conn, platform, identifier, status, extracted_at):
    """Upsert a scrape_log entry (SQLite: DELETE+INSERT, MSSQL: MERGE)."""
    from sqlalchemy import text as _text
    params = {"platform": platform, "identifier": identifier, "status": status, "extracted_at": extracted_at}
    if is_sqlite():
        _t = tbl('scrape_log')
        conn.execute(_text(
            f"DELETE FROM {_t} WHERE platform = :platform AND identifier = :identifier"
        ), params)
        conn.execute(_text(
            f"INSERT INTO {_t} (platform, identifier, status, extracted_at) "
            "VALUES (:platform, :identifier, :status, :extracted_at)"
        ), params)
        return
    _t = tbl('scrape_log')
    conn.execute(_text(
        f"MERGE {_t} AS target "
        "USING (SELECT :platform AS platform, :identifier AS identifier) AS source "
        "ON target.platform = source.platform AND target.identifier = source.identifier "
        "WHEN MATCHED THEN UPDATE SET status = :status, extracted_at = :extracted_at "
        "WHEN NOT MATCHED THEN INSERT (platform, identifier, status, extracted_at) "
        "VALUES (:platform, :identifier, :status, :extracted_at);"
    ), params)


# ---------------------------------------------------------------------------
# Duplicate check for trends
# ---------------------------------------------------------------------------

def duplicate_check_sql():
    """Return SQL to check if a trend already exists today."""
    _t = tbl('trends')
    if is_sqlite():
        return (
            f"SELECT 1 FROM {_t} WHERE platform = :platform AND topic = :topic "
            "AND keyword = :keyword AND geo = :geo "
            "AND extracted_at > date('now')"
        )
    return (
        f"SELECT 1 FROM {_t} WHERE platform = :platform AND topic = :topic "
        "AND keyword = :keyword AND geo = :geo "
        "AND extracted_at > CAST(GETDATE() AS DATE)"
    )


# ---------------------------------------------------------------------------
# Conditional INSERT (niches seeding)
# ---------------------------------------------------------------------------

def insert_if_not_exists_niches():
    """Return SQL to insert a niche keyword if it doesn't exist."""
    _t = tbl('niches')
    if is_sqlite():
        return (
            f"INSERT OR IGNORE INTO {_t} (niche_name, keyword) "
            "VALUES (:niche_name, :kw)"
        )
    return (
        f"IF NOT EXISTS ("
        f"    SELECT 1 FROM {_t} WHERE niche_name = :niche_name AND keyword = :kw"
        ") "
        f"INSERT INTO {_t} (niche_name, keyword) VALUES (:niche_name, :kw)"
    )


# ---------------------------------------------------------------------------
# OTP verification query
# ---------------------------------------------------------------------------

def upsert_platform_row(conn, table, match_col, match_val, update_cols, insert_cols, params):
    """Generic upsert for platform tables (SQLite: UPDATE-or-INSERT, MSSQL: MERGE).

    Args:
        conn: SQLAlchemy connection
        table: table name (e.g. 'instagram_posts')
        match_col: column to match on (e.g. 'post_pk')
        match_val: param name for match value (e.g. 'post_pk')
        update_cols: list of columns to update on match
        insert_cols: list of columns for insert
        params: dict of all parameter values
    """
    from sqlalchemy import text as _text
    table = tbl(table)
    if is_sqlite():
        # Check if row exists
        row = conn.execute(
            _text(f"SELECT 1 FROM {table} WHERE {match_col} = :{match_val}"),
            {match_val: params[match_val]},
        ).fetchone()
        if row:
            set_clause = ", ".join(f"{c} = :{c}" for c in update_cols)
            conn.execute(
                _text(f"UPDATE {table} SET {set_clause} WHERE {match_col} = :{match_val}"),
                params,
            )
        else:
            col_list = ", ".join(insert_cols)
            val_list = ", ".join(f":{c}" for c in insert_cols)
            conn.execute(
                _text(f"INSERT INTO {table} ({col_list}) VALUES ({val_list})"),
                params,
            )
    else:
        # MSSQL MERGE
        set_clause = ", ".join(f"{c} = :{c}" for c in update_cols)
        col_list = ", ".join(insert_cols)
        val_list = ", ".join(f":{c}" for c in insert_cols)
        conn.execute(
            _text(
                f"MERGE {table} AS target "
                f"USING (SELECT :{match_val} AS {match_col}) AS source "
                f"ON target.{match_col} = source.{match_col} "
                f"WHEN MATCHED THEN UPDATE SET {set_clause} "
                f"WHEN NOT MATCHED THEN INSERT ({col_list}) VALUES ({val_list});"
            ),
            params,
        )


# ---------------------------------------------------------------------------
# OTP verification query
# ---------------------------------------------------------------------------

def otp_verify_sql():
    """Return SQL to find a valid (unused, unexpired) OTP."""
    _t = tbl('otp_codes')
    if is_sqlite():
        return (
            f"SELECT id, code FROM {_t} WHERE email = :email AND code = :code AND used = 0 "
            "AND datetime(created_at, '+10 minutes') > datetime('now') "
            "ORDER BY created_at DESC LIMIT 1"
        )
    return (
        f"SELECT id, code FROM {_t} WHERE email = :email AND code = :code AND used = 0 "
        "AND DATEADD(MINUTE, 10, created_at) > GETDATE() "
        "ORDER BY created_at DESC OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY"
    )
