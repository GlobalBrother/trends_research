import sys
import os
import math
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

# Ensure the project root (the directory containing 'src') is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.dashboard.utils.api_client import APIClient


# ---------------------------------------------------------------------------
# Modern dark Plotly template
# ---------------------------------------------------------------------------

_MODERN_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, -apple-system, sans-serif", color="#c9d1d9", size=12),
        title=dict(font=dict(size=14, color="#e6edf3"), x=0.01, xanchor="left"),
        xaxis=dict(
            gridcolor="rgba(48,54,61,0.5)", zerolinecolor="rgba(48,54,61,0.5)",
            tickfont=dict(size=11), title_font=dict(size=12),
        ),
        yaxis=dict(
            gridcolor="rgba(48,54,61,0.5)", zerolinecolor="rgba(48,54,61,0.5)",
            tickfont=dict(size=11), title_font=dict(size=12),
        ),
        colorway=[
            "#58a6ff", "#3fb950", "#d29922", "#f778ba",
            "#79c0ff", "#56d364", "#e3b341", "#db61a2",
            "#a5d6ff", "#7ee787", "#f0c74f", "#ff7b72",
        ],
        margin=dict(t=40, b=20, l=20, r=20),
        hoverlabel=dict(
            bgcolor="#1c2128", bordercolor="#58a6ff",
            font=dict(color="#e6edf3", size=12),
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)", bordercolor="rgba(48,54,61,0.5)",
            font=dict(size=11),
        ),
    )
)

pio.templates["modern_dark"] = _MODERN_TEMPLATE
pio.templates.default = "modern_dark"

# Shared color scales
GRADIENT_TEAL = ["#0d3b4f", "#0e6655", "#1abc9c", "#58d68d", "#abebc6"]
GRADIENT_BLUE = ["#0a1929", "#1a3a5c", "#2e6da4", "#58a6ff", "#a5d6ff"]
GRADIENT_PURPLE = ["#1a0a2e", "#3b1f6e", "#6c3fa0", "#a855f7", "#d8b4fe"]
GRADIENT_SUNSET = ["#1a0a0a", "#6b2020", "#d35400", "#f39c12", "#f9e79f"]


def _apply_modern_layout(fig, **overrides):
    """Apply consistent modern styling to any plotly figure."""
    defaults = dict(
        template="modern_dark",
        margin=dict(t=40, b=20, l=20, r=20),
    )
    defaults.update(overrides)
    fig.update_layout(**defaults)
    fig.update_traces(marker=dict(line=dict(width=0)))
    return fig


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def format_number(val):
    """Format large numbers with K/M suffixes."""
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


def metric_cards(metrics: list[dict]):
    """Render a row of styled metric cards."""
    html = '<div class="metric-row">'
    for m in metrics:
        html += f"""
        <div class="metric-card">
            <div class="metric-value">{m.get('icon','')} {m['value']}</div>
            <div class="metric-label">{m['label']}</div>
        </div>"""
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def section_header(icon, title):
    """Render a styled section header."""
    st.markdown(f'<div class="section-header"><h3>{icon} {title}</h3></div>', unsafe_allow_html=True)


def render_dataframe(df, columns, col_config=None, height=400, search_key=None):
    """Render an interactive dataframe with search/filter and column sorting."""
    available = [c for c in columns if c in df.columns]
    if not available:
        st.info("No data columns available.")
        return
    display_df = df[available].copy()

    # Interactive search filter
    if search_key and len(display_df) > 5:
        search_term = st.text_input(
            "🔍 Search table…", key=search_key, placeholder="Type to filter rows…",
            label_visibility="collapsed",
        )
        if search_term:
            mask = display_df.apply(
                lambda row: row.astype(str).str.contains(search_term, case=False, na=False).any(),
                axis=1,
            )
            display_df = display_df[mask]
            if display_df.empty:
                st.caption(f"No results for _{search_term}_")
                return

    kwargs = dict(column_config=col_config, use_container_width=True, hide_index=True)
    if height is not None:
        kwargs["height"] = height
    try:
        st.dataframe(display_df, **kwargs)
    except Exception:
        st.dataframe(display_df, **kwargs)


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
# Per-tab filter helper
# ---------------------------------------------------------------------------

def render_tab_filters(api, tab_key, table_name, geo_col="geo", keyword_col="search_keyword", show_geo=True):
    """Render Country & Niche selectors inside a tab, populated from DB data."""
    geos, keywords = api.get_table_filters(table_name, geo_col=geo_col, keyword_col=keyword_col)
    niches = api.get_niches()

    if show_geo:
        col1, col2 = st.columns(2)
        with col1:
            geo = st.selectbox("🌍 Country / Geo", geos, key=f"geo_{tab_key}")
        with col2:
            niche = st.selectbox("🎯 Niche", niches, key=f"niche_{tab_key}")
    else:
        geo = "All"
        niche = st.selectbox("🎯 Niche", niches, key=f"niche_{tab_key}")

    # Map "All" back to values the API methods expect
    effective_geo = None if geo == "All" else geo
    return {"geo": effective_geo, "niche": niche, "geo_label": geo}


# ---------------------------------------------------------------------------
# Tab renderers
# ---------------------------------------------------------------------------

def tab_niche_research(api):
    """Niche Research — overview with KPI cards, table, and charts."""
    cfg = render_tab_filters(api, "niche", "trends", geo_col="geo", keyword_col="keyword")
    niche, geo = cfg["niche"], cfg["geo"]

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.markdown(f"#### 🎯 {niche} — {cfg['geo_label']}")
    with col_b:
        if st.button("🔄 Refresh", key="refresh_niche", width='stretch'):
            st.cache_data.clear()
            st.rerun()

    with st.spinner(f"Loading trends…"):
        df = api.get_trends(geo=geo or "Global", niche_name=niche)

    if df.empty:
        st.warning(f"No trends for **{niche}** in **{cfg['geo_label']}**. Run the scraper first.")
        return df

    work = exclude_regions(df)
    if geo and geo != "Global" and 'geo' in work.columns:
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
        search_key="search_niche",
    )

    # Charts — always visible, side by side
    section_header("📊", "Visual Breakdown")
    c1, c2 = st.columns(2)
    plot_df = flatten_platform(work)
    with c1:
        if not plot_df.empty:
            fig = px.pie(plot_df.head(15), names=topic_col, values='virality_score',
                         title="Virality Share", hole=0.45,
                         color_discrete_sequence=GRADIENT_TEAL)
            _apply_modern_layout(fig, showlegend=False)
            fig.update_traces(textinfo="percent+label", textfont_size=11,
                              marker=dict(line=dict(color="#0e1117", width=1.5)))
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        if not plot_df.empty:
            fig2 = px.bar(plot_df.head(15), x=topic_col, y='growth', color='platform',
                          title="Growth by Platform")
            _apply_modern_layout(fig2, xaxis_tickangle=-40, bargap=0.15)
            fig2.update_traces(marker=dict(line=dict(width=0),
                               opacity=0.9))
            st.plotly_chart(fig2, use_container_width=True)

    return df


def tab_daily_trends(api):
    """Google Trending Now / Daily Trends."""
    cfg = render_tab_filters(api, "daily", "trends", geo_col="geo", keyword_col="keyword")
    geo = cfg["geo"]
    country = cfg["geo_label"]
    if not geo or geo == "Global":
        country = "United States (default)"
        geo = "US"

    col_a, col_b, col_c = st.columns([2, 1, 1])
    with col_a:
        st.markdown(f"#### 📈 Daily Trends — {country}")
    with col_b:
        trend_type = st.radio("Type", ["daily", "realtime"], horizontal=True, label_visibility="collapsed")
    with col_c:
        if st.button("🔄 Refresh", key="refresh_daily", width='stretch'):
            st.cache_data.clear()
            st.rerun()

    with st.spinner(f"Fetching {trend_type} trends…"):
        df = api.get_trending_now(geo=geo, trend_type=trend_type)

    if df.empty:
        st.info("No daily trends found. The scraper might be running or blocked.")
        return

    # Ensure numeric columns are properly typed
    for col in ('growth', 'virality_score'):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

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
        search_key="search_daily",
    )

    section_header("📊", f"Top {trend_type.capitalize()} Trends")
    fig = px.bar(df.head(15), x='topic', y='growth', color='virality_score',
                 color_continuous_scale=GRADIENT_BLUE)
    _apply_modern_layout(fig, xaxis_tickangle=-40, bargap=0.15)
    st.plotly_chart(fig, use_container_width=True)


def tab_youtube(api):
    """YouTube — dedicated tab using youtube_videos table."""
    cfg = render_tab_filters(api, "yt", "youtube_videos", show_geo=False)

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.markdown("##### 🎬 YouTube Videos")
    with col_b:
        if st.button("🔄 Refresh", key="refresh_yt", width='stretch'):
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
        search_key="search_yt",
    )

    # --- Charts ---
    if 'view_count' in df.columns and 'engagement_total' in df.columns:
        section_header("📊", "Views vs Engagement")
        fig = px.scatter(df.head(50), x='view_count', y='engagement_total',
                         hover_name='title' if 'title' in df.columns else None,
                         color='engagement_total', color_continuous_scale=GRADIENT_TEAL,
                         size='view_count', size_max=30)
        _apply_modern_layout(fig)
        st.plotly_chart(fig, use_container_width=True)

    if 'channel_title' in df.columns and 'view_count' in df.columns:
        section_header("📊", "Top Channels by Views")
        top_channels = df.groupby('channel_title')['view_count'].sum().nlargest(15).reset_index()
        fig2 = px.bar(top_channels, x='channel_title', y='view_count',
                      color='view_count', color_continuous_scale=GRADIENT_TEAL)
        _apply_modern_layout(fig2, xaxis_tickangle=-40, bargap=0.15)
        st.plotly_chart(fig2, use_container_width=True)


def tab_tiktok(api):
    """TikTok — dedicated tab using tiktok_videos table."""
    cfg = render_tab_filters(api, "tiktok", "tiktok_videos", show_geo=False)

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.markdown("##### 🎵 TikTok Videos")
    with col_b:
        if st.button("🔄 Refresh", key="refresh_tiktok", width='stretch'):
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
        search_key="search_tiktok",
    )

    # --- Charts side by side ---
    c1, c2 = st.columns(2)
    with c1:
        section_header("📊", "Plays vs Engagement")
        if 'play_count' in df.columns and 'engagement_total' in df.columns:
            chart_df = df.head(30).copy()
            fig = px.scatter(
                chart_df, x='play_count', y='engagement_total',
                size='digg_count' if 'digg_count' in chart_df.columns else None,
                color='engagement_total', hover_name='description',
                color_continuous_scale=GRADIENT_PURPLE,
                labels={'play_count': 'Plays', 'engagement_total': 'Engagement'},
            )
            _apply_modern_layout(fig)
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        # --- Engagement breakdown donut ---
        if all(c in df.columns for c in ['digg_count', 'comment_count', 'share_count', 'collect_count']):
            section_header("📈", "Engagement Breakdown")
            eng_data = {
                'Type': ['Likes', 'Comments', 'Shares', 'Saves'],
                'Count': [df['digg_count'].sum(), df['comment_count'].sum(),
                          df['share_count'].sum(), df['collect_count'].sum()]
            }
            fig3 = px.pie(pd.DataFrame(eng_data), names='Type', values='Count', hole=0.5,
                          color_discrete_sequence=['#f778ba', '#58a6ff', '#3fb950', '#d29922'])
            _apply_modern_layout(fig3)
            fig3.update_traces(textinfo="percent+label", textfont_size=11,
                              marker=dict(line=dict(color="#0e1117", width=1.5)))
            st.plotly_chart(fig3, use_container_width=True)

    # --- Top creators bar chart ---
    if 'author_unique_id' in df.columns and 'play_count' in df.columns:
        section_header("👤", "Top Creators by Plays")
        creator_df = df.groupby('author_unique_id', as_index=False)['play_count'].sum() \
                       .sort_values('play_count', ascending=False).head(15)
        fig2 = px.bar(creator_df, x='author_unique_id', y='play_count',
                      color='play_count', color_continuous_scale=GRADIENT_PURPLE,
                      labels={'author_unique_id': 'Creator', 'play_count': 'Total Plays'})
        _apply_modern_layout(fig2, xaxis_tickangle=-40, bargap=0.15)
        st.plotly_chart(fig2, use_container_width=True)


def tab_instagram(api):
    """Instagram posts from dedicated table."""
    cfg = render_tab_filters(api, "instagram", "instagram_posts", show_geo=False)

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.markdown("##### 📸 Instagram")
    with col_b:
        if st.button("🔄 Refresh", key="refresh_instagram", width='stretch'):
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
        search_key="search_instagram",
    )

    if 'username' in df.columns and 'like_count' in df.columns:
        section_header("📊", "Top Creators by Likes")
        top_creators = df.groupby('username')['like_count'].sum().nlargest(15).reset_index()
        fig = px.bar(top_creators, x='username', y='like_count',
                     color='like_count', color_continuous_scale=GRADIENT_PURPLE)
        _apply_modern_layout(fig, xaxis_tickangle=-40, bargap=0.15)
        st.plotly_chart(fig, use_container_width=True)


def tab_threads(api):
    """Threads posts from dedicated table."""
    cfg = render_tab_filters(api, "threads", "threads_posts")

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.markdown("##### 💬 Threads")
    with col_b:
        if st.button("🔄 Refresh", key="refresh_threads", width='stretch'):
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
        search_key="search_threads",
    )

    if 'username' in df.columns and 'like_count' in df.columns:
        section_header("📊", "Top Creators by Likes")
        top_creators = df.groupby('username')['like_count'].sum().nlargest(15).reset_index()
        fig = px.bar(top_creators, x='username', y='like_count',
                     color='like_count', color_continuous_scale=GRADIENT_BLUE)
        _apply_modern_layout(fig, xaxis_tickangle=-40, bargap=0.15)
        st.plotly_chart(fig, use_container_width=True)



def tab_reddit(api):
    """Reddit posts from dedicated table."""
    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.markdown("##### 👽 Reddit")
    with col_b:
        if st.button("🔄 Refresh", key="refresh_reddit", width='stretch'):
            st.cache_data.clear()
            st.rerun()

    with st.spinner("Fetching Reddit posts…"):
        df = api.get_reddit_posts()

    if df.empty:
        st.info("No Reddit posts found. Run the scraper first.")
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
        height=None,
        search_key="search_reddit",
    )

    c1, c2 = st.columns(2)
    with c1:
        if 'score' in df.columns and 'num_comments' in df.columns:
            section_header("📊", "Score vs Comments")
            fig = px.scatter(df.head(50), x='score', y='num_comments',
                             hover_name='title' if 'title' in df.columns else None,
                             color='engagement_total' if 'engagement_total' in df.columns else None,
                             color_continuous_scale=GRADIENT_SUNSET,
                             size='score', size_max=30)
            _apply_modern_layout(fig)
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        if 'subreddit' in df.columns and 'score' in df.columns:
            section_header("📊", "Top Subreddits by Score")
            top_subs = df.groupby('subreddit')['score'].sum().nlargest(15).reset_index()
            fig2 = px.bar(top_subs, x='subreddit', y='score',
                          color='score', color_continuous_scale=GRADIENT_SUNSET)
            _apply_modern_layout(fig2, xaxis_tickangle=-40, bargap=0.15)
            st.plotly_chart(fig2, use_container_width=True)


def tab_community_news(api):
    """Hacker News, News."""
    cfg = render_tab_filters(api, "community", "trends", geo_col="geo", keyword_col="keyword")
    sources = {"🧡 Hacker News": "hn", "📰 News": "news"}

    col_a, col_b = st.columns([3, 1])
    with col_a:
        choice = st.radio("Source", list(sources.keys()), horizontal=True, label_visibility="collapsed")
    src = sources[choice]

    # --- Hacker News ---
    if src == "hn":
        with col_b:
            if st.button("🔄 Refresh", key="refresh_hn", width='stretch'):
                st.cache_data.clear()
                st.rerun()

        with st.spinner("Fetching Hacker News…"):
            df = api.get_hackernews_trends(niche_name=cfg["niche"], geo=cfg["geo"] or "US")

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
            search_key="search_hn",
        )

        section_header("📊", "Points vs Comments")
        fig = px.scatter(df, x='growth', y='engagement', size='virality_score',
                         color='virality_score', hover_name='topic',
                         color_continuous_scale=GRADIENT_TEAL)
        _apply_modern_layout(fig)
        st.plotly_chart(fig, use_container_width=True)

    # --- News ---
    elif src == "news":
        with col_b:
            news_query = st.text_input("Query", value=cfg["niche"] or "Health",
                                       label_visibility="collapsed", placeholder="query…")

        with st.spinner("Fetching News…"):
            df = api.get_news_trends(query=news_query, niche_name=cfg["niche"], geo=cfg["geo"] or "US")

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
            search_key="search_news",
        )
