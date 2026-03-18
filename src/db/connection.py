"""
Database connection management.

Supports two backends:
- SQLite (local development, default)
- Azure SQL Server (production via ODBC)

The active backend is determined by environment variables and can be
switched at runtime via :func:`switch_backend`.
"""

import logging
import os
import re
import sys
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
# Module-level state
# ---------------------------------------------------------------------------

_engine: Engine | None = None
_backend: str | None = None  # "sqlite" or "mssql"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_BACKENDS = ("sqlite", "mssql")
DEFAULT_SQLITE_PATH = os.path.join(project_root, "src", "collector", "trends.db")
DEFAULT_ODBC_DRIVER = "ODBC Driver 18 for SQL Server"
POOL_RECYCLE_SECONDS = 300
SQLITE_BUSY_TIMEOUT_MS = 10000


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

def _detect_backend() -> str:
    """Determine which database backend to use based on env vars."""
    explicit = os.getenv("DB_BACKEND", "").lower()
    if explicit in VALID_BACKENDS:
        return explicit
    if os.getenv("AZURE_SQL_CONNECTIONSTRING") or os.getenv("AZURE_SQL_SERVER"):
        return "mssql"
    return "sqlite"


def get_backend() -> str:
    """Return the active backend name: ``'sqlite'`` or ``'mssql'``."""
    global _backend
    if _backend is None:
        _backend = _detect_backend()
    return _backend


def is_sqlite() -> bool:
    """Return ``True`` if the active backend is SQLite."""
    return get_backend() == "sqlite"


# ---------------------------------------------------------------------------
# Backend switching
# ---------------------------------------------------------------------------

def switch_backend(backend: str) -> str:
    """Switch the database backend at runtime.

    Parameters
    ----------
    backend : str
        Either ``"sqlite"`` or ``"mssql"``.

    Returns
    -------
    str
        The newly active backend name.

    Raises
    ------
    ValueError
        If *backend* is not a valid backend name.
    """
    global _engine, _backend
    backend = backend.lower()
    if backend not in VALID_BACKENDS:
        raise ValueError(f"Invalid backend: {backend!r}. Must be one of {VALID_BACKENDS}.")

    if _engine is not None:
        try:
            _engine.dispose()
        except Exception:
            pass
        _engine = None

    _backend = backend
    os.environ["DB_BACKEND"] = backend
    get_engine()
    return _backend


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
                backend = get_backend()
                if backend == "sqlite":
                    db_path = os.getenv("DB_PATH", DEFAULT_SQLITE_PATH)
                    return True, f"Connected to SQLite: {db_path}"
                server = os.getenv("AZURE_SQL_SERVER", "Azure SQL")
                db = os.getenv("AZURE_SQL_DB", os.getenv("AZURE_SQL_DATABASE", ""))
                return True, f"Connected to Azure SQL: {server}/{db}"
        return False, "Connection returned no result"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Engine creation
# ---------------------------------------------------------------------------

def get_engine() -> Engine:
    """Return a SQLAlchemy engine (singleton).

    Supports two backends:
    1. **SQLite** — local development (default when no Azure env vars).
    2. **Azure SQL Server** — production, via ODBC connection string or
       individual ``AZURE_SQL_*`` env vars.

    If the Azure SQL connection fails, automatically falls back to SQLite.
    """
    global _engine, _backend
    if _engine is not None:
        return _engine

    _backend = _detect_backend()

    if _backend == "sqlite":
        _engine = _create_sqlite_engine()
    else:
        try:
            engine = _create_mssql_engine()
            # Verify the connection actually works
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            _engine = engine
        except Exception as e:
            logger.warning(
                "Azure SQL connection failed, falling back to SQLite: %s", e
            )
            _backend = "sqlite"
            _engine = _create_sqlite_engine()

    return _engine


def _create_sqlite_engine() -> Engine:
    """Create and configure a SQLite engine."""
    from sqlalchemy.pool import StaticPool

    db_path = os.getenv("DB_PATH", DEFAULT_SQLITE_PATH)
    if not os.path.isabs(db_path):
        db_path = os.path.join(project_root, db_path)
    db_path = os.path.abspath(db_path)

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_pre_ping=True,
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        cursor.close()

    return engine


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


def _create_mssql_engine() -> Engine:
    """Create and configure an Azure SQL / MSSQL engine."""
    driver = _detect_odbc_driver()
    has_modern_driver = "ODBC Driver" in driver
    conn_str = os.getenv("AZURE_SQL_CONNECTIONSTRING", "")

    if conn_str:
        conn_str = _normalise_connection_string(conn_str, driver, has_modern_driver)
    else:
        conn_str = _build_connection_string(driver, has_modern_driver)

    return create_engine(
        f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}",
        pool_pre_ping=True,
        pool_recycle=POOL_RECYCLE_SECONDS,
    )


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


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def get_session_factory() -> sessionmaker:
    """Return a sessionmaker bound to the engine."""
    return sessionmaker(bind=get_engine())


def get_session() -> Session:
    """Return a new ORM session."""
    return get_session_factory()()
