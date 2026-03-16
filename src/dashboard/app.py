import sys
import os
import streamlit as st
import pandas as pd
import plotly.express as px
import streamlit.components.v1 as components
from datetime import datetime, timedelta

# Ensure the project root (the directory containing 'src') is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.dashboard.utils.api_client import APIClient
from src.dashboard.tabs import (
    format_number, tab_niche_research, tab_daily_trends, tab_youtube,
    tab_tiktok, tab_instagram, tab_threads, tab_reddit, tab_community_news,
)


def inject_custom_css():
    """Inject custom CSS from an external style.css file."""
    css_path = os.path.join(os.path.dirname(__file__), "style.css")
    with open(css_path, encoding="utf-8") as f:
        css = f.read()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _set_cookie_js(name, value, max_age_seconds=43200):
    """Set a browser cookie via injected JavaScript (immediate, no render cycle needed)."""
    js = f"""
    <script>
    document.cookie = "{name}={value}; path=/; max-age={max_age_seconds}; SameSite=Lax";
    </script>
    """
    components.html(js, height=0, width=0)


def _delete_cookie_js(name):
    """Delete a browser cookie via injected JavaScript."""
    js = f"""
    <script>
    document.cookie = "{name}=; path=/; max-age=0; SameSite=Lax";
    </script>
    """
    components.html(js, height=0, width=0)


def _get_cookie_from_headers(name):
    """Read a cookie value from the Streamlit request headers."""
    try:
        cookie_header = st.context.headers.get("Cookie", "")
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith(f"{name}="):
                return part[len(name) + 1:]
    except Exception:
        pass
    return None


def _init_session_state():
    """Initialise auth-related session state keys and restore from cookies."""
    for key, default in [("authenticated", False), ("user_email", ""), ("user_role", ""), ("otp_sent", False)]:
        if key not in st.session_state:
            st.session_state[key] = default


def _try_restore_from_cookies(api):
    """Attempt to restore auth session from a cached token cookie."""
    if st.session_state.authenticated:
        return
    token = _get_cookie_from_headers("tr_token")
    if token:
        result = api.validate_token(token)
        if "error" not in result:
            st.session_state.authenticated = True
            st.session_state.user_email = result["email"]
            st.session_state.user_role = result["role"]
            st.session_state.auth_token = token


def _save_auth_cookies(token):
    """Persist auth token in a cookie valid for 12 hours."""
    _set_cookie_js("tr_token", token, max_age_seconds=43200)


def _clear_auth_cookies():
    """Remove auth cookie on logout."""
    _delete_cookie_js("tr_token")


def login_page(api):
    """Render the OTP login form. Returns True when authenticated."""
    st.markdown("## 🔐 Login")
    st.caption("Enter your whitelisted email to receive a one-time code.")

    email = st.text_input("Email", key="login_email")

    if not st.session_state.otp_sent:
        if st.button("Send OTP", disabled=not email):
            res = api.request_otp(email)
            if "error" in res:
                st.error(res["error"])
            else:
                st.session_state.otp_sent = True
                st.session_state.user_email = email
                st.rerun()
    else:
        st.success(f"OTP sent to **{st.session_state.user_email}**")
        code = st.text_input("Enter OTP code", key="login_code")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Verify"):
                res = api.verify_otp(st.session_state.user_email, code)
                if "error" in res:
                    st.error(res["error"])
                else:
                    st.session_state.authenticated = True
                    st.session_state.user_role = res["role"]
                    st.session_state.auth_token = res["token"]
                    _save_auth_cookies(res["token"])
                    st.rerun()
        with col2:
            if st.button("Back"):
                st.session_state.otp_sent = False
                st.rerun()

    return False


def logout():
    """Clear auth session state and cookies."""
    _clear_auth_cookies()
    for key in ("authenticated", "user_email", "user_role", "otp_sent"):
        st.session_state[key] = "" if key in ("user_email", "user_role") else False


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar(api):
    """Build sidebar controls (mode indicator only — filters moved to tabs)."""
    with st.sidebar:
        st.markdown("### ⚙️ Controls")

        if api.direct:
            st.markdown('<span class="status-badge status-ok">⚡ Direct mode</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-badge status-warn">🌐 API mode</span>', unsafe_allow_html=True)

        st.divider()
        st.caption(f"👤 {st.session_state.user_email}  •  **{st.session_state.user_role}**")
        if st.button("🚪 Logout", key="logout_btn"):
            logout()
            st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Trends Research", layout="wide", page_icon="🚀")
    inject_custom_css()
    _init_session_state()

    api = APIClient()

    # --- Restore session from cookies if available ---
    _try_restore_from_cookies(api)

    # --- Auth gate (hide sidebar until logged in) ---
    if not st.session_state.authenticated:
        login_page(api)
        return

    st.markdown("## 🚀 Trends Research")
    render_sidebar(api)

    role = st.session_state.user_role

    # Define all available tabs with their role requirements
    # "trends" role: only Niche Research and Daily Trends
    # "admin" role: all tabs
    all_tabs = [
        ("🎯 Niche Research", tab_niche_research, "trends"),
        ("📈 Daily Trends", tab_daily_trends, "trends"),
        ("🎬 YouTube", tab_youtube, "admin"),
        ("🎵 TikTok", tab_tiktok, "admin"),
        ("👽 Reddit", tab_reddit, "admin"),
        ("📸 Instagram", tab_instagram, "admin"),
        ("💬 Threads", tab_threads, "admin"),
        ("🌐 Community & News", tab_community_news, "admin"),
    ]

    # Filter tabs based on role
    if role == "admin":
        visible_tabs = all_tabs
    else:
        visible_tabs = [t for t in all_tabs if t[2] == "trends"]

    tab_objects = st.tabs([t[0] for t in visible_tabs])

    niche_df = None
    for tab_obj, (label, renderer, _) in zip(tab_objects, visible_tabs):
        with tab_obj:
            result = renderer(api)
            if label == "🎯 Niche Research":
                niche_df = result

    # Sidebar export
    with st.sidebar:
        st.markdown("---")
        with st.expander("📥 Export", expanded=False):
            try:
                if niche_df is not None and not niche_df.empty:
                    csv = niche_df.to_csv(index=False).encode('utf-8')
                    st.download_button("Download CSV", data=csv, file_name='trends.csv', mime='text/csv')
                    json_data = niche_df.to_json(orient="records")
                    st.download_button("Download JSON", data=json_data, file_name='trends.json', mime='application/json')
                else:
                    st.caption("No data to export.")
            except Exception:
                st.caption("No data to export.")


if __name__ == "__main__":
    main()
