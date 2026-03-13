import sys
import os
import streamlit as st
import pandas as pd
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
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
.block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #0e1117 0%, #1a1d23 100%); }

/* Metric cards */
.metric-row { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem; }
.metric-card {
    flex: 1 1 140px;
    background: linear-gradient(135deg, #1e2130 0%, #262a3a 100%);
    border: 1px solid #333;
    border-radius: 12px;
    padding: 1rem 1.2rem;
    text-align: center;
    min-width: 140px;
}
.metric-card .metric-value {
    font-size: 1.6rem; font-weight: 700; color: #58a6ff; line-height: 1.2;
}
.metric-card .metric-label {
    font-size: 0.78rem; color: #8b949e; margin-top: 0.25rem;
    text-transform: uppercase; letter-spacing: 0.5px;
}

/* Section headers */
.section-header {
    display: flex; align-items: center; gap: 0.5rem;
    margin: 1.2rem 0 0.6rem 0; padding-bottom: 0.4rem;
    border-bottom: 2px solid #30363d;
}
.section-header h3 { margin: 0; font-size: 1.1rem; font-weight: 600; color: #e6edf3; }

/* Status badges */
.status-badge {
    display: inline-block; padding: 0.2rem 0.6rem; border-radius: 20px;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.3px;
}
.status-ok { background: #1a3a2a; color: #3fb950; border: 1px solid #238636; }
.status-warn { background: #3a2a1a; color: #d29922; border: 1px solid #9e6a03; }
.status-err { background: #3a1a1a; color: #f85149; border: 1px solid #da3633; }

/* Scraper card */
.scraper-card {
    background: linear-gradient(135deg, #161b22 0%, #1c2333 100%);
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 1.2rem;
    margin-bottom: 0.75rem;
}
.scraper-card h4 { margin: 0 0 0.5rem 0; font-size: 1rem; }
</style>
""", unsafe_allow_html=True)


def metric_cards(metrics):
    html = '<div class="metric-row">'
    for m in metrics:
        html += f'''<div class="metric-card">
            <div class="metric-value">{m.get("icon","")} {m["value"]}</div>
            <div class="metric-label">{m["label"]}</div>
        </div>'''
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def section_header(icon, title):
    st.markdown(f'<div class="section-header"><h3>{icon} {title}</h3></div>', unsafe_allow_html=True)


def format_number(val):
    if not isinstance(val, (int, float)):
        try:
            val = float(val)
        except Exception:
            return str(val)
    import math
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
]


# ---------------------------------------------------------------------------
# Sidebar — settings
# ---------------------------------------------------------------------------

def render_admin_sidebar(api):
    with st.sidebar:
        st.markdown("### 🛠️ Admin Controls")

        if api.direct:
            st.markdown('<span class="status-badge status-ok">⚡ Direct mode</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-badge status-warn">🌐 API mode</span>', unsafe_allow_html=True)

        st.markdown("---")

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

        st.markdown("---")

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

        st.markdown("---")

        with st.expander("📥 Import Google Trends JSON", expanded=False):
            st.caption("Upload the JSON/TXT file from a 429 error.")
            uploaded = st.file_uploader("Choose file", type=["json", "txt"], key="admin_token_upload")
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
    _init_history()
    st.session_state.scrape_history.insert(0, {
        "time": datetime.now().strftime("%H:%M:%S"),
        "scraper": label,
        "key": scraper_key,
        "niche": niche,
        "geo": geo,
        "status": "✅ Success" if success else "❌ Failed",
    })
    # Keep last 50
    st.session_state.scrape_history = st.session_state.scrape_history[:50]


# ---------------------------------------------------------------------------
# Main admin page
# ---------------------------------------------------------------------------

def admin_main():
    st.markdown("## 🛠️ Admin — Scraper Control Panel")

    api = APIClient()
    cfg = render_admin_sidebar(api)
    _init_history()

    niche = cfg["niche"]
    geo = cfg["geo"]
    country = cfg["country_name"]

    # --- Top KPI ---
    metric_cards([
        {"label": "Active Niche", "value": niche or "—", "icon": "🎯"},
        {"label": "Region", "value": country, "icon": "🌍"},
        {"label": "Mode", "value": "Direct" if api.direct else "API", "icon": "⚡"},
        {"label": "Session Scrapes", "value": str(len(st.session_state.scrape_history)), "icon": "📊"},
    ])

    # --- Tabs ---
    tab_scrape, tab_batch, tab_history, tab_errors = st.tabs([
        "🚀 Scrape by Platform", "⚡ Batch Scrape", "📋 History", "⚠️ Errors"
    ])

    # ---- Tab 1: Per-platform scraping ----
    with tab_scrape:
        section_header("🚀", "Launch Scrapers")
        st.caption(f"Scraping for niche **{niche}** in **{country}** ({geo})")

        for i in range(0, len(SCRAPERS), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                idx = i + j
                if idx >= len(SCRAPERS):
                    break
                s = SCRAPERS[idx]
                with col:
                    st.markdown(f"""<div class="scraper-card">
                        <h4>{s['icon']} {s['label']}</h4>
                        <p style="color:#8b949e;font-size:0.82rem;margin:0">{s['desc']}</p>
                    </div>""", unsafe_allow_html=True)

                    if st.button(f"🚀 Scrape {s['label']}", key=f"admin_scrape_{s['key']}",
                                 use_container_width=True):
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

    # ---- Tab 2: Batch scrape ----
    with tab_batch:
        section_header("⚡", "Batch Scrape — Run Multiple Scrapers")
        st.caption(f"Select scrapers to run for **{niche}** in **{country}**")

        selected = []
        cols = st.columns(4)
        for i, s in enumerate(SCRAPERS):
            with cols[i % 4]:
                if st.checkbox(f"{s['icon']} {s['label']}", value=True, key=f"batch_{s['key']}"):
                    selected.append(s)

        st.markdown("---")

        c1, c2, c3 = st.columns([1, 1, 3])
        with c1:
            run_all = st.button("🚀 Run Selected", use_container_width=True, type="primary",
                                key="admin_run_selected")
        with c2:
            run_everything = st.button("⚡ Run ALL", use_container_width=True, key="admin_run_all")

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

            st.markdown("#### Results")
            st.dataframe(pd.DataFrame(results), hide_index=True, use_container_width=True)

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

            st.markdown("#### Results")
            st.dataframe(pd.DataFrame(results), hide_index=True, use_container_width=True)

            ok_count = sum(1 for r in results if "✅" in r["Status"])
            st.toast(f"All scrapers done: {ok_count}/{len(results)} succeeded", icon="🏁")

    # ---- Tab 3: History ----
    with tab_history:
        section_header("📋", "Scrape History (this session)")

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
        section_header("⚠️", "Scrape Errors")

        if st.button("🔄 Refresh Errors", key="admin_refresh_errors"):
            st.cache_data.clear()
            st.rerun()

        errors_df = api.get_scrape_errors()
        if errors_df.empty:
            st.success("No scrape errors recorded! 🚀")
        else:
            metric_cards([
                {"label": "Total Errors", "value": format_number(len(errors_df)), "icon": "⚠️"},
            ])
            st.dataframe(
                errors_df,
                column_config={
                    "url": st.column_config.LinkColumn("Failed URL"),
                    "status": "HTTP Status", "extracted_at": "Timestamp"
                },
                use_container_width=True, hide_index=True, height=400,
            )


admin_main()
