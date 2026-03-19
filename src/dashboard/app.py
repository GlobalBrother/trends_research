"""
Streamlit Dashboard — Trends Research System v2.0

Redesigned with:
  - Cleaner visual hierarchy and consistent spacing
  - KPI metric cards at the top of each view
  - Improved chart defaults (color scales, labels)
  - Consolidated helper functions to reduce repetition
  - Custom CSS for a polished, professional look
"""

import sys
import os

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.dashboard.utils.api_client import APIClient
from src.config import COUNTRIES, TIMEFRAMES, CATEGORIES

# ---------------------------------------------------------------------------
# Page config & custom CSS
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Trends Research",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* Tighten default Streamlit padding */
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
    /* Sidebar header */
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2 {
        font-size: 1.1rem; margin-bottom: 0.25rem;
    }
    /* Metric cards */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border: 1px solid #dee2e6;
        border-radius: 0.5rem;
        padding: 0.75rem 1rem;
    }
    [data-testid="stMetric"] label { font-size: 0.8rem; color: #6c757d; }
    [data-testid="stMetric"] [data-testid="stMetricValue"] { font-size: 1.4rem; font-weight: 700; }
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] { gap: 0.25rem; }
    .stTabs [data-baseweb="tab"] {
        padding: 0.5rem 1rem; border-radius: 0.375rem 0.375rem 0 0;
    }
    /* Dataframe tweaks */
    .stDataFrame { border-radius: 0.375rem; }
    /* Hide Streamlit branding */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    /* Section dividers */
    hr { margin: 0.5rem 0; border-color: #dee2e6; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _format_number(val) -> str:
    """Human-readable number formatting (1.2K, 3.4M, etc.)."""
    try:
        val = float(val)
    except (TypeError, ValueError):
        return str(val)
    if val >= 1_000_000:
        return f"{val / 1_000_000:.1f}M"
    if val >= 1_000:
        return f"{val / 1_000:.1f}K"
    return str(int(val))


def _flatten_list_col(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Convert list-type column values to comma-separated strings."""
    if col in df.columns:
        df[col] = df[col].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x) if x else "")
    return df


def _ensure_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Add missing columns with 'N/A' so display never fails."""
    for c in cols:
        if c not in df.columns:
            df[c] = "N/A"
    return df


def _display_table(df: pd.DataFrame, cols: list[str], col_config: dict | None = None,
                   height: int = 380, gradient_col: str | None = "virality_score"):
    """Render a styled dataframe with optional gradient highlighting."""
    if df.empty:
        st.info("No data available.")
        return

    display = _ensure_cols(df.copy(), cols)
    display = _flatten_list_col(display, "platform")
    display = _flatten_list_col(display, "geo")

    if gradient_col and gradient_col in display.columns:
        display[gradient_col] = pd.to_numeric(display[gradient_col], errors="coerce").fillna(0)

    try:
        if gradient_col and gradient_col in cols:
            styled = display[cols].style.background_gradient(
                subset=[gradient_col], cmap="YlOrRd"
            )
            st.dataframe(styled, column_config=col_config, height=height, use_container_width=True)
        else:
            st.dataframe(display[cols], column_config=col_config, height=height, use_container_width=True)
    except Exception:
        st.dataframe(display[cols], column_config=col_config, height=height, use_container_width=True)


def _kpi_row(df: pd.DataFrame):
    """Render a row of KPI metric cards summarizing the current dataset."""
    if df.empty:
        return
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Trends", _format_number(len(df)))
    with c2:
        top_score = df["virality_score"].max() if "virality_score" in df.columns else 0
        st.metric("Top Virality", f"{top_score:.1f}")
    with c3:
        platforms = set()
        if "platform" in df.columns:
            for p in df["platform"]:
                if isinstance(p, list):
                    platforms.update(p)
                else:
                    platforms.add(p)
        st.metric("Platforms", len(platforms))
    with c4:
        avg_growth = df["growth"].mean() if "growth" in df.columns else 0
        st.metric("Avg Growth", _format_number(avg_growth))


# Plotly defaults
_PLOTLY_LAYOUT = dict(
    margin=dict(t=40, b=20, l=20, r=20),
    font=dict(family="Inter, sans-serif", size=12),
    plot_bgcolor="#fafafa",
    paper_bgcolor="#ffffff",
    colorway=px.colors.qualitative.Set2,
)

def _apply_layout(fig, **overrides):
    fig.update_layout(**{**_PLOTLY_LAYOUT, **overrides})
    return fig


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    api = APIClient()

    # ===== Sidebar =====
    with st.sidebar:
        st.markdown("## Trends Research")
        st.caption("v2.0 — Multi-platform niche intelligence")
        st.divider()

        refresh = st.button("Refresh Data", use_container_width=True, type="primary")

        selected_country = st.selectbox("Region", list(COUNTRIES.keys()), index=0)
        selected_geo = COUNTRIES[selected_country]

        niches = api.get_niches()
        selected_niche = st.selectbox("Niche", niches)

        with st.expander("Scraper Settings"):
            selected_tf_name = st.selectbox("Time Range", list(TIMEFRAMES.keys()))
            selected_tf = TIMEFRAMES[selected_tf_name]
            selected_cat_name = st.selectbox("Category", list(CATEGORIES.keys()))
            selected_cat = CATEGORIES[selected_cat_name]

        if st.button(f"Scrape {selected_niche}", use_container_width=True):
            with st.status(f"Scraping {selected_niche}...", expanded=True) as status:
                st.write(f"Requesting data for {selected_niche}...")
                ok = api.trigger_scrape(selected_niche, geo=selected_geo,
                                        timeframe=selected_tf, category=selected_cat)
                if ok:
                    status.update(label=f"{selected_niche} scrape started!", state="complete", expanded=False)
                    st.cache_data.clear()
                    refresh = True
                else:
                    status.update(label="Scraping failed", state="error")

        st.divider()
        with st.expander("Export"):
            # Will be populated after data loads
            pass

    # ===== Clear cache on refresh or geo change =====
    if refresh or st.session_state.get("_last_geo") != selected_geo:
        st.cache_data.clear()
        st.session_state["_last_geo"] = selected_geo

    # ===== Tabs =====
    tab_niche, tab_daily, tab_social, tab_community, tab_errors = st.tabs([
        "Niche Research",
        "Daily Trends",
        "Social Media",
        "Community & News",
        "System Health",
    ])

    # ==================== TAB 1: Niche Research ====================
    with tab_niche:
        with st.spinner(f"Loading {selected_niche} trends for {selected_country}..."):
            df = api.get_trends(geo=selected_geo, niche_name=selected_niche)

        if df.empty:
            st.warning(f"No trends found for **{selected_niche}** in **{selected_country}**. "
                       "Run the scraper to populate data.")
        else:
            _kpi_row(df)
            st.divider()

            # Filter out Google Regions for the main table
            topics_df = df.copy()
            if "platform" in topics_df.columns:
                topics_df = topics_df[topics_df["platform"].apply(
                    lambda x: x != "Google Regions" and not (isinstance(x, list) and x == ["Google Regions"])
                )]
            if selected_geo != "Global" and "geo" in topics_df.columns:
                topics_df = topics_df[topics_df["geo"].apply(
                    lambda x: x != "Global" and x != "" and not (isinstance(x, list) and "Global" in x)
                )]

            topic_col = "aggregated_topic" if "aggregated_topic" in topics_df.columns else "topic"
            cols = [topic_col, "platform", "growth", "sentiment", "virality_score"]
            for opt in ("geo", "keyword", "url"):
                if opt in topics_df.columns:
                    cols.append(opt)

            st.subheader("Trending Topics")
            _display_table(topics_df, cols, col_config={
                "url": st.column_config.LinkColumn("Source"),
                "growth": st.column_config.NumberColumn("Growth", format="%.0f"),
                "virality_score": st.column_config.NumberColumn("Virality", format="%.1f"),
                "sentiment": st.column_config.NumberColumn("Sentiment", format="%.2f"),
            })

            # Charts
            col_a, col_b = st.columns(2)
            with col_a:
                chart_df = topics_df.head(12).copy()
                if not chart_df.empty:
                    fig = px.treemap(
                        chart_df, path=[topic_col], values="virality_score",
                        color="virality_score", color_continuous_scale="YlOrRd",
                        title="Virality Treemap",
                    )
                    _apply_layout(fig, height=380)
                    st.plotly_chart(fig, use_container_width=True)

            with col_b:
                chart_df2 = topics_df.head(12).copy()
                chart_df2 = _flatten_list_col(chart_df2, "platform")
                if not chart_df2.empty:
                    fig2 = px.bar(
                        chart_df2, x=topic_col, y="growth", color="platform",
                        title="Growth by Platform",
                    )
                    _apply_layout(fig2, height=380, xaxis_tickangle=-45)
                    st.plotly_chart(fig2, use_container_width=True)

    # ==================== TAB 2: Daily Trends ====================
    with tab_daily:
        effective_geo = selected_geo if selected_geo != "Global" else "US"
        display_geo = selected_country if selected_geo != "Global" else "United States (default)"

        col_ctrl, col_data = st.columns([1, 5])
        with col_ctrl:
            trend_type = st.radio("Type", ["daily", "realtime"], index=0)
            if st.button("Refresh", key="refresh_daily"):
                st.cache_data.clear()

        with st.spinner(f"Fetching {trend_type} trends for {display_geo}..."):
            daily_df = api.get_trending_now(geo=effective_geo, trend_type=trend_type)

        with col_data:
            if daily_df.empty:
                st.info("No daily trends found. The scraper might be running or blocked.")
            else:
                _kpi_row(daily_df)
                _display_table(daily_df, ["topic", "growth", "virality_score", "url"], col_config={
                    "url": st.column_config.LinkColumn("Link"),
                    "growth": "Traffic",
                })

        if not daily_df.empty:
            fig_d = px.bar(
                daily_df.head(15), x="topic", y="growth",
                color="virality_score", color_continuous_scale="Viridis",
                title=f"Top {trend_type.capitalize()} Trends — {display_geo}",
            )
            _apply_layout(fig_d, height=380, xaxis_tickangle=-45)
            st.plotly_chart(fig_d, use_container_width=True)

    # ==================== TAB 3: Social Media ====================
    with tab_social:
        platform_choice = st.radio(
            "Platform", ["X (Twitter)", "Threads", "Instagram"], horizontal=True
        )
        platform_map = {"X (Twitter)": "X", "Threads": "Threads", "Instagram": "Instagram"}
        platform_key = platform_map[platform_choice]

        if st.button("Refresh", key="refresh_social"):
            st.cache_data.clear()

        with st.spinner(f"Fetching {platform_key} trends for {selected_niche}..."):
            social_df = api.get_social_trends(platform=platform_key, niche_name=selected_niche, geo=selected_geo)

        if social_df.empty:
            st.info(f"No {platform_key} trends found for **{selected_niche}**. Run the scraper to populate data.")
        else:
            _kpi_row(social_df)
            data_cols = ["topic", "replies" if platform_key == "Threads" else "posts",
                         "growth", "virality_score", "url"]
            _display_table(social_df, data_cols, col_config={
                "url": st.column_config.LinkColumn("Source"),
                "growth": "Engagement",
            })

            fig_s = px.bar(
                social_df.head(10), x="topic", y="virality_score",
                color="virality_score", color_continuous_scale="Tealgrn",
                title=f"{platform_choice} — Top Trends",
            )
            _apply_layout(fig_s, height=380, xaxis_tickangle=-45)
            st.plotly_chart(fig_s, use_container_width=True)

    # ==================== TAB 4: Community & News ====================
    with tab_community:
        source = st.radio("Source", ["Hacker News", "Reddit", "News"], horizontal=True)

        if source == "Hacker News":
            if st.button("Refresh", key="refresh_hn"):
                st.cache_data.clear()
            with st.spinner("Fetching Hacker News..."):
                hn_df = api.get_hackernews_trends(niche_name=selected_niche, geo=selected_geo)
            if hn_df.empty:
                st.info("No Hacker News trends found.")
            else:
                _kpi_row(hn_df)
                _display_table(hn_df, ["topic", "author", "growth", "engagement", "virality_score", "url"],
                               col_config={"url": st.column_config.LinkColumn("Link"),
                                           "growth": "Points", "engagement": "Comments", "author": "By"})
                fig_hn = px.scatter(
                    hn_df, x="growth", y="engagement", size="virality_score",
                    color="virality_score", hover_name="topic",
                    color_continuous_scale="Sunset", title="Points vs Comments",
                )
                _apply_layout(fig_hn, height=400)
                st.plotly_chart(fig_hn, use_container_width=True)

        elif source == "Reddit":
            col_r1, col_r2 = st.columns([4, 1])
            with col_r2:
                subreddit = st.text_input("Subreddit", value="all")
            if st.button("Refresh", key="refresh_reddit"):
                st.cache_data.clear()
            with st.spinner("Fetching Reddit..."):
                reddit_df = api.get_reddit_trends(subreddit=subreddit, niche_name=selected_niche, geo=selected_geo)
            if reddit_df.empty:
                st.info("No Reddit trends found.")
            else:
                _kpi_row(reddit_df)
                _display_table(reddit_df, ["topic", "subreddit", "growth", "engagement", "virality_score", "url"],
                               col_config={"url": st.column_config.LinkColumn("Link"),
                                           "growth": "Score", "engagement": "Comments"})
                fig_r = px.scatter(
                    reddit_df, x="growth", y="engagement", size="virality_score",
                    color="virality_score", hover_name="topic",
                    color_continuous_scale="Bluered", title=f"r/{subreddit} — Score vs Comments",
                )
                _apply_layout(fig_r, height=400)
                st.plotly_chart(fig_r, use_container_width=True)

        elif source == "News":
            news_query = st.text_input("Query", value=selected_niche or "Health")
            if st.button("Refresh", key="refresh_news"):
                st.cache_data.clear()
            with st.spinner("Fetching News..."):
                news_df = api.get_news_trends(query=news_query, niche_name=selected_niche, geo=selected_geo)
            if news_df.empty:
                st.info("No news trends found.")
            else:
                _kpi_row(news_df)
                _display_table(news_df, ["topic", "source", "virality_score", "url"],
                               col_config={"url": st.column_config.LinkColumn("Article"), "source": "Source"})

    # ==================== TAB 5: System Health ====================
    with tab_errors:
        st.subheader("Scrape Error Log")
        if st.button("Refresh", key="refresh_errors"):
            st.cache_data.clear()
        errors_df = api.get_scrape_errors()
        if errors_df.empty:
            st.success("No scrape errors recorded — all systems healthy.")
        else:
            # Summary metrics
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Total Errors", len(errors_df))
            with c2:
                if "platform" in errors_df.columns:
                    st.metric("Affected Platforms", errors_df["platform"].nunique())
            with c3:
                if "status" in errors_df.columns:
                    most_common = errors_df["status"].mode()
                    st.metric("Most Common Status", most_common.iloc[0] if not most_common.empty else "N/A")

            st.dataframe(
                errors_df,
                column_config={
                    "url": st.column_config.LinkColumn("Failed URL"),
                    "status": "HTTP Status",
                    "extracted_at": "Timestamp",
                },
                use_container_width=True, hide_index=True, height=400,
            )

            # Error distribution chart
            if "platform" in errors_df.columns:
                fig_err = px.histogram(errors_df, x="platform", color="status",
                                       title="Errors by Platform")
                _apply_layout(fig_err, height=300)
                st.plotly_chart(fig_err, use_container_width=True)

    # ===== Sidebar export (after data is loaded) =====
    with st.sidebar:
        with st.expander("Export Data"):
            if not df.empty:
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button("Download CSV", data=csv, file_name="trends.csv", mime="text/csv",
                                   use_container_width=True)
                json_data = df.to_json(orient="records")
                st.download_button("Download JSON", data=json_data, file_name="trends.json",
                                   mime="application/json", use_container_width=True)
            else:
                st.caption("No data to export.")


if __name__ == "__main__":
    main()
