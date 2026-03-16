import sys
import os
import math
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

# Ensure the project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.dashboard.utils.api_client import APIClient

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Admin — Scraper Control", layout="wide", page_icon="🛠️")

# ---------------------------------------------------------------------------
# Auth guard — admin only
# ---------------------------------------------------------------------------
if not st.session_state.get("authenticated"):
    st.warning("Please log in from the main page first.")
    st.stop()

if st.session_state.get("user_role") != "admin":
    st.error("⛔ Access denied — admin privileges required.")
    st.stop()


def format_number(val):
    if not isinstance(val, (int, float)):
        try:
            val = float(val)
        except Exception:
            return str(val)
    if math.isnan(val) or math.isinf(val):
        return "0"
    if val >= 1_000_000:
        return f"{val / 1_000_000:.1f}M"
    if val >= 1_000:
        return f"{val / 1_000:.1f}K"
    return str(int(val))


# ---------------------------------------------------------------------------
# Scraper definitions
# ---------------------------------------------------------------------------

SCRAPERS = [
    {"key": "google_trends", "label": "Google Trends", "icon": "📈", "desc": "Niche & daily trends from Google"},
    {"key": "youtube",       "label": "YouTube",       "icon": "🎬", "desc": "Video search via EnsembleData"},
    {"key": "TikTok",        "label": "TikTok",        "icon": "🎵", "desc": "Video search via EnsembleData"},
    {"key": "reddit",        "label": "Reddit",        "icon": "👽", "desc": "Subreddit posts via EnsembleData"},
    {"key": "Instagram",     "label": "Instagram",     "icon": "📸", "desc": "Hashtag/user search via EnsembleData"},
    {"key": "Threads",       "label": "Threads",       "icon": "💬", "desc": "Thread search via EnsembleData"},
    {"key": "hackernews",    "label": "Hacker News",   "icon": "🧡", "desc": "Top stories from HN"},
    {"key": "news",          "label": "News",          "icon": "📰", "desc": "News articles search"},
    {"key": "gethookedai",   "label": "GetHookd AI Ads", "icon": "📢", "desc": "Ad library search via GetHookd AI"},
]


# ---------------------------------------------------------------------------
# Sidebar — settings
# ---------------------------------------------------------------------------

def render_admin_sidebar(api):
    with st.sidebar:
        st.subheader("🛠️ Admin Controls")

        if api.direct:
            st.success("⚡ Direct mode", icon="⚡")
        else:
            st.warning("🌐 API mode", icon="🌐")

        st.divider()

        countries = {
            "United States": "US", "Global": "Global", "United Kingdom": "GB",
            "Canada": "CA", "Australia": "AU", "Germany": "DE", "France": "FR",
            "Italy": "IT", "Spain": "ES", "Brazil": "BR", "India": "IN",
            "Japan": "JP", "Romania": "RO", "Netherlands": "NL", "Sweden": "SE",
            "Switzerland": "CH", "Mexico": "MX", "Argentina": "AR",
            "Singapore": "SG", "South Korea": "KR", "China": "CN", "Russia": "RU",
            "South Africa": "ZA", "Turkey": "TR", "United Arab Emirates": "AE",
            "Poland": "PL", "Belgium": "BE", "Austria": "AT", "Denmark": "DK",
            "Norway": "NO", "Finland": "FI", "Portugal": "PT", "Greece": "GR",
            "Czech Republic": "CZ", "Hungary": "HU"
        }
        country_name = st.selectbox("🌍 Country", list(countries.keys()), key="admin_country")
        geo = countries[country_name]

        niches = api.get_niches()
        niche = st.selectbox("🎯 Niche", niches, key="admin_niche")

        st.divider()

        timeframes = {
            "Last 12 Months": "today 12-m", "Last hour": "now 1-H",
            "Last 4 hours": "now 4-H", "Last day": "now 1-d",
            "Last 7 days": "now 7-d", "Last 30 days": "today 1-m",
            "Last 90 days": "today 3-m", "Last 5 years": "today 5-y",
            "All (since 2004)": "all"
        }
        tf_name = st.selectbox("⏱️ Time Range", list(timeframes.keys()), key="admin_tf")
        timeframe = timeframes[tf_name]

        categories = {
            "All Categories": 0, "Arts & Entertainment": 3, "Autos & Vehicles": 47,
            "Beauty & Fitness": 44, "Books & Literature": 22, "Business & Industrial": 12,
            "Computers & Electronics": 5, "Finance": 7, "Food & Drink": 71, "Games": 8,
            "Health": 45, "Hobbies & Leisure": 65, "Home & Garden": 11,
            "Internet & Telecom": 13, "Jobs & Education": 958, "Law & Government": 19,
            "News": 16, "Online Communities": 299, "People & Society": 14,
            "Pets & Animals": 66, "Real Estate": 29, "Reference": 533, "Science": 174,
            "Shopping": 18, "Sports": 20, "Travel": 67
        }
        cat_name = st.selectbox("📂 Category", list(categories.keys()), key="admin_cat")
        category = categories[cat_name]

        st.divider()

        with st.expander("📥 Import Google Trends JSON", expanded=False):
            st.caption("Upload the JSON/TXT file from a 429 error.")
            uploaded = st.file_uploader("Choose file", type=["md.json", "txt"], key="admin_token_upload")
            if uploaded is not None and st.button("⬆️ Import", key="admin_import_btn"):
                with st.spinner("Importing..."):
                    result = api.import_tokens(uploaded.getvalue(), uploaded.name, geo=geo)
                    if result:
                        st.success(result.get("message", "Import started!"))
                    else:
                        st.error("❌ Import failed")

    return {
        "country_name": country_name, "geo": geo, "niche": niche,
        "timeframe": timeframe, "category": category,
    }


# ---------------------------------------------------------------------------
# Scrape history tracking (session state)
# ---------------------------------------------------------------------------

def _init_history():
    if "scrape_history" not in st.session_state:
        st.session_state.scrape_history = []


def _record_scrape(scraper_key, label, success, niche, geo):
    st.session_state.scrape_history.insert(0, {
        "time": datetime.now().strftime("%H:%M:%S"),
        "scraper": label,
        "niche": niche or "—",
        "geo": geo,
        "status": "✅ Success" if success else "❌ Failed",
    })
    # Keep last 50
    st.session_state.scrape_history = st.session_state.scrape_history[:50]


# ---------------------------------------------------------------------------
# Main admin page
# ---------------------------------------------------------------------------

def admin_main():
    # Auth gate: only admins can access this page
    if not st.session_state.get("authenticated", False):
        st.warning("🔐 Please log in from the main page first.")
        st.stop()
    if st.session_state.get("user_role", "") != "admin":
        st.error("⛔ You do not have permission to access this page.")
        st.stop()

    st.header("🛠️ Admin — Scraper Control Panel")

    api = APIClient()
    cfg = render_admin_sidebar(api)
    _init_history()

    niche = cfg["niche"]
    geo = cfg["geo"]
    country = cfg["country_name"]

    # --- Top KPI ---
    kpi_cols = st.columns(4)
    with kpi_cols[0]:
        st.metric("🎯 Active Niche", niche or "—")
    with kpi_cols[1]:
        st.metric("🌍 Region", country)
    with kpi_cols[2]:
        st.metric("⚡ Mode", "Direct" if api.direct else "API")
    with kpi_cols[3]:
        st.metric("📊 Session Scrapes", str(len(st.session_state.scrape_history)))

    # --- Tabs ---
    tab_scrape, tab_batch, tab_ads, tab_history, tab_errors, tab_tokens, tab_users = st.tabs([
        "🚀 Scrape by Platform", "⚡ Batch Scrape", "📢 Ads Scraper", "📋 History", "⚠️ Errors", "🪙 Token Usage", "👥 Users"
    ])

    # ---- Tab 1: Per-platform scraping ----
    with tab_scrape:
        st.subheader("🚀 Launch Scrapers")
        st.caption(f"Scraping for niche **{niche}** in **{country}** ({geo})")

        for i in range(0, len(SCRAPERS), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                idx = i + j
                if idx >= len(SCRAPERS):
                    break
                s = SCRAPERS[idx]
                with col:
                    with st.container(border=True):
                        st.markdown(f"**{s['icon']} {s['label']}**")
                        st.caption(s['desc'])

                        if st.button(f"🚀 Scrape {s['label']}", key=f"admin_scrape_{s['key']}",
                                     width='stretch'):
                            with st.spinner(f"Running {s['label']} scraper…"):
                                ok = api.trigger_scrape(
                                    niche_name=niche, geo=geo,
                                    timeframe=cfg["timeframe"],
                                    category=cfg["category"],
                                    scraper_type=s["key"],
                                )
                            _record_scrape(s["key"], s["label"], ok, niche, geo)
                            if ok:
                                st.toast(f"✅ {s['label']} scrape completed!", icon="🎉")
                            else:
                                st.error(f"❌ {s['label']} scrape failed")

    # ---- Tab: Ads Scraper ----
    with tab_ads:
        st.subheader("📢 GetHookd AI — Ads Scraper")
        st.caption("Search the ad library or spy on a brand's ads.")

        ads_col1, ads_col2 = st.columns(2)

        with ads_col1:
            with st.container(border=True):
                st.markdown("**🔍 Search Ad Library**")
                ads_keywords = st.text_input(
                    "Keywords (comma-separated)",
                    value=niche or "fitness",
                    key="admin_ads_keywords",
                )
                ads_max_pages = st.slider("Max pages (20 ads/page)", 1, 10, 3, key="admin_ads_pages")

                if st.button("🚀 Scrape Ads", key="admin_scrape_ads", width="stretch", type="primary"):
                    kws = [k.strip() for k in ads_keywords.split(",") if k.strip()]
                    if not kws:
                        st.warning("Enter at least one keyword.")
                    else:
                        with st.spinner(f"Searching ads for: {', '.join(kws)}…"):
                            ok = api.scrape_ads_direct(kws, max_pages=ads_max_pages)
                        _record_scrape("gethookedai", "GetHookd AI Ads", ok, niche, geo)
                        if ok:
                            st.toast("✅ Ads scrape completed!", icon="🎉")
                            st.cache_data.clear()
                        else:
                            st.error("❌ Ads scrape failed")

        with ads_col2:
            with st.container(border=True):
                st.markdown("**🕵️ Brand Spy**")
                brand_query = st.text_input("Brand Name", placeholder="e.g. Gundry MD", key="admin_brand_query")

                if st.button("🔍 Search Brand", key="admin_search_brand", width="stretch"):
                    if not brand_query.strip():
                        st.warning("Enter a brand name to search.")
                    else:
                        with st.spinner(f"Searching for '{brand_query}'…"):
                            results = api.search_brands(brand_query.strip())
                        if results:
                            st.session_state["brand_search_results"] = results
                        else:
                            st.session_state.pop("brand_search_results", None)
                            st.info("No brands found for that query.")

                results = st.session_state.get("brand_search_results", [])
                if results:
                    options = {f"{b['name']} ({b['active_ads']} ads)": b for b in results}
                    selected = st.selectbox("Select Brand", list(options.keys()), key="admin_brand_select")
                    brand = options[selected]

                    if st.button("🕵️ Spy on Brand", key="admin_spy_brand", width="stretch"):
                        with st.spinner(f"Fetching ads for {brand['name']}…"):
                            ok = api.scrape_ads_direct([brand["name"]], max_pages=5)
                        _record_scrape("gethookedai", f"Brand Spy: {brand['name']}", ok, niche, geo)
                        if ok:
                            st.toast(f"✅ {brand['name']} ads fetched!", icon="🎉")
                            st.cache_data.clear()
                        else:
                            st.error("❌ Brand spy failed")

        # Preview latest ads
        st.divider()
        st.markdown("**📊 Latest Ads in Database**")
        ads_df = api.get_ads_insight(niche_name=niche, limit=50)
        if ads_df.empty:
            st.info("No ads data yet. Run a scrape above to populate.")
        else:
            st.metric("Total Ads", format_number(len(ads_df)))
            display_cols = [c for c in ["brand_name", "title", "platform", "display_format",
                                         "performance_score", "days_active", "cta_type", "share_url",
                                         "search_keyword"] if c in ads_df.columns]
            st.dataframe(
                ads_df[display_cols] if display_cols else ads_df,
                hide_index=True, width="stretch", height=350,
                column_config={
                    "share_url": st.column_config.LinkColumn("Ad Link"),
                    "performance_score": "Score",
                    "days_active": "Days Active",
                },
            )

    # ---- Tab 2: Batch scrape ----
    with tab_batch:
        st.subheader("⚡ Batch Scrape — Run Multiple Scrapers")
        st.caption(f"Select scrapers to run for **{niche}** in **{country}**")

        selected = []
        cols = st.columns(4)
        for i, s in enumerate(SCRAPERS):
            with cols[i % 4]:
                if st.checkbox(f"{s['icon']} {s['label']}", value=True, key=f"batch_{s['key']}"):
                    selected.append(s)

        st.divider()

        c1, c2, c3 = st.columns([1, 1, 3])
        with c1:
            run_all = st.button("🚀 Run Selected", width='stretch', type="primary",
                                key="admin_run_selected")
        with c2:
            run_everything = st.button("⚡ Run ALL", width='stretch', key="admin_run_all")

        if run_all and selected:
            progress = st.progress(0, text="Starting batch scrape…")
            results = []
            for i, s in enumerate(selected):
                progress.progress((i + 1) / len(selected), text=f"Scraping {s['label']}…")
                ok = api.trigger_scrape(
                    niche_name=niche, geo=geo,
                    timeframe=cfg["timeframe"],
                    category=cfg["category"],
                    scraper_type=s["key"],
                )
                _record_scrape(s["key"], s["label"], ok, niche, geo)
                results.append({"Scraper": f"{s['icon']} {s['label']}", "Status": "✅" if ok else "❌"})
            progress.empty()

            st.subheader("Results")
            st.dataframe(pd.DataFrame(results), hide_index=True, width='stretch')

            ok_count = sum(1 for r in results if "✅" in r["Status"])
            st.toast(f"Batch complete: {ok_count}/{len(results)} succeeded", icon="🏁")

        if run_everything:
            progress = st.progress(0, text="Running all scrapers…")
            results = []
            for i, s in enumerate(SCRAPERS):
                progress.progress((i + 1) / len(SCRAPERS), text=f"Scraping {s['label']}…")
                ok = api.trigger_scrape(
                    niche_name=niche, geo=geo,
                    timeframe=cfg["timeframe"],
                    category=cfg["category"],
                    scraper_type=s["key"],
                )
                _record_scrape(s["key"], s["label"], ok, niche, geo)
                results.append({"Scraper": f"{s['icon']} {s['label']}", "Status": "✅" if ok else "❌"})
            progress.empty()

            st.subheader("Results")
            st.dataframe(pd.DataFrame(results), hide_index=True, width='stretch')

            ok_count = sum(1 for r in results if "✅" in r["Status"])
            st.toast(f"All scrapers done: {ok_count}/{len(results)} succeeded", icon="🏁")

    # ---- Tab 3: History ----
    with tab_history:
        st.subheader("📋 Scrape History (this session)")

        if st.session_state.scrape_history:
            hist_df = pd.DataFrame(st.session_state.scrape_history)
            st.dataframe(
                hist_df[["time", "scraper", "niche", "geo", "status"]],
                hide_index=True, width='stretch', height=400,
                column_config={
                    "time": "Time", "scraper": "Scraper",
                    "niche": "Niche", "geo": "Region", "status": "Status",
                },
            )

            if st.button("🗑️ Clear History", key="admin_clear_hist"):
                st.session_state.scrape_history = []
                st.rerun()
        else:
            st.info("No scrapes run yet this session. Use the **Scrape by Platform** or **Batch Scrape** tabs.")

    # ---- Tab 4: Errors ----
    with tab_errors:
        st.subheader("⚠️ Scrape Errors")

        c_ref, c_clr = st.columns([1, 1])
        with c_ref:
            if st.button("🔄 Refresh Errors", key="admin_refresh_errors"):
                st.cache_data.clear()
                st.rerun()
        with c_clr:
            if st.button("🗑️ Clear All Errors", key="admin_clear_errors", type="primary"):
                if api.clear_scrape_errors():
                    st.cache_data.clear()
                    st.toast("All scrape errors cleared!", icon="🗑️")
                    st.rerun()
                else:
                    st.error("Failed to clear errors.")

        errors_df = api.get_scrape_errors()
        if errors_df.empty:
            st.success("No scrape errors recorded! 🚀")
        else:
            st.metric("⚠️ Total Errors", format_number(len(errors_df)))
            st.dataframe(
                errors_df,
                column_config={
                    "url": st.column_config.LinkColumn("Failed URL"),
                    "status": "HTTP Status", "extracted_at": "Timestamp"
                },
                width='stretch', hide_index=True, height=400,
            )


    # ---- Tab: Token Usage ----
    with tab_tokens:
        st.subheader("🪙 API Token / Units Consumed")

        if st.button("🔄 Refresh", key="admin_refresh_tokens"):
            st.cache_data.clear()
            st.rerun()

        usage = api.get_token_usage()
        summary = usage.get("summary", [])
        detail = usage.get("data", [])

        if summary:
            st.markdown("**Summary by Platform**")
            sum_df = pd.DataFrame(summary)
            sum_df.columns = ["Platform", "Total Units", "Requests"]
            sum_df["Total Units"] = sum_df["Total Units"].round(2)

            # KPI row
            total_units = sum_df["Total Units"].sum()
            total_reqs = sum_df["Requests"].sum()
            k1, k2, k3 = st.columns(3)
            with k1:
                st.metric("🪙 Total Units", f"{total_units:,.1f}")
            with k2:
                st.metric("📡 Total Requests", f"{int(total_reqs):,}")
            with k3:
                st.metric("📊 Platforms", str(len(sum_df)))

            st.dataframe(sum_df, hide_index=True, width="stretch")

            # Bar chart
            if len(sum_df) > 1:
                fig = px.bar(sum_df, x="Platform", y="Total Units", color="Platform",
                             title="Units Consumed by Platform")
                fig.update_layout(showlegend=False, margin=dict(t=40, b=10, l=10, r=10))
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No token usage recorded yet. Run some scrapes first.")

        if detail:
            st.divider()
            st.markdown("**Recent Requests (last 1000)**")
            det_df = pd.DataFrame(detail)
            st.dataframe(
                det_df,
                hide_index=True, width="stretch", height=400,
                column_config={
                    "platform": "Platform", "keyword": "Keyword",
                    "units_charged": "Units", "geo": "Region",
                    "created_at": "Timestamp",
                },
            )

    # ---- Tab: User Management ----
    with tab_users:
        st.subheader("👥 Whitelisted Users")

        users = api.list_users()
        if users:
            st.dataframe(
                pd.DataFrame(users),
                hide_index=True, width="stretch", height=300,
                column_config={"email": "Email", "role": "Role", "created_at": "Added"},
            )
        else:
            st.info("No users yet.")

        st.divider()
        st.markdown("**Add User**")
        u_col1, u_col2, u_col3 = st.columns([3, 2, 1])
        with u_col1:
            new_email = st.text_input("Email", key="admin_new_email")
        with u_col2:
            new_role = st.selectbox("Role", ["trends", "admin", "ads insight"], key="admin_new_role")
        with u_col3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ Add", key="admin_add_user"):
                if new_email:
                    res = api.add_user(new_email, new_role)
                    if "error" in res:
                        st.error(res["error"])
                    else:
                        st.toast(f"User {new_email} added!", icon="✅")
                        st.rerun()

        st.divider()
        st.markdown("**Remove User**")
        r_col1, r_col2 = st.columns([3, 1])
        with r_col1:
            del_email = st.text_input("Email to remove", key="admin_del_email")
        with r_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ Remove", key="admin_del_user", type="primary"):
                if del_email:
                    res = api.delete_user(del_email)
                    if "error" in res:
                        st.error(res["error"])
                    else:
                        st.toast(f"User {del_email} removed!", icon="🗑️")
                        st.rerun()


admin_main()
