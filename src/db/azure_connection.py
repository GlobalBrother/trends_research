"""Azure SQL Database connection management using SQLAlchemy."""

import logging
import os
import struct
import sys
import urllib.parse

from sqlalchemy import create_engine, event
from dotenv import load_dotenv

load_dotenv()

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

logger = logging.getLogger(__name__)


def _get_azure_token():
    """Get an Azure AD access token for SQL Database using azure-identity."""
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    token = credential.get_token("https://database.windows.net/.default")
    token_bytes = token.token.encode("UTF-16-LE")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
    return token_struct


def _parse_connection_string(conn_str: str) -> dict:
    """Parse a semicolon-delimited connection string into a dict."""
    params = {}
    for part in conn_str.split(";"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            params[key.strip()] = value.strip().strip('"').strip("'")
    return params


def _build_odbc_url(server: str, database: str, driver: str, *,
                    encrypt: str = "yes", trust_cert: str = "no",
                    timeout: str = "30", uid: str = None, pwd: str = None) -> str:
    """Build an ODBC connection URL for SQLAlchemy."""
    parts = [
        f"DRIVER={driver}",
        f"SERVER={server}",
        f"DATABASE={database}",
    ]
    if uid and pwd:
        parts.extend([f"UID={uid}", f"PWD={pwd}"])
    parts.extend([
        f"Encrypt={encrypt}",
        f"TrustServerCertificate={trust_cert}",
        f"Connection Timeout={timeout}",
    ])
    odbc_str = ";".join(parts) + ";"
    params = urllib.parse.quote_plus(odbc_str)
    return f"mssql+pyodbc:///?odbc_connect={params}"


def _create_engine_from_connection_string(conn_str: str, driver: str):
    """Attempt to create an engine from AZURE_SQL_CONNECTIONSTRING."""
    # If it's already a SQLAlchemy URL, use it directly
    if "://" in conn_str:
        engine = create_engine(conn_str)
        with engine.connect():
            logger.info("Connected using AZURE_SQL_CONNECTIONSTRING (direct URL).")
        return engine

    parsed = _parse_connection_string(conn_str)
    auth_mode = parsed.get("Authentication", "").lower().replace(" ", "")
    use_ad = auth_mode in (
        "activedirectorydefault",
        "activedirectoryinteractive",
        "activedirectoryserviceprincipal",
    )

    server = parsed.get("Server", parsed.get("server", ""))
    database = parsed.get("Initial Catalog", parsed.get("Database", ""))
    encrypt = parsed.get("Encrypt", "yes")
    trust_cert = parsed.get("TrustServerCertificate", "no")
    timeout = parsed.get("Connection Timeout", "30")
    uid = parsed.get("UID", parsed.get("User ID", parsed.get("User Id", None)))
    pwd = parsed.get("PWD", parsed.get("Password", None))

    url = _build_odbc_url(server, database, driver,
                          encrypt=encrypt, trust_cert=trust_cert, timeout=timeout,
                          uid=uid, pwd=pwd)
    engine = create_engine(url)

    if use_ad:
        @event.listens_for(engine, "do_connect")
        def _provide_token(dialect, conn_rec, cargs, cparams):
            cargs[0] = cargs[0].replace(";Trusted_Connection=Yes", "")
            SQL_COPT_SS_ACCESS_TOKEN = 1256
            cparams["attrs_before"] = {SQL_COPT_SS_ACCESS_TOKEN: _get_azure_token()}

    with engine.connect():
        logger.info("Connected using AZURE_SQL_CONNECTIONSTRING.")
    return engine


def _create_engine_from_env_vars(driver: str):
    """Attempt to create an engine from individual environment variables."""
    server = os.getenv("AZURE_SQL_SERVER")
    database = os.getenv("AZURE_SQL_DATABASE", os.getenv("AZURE_SQL_DB"))
    username = os.getenv("AZURE_SQL_USER")
    password = os.getenv("AZURE_SQL_PASSWORD", os.getenv("AZURE_SQL_PASS"))

    if not all([server, database, username, password]):
        return None

    url = _build_odbc_url(server, database, driver, uid=username, pwd=password)
    engine = create_engine(url)
    with engine.connect():
        logger.info("Connected using individual Azure SQL environment variables.")
    return engine


def get_azure_engine():
    """
    Create an SQLAlchemy engine for Azure SQL Database.

    Supports Azure AD authentication via azure-identity,
    as well as SQL authentication via individual env vars.

    Returns:
        Engine or None if connection cannot be established.
    """
    driver = os.getenv("AZURE_SQL_DRIVER", "ODBC Driver 18 for SQL Server")

    # Strategy 1: Connection string
    conn_str = os.getenv("AZURE_SQL_CONNECTIONSTRING")
    if conn_str:
        try:
            return _create_engine_from_connection_string(conn_str, driver)
        except Exception as exc:
            logger.warning("Failed to connect using connection string: %s", exc)
            raise exc

    # Strategy 2: Individual environment variables
    try:
        engine = _create_engine_from_env_vars(driver)
        if engine:
            return engine
    except Exception as exc:
        logger.error("Failed to connect using individual variables: %s", exc)
        raise exc

    logger.error("Missing or invalid Azure SQL connection configuration.")
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = get_azure_engine()
    if engine:
        logger.info("Engine created successfully.")
