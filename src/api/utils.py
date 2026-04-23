import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd
from src.config import CACHE_TTL_SECONDS

from sqlalchemy import func
from src.db.connection import session_scope
from src.db.models import TrendCluster

logger = logging.getLogger(__name__)


def decode_json_field(value, fallback=None):
    if value in (None, "", "null"):
        return [] if fallback is None else fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback if fallback is not None else value


def cluster_snapshot_stale(session, max_age_hours: int = 6) -> bool:
    latest = session.query(func.max(TrendCluster.updated_at)).scalar()
    if latest is None:
        return True
    return (datetime.utcnow() - latest).total_seconds() > (max_age_hours * 3600)


def ensure_cluster_snapshot(pipeline, force: bool = False) -> dict:
    with session_scope() as session:
        if not force and not cluster_snapshot_stale(session):
            return {"refreshed": False}
        result = pipeline.sync(session)
        return {"refreshed": True, **result}

# ---------------------------------------------------------------------------
# Email provider setup
# ---------------------------------------------------------------------------
_acs_conn_str = os.getenv("ACS_CONNECTION_STRING", "")
_acs_sender = os.getenv("ACS_SENDER_ADDRESS", "")
_email_client = None

if _acs_conn_str:
    try:
        from azure.communication.email import EmailClient
        _email_client = EmailClient.from_connection_string(_acs_conn_str)
    except Exception as _acs_err:
        logger.warning(f"ACS Email init failed ({_acs_err}), falling back to Resend")

if not _email_client:
    try:
        import resend
        resend.api_key = os.getenv("RESEND_API_KEY", "")
    except ImportError:
        pass

EMAIL_FROM = _acs_sender or os.getenv("RESEND_FROM_EMAIL", "noreply@yourdomain.com")


def send_email(to_email: str, subject: str, html_body: str) -> str:
    """Send an email via ACS or Resend, depending on what's configured.

    Returns the name of the provider used on success ("acs" or "resend").
    Raises ``RuntimeError`` (with a descriptive message) on any failure or
    if no provider is configured. Callers that want to swallow errors must
    do so explicitly.
    """
    if _email_client:
        try:
            message = {
                "content": {"subject": subject, "html": html_body},
                "recipients": {"to": [{"address": to_email}]},
                "senderAddress": EMAIL_FROM,
            }
            poller = _email_client.begin_send(message)
            poller.result()
            return "acs"
        except Exception as e:
            logger.error(f"ACS send_email failed for {to_email}: {e}")
            raise RuntimeError(f"ACS email send failed: {e}") from e

    # Fall back to Resend
    resend_key = os.getenv("RESEND_API_KEY", "")
    if not resend_key:
        raise RuntimeError(
            "No email provider configured: set ACS_CONNECTION_STRING + "
            "ACS_SENDER_ADDRESS, or RESEND_API_KEY + RESEND_FROM_EMAIL."
        )
    try:
        import resend
        # Re-assert the API key in case the module was imported before env was loaded
        resend.api_key = resend_key
        resend.Emails.send({
            "from": EMAIL_FROM,
            "to": to_email,
            "subject": subject,
            "html": html_body,
        })
        return "resend"
    except Exception as e:
        logger.error(f"Resend send_email failed for {to_email}: {e}")
        raise RuntimeError(f"Resend email send failed: {e}") from e


# ---------------------------------------------------------------------------
# JSON & DataFrame Helpers
# ---------------------------------------------------------------------------

class CustomJSONEncoder(json.JSONEncoder):
    """Handle numpy, pandas, datetime, and set types."""
    def default(self, obj):
        if hasattr(obj, "tolist"):
            return obj.tolist()
        if isinstance(obj, (datetime, pd.Timestamp)):
            return obj.isoformat()
        if isinstance(obj, set):
            return list(obj)
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


def sanitize_dataframe(df: pd.DataFrame) -> list[dict]:
    """Replace NaN/Inf and serialize a DataFrame to JSON-safe records."""
    df = df.copy()
    df = df.fillna("")
    df = df.replace([float("inf"), float("-inf")], None)
    records = df.to_dict(orient="records")
    return json.loads(json.dumps(records, cls=CustomJSONEncoder))


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[float, Any]] = {}


def get_cached(key: str, fn, ttl: int = CACHE_TTL_SECONDS):
    """Return cached result if fresh, otherwise compute, cache, and return."""
    now = time.time()
    if key in _cache:
        ts, data = _cache[key]
        if now - ts < ttl:
            return data
    result = fn()
    _cache[key] = (now, result)
    return result


def needs_scrape(df: pd.DataFrame, platform_col_value: str, hours: int = 24) -> bool:
    """Return True if the data for *platform_col_value* is stale or missing."""
    if df.empty or "platform" not in df.columns:
        return True
    subset = df[df["platform"] == platform_col_value]
    if subset.empty:
        return True
    last = pd.to_datetime(subset["extracted_at"]).max()
    return datetime.now() - last.to_pydatetime() > timedelta(hours=hours)
