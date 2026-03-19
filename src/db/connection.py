"""
Database connection management.

Uses Azure SQL Server (MSSQL) via ODBC as the sole database backend.
Provides a singleton engine with tuned connection pooling, a reusable
session factory, and a context-manager helper for clean session lifecycle.
"""

import contextlib
import logging
import os
import re
import struct
import sys
from typing import Generator
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

logger = logging.getLogger(__name__)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_engine: Engine | None = None
_session_factory: sessionmaker | None = None

# ---------------------------------------------------------------------------
# Pool & connection constants
# ---------------------------------------------------------------------------

DEFAULT_ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

# Pool sizing — tuned for a mixed workload of API reads + scraper writes.
# pool_size   : number of persistent connections kept open in the pool.
# max_overflow: extra connections allowed above pool_size under burst load.
# pool_timeout: seconds to wait for a connection before raising an error.
# pool_recycle: seconds before a connection is recycled (Azure kills idle
#               connections after ~30 min; 300 s keeps us well within that).
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
POOL_MAX_OVERFLOW = int(os.getenv("DB_POOL_MAX_OVERFLOW", "20"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
POOL_RECYCLE_SECONDS = int(os.getenv("DB_POOL_RECYCLE", "300"))


# ---------------------------------------------------------------------------
# Engine creation
# ---------------------------------------------------------------------------

def get_engine() -> Engine:
    """Return a SQLAlchemy engine (singleton) connected to Azure SQL Server.

    The engine is created once and reused for the lifetime of the process.
    Connection health is validated on first creation and on every checkout
    via ``pool_pre_ping``.
    """
    global _engine
    if _engine is not None:
        return _engine

    engine = _create_mssql_engine()
    # Verify the connection actually works
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    _engine = engine
    logger.info(
        "Database engine created (pool_size=%d, max_overflow=%d, recycle=%ds)",
        POOL_SIZE, POOL_MAX_OVERFLOW, POOL_RECYCLE_SECONDS,
    )
    return _engine


# ---------------------------------------------------------------------------
# Session factory & helpers
# ---------------------------------------------------------------------------

def get_session_factory() -> sessionmaker:
    """Return a **singleton** sessionmaker bound to the engine.

    Unlike the previous implementation that created a new ``sessionmaker``
    on every call, this caches the factory so that all callers share the
    same configuration and underlying connection pool.
    """
    global _session_factory
    if _session_factory is not None:
        return _session_factory
    _session_factory = sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,  # avoid lazy-load after commit
    )
    return _session_factory


def get_session() -> Session:
    """Return a new ORM session from the singleton factory.

    Callers are responsible for calling ``session.close()`` when done.
    Prefer :func:`session_scope` for automatic lifecycle management.
    """
    return get_session_factory()()


@contextlib.contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager that provides a transactional session scope.

    Usage::

        with session_scope() as session:
            session.add(MyModel(...))
            # auto-commits on clean exit, auto-rolls-back on exception

    This eliminates the repetitive try/except/rollback/finally/close
    pattern scattered throughout the codebase.
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Connection testing
# ---------------------------------------------------------------------------

def test_connection() -> tuple[bool, str]:
    """Test the current database connection.

    Returns
    -------
    tuple[bool, str]
        ``(True, info_message)`` on success, ``(False, error_message)`` on failure.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(text("SELECT 1")).fetchone()
            if row:
                server = os.getenv("AZURE_SQL_SERVER", "Azure SQL")
                db = os.getenv("AZURE_SQL_DB", os.getenv("AZURE_SQL_DATABASE", ""))
                return True, f"Connected to Azure SQL: {server}/{db}"
        return False, "Connection returned no result"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# ODBC driver detection
# ---------------------------------------------------------------------------

def _detect_odbc_driver() -> str:
    """Auto-detect the best available SQL Server ODBC driver."""
    driver = os.getenv("AZURE_SQL_DRIVER", "")
    if driver:
        return driver
    try:
        import pyodbc
        sql_drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
        preferred = sorted(sql_drivers, key=lambda d: ("ODBC Driver" in d, d), reverse=True)
        return preferred[0] if preferred else DEFAULT_ODBC_DRIVER
    except Exception:
        return DEFAULT_ODBC_DRIVER


# ---------------------------------------------------------------------------
# Engine builders
# ---------------------------------------------------------------------------

def _uses_ad_auth(conn_str: str) -> bool:
    """Return True if the connection string uses Active Directory authentication."""
    return "Active Directory" in conn_str or "ActiveDirectory" in conn_str


def _create_mssql_engine() -> Engine:
    """Create and configure an Azure SQL / MSSQL engine with tuned pooling."""
    driver = _detect_odbc_driver()
    has_modern_driver = "ODBC Driver" in driver
    raw_conn_str = os.getenv("AZURE_SQL_CONNECTIONSTRING", "")

    if raw_conn_str:
        conn_str = _normalise_connection_string(raw_conn_str, driver, has_modern_driver)
    else:
        conn_str = _build_connection_string(driver, has_modern_driver)

    pool_kwargs = dict(
        pool_pre_ping=True,
        pool_size=POOL_SIZE,
        max_overflow=POOL_MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT,
        pool_recycle=POOL_RECYCLE_SECONDS,
    )

    # If using Azure AD auth, use token-based approach via azure-identity
    if _uses_ad_auth(raw_conn_str or conn_str):
        return _create_mssql_engine_with_token(conn_str, driver, pool_kwargs)

    return create_engine(
        f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}",
        **pool_kwargs,
    )


def _get_azure_token() -> bytes:
    """Obtain an Azure AD access token and encode it for ODBC."""
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    token = credential.get_token("https://database.windows.net/.default")
    token_bytes = token.token.encode("UTF-16-LE")
    return struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)


def _create_mssql_engine_with_token(conn_str: str, driver: str, pool_kwargs: dict) -> Engine:
    """Create an MSSQL engine using Azure AD token authentication."""
    # Strip any Authentication= attribute from the ODBC string
    conn_str = re.sub(r'Authentication="[^"]*";?\s*', "", conn_str)
    conn_str = re.sub(r'Authentication=[^;]*;?\s*', "", conn_str)

    if "DRIVER=" not in conn_str.upper():
        conn_str = f"DRIVER={{{driver}}};{conn_str}"

    SQL_COPT_SS_ACCESS_TOKEN = 1256

    def creator():
        import pyodbc
        token_struct = _get_azure_token()
        return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})

    return create_engine(
        "mssql+pyodbc://",
        creator=creator,
        **pool_kwargs,
    )


# ---------------------------------------------------------------------------
# Connection string helpers
# ---------------------------------------------------------------------------

def _normalise_connection_string(conn_str: str, driver: str, has_modern_driver: bool) -> str:
    """Normalise an ADO.NET / ODBC connection string."""
    if "DRIVER=" not in conn_str.upper():
        conn_str = f"DRIVER={{{driver}}};{conn_str}"

    # Map ADO.NET keys to ODBC equivalents
    replacements = {
        "Initial Catalog=": "DATABASE=",
        "User ID=": "UID=",
        "User Id=": "UID=",
        "Password=": "PWD=",
    }
    for old, new in replacements.items():
        conn_str = conn_str.replace(old, new)

    # Map ADO.NET boolean values to ODBC equivalents
    conn_str = conn_str.replace("Encrypt=True", "Encrypt=yes")
    conn_str = conn_str.replace("Encrypt=False", "Encrypt=no")
    conn_str = conn_str.replace("TrustServerCertificate=True", "TrustServerCertificate=yes")
    conn_str = conn_str.replace("TrustServerCertificate=False", "TrustServerCertificate=no")

    # Strip ADO.NET-only keys unsupported by ODBC
    conn_str = re.sub(r"Persist Security Info=[^;]*;?\s*", "", conn_str)
    conn_str = re.sub(r"MultipleActiveResultSets=[^;]*;?\s*", "", conn_str)

    if not has_modern_driver and "Active Directory" in conn_str:
        logger.warning(
            "Legacy 'SQL Server' ODBC driver does not support Azure AD auth. "
            "Install '%s' for full Azure support. Falling back to SQL authentication.",
            DEFAULT_ODBC_DRIVER,
        )
        conn_str = re.sub(r'Authentication="[^"]*";?\s*', "", conn_str)

    if not has_modern_driver:
        conn_str = conn_str.replace("TrustServerCertificate=False", "TrustServerCertificate=Yes")

    return conn_str


def _build_connection_string(driver: str, has_modern_driver: bool) -> str:
    """Build an ODBC connection string from individual env vars."""
    server = os.getenv("AZURE_SQL_SERVER")
    db = os.getenv("AZURE_SQL_DB", os.getenv("AZURE_SQL_DATABASE"))
    user = os.getenv("AZURE_SQL_USER")
    pwd = os.getenv("AZURE_SQL_PASS")

    trust_cert = "no" if has_modern_driver else "yes"
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={db};"
        f"UID={user};PWD={pwd};"
        f"Encrypt=yes;TrustServerCertificate={trust_cert};"
    )
