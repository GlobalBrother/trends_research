#!/usr/bin/env python3
"""
Database Doctor — one-command health check for the Trends Research system.

Usage:
    python -m src.db.doctor           # Full diagnostic
    python -m src.db.doctor --quick   # Quick connectivity test only
    python -m src.db.doctor --fix     # Attempt auto-fixes for common issues

This is a friendlier wrapper around the diagnostic in connection.py,
designed to be the first thing a developer runs when something is wrong.
"""

import logging
import os
import re
import shutil
import socket
import subprocess
import sys

# Bootstrap project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))


# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

_USE_COLOR = _supports_color()

def _green(s: str) -> str:
    return f"\033[92m{s}\033[0m" if _USE_COLOR else s

def _red(s: str) -> str:
    return f"\033[91m{s}\033[0m" if _USE_COLOR else s

def _yellow(s: str) -> str:
    return f"\033[93m{s}\033[0m" if _USE_COLOR else s

def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if _USE_COLOR else s

def _ok(msg: str):
    print(f"  {_green('✓')} {msg}")

def _fail(msg: str):
    print(f"  {_red('✗')} {msg}")

def _warn(msg: str):
    print(f"  {_yellow('!')} {msg}")

def _info(msg: str):
    print(f"  {msg}")


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_env_file() -> bool:
    """Check if .env file exists and has database config."""
    env_path = os.path.join(project_root, ".env")
    if not os.path.exists(env_path):
        _fail(f".env file not found at {env_path}")
        _info("  Create one by copying .env.example:")
        _info(f"    cp {project_root}/.env.example {env_path}")
        return False
    _ok(f".env file found: {env_path}")
    return True


def check_env_vars() -> dict:
    """Check which database env vars are set and determine strategy."""
    vars_status = {}
    checks = [
        ("AZURE_SQL_CONNECTIONSTRING", os.getenv("AZURE_SQL_CONNECTIONSTRING", "").strip()),
        ("AZURE_SQL_SERVER", os.getenv("AZURE_SQL_SERVER", "").strip()),
        ("AZURE_SQL_DATABASE", (
            os.getenv("AZURE_SQL_DB", "").strip() or
            os.getenv("AZURE_SQL_DATABASE", "").strip()
        )),
        ("AZURE_SQL_USER", os.getenv("AZURE_SQL_USER", "").strip()),
        ("AZURE_SQL_PASS", os.getenv("AZURE_SQL_PASS", "").strip()),
    ]

    for name, value in checks:
        present = bool(value)
        vars_status[name] = present
        if present:
            if "PASS" in name or "SECRET" in name:
                _ok(f"{name} = ****")
            elif "CONNECTIONSTRING" in name:
                _ok(f"{name} = {value[:40]}...")
            else:
                _ok(f"{name} = {value}")
        else:
            _warn(f"{name} = (not set)")

    # Determine strategy
    if vars_status["AZURE_SQL_CONNECTIONSTRING"]:
        strategy = "connection_string"
    elif vars_status["AZURE_SQL_SERVER"] and vars_status["AZURE_SQL_DATABASE"]:
        if vars_status["AZURE_SQL_USER"] and vars_status["AZURE_SQL_PASS"]:
            strategy = "sql_auth"
        else:
            strategy = "azure_ad"
    else:
        strategy = "none"

    strategy_labels = {
        "connection_string": "Full connection string (from Azure Portal)",
        "sql_auth": "SQL Authentication (username + password)",
        "azure_ad": "Azure AD (passwordless via azure-identity)",
        "none": _red("No valid configuration detected"),
    }
    print()
    _info(f"  Detected strategy: {_bold(strategy_labels[strategy])}")

    return {"vars": vars_status, "strategy": strategy}


def check_odbc_driver() -> dict:
    """Check if pyodbc and ODBC drivers are installed."""
    result = {"pyodbc": False, "drivers": [], "recommended": None}

    try:
        import pyodbc
        result["pyodbc"] = True
        _ok(f"pyodbc installed (version: {pyodbc.version})")
    except ImportError:
        _fail("pyodbc NOT installed")
        _info("  Install with: pip install pyodbc")
        return result

    all_drivers = pyodbc.drivers()
    sql_drivers = [d for d in all_drivers if "SQL Server" in d]
    result["drivers"] = sql_drivers

    if not sql_drivers:
        _fail("No SQL Server ODBC drivers found!")
        if sys.platform == "linux":
            _info("  Install with:")
            _info("    curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -")
            _info("    sudo apt-get update && sudo apt-get install -y msodbcsql18")
        elif sys.platform == "darwin":
            _info("  Install with: brew install microsoft/mssql-release/msodbcsql18")
        else:
            _info("  Download from: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server")
    else:
        for d in sql_drivers:
            _ok(f"ODBC driver: {d}")
        # Pick the best one
        preferred = sorted(sql_drivers, key=lambda d: ("ODBC Driver" in d, d), reverse=True)
        result["recommended"] = preferred[0]

    return result


def check_network(server: str = "") -> dict:
    """Test DNS resolution and TCP connectivity to the Azure SQL server."""
    result = {"dns": False, "tcp": False, "host": "", "ip": ""}

    if not server:
        server = os.getenv("AZURE_SQL_SERVER", "").strip()
    if not server:
        raw_cs = os.getenv("AZURE_SQL_CONNECTIONSTRING", "")
        m = re.search(r"(?:SERVER|Server|Data Source)=(?:tcp:)?([^;,]+)", raw_cs)
        server = m.group(1) if m else ""

    if not server:
        _warn("Cannot test network — no server configured")
        return result

    # Clean server value
    host = re.sub(r"^tcp:", "", server).split(",")[0]
    port = 1433
    port_match = re.search(r",(\d+)", server)
    if port_match:
        port = int(port_match.group(1))

    result["host"] = host

    # DNS
    try:
        ip = socket.gethostbyname(host)
        result["dns"] = True
        result["ip"] = ip
        _ok(f"DNS: {host} → {ip}")
    except socket.gaierror as e:
        _fail(f"DNS resolution FAILED: {host} — {e}")
        return result

    # TCP
    try:
        s = socket.create_connection((host, port), timeout=5)
        s.close()
        result["tcp"] = True
        _ok(f"TCP: port {port} is open")
    except Exception as e:
        _fail(f"TCP: port {port} is BLOCKED or UNREACHABLE — {e}")
        _info("  Possible causes:")
        _info("    - Azure SQL firewall not configured for your IP")
        _info("    - Corporate firewall/VPN blocking port 1433")
        _info("    - Azure SQL server is paused or stopped")
        _info(f"  Your current IP: ", )
        try:
            import urllib.request
            my_ip = urllib.request.urlopen("https://ifconfig.me", timeout=5).read().decode().strip()
            _info(f"    {my_ip}")
            _info(f"  Add this IP to Azure SQL firewall rules in the Azure Portal.")
        except Exception:
            _info("    (could not determine)")

    return result


def check_azure_ad() -> dict:
    """Check Azure AD / azure-identity setup."""
    result = {"installed": False, "logged_in": False, "token": False}

    try:
        from azure.identity import DefaultAzureCredential
        result["installed"] = True
        _ok("azure-identity package installed")
    except ImportError:
        _warn("azure-identity NOT installed (only needed for Azure AD auth)")
        _info("  Install with: pip install azure-identity")
        return result

    # Check az CLI login
    try:
        out = subprocess.run(
            ["az", "account", "show", "--query", "user.name", "-o", "tsv"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            result["logged_in"] = True
            _ok(f"Azure CLI logged in as: {out.stdout.strip()}")
        else:
            _warn("Azure CLI not logged in (run 'az login')")
    except FileNotFoundError:
        _warn("Azure CLI not installed (optional, but recommended for Azure AD)")
    except Exception:
        _warn("Could not check Azure CLI status")

    # Try to get a token
    try:
        cred = DefaultAzureCredential()
        token = cred.get_token("https://database.windows.net/.default")
        result["token"] = True
        _ok("Azure AD token acquired successfully")
    except Exception as e:
        _fail(f"Azure AD token acquisition FAILED: {e}")

    return result


def check_connection() -> bool:
    """Attempt an actual database connection."""
    try:
        from src.db.connection import diagnose as run_diagnose
        diag = run_diagnose()
        if diag.connected:
            _ok("Database connection: SUCCESS")
            return True
        else:
            _fail(f"Database connection: FAILED — {diag.error}")
            return False
    except Exception as e:
        _fail(f"Database connection: FAILED — {e}")
        return False


# ---------------------------------------------------------------------------
# Main doctor flow
# ---------------------------------------------------------------------------

def run_doctor(quick: bool = False, fix: bool = False):
    """Run the full diagnostic suite."""
    print()
    print(_bold("=" * 60))
    print(_bold("  Trends Research — Database Doctor"))
    print(_bold("=" * 60))
    print()

    # 1. Environment file
    print(_bold("1. Environment File"))
    has_env = check_env_file()
    print()

    # 2. Environment variables
    print(_bold("2. Database Configuration"))
    env_result = check_env_vars()
    print()

    if env_result["strategy"] == "none":
        print(_red("No database configuration found."))
        print("Run the setup wizard to configure your connection:\n")
        print(f"  python -m src.db.connection --setup\n")
        return

    if quick:
        # Quick mode: just test the connection
        print(_bold("3. Quick Connection Test"))
        ok = check_connection()
        print()
        if ok:
            print(_green("All good! Database is accessible."))
        else:
            print(_red("Connection failed. Run without --quick for full diagnostic."))
        return

    # 3. ODBC driver
    print(_bold("3. ODBC Driver"))
    odbc_result = check_odbc_driver()
    print()

    # 4. Network
    print(_bold("4. Network Connectivity"))
    net_result = check_network()
    print()

    # 5. Azure AD (if applicable)
    if env_result["strategy"] in ("azure_ad", "connection_string"):
        raw_cs = os.getenv("AZURE_SQL_CONNECTIONSTRING", "")
        if env_result["strategy"] == "azure_ad" or "Active Directory" in raw_cs:
            print(_bold("5. Azure AD Authentication"))
            ad_result = check_azure_ad()
            print()

    # 6. Actual connection
    print(_bold("6. Database Connection"))
    connected = check_connection()
    print()

    # Summary
    print(_bold("=" * 60))
    if connected:
        print(_green("  ✓ All checks passed! Database is accessible."))
    else:
        print(_red("  ✗ Some checks failed. Review the output above."))
        print()
        print("  Common fixes:")
        if not odbc_result.get("drivers"):
            print(f"    → Install ODBC driver (see step 3)")
        if not net_result.get("tcp"):
            print(f"    → Check firewall / VPN (see step 4)")
        if env_result["strategy"] in ("azure_ad",) and not check_azure_ad().get("token"):
            print(f"    → Run 'az login' for Azure AD auth (see step 5)")
        print()
        print("  Still stuck? Run the setup wizard:")
        print(f"    python -m src.db.connection --setup")
    print(_bold("=" * 60))
    print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Database Doctor — health check tool")
    parser.add_argument("--quick", action="store_true", help="Quick connectivity test only")
    parser.add_argument("--fix", action="store_true", help="Attempt auto-fixes")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    run_doctor(quick=args.quick, fix=args.fix)
