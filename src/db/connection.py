import os
import sys
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

_engine = None
_backend = None  # "sqlite" or "mssql"


def _detect_backend():
    """Determine which database backend to use based on env vars."""
    # If DB_BACKEND is explicitly set, use it
    explicit = os.getenv("DB_BACKEND", "").lower()
    if explicit in ("sqlite", "mssql"):
        return explicit
    # If Azure connection info is present, use mssql
    if os.getenv("AZURE_SQL_CONNECTIONSTRING") or os.getenv("AZURE_SQL_SERVER"):
        return "mssql"
    # Default to sqlite
    return "sqlite"


def get_backend():
    """Return the active backend name: 'sqlite' or 'mssql'."""
    global _backend
    if _backend is None:
        _backend = _detect_backend()
    return _backend


def is_sqlite():
    return get_backend() == "sqlite"


def switch_backend(backend):
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
        If *backend* is not ``"sqlite"`` or ``"mssql"``.
    """
    global _engine, _backend
    backend = backend.lower()
    if backend not in ("sqlite", "mssql"):
        raise ValueError(f"Invalid backend: {backend!r}. Must be 'sqlite' or 'mssql'.")

    # Dispose the old engine so connections are released
    if _engine is not None:
        try:
            _engine.dispose()
        except Exception:
            pass
        _engine = None

    _backend = backend
    os.environ["DB_BACKEND"] = backend
    # Eagerly create the new engine so callers get immediate feedback
    get_engine()
    return _backend


def test_connection():
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
                    db_path = os.getenv("DB_PATH", os.path.join(project_root, "src", "collector", "trends.db"))
                    return True, f"Connected to SQLite: {db_path}"
                else:
                    server = os.getenv("AZURE_SQL_SERVER", "Azure SQL")
                    db = os.getenv("AZURE_SQL_DB", os.getenv("AZURE_SQL_DATABASE", ""))
                    return True, f"Connected to Azure SQL: {server}/{db}"
        return False, "Connection returned no result"
    except Exception as e:
        return False, str(e)


def get_engine():
    """Return a SQLAlchemy engine (singleton).

    Supports two backends (checked in order):
    1. SQLite  — local development (default when no Azure env vars)
    2. Azure SQL Server — production
       a. AZURE_SQL_CONNECTIONSTRING  – raw ODBC connection string
       b. Individual env vars: AZURE_SQL_SERVER, AZURE_SQL_DB,
          AZURE_SQL_USER, AZURE_SQL_PASS  – SQL authentication
    """
    global _engine, _backend
    if _engine is not None:
        return _engine

    _backend = _detect_backend()

    if _backend == "sqlite":
        db_path = os.getenv("DB_PATH", os.path.join(project_root, "src", "collector", "trends.db"))
        # Resolve to absolute path so relative paths work from any cwd
        if not os.path.isabs(db_path):
            db_path = os.path.join(project_root, db_path)
        db_path = os.path.abspath(db_path)

        from sqlalchemy.pool import StaticPool
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False, "timeout": 30},
            pool_pre_ping=True,
            poolclass=StaticPool,
        )
        # Use WAL mode and relaxed sync for better compatibility with
        # network/OneDrive filesystems and WSL /mnt/c mounts.
        from sqlalchemy import event

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.close()

        return _engine

    # --- mssql ---
    conn_str = os.getenv("AZURE_SQL_CONNECTIONSTRING", "")

    # Auto-detect best available SQL Server ODBC driver
    driver = os.getenv("AZURE_SQL_DRIVER", "")
    if not driver:
        try:
            import pyodbc
            sql_drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
            # Prefer newer drivers (e.g. "ODBC Driver 18" > "ODBC Driver 17" > "SQL Server")
            preferred = sorted(sql_drivers, key=lambda d: ("ODBC Driver" in d, d), reverse=True)
            driver = preferred[0] if preferred else "ODBC Driver 18 for SQL Server"
        except Exception:
            driver = "ODBC Driver 18 for SQL Server"

    has_modern_driver = "ODBC Driver" in driver  # e.g. "ODBC Driver 17/18 for SQL Server"

    if conn_str:
        # The env var may be in ADO.NET format — convert to ODBC format.
        # Ensure it has a DRIVER= clause; inject one if missing.
        if "DRIVER=" not in conn_str.upper():
            conn_str = f"DRIVER={{{driver}}};{conn_str}"

        # Map ADO.NET keys to ODBC equivalents
        conn_str = conn_str.replace("Initial Catalog=", "DATABASE=")
        conn_str = conn_str.replace("User ID=", "UID=")
        conn_str = conn_str.replace("User Id=", "UID=")
        conn_str = conn_str.replace("Password=", "PWD=")
        # Strip ADO.NET-only keys unsupported by ODBC
        import re
        conn_str = re.sub(r'Persist Security Info=[^;]*;?\s*', '', conn_str)
        conn_str = re.sub(r'MultipleActiveResultSets=[^;]*;?\s*', '', conn_str)

        # "Active Directory Default" auth requires ODBC Driver 17+.
        # If only the legacy driver is available, fall back to SQL auth.
        if not has_modern_driver and "Active Directory" in conn_str:
            import logging
            logging.getLogger(__name__).warning(
                "Legacy 'SQL Server' ODBC driver does not support Azure AD auth. "
                "Install 'ODBC Driver 18 for SQL Server' for full Azure support. "
                "Falling back to SQL authentication."
            )
            # Strip the unsupported Authentication parameter
            import re
            conn_str = re.sub(r'Authentication="[^"]*";?\s*', '', conn_str)

        # Legacy driver needs TrustServerCertificate=yes
        if not has_modern_driver:
            conn_str = conn_str.replace("TrustServerCertificate=False", "TrustServerCertificate=Yes")

    else:
        server = os.getenv("AZURE_SQL_SERVER")
        db = os.getenv("AZURE_SQL_DB", os.getenv("AZURE_SQL_DATABASE"))
        user = os.getenv("AZURE_SQL_USER")
        pwd = os.getenv("AZURE_SQL_PASS")

        # Use TrustServerCertificate=yes for the legacy "SQL Server" driver
        encrypt_opts = "Encrypt=yes;TrustServerCertificate=no;"
        if not has_modern_driver:
            encrypt_opts = "Encrypt=yes;TrustServerCertificate=yes;"

        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={db};"
            f"UID={user};PWD={pwd};"
            f"{encrypt_opts}"
        )

    _engine = create_engine(
        f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}",
        pool_pre_ping=True,
        pool_recycle=300,
    )
    return _engine


def get_session_factory():
    """Return a sessionmaker bound to the engine (singleton)."""
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=get_engine())


def get_session():
    """Return a new ORM session."""
    return get_session_factory()()


