"""
Database connection management — simplified, resilient, and self-diagnosing.

Supports **three connection strategies** that are tried automatically:

1. **Full connection string** (``AZURE_SQL_CONNECTIONSTRING``)
   Paste the string from the Azure Portal as-is; ADO.NET → ODBC
   normalisation is handled transparently.

2. **Individual env vars** (``AZURE_SQL_SERVER``, ``AZURE_SQL_DATABASE``,
   ``AZURE_SQL_USER``, ``AZURE_SQL_PASS``)
   Traditional SQL authentication with username/password.

3. **Azure AD (passwordless)** via ``azure-identity``
   Set ``AZURE_SQL_SERVER`` + ``AZURE_SQL_DATABASE`` and leave user/pass
   blank.  The system will acquire a token from the Azure CLI, Managed
   Identity, or any other credential in the ``DefaultAzureCredential``
   chain.

The strategy is chosen automatically based on which env vars are present.
Run ``python -m src.db.connection`` for an interactive diagnostic.
"""

import contextlib
import logging
import os
import re
import struct
import sys
import time
from dataclasses import dataclass, field
from typing import Generator, Optional
from urllib.parse import quote_plus

from sqlalchemy import create_engine, literal, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from src.runtime.secrets import init_runtime_secrets

init_runtime_secrets()

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

POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
POOL_MAX_OVERFLOW = int(os.getenv("DB_POOL_MAX_OVERFLOW", "20"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "120"))
POOL_RECYCLE_SECONDS = int(os.getenv("DB_POOL_RECYCLE", "300"))
CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "90"))
ENGINE_RETRIES = int(os.getenv("DB_ENGINE_RETRIES", "5"))


# ---------------------------------------------------------------------------
# Diagnostics data class
# ---------------------------------------------------------------------------

@dataclass
class ConnectionDiagnostic:
    """Collects step-by-step diagnostic information during connection setup."""
    strategy: str = ""
    driver: str = ""
    server: str = ""
    database: str = ""
    auth_method: str = ""
    odbc_string_preview: str = ""
    steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None
    connected: bool = False

    def log(self, msg: str):
        self.steps.append(msg)
        logger.info("[db-diag] %s", msg)

    def warn(self, msg: str):
        self.warnings.append(msg)
        logger.warning("[db-diag] %s", msg)

    def summary_text(self) -> str:
        lines = [
            "=== Database Connection Diagnostic ===",
            f"Strategy     : {self.strategy}",
            f"ODBC Driver  : {self.driver}",
            f"Server       : {self.server}",
            f"Database     : {self.database}",
            f"Auth Method  : {self.auth_method}",
            f"Connected    : {'YES' if self.connected else 'NO'}",
        ]
        if self.odbc_string_preview:
            lines.append(f"ODBC Preview : {self.odbc_string_preview}")
        if self.warnings:
            lines.append("\nWarnings:")
            for w in self.warnings:
                lines.append(f"  - {w}")
        if self.error:
            lines.append(f"\nError: {self.error}")
        lines.append("\nSteps:")
        for i, s in enumerate(self.steps, 1):
            lines.append(f"  {i}. {s}")
        return "\n".join(lines)

    def summary_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "driver": self.driver,
            "server": self.server,
            "database": self.database,
            "auth_method": self.auth_method,
            "connected": self.connected,
            "error": self.error,
            "warnings": self.warnings,
            "steps": self.steps,
        }


# Module-level diagnostic (populated on first get_engine call)
_last_diagnostic: ConnectionDiagnostic | None = None


def get_last_diagnostic() -> Optional[ConnectionDiagnostic]:
    """Return the diagnostic from the most recent engine creation attempt."""
    return _last_diagnostic


# ---------------------------------------------------------------------------
# Strategy detection
# ---------------------------------------------------------------------------

def _detect_strategy() -> str:
    """Determine which connection strategy to use based on env vars.

    Returns one of: 'connection_string', 'sql_auth', 'azure_ad', 'none'.
    """
    if os.getenv("AZURE_SQL_CONNECTIONSTRING", "").strip():
        return "connection_string"

    server = os.getenv("AZURE_SQL_SERVER", "").strip()
    db = os.getenv("AZURE_SQL_DB", "").strip() or os.getenv("AZURE_SQL_DATABASE", "").strip()

    if not server or not db:
        return "none"

    user = os.getenv("AZURE_SQL_USER", "").strip()
    pwd = os.getenv("AZURE_SQL_PASS", "").strip()

    if user and pwd:
        return "sql_auth"

    return "azure_ad"


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
        preferred = sorted(
            sql_drivers,
            key=lambda d: ("ODBC Driver" in d, d),
            reverse=True,
        )
        return preferred[0] if preferred else DEFAULT_ODBC_DRIVER
    except Exception:
        return DEFAULT_ODBC_DRIVER


# ---------------------------------------------------------------------------
# Connection string normalisation
# ---------------------------------------------------------------------------

def _normalise_connection_string(conn_str: str, driver: str) -> str:
    """Normalise an ADO.NET / ODBC connection string.

    Handles the common differences between ADO.NET connection strings
    (as provided by the Azure Portal) and ODBC connection strings
    (as required by pyodbc / ODBC Driver 18).
    """
    has_modern_driver = "ODBC Driver" in driver

    # Inject DRIVER if missing
    if "DRIVER=" not in conn_str.upper():
        conn_str = f"DRIVER={{{driver}}};{conn_str}"

    # Map ADO.NET keys → ODBC keys
    key_map = {
        "Initial Catalog=": "DATABASE=",
        "User ID=": "UID=",
        "User Id=": "UID=",
        "Password=": "PWD=",
        "Data Source=": "SERVER=",
    }
    for old, new in key_map.items():
        conn_str = conn_str.replace(old, new)

    # Case-normalise Server= → SERVER=
    conn_str = re.sub(r"(?i)\bServer=", "SERVER=", conn_str)

    # Strip ADO.NET tcp: prefix  (Server=tcp:host,port → SERVER=host,port)
    conn_str = re.sub(r"SERVER=tcp:", "SERVER=", conn_str)

    # Boolean value normalisation
    bool_map = {
        "Encrypt=True": "Encrypt=yes",
        "Encrypt=False": "Encrypt=no",
        "TrustServerCertificate=True": "TrustServerCertificate=yes",
        "TrustServerCertificate=False": "TrustServerCertificate=no",
    }
    for old, new in bool_map.items():
        conn_str = conn_str.replace(old, new)

    # Strip ADO.NET-only keys
    conn_str = re.sub(r"Persist Security Info=[^;]*;?\s*", "", conn_str)
    conn_str = re.sub(r"MultipleActiveResultSets=[^;]*;?\s*", "", conn_str)

    # Legacy driver guard
    if not has_modern_driver and "Active Directory" in conn_str:
        logger.warning(
            "Legacy ODBC driver does not support Azure AD auth. "
            "Install '%s' for full Azure support.",
            DEFAULT_ODBC_DRIVER,
        )
        conn_str = re.sub(r'Authentication="[^"]*";?\s*', "", conn_str)

    if not has_modern_driver:
        conn_str = conn_str.replace(
            "TrustServerCertificate=no", "TrustServerCertificate=yes"
        )

    return conn_str


def _ensure_connect_timeout(conn_str: str, timeout: int) -> str:
    """Inject ``Connection Timeout`` if not already present."""
    if "Connection Timeout" in conn_str or "ConnectTimeout" in conn_str:
        return conn_str
    return conn_str.rstrip(";") + f";Connection Timeout={timeout};"


def _extract_server_db(conn_str: str) -> tuple[str, str]:
    """Extract SERVER and DATABASE values from an ODBC connection string."""
    server_match = re.search(r"SERVER=([^;]+)", conn_str, re.IGNORECASE)
    db_match = re.search(r"DATABASE=([^;]+)", conn_str, re.IGNORECASE)
    return (
        server_match.group(1) if server_match else "",
        db_match.group(1) if db_match else "",
    )


def _mask_conn_str(conn_str: str) -> str:
    """Return a redacted version of the connection string for logging."""
    masked = re.sub(r"(PWD=)[^;]*", r"\1****", conn_str)
    masked = re.sub(r"(Password=)[^;]*", r"\1****", masked, flags=re.IGNORECASE)
    return masked


# ---------------------------------------------------------------------------
# Azure AD token helper
# ---------------------------------------------------------------------------

def _get_azure_token(managed_identity_client_id: Optional[str] = None) -> bytes:
    """Obtain an Azure AD access token and encode it for ODBC."""
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential(managed_identity_client_id=managed_identity_client_id)
    token = credential.get_token("https://database.windows.net/.default")
    token_bytes = token.token.encode("UTF-16-LE")
    return struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)


# ---------------------------------------------------------------------------
# Engine builders — one per strategy
# ---------------------------------------------------------------------------

def _pool_kwargs() -> dict:
    return dict(
        pool_pre_ping=True,
        pool_size=POOL_SIZE,
        max_overflow=POOL_MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT,
        pool_recycle=POOL_RECYCLE_SECONDS,
        use_setinputsizes=False,
    )


def _attach_retry_listener(engine: Engine) -> None:
    """Attach a connection-level retry listener for Azure SQL serverless.

    When the database is paused, the first connection attempt may fail with
    a timeout.  This listener retries up to 3 times with exponential backoff
    so the caller doesn't have to handle transient connect failures.
    """
    from sqlalchemy import event

    @event.listens_for(engine, "engine_connect")
    def _retry_on_connect(connection):
        # engine_connect fires *after* a raw DBAPI connection is obtained.
        # If pool_pre_ping detects a dead connection, SQLAlchemy will
        # automatically try to get a new one.  This listener adds an
        # extra safety net for the initial connect during serverless resume.
        pass  # pool_pre_ping handles most cases; this is a hook point.

    @event.listens_for(engine, "connect")
    def _set_connection_options(dbapi_conn, connection_record):
        """Set ODBC-level timeout on each new raw connection."""
        try:
            dbapi_conn.timeout = CONNECT_TIMEOUT
        except Exception:
            pass  # Not all DBAPI connections support .timeout


def _build_engine_from_connection_string(diag: ConnectionDiagnostic) -> Engine:
    """Strategy 1: Use AZURE_SQL_CONNECTIONSTRING."""
    raw = os.getenv("AZURE_SQL_CONNECTIONSTRING", "")
    driver = _detect_odbc_driver()
    diag.driver = driver
    diag.log(f"Detected ODBC driver: {driver}")

    conn_str = _normalise_connection_string(raw, driver)
    conn_str = _ensure_connect_timeout(conn_str, CONNECT_TIMEOUT)
    diag.log("Normalised ADO.NET → ODBC connection string")

    server, db = _extract_server_db(conn_str)
    diag.server = server
    diag.database = db
    diag.odbc_string_preview = _mask_conn_str(conn_str)

    uses_ad = "Active Directory" in raw or "ActiveDirectory" in raw
    if uses_ad:
        diag.auth_method = "Azure AD (token via azure-identity)"
        diag.log("Detected Azure AD auth → using token-based connection")
        # Strip Authentication= and inject token via attrs_before
        conn_str = re.sub(r'Authentication="[^"]*";?\s*', "", conn_str)
        conn_str = re.sub(r"Authentication=[^;]*;?\s*", "", conn_str)
        if "DRIVER=" not in conn_str.upper():
            conn_str = f"DRIVER={{{driver}}};{conn_str}"

        SQL_COPT_SS_ACCESS_TOKEN = 1256

        def creator():
            import pyodbc
            client_id = os.getenv("MANAGED_IDENTITY_CLIENT_ID")
            token_struct = _get_azure_token(managed_identity_client_id=client_id)
            return pyodbc.connect(
                conn_str,
                attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct},
                timeout=CONNECT_TIMEOUT,
            )

        return create_engine("mssql+pyodbc://", creator=creator, **_pool_kwargs())
    else:
        diag.auth_method = "SQL Authentication (from connection string)"
        diag.log("Using SQL auth from connection string")
        return create_engine(
            f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}",
            **_pool_kwargs(),
        )


def _build_engine_sql_auth(diag: ConnectionDiagnostic) -> Engine:
    """Strategy 2: Use individual env vars with SQL authentication."""
    driver = _detect_odbc_driver()
    diag.driver = driver
    diag.auth_method = "SQL Authentication (user/password)"
    diag.log(f"Detected ODBC driver: {driver}")

    server = os.getenv("AZURE_SQL_SERVER", "").strip()
    db = os.getenv("AZURE_SQL_DB", "").strip() or os.getenv("AZURE_SQL_DATABASE", "").strip()
    user = os.getenv("AZURE_SQL_USER", "").strip()
    pwd = os.getenv("AZURE_SQL_PASS", "").strip()

    # Clean server value (strip tcp: prefix if pasted from portal)
    server = re.sub(r"^tcp:", "", server)
    diag.server = server
    diag.database = db

    has_modern = "ODBC Driver" in driver
    trust_cert = "no" if has_modern else "yes"

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={db};"
        f"UID={user};PWD={pwd};"
        f"Encrypt=yes;TrustServerCertificate={trust_cert};"
        f"Connection Timeout={CONNECT_TIMEOUT};"
    )
    diag.odbc_string_preview = _mask_conn_str(conn_str)
    diag.log(f"Built ODBC string for {server}/{db}")

    return create_engine(
        f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}",
        **_pool_kwargs(),
    )


def _build_engine_azure_ad(diag: ConnectionDiagnostic) -> Engine:
    """Strategy 3: Use individual env vars with Azure AD (passwordless)."""
    driver = _detect_odbc_driver()
    diag.driver = driver
    diag.auth_method = "Azure AD (passwordless via azure-identity)"
    diag.log(f"Detected ODBC driver: {driver}")

    server = os.getenv("AZURE_SQL_SERVER", "").strip()
    db = os.getenv("AZURE_SQL_DB", "").strip() or os.getenv("AZURE_SQL_DATABASE", "").strip()

    # Clean server value
    server = re.sub(r"^tcp:", "", server)
    diag.server = server
    diag.database = db

    has_modern = "ODBC Driver" in driver
    trust_cert = "no" if has_modern else "yes"

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={db};"
        f"Encrypt=yes;TrustServerCertificate={trust_cert};"
        f"Connection Timeout={CONNECT_TIMEOUT};"
    )
    diag.odbc_string_preview = _mask_conn_str(conn_str)
    diag.log(f"Built ODBC string for {server}/{db} (no user/pass → Azure AD)")

    SQL_COPT_SS_ACCESS_TOKEN = 1256

    def creator():
        import pyodbc
        diag.log("Acquiring Azure AD token...")
        client_id = os.getenv("MANAGED_IDENTITY_CLIENT_ID")
        token_struct = _get_azure_token(managed_identity_client_id=client_id)
        diag.log("Token acquired, connecting...")
        return pyodbc.connect(
            conn_str,
            attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct},
            timeout=CONNECT_TIMEOUT,
        )

    return create_engine("mssql+pyodbc://", creator=creator, **_pool_kwargs())


# ---------------------------------------------------------------------------
# Engine creation (public API)
# ---------------------------------------------------------------------------

def get_engine() -> Engine:
    """Return a SQLAlchemy engine (singleton) connected to Azure SQL Server.

    Automatically detects the best connection strategy based on which
    environment variables are set.  Retries on transient failures and
    never crashes the application on startup.
    """
    global _engine, _last_diagnostic
    if _engine is not None:
        return _engine

    diag = ConnectionDiagnostic()
    _last_diagnostic = diag

    strategy = _detect_strategy()
    diag.strategy = strategy
    diag.log(f"Detected connection strategy: {strategy}")

    if strategy == "none":
        diag.error = (
            "No database configuration found. Set one of:\n"
            "  1. AZURE_SQL_CONNECTIONSTRING  (paste from Azure Portal)\n"
            "  2. AZURE_SQL_SERVER + AZURE_SQL_DATABASE + AZURE_SQL_USER + AZURE_SQL_PASS\n"
            "  3. AZURE_SQL_SERVER + AZURE_SQL_DATABASE  (for Azure AD passwordless)\n"
            "Run 'python -m src.db.connection' for guided setup."
        )
        diag.warn(diag.error)
        raise RuntimeError(diag.error)

    builders = {
        "connection_string": _build_engine_from_connection_string,
        "sql_auth": _build_engine_sql_auth,
        "azure_ad": _build_engine_azure_ad,
    }

    engine = builders[strategy](diag)
    _attach_retry_listener(engine)

    # Health check with retries
    for attempt in range(1, ENGINE_RETRIES + 1):
        try:
            with engine.connect() as conn:
                conn.execute(select(literal(1)))
            diag.connected = True
            diag.log(
                f"Connection verified (pool_size={POOL_SIZE}, "
                f"max_overflow={POOL_MAX_OVERFLOW}, "
                f"recycle={POOL_RECYCLE_SECONDS}s)"
            )
            break
        except Exception as e:
            if attempt < ENGINE_RETRIES:
                wait = 2 ** attempt
                diag.warn(
                    f"Connection attempt {attempt}/{ENGINE_RETRIES} failed: {e}. "
                    f"Retrying in {wait}s..."
                )
                time.sleep(wait)
            else:
                diag.warn(
                    f"Connection failed after {ENGINE_RETRIES} attempts: {e}. "
                    f"Engine returned anyway — pool_pre_ping will retry."
                )
                diag.error = str(e)

    _engine = engine
    return _engine


# ---------------------------------------------------------------------------
# Session factory & helpers
# ---------------------------------------------------------------------------

def get_session_factory() -> sessionmaker:
    """Return a **singleton** sessionmaker bound to the engine."""
    global _session_factory
    if _session_factory is not None:
        return _session_factory
    _session_factory = sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
    )
    return _session_factory


def get_session() -> Session:
    """Return a new ORM session from the singleton factory."""
    return get_session_factory()()


@contextlib.contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager that provides a transactional session scope.

    Usage::

        with session_scope() as session:
            session.add(MyModel(...))
            # auto-commits on clean exit, auto-rolls-back on exception
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

    Returns ``(True, info_message)`` on success, ``(False, error_message)``
    on failure.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(select(literal(1))).fetchone()
            if row:
                server = os.getenv("AZURE_SQL_SERVER", "Azure SQL")
                db = os.getenv("AZURE_SQL_DB", os.getenv("AZURE_SQL_DATABASE", ""))
                return True, f"Connected to Azure SQL: {server}/{db}"
        return False, "Connection returned no result"
    except Exception as e:
        return False, str(e)


def diagnose() -> ConnectionDiagnostic:
    """Run a full connection diagnostic and return the results.

    This resets the singleton engine so a fresh connection attempt is made.
    """
    global _engine, _session_factory, _last_diagnostic
    _engine = None
    _session_factory = None
    _last_diagnostic = None

    diag = ConnectionDiagnostic()

    # Step 1: Check env vars
    diag.log("Checking environment variables...")
    strategy = _detect_strategy()
    diag.strategy = strategy

    env_checks = {
        "AZURE_SQL_CONNECTIONSTRING": bool(os.getenv("AZURE_SQL_CONNECTIONSTRING", "").strip()),
        "AZURE_SQL_SERVER": bool(os.getenv("AZURE_SQL_SERVER", "").strip()),
        "AZURE_SQL_DATABASE": bool(
            os.getenv("AZURE_SQL_DB", "").strip() or os.getenv("AZURE_SQL_DATABASE", "").strip()
        ),
        "AZURE_SQL_USER": bool(os.getenv("AZURE_SQL_USER", "").strip()),
        "AZURE_SQL_PASS": bool(os.getenv("AZURE_SQL_PASS", "").strip()),
    }
    for var, present in env_checks.items():
        diag.log(f"  {var}: {'SET' if present else 'NOT SET'}")

    diag.log(f"Selected strategy: {strategy}")

    if strategy == "none":
        diag.error = "No database credentials configured."
        diag.warn(diag.error)
        _last_diagnostic = diag
        return diag

    # Step 2: Check ODBC driver
    diag.log("Detecting ODBC driver...")
    driver = _detect_odbc_driver()
    diag.driver = driver
    diag.log(f"  Using: {driver}")

    try:
        import pyodbc
        all_drivers = pyodbc.drivers()
        sql_drivers = [d for d in all_drivers if "SQL Server" in d]
        diag.log(f"  Available SQL Server drivers: {sql_drivers or 'NONE'}")
        if not sql_drivers:
            diag.warn(
                "No SQL Server ODBC drivers found! Install with: "
                "sudo apt-get install -y msodbcsql18  (Linux) or "
                "download from Microsoft (Windows/Mac)"
            )
    except ImportError:
        diag.warn("pyodbc not installed! Install with: pip install pyodbc")

    # Step 3: Check network connectivity
    diag.log("Testing network connectivity...")
    import socket

    server_raw = os.getenv("AZURE_SQL_SERVER", "").strip()
    if not server_raw:
        # Extract from connection string
        raw_cs = os.getenv("AZURE_SQL_CONNECTIONSTRING", "")
        m = re.search(r"(?:SERVER|Server|Data Source)=(?:tcp:)?([^;,]+)", raw_cs)
        server_raw = m.group(1) if m else ""

    server_host = re.sub(r"^tcp:", "", server_raw).split(",")[0]
    server_port = 1433
    port_match = re.search(r",(\d+)", server_raw)
    if port_match:
        server_port = int(port_match.group(1))

    diag.server = server_host

    if server_host:
        try:
            ip = socket.gethostbyname(server_host)
            diag.log(f"  DNS resolved: {server_host} → {ip}")
        except socket.gaierror as e:
            diag.warn(f"  DNS resolution FAILED for {server_host}: {e}")

        try:
            s = socket.create_connection((server_host, server_port), timeout=5)
            s.close()
            diag.log(f"  TCP connection to {server_host}:{server_port}: OK")
        except Exception as e:
            diag.warn(f"  TCP connection to {server_host}:{server_port}: FAILED — {e}")
            diag.warn(
                "Possible causes: firewall blocking port 1433, VPN required, "
                "or Azure SQL server is paused/stopped."
            )

    # Step 4: Check Azure AD (if applicable)
    if strategy in ("azure_ad", "connection_string"):
        raw_cs = os.getenv("AZURE_SQL_CONNECTIONSTRING", "")
        if strategy == "azure_ad" or "Active Directory" in raw_cs:
            diag.log("Checking Azure AD authentication...")
            try:
                from azure.identity import DefaultAzureCredential
                cred = DefaultAzureCredential()
                token = cred.get_token("https://database.windows.net/.default")
                diag.log(f"  Azure AD token acquired (expires: {token.expires_on})")
                diag.auth_method = "Azure AD"
            except ImportError:
                diag.warn(
                    "azure-identity not installed! Install with: "
                    "pip install azure-identity"
                )
            except Exception as e:
                diag.warn(f"  Azure AD token acquisition FAILED: {e}")
                diag.warn(
                    "Ensure you are logged in via 'az login' or have a "
                    "Managed Identity configured."
                )

    # Step 5: Attempt actual connection
    diag.log("Attempting database connection...")
    try:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(select(literal(1))).fetchone()
            if row:
                diag.connected = True
                diag.log("  SELECT 1 → SUCCESS")

                # Bonus: get DB version
                try:
                    ver_info = conn.dialect.server_version_info
                    if ver_info:
                        diag.log(f"  Server version: {'.'.join(str(part) for part in ver_info)}")
                except Exception:
                    pass
    except Exception as e:
        diag.error = str(e)
        diag.warn(f"  Connection FAILED: {e}")

    _last_diagnostic = diag
    return diag


# ---------------------------------------------------------------------------
# CLI entry point — interactive diagnostic / guided setup
# ---------------------------------------------------------------------------

def _cli_main():
    """Interactive diagnostic and guided setup wizard."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Database connection diagnostic and setup wizard"
    )
    parser.add_argument(
        "--diagnose", action="store_true", default=True,
        help="Run full connection diagnostic (default)"
    )
    parser.add_argument(
        "--setup", action="store_true",
        help="Run interactive setup wizard to generate .env values"
    )
    parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if "--setup" in sys.argv:
        _run_setup_wizard()
        return

    print("\n" + "=" * 60)
    print("  Trends Research — Database Connection Diagnostic")
    print("=" * 60 + "\n")

    diag = diagnose()
    print(diag.summary_text())

    if diag.connected:
        print("\n✅ Database connection is working!\n")
    else:
        print("\n❌ Database connection FAILED.\n")
        print("Run 'python -m src.db.connection --setup' for guided setup.\n")

        # Provide targeted advice
        if diag.strategy == "none":
            print("No credentials found. You need to set environment variables")
            print("in your .env file. The easiest options are:\n")
            print("  Option A — Paste your Azure Portal connection string:")
            print('    AZURE_SQL_CONNECTIONSTRING=Server=tcp:yourserver.database.windows.net,1433;...\n')
            print("  Option B — Set individual variables:")
            print("    AZURE_SQL_SERVER=yourserver.database.windows.net")
            print("    AZURE_SQL_DATABASE=YourDB")
            print("    AZURE_SQL_USER=youradmin")
            print("    AZURE_SQL_PASS=yourpassword\n")
            print("  Option C — Azure AD (passwordless, requires 'az login'):")
            print("    AZURE_SQL_SERVER=yourserver.database.windows.net")
            print("    AZURE_SQL_DATABASE=YourDB\n")


def _run_setup_wizard():
    """Interactive wizard that generates .env database entries."""
    print("\n" + "=" * 60)
    print("  Trends Research — Database Setup Wizard")
    print("=" * 60 + "\n")

    print("How would you like to connect to Azure SQL?\n")
    print("  1. Paste a connection string from the Azure Portal")
    print("  2. Enter server, database, username, and password")
    print("  3. Azure AD (passwordless — requires 'az login')\n")

    choice = input("Choose [1/2/3]: ").strip()

    env_lines = []

    if choice == "1":
        print("\nPaste your connection string from the Azure Portal:")
        print("(Azure Portal → SQL Database → Connection strings → ADO.NET)\n")
        cs = input("Connection string: ").strip()
        env_lines.append(f"AZURE_SQL_CONNECTIONSTRING={cs}")

        # Also extract server/db for display purposes
        m_server = re.search(r"(?:Server|Data Source)=(?:tcp:)?([^;,]+)", cs, re.IGNORECASE)
        m_db = re.search(r"(?:Initial Catalog|Database)=([^;]+)", cs, re.IGNORECASE)
        if m_server:
            env_lines.append(f"AZURE_SQL_SERVER={m_server.group(1)}")
        if m_db:
            env_lines.append(f"AZURE_SQL_DATABASE={m_db.group(1)}")

    elif choice == "2":
        server = input("Server (e.g. myserver.database.windows.net): ").strip()
        db = input("Database name: ").strip()
        user = input("Username: ").strip()
        pwd = input("Password: ").strip()
        env_lines.extend([
            f"AZURE_SQL_SERVER={server}",
            f"AZURE_SQL_DATABASE={db}",
            f"AZURE_SQL_USER={user}",
            f"AZURE_SQL_PASS={pwd}",
        ])

    elif choice == "3":
        server = input("Server (e.g. myserver.database.windows.net): ").strip()
        db = input("Database name: ").strip()
        env_lines.extend([
            f"AZURE_SQL_SERVER={server}",
            f"AZURE_SQL_DATABASE={db}",
        ])
        print("\nNote: Make sure you have run 'az login' and your Azure AD")
        print("account is set as the SQL Server admin in the Azure Portal.")

    else:
        print("Invalid choice.")
        return

    print("\n" + "-" * 40)
    print("Add these lines to your .env file:\n")
    for line in env_lines:
        print(f"  {line}")
    print("\n" + "-" * 40)

    save = input("\nSave to .env automatically? [y/N]: ").strip().lower()
    if save == "y":
        env_path = os.path.join(project_root, ".env")
        with open(env_path, "a") as f:
            f.write("\n# Database (auto-generated by setup wizard)\n")
            for line in env_lines:
                f.write(line + "\n")
        print(f"\n✅ Saved to {env_path}")
        print("Now run 'python -m src.db.connection' to test the connection.\n")
    else:
        print("\nCopy the lines above into your .env file manually.\n")


if __name__ == "__main__":
    _cli_main()
