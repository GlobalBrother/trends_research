import sys
import os

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st
import pandas as pd
import plotly.express as px
import streamlit.components.v1 as components
from datetime import datetime, timedelta

from src.dashboard.utils.api_client import APIClient
from src.dashboard.tabs import (
    format_number, tab_niche_research, tab_daily_trends, tab_youtube,
    tab_tiktok, tab_instagram, tab_threads, tab_reddit, tab_community_news,
)
from src.db.connection import test_connection


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
    try {{
        window.top.document.cookie = "{name}={value}; path=/; max-age={max_age_seconds}; SameSite=Lax";
    }} catch(e) {{
        try {{ parent.document.cookie = "{name}={value}; path=/; max-age={max_age_seconds}; SameSite=Lax"; }} catch(e2) {{}}
    }}
    </script>
    """
    components.html(js, height=0, width=0)


def _delete_cookie_js(name):
    """Delete a browser cookie via injected JavaScript."""
    js = f"""
    <script>
    try {{
        window.top.document.cookie = "{name}=; path=/; max-age=0; SameSite=Lax";
    }} catch(e) {{
        try {{ parent.document.cookie = "{name}=; path=/; max-age=0; SameSite=Lax"; }} catch(e2) {{}}
    }}
    </script>
    """
    components.html(js, height=0, width=0)


def _get_cookie_from_headers(name):
    """Read a cookie value from the Streamlit request headers."""
    # First check query params (reliable fallback)
    token_from_params = st.query_params.get(name)
    if token_from_params:
        return token_from_params
    # Then check cookies from headers
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
    # Also persist in query params as a reliable fallback
    st.query_params["tr_token"] = token


def _clear_auth_cookies():
    """Remove auth cookie on logout."""
    _delete_cookie_js("tr_token")
    if "tr_token" in st.query_params:
        del st.query_params["tr_token"]


def login_page(api):
    """Render the OTP login form. Returns True when authenticated."""
    # Centered branded login card
    st.markdown(
        '<div class="login-container">'
        '<div class="login-brand">'
        '<div class="logo">🚀</div>'
        '<div class="title">Trends Research</div>'
        '<div class="subtitle">Sign in with your whitelisted email</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    email = st.text_input("Email address", key="login_email", placeholder="you@company.com")

    if not st.session_state.otp_sent:
        if st.button("Send One-Time Code", disabled=not email, width='stretch', type="primary"):
            res = api.request_otp(email)
            if "error" in res:
                st.error(res["error"])
            else:
                st.session_state.otp_sent = True
                st.session_state.user_email = email
                st.rerun()
    else:
        st.success(f"Code sent to **{st.session_state.user_email}**")
        code = st.text_input("Enter verification code", key="login_code", placeholder="6-digit code")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✓ Verify", width='stretch', type="primary"):
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
            if st.button("← Back", width='content'):
                st.session_state.otp_sent = False
                st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)  # close login-container
    _render_footer()
    return False


def logout():
    """Clear auth session state and cookies."""
    _clear_auth_cookies()
    for key in ("authenticated", "user_email", "user_role", "otp_sent"):
        st.session_state[key] = "" if key in ("user_email", "user_role") else False


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_header():
    """Render the branded app header bar."""
    st.markdown(
        '<div class="app-header">'
        '<span class="app-logo">🚀</span>'
        '<span class="app-title">Trends Research</span>'
        '<span class="app-env-badge">Production</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_footer():
    """Render a minimal footer."""
    st.markdown(
        '<div class="app-footer">'
        '© 2026 Trends Research · Built with Streamlit'
        '</div>',
        unsafe_allow_html=True,
    )


def render_sidebar(api):
    """Build sidebar controls with user card and mode indicator."""
    with st.sidebar:
        # Branding
        st.markdown(
            '<div style="text-align:center;padding:0.5rem 0 0.8rem 0;">'
            '<span style="font-size:1.6rem;">🚀</span><br>'
            '<span style="font-size:0.9rem;font-weight:700;'
            'background:linear-gradient(135deg,#58a6ff,#a855f7);'
            '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">'
            'Trends Research</span></div>',
            unsafe_allow_html=True,
        )

        # User card
        email = st.session_state.user_email
        role = st.session_state.user_role
        initial = email[0].upper() if email else "?"
        st.markdown(
            f'<div class="sidebar-user">'
            f'<div class="user-avatar">{initial}</div>'
            f'<div class="user-info">'
            f'<div class="user-email">{email}</div>'
            f'<div class="user-role">{role}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        if api.direct:
            st.markdown('<span class="status-badge status-ok">⚡ Direct mode</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-badge status-warn">🌐 API mode</span>', unsafe_allow_html=True)

        # --- Database connection status ---
        st.divider()
        st.markdown(
            '<div style="font-size:0.75rem;font-weight:600;color:#8b949e;'
            'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.4rem;">'
            '🗄️ Database</div>',
            unsafe_allow_html=True,
        )

        if "db_status" not in st.session_state:
            st.session_state.db_status = None

        if st.button("🔌 Check Connection", key="db_connect_btn", width='stretch'):
            try:
                ok, msg = test_connection()
                if ok:
                    st.session_state.db_status = ("success", msg)
                else:
                    st.session_state.db_status = ("error", msg)
            except Exception as e:
                st.session_state.db_status = ("error", str(e))
            st.rerun()

        if st.session_state.db_status:
            level, msg = st.session_state.db_status
            if level == "success":
                st.success(msg, icon="✅")
            else:
                st.error(msg, icon="❌")

        # App switcher for admin users
        if role == "admin":
            st.divider()
            st.markdown(
                '<div style="font-size:0.75rem;font-weight:600;color:#8b949e;'
                'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.4rem;">'
                '🔀 Switch App</div>',
                unsafe_allow_html=True,
            )
            st.page_link("pages/admin.py", label="🛠️ Admin Panel", width='stretch')
            st.page_link("pages/ads_insight.py", label="📢 Ads Insight", width='stretch')

        st.divider()
        if st.button("🚪 Logout", key="logout_btn", width='stretch'):
            logout()
            st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="Trends Research",
        layout="wide",
        page_icon="🚀",
        initial_sidebar_state="expanded",
    )
    inject_custom_css()
    _init_session_state()

    api = APIClient()

    # --- Restore session from cookies if available ---
    _try_restore_from_cookies(api)

    # --- Auth gate (hide sidebar until logged in) ---
    if not st.session_state.authenticated:
        login_page(api)
        return

    _render_header()
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


    # Footer
    _render_footer()


if __name__ == "__main__":
    main()
