import sys
import os
import streamlit as st
import pandas as pd
import plotly.express as px

# Ensure the project root (the directory containing 'src') is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.dashboard.utils.api_client import APIClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_number(val):
    """Format large numbers with K/M suffixes."""
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


def inject_custom_css():
    """Inject custom CSS for a cleaner, more responsive UI."""
    st.markdown("""
    <style>
    /* ---- Global ---- */
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #0e1117 0%, #1a1d23 100%); }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stRadio label { font-size: 0.85rem; }

    /* ---- Metric cards ---- */
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
        font-size: 1.6rem;
        font-weight: 700;
        color: #58a6ff;
        line-height: 1.2;
    }
    .metric-card .metric-label {
        font-size: 0.78rem;
        color: #8b949e;
        margin-top: 0.25rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* ---- Section headers ---- */
    .section-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 1.2rem 0 0.6rem 0;
        padding-bottom: 0.4rem;
        border-bottom: 2px solid #30363d;
    }
    .section-header h3 {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
        color: #e6edf3;
    }

    /* ---- Action bar ---- */
    .action-bar {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 0.75rem;
        flex-wrap: wrap;
    }

    /* ---- Status badge ---- */
    .status-badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 20px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.3px;
    }
    .status-ok { background: #1a3a2a; color: #3fb950; border: 1px solid #238636; }
    .status-warn { background: #3a2a1a; color: #d29922; border: 1px solid #9e6a03; }

    /* ---- Tabs ---- */
    .stTabs [data-baseweb="tab-list"] { gap: 0.25rem; }
    .stTabs [data-baseweb="tab"] {
        padding: 0.5rem 1rem;
        border-radius: 8px 8px 0 0;
        font-size: 0.85rem;
    }

    /* ---- Dataframe tweaks ---- */
    [data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }

    /* ---- Responsive ---- */
    @media (max-width: 768px) {
        .metric-card { min-width: 100px; padding: 0.7rem; }
        .metric-card .metric-value { font-size: 1.2rem; }
    }
    </style>
    """, unsafe_allow_html=True)


def metric_cards(metrics: list[dict]):
    """Render a row of metric cards. Each dict: {label, value, icon?}."""
    cards_html = '<div class="metric-row">'
    for m in metrics:
        icon = m.get("icon", "")
        cards_html += f"""
        <div class="metric-card">
            <div class="metric-value">{icon} {m['value']}</div>
            <div class="metric-label">{m['label']}</div>
        </div>"""
    cards_html += '</div>'
    st.markdown(cards_html, unsafe_allow_html=True)


def section_header(icon, title):
    st.markdown(f'<div class="section-header"><h3>{icon} {title}</h3></div>', unsafe_allow_html=True)


def render_dataframe(df, columns, col_config=None, height=400):
    """Display a dataframe with safe column handling and optional gradient."""
    if df.empty:
        st.info("No data available.")
        return
    display_df = df.copy()
    for col in columns:
        if col not in display_df.columns:
            display_df[col] = "N/A"
    if 'virality_score' in display_df.columns:
        display_df['virality_score'] = pd.to_numeric(display_df['virality_score'], errors='coerce').fillna(0)
    try:
        if 'virality_score' in columns:
            st.dataframe(
                display_df[columns].style.background_gradient(subset=['virality_score'], cmap='viridis'),
                column_config=col_config, height=height, use_container_width=True, hide_index=True
            )
        else:
            st.dataframe(
                display_df[columns],
                column_config=col_config, height=height, use_container_width=True, hide_index=True
            )
    except Exception:
        st.dataframe(display_df[columns], column_config=col_config, height=height, use_container_width=True, hide_index=True)


def scrape_button(api, label, scraper_type, niche, geo, timeframe, category, key):
    """Compact scrape trigger that returns True on success."""
    if st.button(f"🚀 {label}", key=key, use_container_width=True):
        with st.spinner(f"Scraping {label}..."):
            ok = api.trigger_scrape(niche_name=niche, geo=geo, timeframe=timeframe,
                                    category=category, scraper_type=scraper_type)
            if ok:
                st.toast(f"✅ {label} scrape started!", icon="🎉")
                st.cache_data.clear()
            else:
                st.error("❌ Scraping failed")
            return ok
    return False


def flatten_platform(df):
    """Ensure platform/geo columns are strings, not lists."""
    out = df.copy()
    for col in ('platform', 'geo'):
        if col in out.columns:
            out[col] = out[col].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x))
    return out


def exclude_regions(df):
    """Filter out Google Regions rows."""
    if 'platform' not in df.columns:
        return df
    return df[df['platform'].apply(lambda x: x != 'Google Regions' and not (isinstance(x, list) and x == ['Google Regions']))]


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar(api):
    """Build sidebar controls and return selections dict."""
    with st.sidebar:
        st.markdown("### ⚙️ Controls")

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
        country_name = st.selectbox("🌍 Country", list(countries.keys()))
        geo = countries[country_name]

        niches = api.get_niches()
        niche = st.selectbox("🎯 Niche", niches)

        st.markdown("---")

        with st.expander("🔧 Scraper Settings", expanded=False):
            timeframes = {
                "Last 12 Months": "today 12-m", "Last hour": "now 1-H",
                "Last 4 hours": "now 4-H", "Last day": "now 1-d",
                "Last 7 days": "now 7-d", "Last 30 days": "today 1-m",
                "Last 90 days": "today 3-m", "Last 5 years": "today 5-y",
                "All (since 2004)": "all"
            }
            tf_name = st.selectbox("Time Range", list(timeframes.keys()))
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
            cat_name = st.selectbox("Category", list(categories.keys()))
            category = categories[cat_name]

        with st.expander("📥 Import Google Trends JSON", expanded=False):
            st.caption("Upload the JSON/TXT file from a 429 error.")
            uploaded = st.file_uploader("Choose file", type=["json", "txt"], key="token_upload")
            if uploaded is not None and st.button("⬆️ Import", key="import_btn"):
                with st.spinner("Importing..."):
                    result = api.import_tokens(uploaded.getvalue(), uploaded.name, geo=geo)
                    if result:
                        st.success(result.get("message", "Import started!"))
                        st.cache_data.clear()
                    else:
                        st.error("❌ Import failed")

    return {
        "country_name": country_name, "geo": geo, "niche": niche,
        "timeframe": timeframe, "category": category,
    }


# ---------------------------------------------------------------------------
# Tab renderers
# ---------------------------------------------------------------------------

def tab_niche_research(api, cfg):
    """Niche Research — overview with KPI cards, table, and charts."""
    niche, geo, country = cfg["niche"], cfg["geo"], cfg["country_name"]

    col_a, col_b, col_c = st.columns([2, 1, 1])
    with col_a:
        st.markdown(f"#### 🎯 {niche} — {country}")
    with col_b:
        scrape_button(api, f"Scrape {niche}", "google_trends", niche, geo,
                       cfg["timeframe"], cfg["category"], "scrape_niche")
    with col_c:
        if st.button("🔄 Refresh", key="refresh_niche", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    with st.spinner(f"Loading trends…"):
        df = api.get_trends(geo=geo, niche_name=niche)

    if df.empty:
        st.warning(f"No trends for **{niche}** in **{country}**. Run the scraper first.")
        return df

    work = exclude_regions(df)
    if geo != "Global" and 'geo' in work.columns:
        work = work[work['geo'].apply(lambda x: x != 'Global' and x != '' and not (isinstance(x, list) and 'Global' in x))]

    # KPI cards
    total = len(work)
    platforms = work['platform'].apply(lambda x: x if isinstance(x, str) else str(x)).nunique() if 'platform' in work.columns else 0
    avg_virality = work['virality_score'].mean() if 'virality_score' in work.columns else 0
    top_growth = work['growth'].max() if 'growth' in work.columns else 0
    metric_cards([
        {"label": "Total Trends", "value": format_number(total), "icon": "📊"},
        {"label": "Platforms", "value": str(platforms), "icon": "🔗"},
        {"label": "Avg Virality", "value": f"{avg_virality:.1f}", "icon": "🔥"},
        {"label": "Top Growth", "value": format_number(top_growth), "icon": "📈"},
    ])

    # Table
    section_header("📋", "Trending Topics")
    topic_col = 'aggregated_topic' if 'aggregated_topic' in work.columns else 'topic'
    cols = [topic_col, 'platform', 'growth', 'sentiment', 'virality_score']
    for opt in ('geo', 'keyword', 'url'):
        if opt in work.columns:
            cols.append(opt)
    render_dataframe(
        flatten_platform(work), cols,
        col_config={
            "url": st.column_config.LinkColumn("Source"),
            "growth": st.column_config.NumberColumn("Growth", format="%.1f"),
            "virality_score": st.column_config.NumberColumn("Virality", format="%.2f"),
        },
        height=380,
    )

    # Charts — always visible, side by side
    section_header("📊", "Visual Breakdown")
    c1, c2 = st.columns(2)
    plot_df = flatten_platform(work)
    with c1:
        if not plot_df.empty:
            fig = px.pie(plot_df.head(15), names=topic_col, values='virality_score',
                         title="Virality Share", hole=0.4,
                         color_discrete_sequence=px.colors.sequential.Tealgrn)
            fig.update_layout(margin=dict(t=40, b=10, l=10, r=10), showlegend=False,
                              paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        if not plot_df.empty:
            fig2 = px.bar(plot_df.head(15), x=topic_col, y='growth', color='platform',
                          title="Growth by Platform",
                          color_discrete_sequence=px.colors.qualitative.Set2)
            fig2.update_layout(margin=dict(t=40, b=10, l=10, r=10), xaxis_tickangle=-40,
                               paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig2, use_container_width=True)

    return df


def tab_daily_trends(api, cfg):
    """Google Trending Now / Daily Trends."""
    geo = cfg["geo"]
    country = cfg["country_name"]
    if geo == "Global":
        country = "United States (default)"
        geo = "US"

    col_a, col_b, col_c, col_d = st.columns([2, 1, 1, 1])
    with col_a:
        st.markdown(f"#### 📈 Daily Trends — {country}")
    with col_b:
        trend_type = st.radio("Type", ["daily", "realtime"], horizontal=True, label_visibility="collapsed")
    with col_c:
        scrape_button(api, "Scrape Daily", "daily", cfg["niche"], geo,
                       cfg["timeframe"], cfg["category"], "scrape_daily")
    with col_d:
        if st.button("🔄 Refresh", key="refresh_daily", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    with st.spinner(f"Fetching {trend_type} trends…"):
        df = api.get_trending_now(geo=geo, trend_type=trend_type)

    if df.empty:
        st.info("No daily trends found. The scraper might be running or blocked.")
        return

    # KPIs
    metric_cards([
        {"label": "Trends", "value": format_number(len(df)), "icon": "🔥"},
        {"label": "Top Traffic", "value": format_number(df['growth'].max()) if 'growth' in df.columns else "—", "icon": "📈"},
        {"label": "Avg Virality", "value": f"{df['virality_score'].mean():.1f}" if 'virality_score' in df.columns else "—", "icon": "⚡"},
    ])

    render_dataframe(
        df, ['topic', 'growth', 'virality_score', 'url'],
        col_config={"url": st.column_config.LinkColumn("Link"), "growth": "Traffic"},
        height=380,
    )

    section_header("📊", f"Top {trend_type.capitalize()} Trends")
    fig = px.bar(df.head(15), x='topic', y='growth', color='virality_score',
                 color_continuous_scale='viridis')
    fig.update_layout(margin=dict(t=20, b=10, l=10, r=10), xaxis_tickangle=-40,
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)


def tab_youtube(api, cfg):
    """YouTube — dedicated tab using youtube_videos table."""
    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.markdown("##### 🎬 YouTube Videos")
    with col_b:
        c1, c2 = st.columns(2)
        with c1:
            scrape_button(api, "YouTube", "youtube", cfg["niche"], cfg["geo"],
                          cfg["timeframe"], cfg["category"], "scrape_yt")
        with c2:
            if st.button("🔄", key="refresh_yt", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

    with st.spinner("Fetching YouTube videos…"):
        df = api.get_youtube_videos(niche_name=cfg["niche"], geo=cfg["geo"])

    if df.empty:
        st.info(f"No YouTube videos for **{cfg['niche']}**. Run the YouTube scraper first.")
        return

    # --- KPI cards ---
    total_views = df['view_count'].sum() if 'view_count' in df.columns else 0
    total_engagement = df['engagement_total'].sum() if 'engagement_total' in df.columns else 0
    top_likes = df['like_count'].max() if 'like_count' in df.columns else 0
    unique_channels = df['channel_title'].nunique() if 'channel_title' in df.columns else 0

    metric_cards([
        {"label": "Videos", "value": format_number(len(df)), "icon": "🎬"},
        {"label": "Total Views", "value": format_number(total_views), "icon": "👁️"},
        {"label": "Total Engagement", "value": format_number(total_engagement), "icon": "🔥"},
        {"label": "Top Likes", "value": format_number(top_likes), "icon": "❤️"},
        {"label": "Channels", "value": format_number(unique_channels), "icon": "📺"},
    ])

    # --- Data table ---
    display_cols = [c for c in [
        'title', 'channel_title', 'view_count', 'like_count',
        'comment_count', 'engagement_total', 'published', 'duration', 'tags', 'url'
    ] if c in df.columns]

    num_cols = ['view_count', 'like_count', 'comment_count', 'engagement_total']
    display_df = df.copy()
    for nc in num_cols:
        if nc in display_df.columns:
            display_df[nc] = display_df[nc].apply(format_number)

    render_dataframe(
        display_df, display_cols,
        col_config={
            "url": st.column_config.LinkColumn("Link"),
            "view_count": "👁️ Views",
            "like_count": "❤️ Likes",
            "comment_count": "💬 Comments",
            "engagement_total": "🔥 Engagement",
            "channel_title": "Channel",
            "title": "Title",
            "published": "Published",
            "duration": "Duration",
            "tags": "Tags",
        },
        height=380,
    )

    # --- Charts ---
    if 'view_count' in df.columns and 'engagement_total' in df.columns:
        section_header("📊", "Views vs Engagement")
        fig = px.scatter(df.head(50), x='view_count', y='engagement_total',
                         hover_name='title' if 'title' in df.columns else None,
                         color='engagement_total', color_continuous_scale='tealgrn',
                         size='view_count', size_max=30)
        fig.update_layout(margin=dict(t=20, b=10, l=10, r=10),
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

    if 'channel_title' in df.columns and 'view_count' in df.columns:
        section_header("📊", "Top Channels by Views")
        top_channels = df.groupby('channel_title')['view_count'].sum().nlargest(15).reset_index()
        fig2 = px.bar(top_channels, x='channel_title', y='view_count',
                      color='view_count', color_continuous_scale='tealgrn')
        fig2.update_layout(margin=dict(t=20, b=10, l=10, r=10), xaxis_tickangle=-40,
                           paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig2, use_container_width=True)


def tab_tiktok(api, cfg):
    """TikTok — dedicated tab using tiktok_videos table."""
    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.markdown("##### 🎵 TikTok Videos")
    with col_b:
        c1, c2 = st.columns(2)
        with c1:
            scrape_button(api, "TikTok", "TikTok", cfg["niche"], cfg["geo"],
                          cfg["timeframe"], cfg["category"], "scrape_tiktok")
        with c2:
            if st.button("🔄", key="refresh_tiktok", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

    with st.spinner("Fetching TikTok videos…"):
        df = api.get_tiktok_videos(niche_name=cfg["niche"], geo=cfg["geo"])

    if df.empty:
        st.info(f"No TikTok videos for **{cfg['niche']}**. Run the TikTok scraper first.")
        return

    # --- KPI cards ---
    total_plays = df['play_count'].sum() if 'play_count' in df.columns else 0
    total_engagement = df['engagement_total'].sum() if 'engagement_total' in df.columns else 0
    top_likes = df['digg_count'].max() if 'digg_count' in df.columns else 0
    unique_authors = df['author_unique_id'].nunique() if 'author_unique_id' in df.columns else 0

    metric_cards([
        {"label": "Videos", "value": format_number(len(df)), "icon": "🎬"},
        {"label": "Total Plays", "value": format_number(total_plays), "icon": "▶️"},
        {"label": "Total Engagement", "value": format_number(total_engagement), "icon": "🔥"},
        {"label": "Top Likes", "value": format_number(top_likes), "icon": "❤️"},
        {"label": "Creators", "value": format_number(unique_authors), "icon": "👤"},
    ])

    # --- Data table ---
    display_cols = [c for c in [
        'description', 'author_unique_id', 'play_count', 'digg_count',
        'comment_count', 'share_count', 'collect_count', 'engagement_total',
        'hashtags', 'music_title', 'created', 'share_url'
    ] if c in df.columns]

    # Normalize large numbers with K/M suffixes for readability
    num_cols = ['play_count', 'digg_count', 'comment_count', 'share_count',
                'collect_count', 'engagement_total']
    display_df = df.copy()
    for nc in num_cols:
        if nc in display_df.columns:
            display_df[nc] = display_df[nc].apply(format_number)

    render_dataframe(
        display_df, display_cols,
        col_config={
            "share_url": st.column_config.LinkColumn("Link"),
            "play_count": "▶️ Plays",
            "digg_count": "❤️ Likes",
            "comment_count": "💬 Comments",
            "share_count": "🔗 Shares",
            "collect_count": "⭐ Saves",
            "engagement_total": "🔥 Engagement",
            "author_unique_id": "Creator",
            "description": "Description",
            "hashtags": "#Tags",
            "music_title": "🎵 Sound",
            "created": "Posted",
        },
        height=420,
    )

    # --- Charts ---
    section_header("📊", "Plays vs Engagement")
    if 'play_count' in df.columns and 'engagement_total' in df.columns:
        chart_df = df.head(30).copy()
        fig = px.scatter(
            chart_df, x='play_count', y='engagement_total',
            size='digg_count' if 'digg_count' in chart_df.columns else None,
            color='engagement_total', hover_name='description',
            color_continuous_scale='purp',
            labels={'play_count': 'Plays', 'engagement_total': 'Engagement'},
        )
        fig.update_layout(margin=dict(t=20, b=10, l=10, r=10),
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

    # --- Top creators bar chart ---
    if 'author_unique_id' in df.columns and 'play_count' in df.columns:
        section_header("👤", "Top Creators by Plays")
        creator_df = df.groupby('author_unique_id', as_index=False)['play_count'].sum() \
                       .sort_values('play_count', ascending=False).head(15)
        fig2 = px.bar(creator_df, x='author_unique_id', y='play_count',
                      color='play_count', color_continuous_scale='tealgrn',
                      labels={'author_unique_id': 'Creator', 'play_count': 'Total Plays'})
        fig2.update_layout(margin=dict(t=20, b=10, l=10, r=10), xaxis_tickangle=-40,
                           paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig2, use_container_width=True)

    # --- Engagement breakdown donut ---
    if all(c in df.columns for c in ['digg_count', 'comment_count', 'share_count', 'collect_count']):
        section_header("📈", "Engagement Breakdown")
        eng_data = {
            'Type': ['Likes', 'Comments', 'Shares', 'Saves'],
            'Count': [df['digg_count'].sum(), df['comment_count'].sum(),
                      df['share_count'].sum(), df['collect_count'].sum()]
        }
        fig3 = px.pie(pd.DataFrame(eng_data), names='Type', values='Count', hole=0.45,
                      color_discrete_sequence=['#ff6b6b', '#4ecdc4', '#45b7d1', '#f9ca24'])
        fig3.update_layout(margin=dict(t=20, b=10, l=10, r=10),
                           paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig3, use_container_width=True)


def tab_instagram(api, cfg):
    """Instagram posts from dedicated table."""
    col_a, col_b = st.columns([3, 1])
    with col_b:
        c1, c2 = st.columns(2)
        with c1:
            scrape_button(api, "Instagram", "Instagram", cfg["niche"], cfg["geo"],
                           cfg["timeframe"], cfg["category"], "scrape_instagram")
        with c2:
            if st.button("🔄", key="refresh_instagram", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

    with st.spinner("Fetching Instagram posts…"):
        df = api.get_instagram_posts(niche_name=cfg["niche"], geo=cfg["geo"])

    if df.empty:
        st.info(f"No Instagram posts for **{cfg['niche']}**. Run the scraper first.")
        return

    total_likes = df['like_count'].sum() if 'like_count' in df.columns else 0
    total_engagement = df['engagement_total'].sum() if 'engagement_total' in df.columns else 0
    unique_users = df['username'].nunique() if 'username' in df.columns else 0

    metric_cards([
        {"label": "Posts", "value": format_number(len(df)), "icon": "📸"},
        {"label": "Total Likes", "value": format_number(total_likes), "icon": "❤️"},
        {"label": "Total Engagement", "value": format_number(total_engagement), "icon": "🔥"},
        {"label": "Creators", "value": format_number(unique_users), "icon": "👤"},
    ])

    display_cols = [c for c in [
        'caption', 'username', 'like_count', 'comment_count', 'share_count',
        'save_count', 'engagement_total', 'hashtags', 'posted', 'url'
    ] if c in df.columns]

    num_cols = ['like_count', 'comment_count', 'share_count', 'save_count', 'engagement_total']
    display_df = df.copy()
    for nc in num_cols:
        if nc in display_df.columns:
            display_df[nc] = display_df[nc].apply(format_number)

    render_dataframe(
        display_df, display_cols,
        col_config={
            "url": st.column_config.LinkColumn("Link"),
            "like_count": "❤️ Likes", "comment_count": "💬 Comments",
            "share_count": "🔗 Shares", "save_count": "⭐ Saves",
            "engagement_total": "🔥 Engagement",
            "username": "Creator", "caption": "Caption",
            "hashtags": "#Tags", "posted": "Posted",
        },
        height=380,
    )

    if 'username' in df.columns and 'like_count' in df.columns:
        section_header("📊", "Top Creators by Likes")
        top_creators = df.groupby('username')['like_count'].sum().nlargest(15).reset_index()
        fig = px.bar(top_creators, x='username', y='like_count',
                     color='like_count', color_continuous_scale='purp')
        fig.update_layout(margin=dict(t=20, b=10, l=10, r=10), xaxis_tickangle=-40,
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)


def tab_threads(api, cfg):
    """Threads posts from dedicated table."""
    col_a, col_b = st.columns([3, 1])
    with col_b:
        c1, c2 = st.columns(2)
        with c1:
            scrape_button(api, "Threads", "Threads", cfg["niche"], cfg["geo"],
                           cfg["timeframe"], cfg["category"], "scrape_threads")
        with c2:
            if st.button("🔄", key="refresh_threads", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

    with st.spinner("Fetching Threads posts…"):
        df = api.get_threads_posts(niche_name=cfg["niche"], geo=cfg["geo"])

    if df.empty:
        st.info(f"No Threads posts for **{cfg['niche']}**. Run the scraper first.")
        return

    total_likes = df['like_count'].sum() if 'like_count' in df.columns else 0
    total_engagement = df['engagement_total'].sum() if 'engagement_total' in df.columns else 0
    unique_users = df['username'].nunique() if 'username' in df.columns else 0

    metric_cards([
        {"label": "Posts", "value": format_number(len(df)), "icon": "💬"},
        {"label": "Total Likes", "value": format_number(total_likes), "icon": "❤️"},
        {"label": "Total Engagement", "value": format_number(total_engagement), "icon": "🔥"},
        {"label": "Creators", "value": format_number(unique_users), "icon": "👤"},
    ])

    display_cols = [c for c in [
        'caption', 'username', 'like_count', 'reply_count', 'repost_count',
        'quote_count', 'engagement_total', 'posted', 'url'
    ] if c in df.columns]

    num_cols = ['like_count', 'reply_count', 'repost_count', 'quote_count', 'engagement_total']
    display_df = df.copy()
    for nc in num_cols:
        if nc in display_df.columns:
            display_df[nc] = display_df[nc].apply(format_number)

    render_dataframe(
        display_df, display_cols,
        col_config={
            "url": st.column_config.LinkColumn("Link"),
            "like_count": "❤️ Likes", "reply_count": "💬 Replies",
            "repost_count": "🔁 Reposts", "quote_count": "💭 Quotes",
            "engagement_total": "🔥 Engagement",
            "username": "Creator", "caption": "Caption", "posted": "Posted",
        },
        height=380,
    )

    if 'username' in df.columns and 'like_count' in df.columns:
        section_header("📊", "Top Creators by Likes")
        top_creators = df.groupby('username')['like_count'].sum().nlargest(15).reset_index()
        fig = px.bar(top_creators, x='username', y='like_count',
                     color='like_count', color_continuous_scale='purp')
        fig.update_layout(margin=dict(t=20, b=10, l=10, r=10), xaxis_tickangle=-40,
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)



def tab_reddit(api, cfg):
    """Reddit posts from dedicated table."""
    col_a, col_b = st.columns([3, 1])
    with col_b:
        c1, c2 = st.columns(2)
        with c1:
            scrape_button(api, "Reddit", "reddit", cfg["niche"], cfg["geo"],
                           cfg["timeframe"], cfg["category"], "scrape_reddit")
        with c2:
            if st.button("🔄", key="refresh_reddit", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

    with st.spinner("Fetching Reddit posts…"):
        df = api.get_reddit_posts(niche_name=cfg["niche"], geo=cfg["geo"])

    if df.empty:
        st.info(f"No Reddit posts for **{cfg['niche']}**. Run the scraper first.")
        return

    total_score = df['score'].sum() if 'score' in df.columns else 0
    total_engagement = df['engagement_total'].sum() if 'engagement_total' in df.columns else 0
    total_comments = df['num_comments'].sum() if 'num_comments' in df.columns else 0
    unique_subs = df['subreddit'].nunique() if 'subreddit' in df.columns else 0

    metric_cards([
        {"label": "Posts", "value": format_number(len(df)), "icon": "👽"},
        {"label": "Total Score", "value": format_number(total_score), "icon": "⬆️"},
        {"label": "Total Comments", "value": format_number(total_comments), "icon": "💬"},
        {"label": "Subreddits", "value": format_number(unique_subs), "icon": "📂"},
    ])

    display_cols = [c for c in [
        'title', 'subreddit', 'author', 'score', 'num_comments',
        'upvote_ratio', 'engagement_total', 'link_flair_text', 'posted', 'url'
    ] if c in df.columns]

    num_cols = ['score', 'num_comments', 'engagement_total']
    display_df = df.copy()
    for nc in num_cols:
        if nc in display_df.columns:
            display_df[nc] = display_df[nc].apply(format_number)

    render_dataframe(
        display_df, display_cols,
        col_config={
            "url": st.column_config.LinkColumn("Link"),
            "score": "⬆️ Score", "num_comments": "💬 Comments",
            "upvote_ratio": "📊 Ratio", "engagement_total": "🔥 Engagement",
            "subreddit": "Subreddit", "author": "Author",
            "title": "Title", "link_flair_text": "Flair", "posted": "Posted",
        },
        height=380,
    )

    if 'score' in df.columns and 'num_comments' in df.columns:
        section_header("📊", "Score vs Comments")
        fig = px.scatter(df.head(50), x='score', y='num_comments',
                         hover_name='title' if 'title' in df.columns else None,
                         color='engagement_total' if 'engagement_total' in df.columns else None,
                         color_continuous_scale='sunset',
                         size='score', size_max=30)
        fig.update_layout(margin=dict(t=20, b=10, l=10, r=10),
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

    if 'subreddit' in df.columns and 'score' in df.columns:
        section_header("📊", "Top Subreddits by Score")
        top_subs = df.groupby('subreddit')['score'].sum().nlargest(15).reset_index()
        fig2 = px.bar(top_subs, x='subreddit', y='score',
                      color='score', color_continuous_scale='sunset')
        fig2.update_layout(margin=dict(t=20, b=10, l=10, r=10), xaxis_tickangle=-40,
                           paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig2, use_container_width=True)


def tab_community_news(api, cfg):
    """Hacker News, News."""
    sources = {"🧡 Hacker News": "hn", "📰 News": "news"}

    col_a, col_b = st.columns([3, 1])
    with col_a:
        choice = st.radio("Source", list(sources.keys()), horizontal=True, label_visibility="collapsed")
    src = sources[choice]

    # --- Hacker News ---
    if src == "hn":
        with col_b:
            c1, c2 = st.columns(2)
            with c1:
                scrape_button(api, "HN", "hackernews", cfg["niche"], cfg["geo"],
                               cfg["timeframe"], cfg["category"], "scrape_hn")
            with c2:
                if st.button("🔄", key="refresh_hn", use_container_width=True):
                    st.cache_data.clear()
                    st.rerun()

        with st.spinner("Fetching Hacker News…"):
            df = api.get_hackernews_trends(niche_name=cfg["niche"], geo=cfg["geo"])

        if df.empty:
            st.info("No Hacker News trends found.")
            return

        metric_cards([
            {"label": "Stories", "value": format_number(len(df)), "icon": "🧡"},
            {"label": "Top Points", "value": format_number(df['growth'].max()) if 'growth' in df.columns else "—", "icon": "⬆️"},
        ])

        render_dataframe(
            df, ['topic', 'author', 'growth', 'engagement', 'virality_score', 'url'],
            col_config={"url": st.column_config.LinkColumn("Link"), "growth": "Points",
                        "engagement": "Comments", "author": "By"},
            height=380,
        )

        section_header("📊", "Points vs Comments")
        fig = px.scatter(df, x='growth', y='engagement', size='virality_score',
                         color='virality_score', hover_name='topic',
                         color_continuous_scale='tealgrn')
        fig.update_layout(margin=dict(t=20, b=10, l=10, r=10),
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

    # --- News ---
    elif src == "news":
        with col_b:
            news_query = st.text_input("Query", value=cfg["niche"] or "Health",
                                       label_visibility="collapsed", placeholder="query…")

        c1, c2 = st.columns([1, 5])
        with c1:
            scrape_button(api, "News", "news", cfg["niche"], cfg["geo"],
                           cfg["timeframe"], cfg["category"], "scrape_news")

        with st.spinner("Fetching News…"):
            df = api.get_news_trends(query=news_query, niche_name=cfg["niche"], geo=cfg["geo"])

        if df.empty:
            st.info("No news trends found.")
            return

        metric_cards([
            {"label": "Articles", "value": format_number(len(df)), "icon": "📰"},
        ])

        render_dataframe(
            df, ['topic', 'source', 'virality_score', 'url'],
            col_config={"url": st.column_config.LinkColumn("Article"), "source": "Source"},
            height=380,
        )


def tab_errors(api):
    """Scrape errors log."""
    if st.button("🔄 Refresh", key="refresh_errors"):
        st.cache_data.clear()
        st.rerun()

    errors_df = api.get_scrape_errors()
    if errors_df.empty:
        st.success("No scrape errors recorded! 🚀")
        return

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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Trends Research", layout="wide", page_icon="🚀")
    inject_custom_css()

    st.markdown("## 🚀 Trends Research")

    api = APIClient()
    cfg = render_sidebar(api)

    # Handle refresh via geo change
    if st.session_state.get("last_geo") != cfg["geo"]:
        st.cache_data.clear()
        st.session_state.last_geo = cfg["geo"]

    # Tabs
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
        "🎯 Niche Research", "📈 Daily Trends", "🎬 YouTube", "🎵 TikTok",
        "👽 Reddit", "📸 Instagram", "💬 Threads", "🌐 Community & News", "⚠️ Errors"
    ])

    with tab1:
        niche_df = tab_niche_research(api, cfg)

    with tab2:
        tab_daily_trends(api, cfg)

    with tab3:
        tab_youtube(api, cfg)

    with tab4:
        tab_tiktok(api, cfg)

    with tab5:
        tab_reddit(api, cfg)

    with tab6:
        tab_instagram(api, cfg)

    with tab7:
        tab_threads(api, cfg)

    with tab8:
        tab_community_news(api, cfg)

    with tab9:
        tab_errors(api)

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
