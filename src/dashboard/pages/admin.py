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
from src.dashboard.tabs import _apply_modern_layout, GRADIENT_BLUE, GRADIENT_TEAL

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

        # App switcher
        st.markdown(
            '<div style="font-size:0.75rem;font-weight:600;color:#8b949e;'
            'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.4rem;">'
            '🔀 Switch App</div>',
            unsafe_allow_html=True,
        )
        st.page_link("app.py", label="🚀 Trends Research", use_container_width=True)
        st.page_link("pages/ads_insight.py", label="📢 Ads Insight", use_container_width=True)
        st.divider()

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
    tab_scrape, tab_batch, tab_ads, tab_niches, tab_history, tab_errors, tab_tokens, tab_users, tab_azure = st.tabs([
        "🚀 Scrape by Platform", "⚡ Batch Scrape", "📢 Ads Scraper", "🎯 Niches & Keywords",
        "📋 History", "⚠️ Errors", "🪙 Token Usage", "👥 Users", "☁️ Azure DB"
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
            search_ads = st.text_input("🔍 Search ads…", key="search_admin_ads",
                                        placeholder="Type to filter…", label_visibility="collapsed")
            show_df = ads_df[display_cols] if display_cols else ads_df
            if search_ads:
                mask = show_df.apply(
                    lambda row: row.astype(str).str.contains(search_ads, case=False, na=False).any(), axis=1)
                show_df = show_df[mask]
            st.dataframe(
                show_df,
                hide_index=True, use_container_width=True, height=350,
                column_config={
                    "share_url": st.column_config.LinkColumn("Ad Link"),
                    "performance_score": "Score",
                    "days_active": "Days Active",
                },
            )

    # ---- Tab: Niches & Keywords ----
    with tab_niches:
        st.subheader("🎯 Manage Niches & Keywords")
        st.caption("Add, remove, and edit niches and their associated keywords dynamically.")

        niches_list = api.get_niches()

        # --- Add new niche ---
        with st.container(border=True):
            st.markdown("**➕ Add New Niche**")
            n_col1, n_col2 = st.columns([2, 3])
            with n_col1:
                new_niche_name = st.text_input("Niche Name", placeholder="e.g. Fitness", key="admin_new_niche_name")
            with n_col2:
                new_niche_kws = st.text_input(
                    "Keywords (comma-separated)",
                    placeholder="e.g. workout, gym, exercise, bodybuilding",
                    key="admin_new_niche_kws",
                )
            if st.button("➕ Create Niche", key="admin_create_niche", type="primary"):
                if not new_niche_name.strip():
                    st.warning("Enter a niche name.")
                else:
                    kws = [k.strip() for k in new_niche_kws.split(",") if k.strip()] if new_niche_kws.strip() else []
                    res = api.create_niche(new_niche_name.strip(), kws if kws else None)
                    if "error" in res:
                        st.error(res["error"])
                    else:
                        st.toast(res.get("message", "Niche created!"), icon="✅")
                        st.rerun()

        st.divider()

        # --- Browse / edit existing niches ---
        if not niches_list:
            st.info("No niches defined yet. Create one above.")
        else:
            selected_niche = st.selectbox(
                "Select a niche to manage",
                niches_list,
                key="admin_manage_niche_select",
            )

            if selected_niche:
                kws = api.get_niche_keywords(selected_niche)

                st.markdown(f"**Keywords for _{selected_niche}_** ({len(kws)})")

                # Display keywords as removable chips
                if kws:
                    cols_per_row = 4
                    for row_start in range(0, len(kws), cols_per_row):
                        row_kws = kws[row_start:row_start + cols_per_row]
                        cols = st.columns(cols_per_row)
                        for ci, kw in enumerate(row_kws):
                            with cols[ci]:
                                with st.container(border=True):
                                    kw_col, btn_col = st.columns([3, 1])
                                    with kw_col:
                                        st.markdown(f"`{kw}`")
                                    with btn_col:
                                        if st.button("🗑️", key=f"del_kw_{selected_niche}_{kw}",
                                                     help=f"Remove '{kw}'"):
                                            res = api.delete_keyword(selected_niche, kw)
                                            if "error" in res:
                                                st.error(res["error"])
                                            else:
                                                st.toast(f"Keyword '{kw}' removed", icon="🗑️")
                                                st.rerun()
                else:
                    st.info("No keywords for this niche.")

                # Add keywords to existing niche
                st.markdown("**Add Keywords**")
                add_kw_col1, add_kw_col2 = st.columns([4, 1])
                with add_kw_col1:
                    add_kws_input = st.text_input(
                        "New keywords (comma-separated)",
                        placeholder="e.g. cardio, HIIT, strength training",
                        key=f"admin_add_kws_{selected_niche}",
                    )
                with add_kw_col2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("➕ Add", key=f"admin_add_kws_btn_{selected_niche}"):
                        new_kws = [k.strip() for k in add_kws_input.split(",") if k.strip()]
                        if not new_kws:
                            st.warning("Enter at least one keyword.")
                        else:
                            res = api.add_keywords(selected_niche, new_kws)
                            if "error" in res:
                                st.error(res["error"])
                            else:
                                st.toast(res.get("message", "Keywords added!"), icon="✅")
                                st.rerun()

                # Delete entire niche
                st.divider()
                if st.button(f"🗑️ Delete Entire Niche '{selected_niche}'",
                             key=f"admin_del_niche_{selected_niche}", type="primary"):
                    res = api.delete_niche(selected_niche)
                    if "error" in res:
                        st.error(res["error"])
                    else:
                        st.toast(f"Niche '{selected_niche}' deleted!", icon="🗑️")
                        st.rerun()

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
                hide_index=True, use_container_width=True, height=400,
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
                use_container_width=True, hide_index=True, height=400,
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
        provider_summary = usage.get("provider_summary", [])

        # --- Provider-level KPIs (ensembledata & gethookedai) ---
        if provider_summary:
            st.markdown("**Usage by Provider**")
            prov_df = pd.DataFrame(provider_summary)
            prov_df.columns = ["Provider", "Total Units", "Requests"]
            prov_df["Total Units"] = prov_df["Total Units"].round(2)

            cols = st.columns(len(prov_df) + 1)
            total_units = prov_df["Total Units"].sum()
            total_reqs = prov_df["Requests"].sum()
            with cols[0]:
                st.metric("🪙 Total Units", f"{total_units:,.1f}")
            for i, row in prov_df.iterrows():
                with cols[i + 1]:
                    icon = "🔗" if row["Provider"] == "ensembledata" else "📢"
                    st.metric(f"{icon} {row['Provider']}", f"{row['Total Units']:,.1f} units")

            st.dataframe(prov_df, hide_index=True, use_container_width=True)

            # Provider bar chart
            if len(prov_df) > 1:
                fig_prov = px.bar(prov_df, x="Provider", y="Total Units", color="Provider",
                                  title="Units Consumed by Provider")
                _apply_modern_layout(fig_prov, showlegend=False)
                st.plotly_chart(fig_prov, use_container_width=True)

        # --- Platform breakdown ---
        if summary:
            st.divider()
            st.markdown("**Breakdown by Platform**")
            sum_df = pd.DataFrame(summary)
            if "provider" in sum_df.columns:
                sum_df.columns = ["Platform", "Total Units", "Requests", "Provider"]
            else:
                sum_df.columns = ["Platform", "Total Units", "Requests"]
            sum_df["Total Units"] = sum_df["Total Units"].round(2)

            st.dataframe(sum_df, hide_index=True, use_container_width=True)

            # Bar chart
            if len(sum_df) > 1:
                fig = px.bar(sum_df, x="Platform", y="Total Units", color="Platform",
                             title="Units Consumed by Platform")
                _apply_modern_layout(fig, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
        elif not provider_summary:
            st.info("No token usage recorded yet. Run some scrapes first.")

        if detail:
            st.divider()
            st.markdown("**Recent Requests (last 1000)**")
            det_df = pd.DataFrame(detail)
            search_tokens = st.text_input("🔍 Search requests…", key="search_admin_tokens",
                                           placeholder="Type to filter…", label_visibility="collapsed")
            show_det = det_df
            if search_tokens:
                mask = det_df.apply(
                    lambda row: row.astype(str).str.contains(search_tokens, case=False, na=False).any(), axis=1)
                show_det = det_df[mask]
            st.dataframe(
                show_det,
                hide_index=True, use_container_width=True, height=400,
                column_config={
                    "provider": "Provider", "platform": "Platform",
                    "keyword": "Keyword", "units_charged": "Units",
                    "geo": "Region", "created_at": "Timestamp",
                },
            )

    # ---- Tab: User Management ----
    with tab_users:
        st.subheader("👥 Whitelisted Users")

        users = api.list_users()
        if users:
            st.dataframe(
                pd.DataFrame(users),
                hide_index=True, use_container_width=True, height=300,
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


    # ---- Tab: Azure DB ----
    with tab_azure:
        st.subheader("☁️ Azure SQL Server")
        st.caption("Manage the Azure SQL database: check connection health, run diagnostics, create schema, and migrate.")

        # ---- Connection Status Banner ----
        if st.button("🔍 Check Connection", key="admin_azure_status", type="primary"):
            with st.spinner("Checking Azure SQL connection…"):
                result = api._request("GET", "/admin/azure/status")
            if result and result.get("connected"):
                st.success("✅ Connected to Azure SQL")
                # Show diagnostic summary if available
                diag = result.get("diagnostic")
                if diag:
                    dcol1, dcol2, dcol3 = st.columns(3)
                    dcol1.metric("Strategy", diag.get("strategy", "—"))
                    dcol2.metric("Auth Method", diag.get("auth_method", "—")[:30])
                    dcol3.metric("ODBC Driver", diag.get("driver", "—")[:30])
                # Show table row counts
                tables = result.get("tables", {})
                if tables:
                    rows_data = [{"Table": t, "Rows": str(c)} for t, c in tables.items()]
                    st.dataframe(pd.DataFrame(rows_data), hide_index=True, use_container_width=True)
            elif result:
                st.error(f"❌ Connection failed: {result.get('error', 'Unknown error')}")
                diag = result.get("diagnostic")
                if diag:
                    with st.expander("🔎 Diagnostic Details", expanded=True):
                        if diag.get("strategy"):
                            st.info(f"**Strategy:** {diag['strategy']}  |  **Auth:** {diag.get('auth_method', '—')}")
                        if diag.get("warnings"):
                            st.warning("**Warnings:**")
                            for w in diag["warnings"]:
                                st.markdown(f"- {w}")
                        if diag.get("steps"):
                            st.caption("**Steps taken:**")
                            for s in diag["steps"]:
                                st.markdown(f"  {s}")
            else:
                st.error("❌ Could not reach API")

        st.divider()

        az_col1, az_col2, az_col3 = st.columns(3)

        # ---- Full Diagnostic ----
        with az_col1:
            with st.container(border=True):
                st.markdown("**🩺 Full Diagnostic**")
                st.caption("Resets the connection and runs a complete diagnostic: env vars, ODBC driver, network, auth, and connectivity.")
                if st.button("Run Full Diagnostic", key="admin_azure_diagnose", width="stretch"):
                    with st.spinner("Running full diagnostic (this resets the connection)…"):
                        result = api._request("GET", "/admin/azure/diagnose")
                    if result:
                        if result.get("connected"):
                            st.success("✅ All checks passed!")
                        else:
                            st.error(f"❌ Diagnostic failed: {result.get('error', 'Unknown')}")
                        # Show steps
                        with st.expander("Diagnostic Steps", expanded=True):
                            for i, step in enumerate(result.get("steps", []), 1):
                                st.markdown(f"{i}. {step}")
                        # Show warnings
                        warnings = result.get("warnings", [])
                        if warnings:
                            with st.expander("⚠️ Warnings", expanded=True):
                                for w in warnings:
                                    st.warning(w)
                    else:
                        st.error("❌ Could not reach API")

        # ---- Schema Setup ----
        with az_col2:
            with st.container(border=True):
                st.markdown("**🏗️ Setup Schema**")
                st.caption("Create all tables and indexes in Azure SQL (idempotent — safe to run multiple times).")
                if st.button("🏗️ Run Schema Setup", key="admin_azure_schema", width="stretch"):
                    with st.spinner("Running schema setup…"):
                        result = api._request("POST", "/admin/azure/setup_schema")
                    if result and "message" in result:
                        st.toast("✅ Schema setup started!", icon="🏗️")
                        st.info(result["message"])
                    else:
                        st.error("❌ Schema setup failed")

        # ---- Migration ----
        with az_col3:
            with st.container(border=True):
                st.markdown("**🔄 Run Migration**")
                st.caption("Add missing indexes and tables to match the latest code. Run after code updates.")
                dry_run = st.checkbox("Dry run (preview only)", key="admin_migrate_dry", value=True)
                if st.button("🔄 Run Migration", key="admin_azure_migrate", width="stretch"):
                    with st.spinner("Running migration…"):
                        result = api._request("POST", f"/admin/azure/migrate?dry_run={str(dry_run).lower()}")
                    if result and "summary" in result:
                        st.info(result["summary"])
                    elif result and "message" in result:
                        st.info(result["message"])
                    else:
                        st.error("❌ Migration failed")

        # ---- CLI Hint ----
        st.divider()
        with st.expander("💡 CLI Tools", expanded=False):
            st.markdown("""
**Database Doctor** — Run from your terminal for a full diagnostic:
```bash
python -m src.db.doctor
python -m src.db.doctor --quick
```

**Setup Wizard** — Interactive guided setup:
```bash
python -m src.db.connection --setup
```

**Run Migration** — Apply schema changes:
```bash
python -m src.db.migrate
python -m src.db.migrate --dry   # preview only
```
""")



admin_main()
