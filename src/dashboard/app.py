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
import io

def format_views(val):
    if not isinstance(val, (int, float)):
        try:
            val = float(val)
        except:
            return str(val)
    if val >= 1000000:
        return f"{val/1000000:.1f}M"
    if val >= 1000:
        return f"{val/1000:.1f}K"
    return str(int(val))

def safe_dataframe_display(df, required_cols, col_config=None, cmap='viridis', height=400):
    """Displays a dataframe in Streamlit while ensuring all required columns exist."""
    if df.empty:
        st.info("No data available to display.")
        return
        
    display_df = df.copy()
    for col in required_cols:
        if col not in display_df.columns:
            display_df[col] = "N/A"
    
    # Ensure virality_score is numeric for the gradient to work
    if 'virality_score' in display_df.columns:
        display_df['virality_score'] = pd.to_numeric(display_df['virality_score'], errors='coerce').fillna(0)

    try:
        if 'virality_score' in required_cols:
            st.dataframe(
                display_df[required_cols].style.background_gradient(subset=['virality_score'], cmap=cmap),
                column_config=col_config,
                height=height,
                width='stretch'
            )
        else:
            st.dataframe(
                display_df[required_cols],
                column_config=col_config,
                height=height,
                width='stretch'
            )
    except Exception as e:
        st.dataframe(display_df[required_cols], column_config=col_config, height=height, width='stretch')


def main():
    st.set_page_config(page_title="Trends Research", layout="wide")
    st.title("🚀 Trends Research")

    # Initialize API Client
    api = APIClient()

    # --- Sidebar ---
    st.sidebar.header("Controls")
    if api.direct:
        st.sidebar.success("⚡ Direct mode (ensembledata)")
    else:
        st.sidebar.info("🌐 API mode (FastAPI backend)")
    refresh = st.sidebar.button("🔄 Refresh")
    
    # Country Selection
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
    selected_country_name = st.sidebar.selectbox("Country", list(countries.keys()))
    selected_geo = countries[selected_country_name]
    
    # Niche Selection
    niches = api.get_niches()
    selected_niche = st.sidebar.selectbox("Niche", niches)

    # Scraper Settings in expander
    with st.sidebar.expander("⚙️ Scraper Settings", expanded=False):
        timeframes = {
            "Last 12 Months": "today 12-m", "Last hour": "now 1-H",
            "Last 4 hours": "now 4-H", "Last day": "now 1-d",
            "Last 7 days": "now 7-d", "Last 30 days": "today 1-m",
            "Last 90 days": "today 3-m", "Last 5 years": "today 5-y",
            "All (since 2004)": "all"
        }
        selected_timeframe_name = st.selectbox("Time Range", list(timeframes.keys()))
        selected_timeframe = timeframes[selected_timeframe_name]
        
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
        selected_category_name = st.selectbox("Category", list(categories.keys()))
        selected_category = categories[selected_category_name]
    
    # Token Import (for 429 workaround)
    with st.sidebar.expander("📥 Import Google Trends JSON", expanded=False):
        st.caption("Upload the JSON/TXT file Google Trends gives you when it returns a 429 error.")
        uploaded_file = st.file_uploader("Choose JSON or TXT file", type=["json", "txt"], key="token_upload")
        if uploaded_file is not None:
            if st.button("⬆️ Import Tokens", key="import_tokens_btn"):
                with st.spinner("Importing tokens..."):
                    result = api.import_tokens(uploaded_file.getvalue(), uploaded_file.name, geo=selected_geo)
                    if result:
                        st.success(result.get("message", "Import started!"))
                        st.cache_data.clear()
                    else:
                        st.error("❌ Import failed")

    # --- Tabs (consolidated from 10 → 6) ---
    tab1, tab2, tab_yt, tab3, tab4, tab5 = st.tabs([
        "🎯 Niche Research", "📈 Daily Trends", "🎬 YouTube", "📱 Social Media", "🌐 Community & News", "⚠️ Errors"
    ])

    # ==================== TAB 1: Niche Research ====================
    with tab1:
        if refresh or st.session_state.get("last_geo") != selected_geo:
            st.cache_data.clear()
            st.session_state.last_geo = selected_geo

        col_scrape1, _ = st.columns([1, 4])
        with col_scrape1:
            if st.button(f"🚀 Scrape {selected_niche}", key="scrape_niche"):
                with st.spinner(f"Scraping {selected_niche}..."):
                    success = api.trigger_scrape(
                        niche_name=selected_niche, geo=selected_geo,
                        timeframe=selected_timeframe, category=selected_category,
                        scraper_type="google_trends"
                    )
                    if success:
                        st.success(f"✅ {selected_niche} scrape started!")
                        st.cache_data.clear()
                    else:
                        st.error("❌ Scraping failed")

        with st.spinner(f"Loading {selected_niche} trends for {selected_country_name}..."):
            df = api.get_trends(geo=selected_geo, niche_name=selected_niche)

        if df.empty:
            st.warning(f"No trends found for **{selected_niche}** in **{selected_country_name}**. Run the scraper to populate data.")
        else:
            st.caption(f"📊 {len(df)} trends loaded for {selected_niche} — {selected_country_name}")

            # --- Topics Table ---
            st.subheader("🔥 Trending Topics & Virality")
            topics_df = df.copy()
            if 'platform' in topics_df.columns:
                topics_df = topics_df[topics_df['platform'].apply(lambda x: x != 'Google Regions' and not (isinstance(x, list) and x == ['Google Regions']))]
            if selected_geo != "Global" and 'geo' in topics_df.columns:
                topics_df = topics_df[topics_df['geo'].apply(
                    lambda x: x != 'Global' and x != '' and not (isinstance(x, list) and 'Global' in x)
                )]
            
            topic_col = 'aggregated_topic' if 'aggregated_topic' in topics_df.columns else 'topic'
            available_cols = topics_df.columns.tolist()
            cols_to_show = [topic_col, 'platform', 'growth', 'sentiment', 'virality_score']
            for opt_col in ['geo', 'keyword', 'url']:
                if opt_col in available_cols:
                    cols_to_show.append(opt_col)

            display_df = topics_df.copy()
            if 'platform' in display_df.columns:
                display_df['platform'] = display_df['platform'].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
            if 'geo' in display_df.columns:
                display_df['geo'] = display_df['geo'].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
            
            safe_dataframe_display(
                display_df, cols_to_show,
                col_config={
                    "url": st.column_config.LinkColumn("Source Link"),
                    "growth": st.column_config.NumberColumn("Growth", format="%.1f"),
                    "virality_score": st.column_config.NumberColumn("Virality", format="%.2f")
                },
                height=350
            )

            # --- Charts side by side ---
            col_a, col_b = st.columns(2)
            with col_a:
                pie_df = df.copy()
                if 'platform' in pie_df.columns:
                    pie_df = pie_df[pie_df['platform'].apply(lambda x: x != 'Google Regions' and not (isinstance(x, list) and x == ['Google Regions']))]
                if not pie_df.empty:
                    fig = px.pie(pie_df.head(15), names=topic_col, values='virality_score',
                                 title="Virality Distribution", height=350)
                    fig.update_layout(margin=dict(t=40, b=10, l=10, r=10), showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)

            with col_b:
                plot_df = df[df['platform'].apply(lambda x: x != 'Google Regions' and not (isinstance(x, list) and x == ['Google Regions']))].copy() if 'platform' in df.columns else df.copy()
                if not plot_df.empty:
                    if 'platform' in plot_df.columns and plot_df['platform'].apply(lambda x: isinstance(x, list)).any():
                        plot_df['platform'] = plot_df['platform'].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x))
                    fig_bar = px.bar(plot_df.head(15), x=topic_col, y='growth', color='platform',
                                     title="Growth by Platform", height=350)
                    fig_bar.update_layout(margin=dict(t=40, b=10, l=10, r=10), xaxis_tickangle=-45, showlegend=True)
                    st.plotly_chart(fig_bar, use_container_width=True)

    # ==================== TAB 2: Daily Trends ====================
    with tab2:
        display_geo_name = selected_country_name
        effective_geo = selected_geo
        if selected_geo == "Global":
            display_geo_name = "United States (Default)"
            effective_geo = "US"
            
        col_t1, col_t2 = st.columns([1, 4])
        with col_t1:
            trend_type = st.radio("Type", ["daily", "realtime"], index=0)
            if st.button("🔄 Refresh", key="refresh_daily"):
                st.cache_data.clear()
            if st.button("🚀 Scrape Daily", key="scrape_daily"):
                with st.spinner("Scraping daily trends..."):
                    success = api.trigger_scrape(
                        niche_name=selected_niche, geo=effective_geo,
                        timeframe=selected_timeframe, category=selected_category,
                        scraper_type="daily"
                    )
                    if success:
                        st.success("✅ Scrape started!")
                        st.cache_data.clear()
                    else:
                        st.error("❌ Scraping failed")
        
        with st.spinner(f"Fetching {trend_type} trends for {display_geo_name}..."):
            daily_df = api.get_trending_now(geo=effective_geo, trend_type=trend_type)

        with col_t2:
            if not daily_df.empty:
                safe_dataframe_display(
                    daily_df,
                    ['topic', 'growth', 'virality_score', 'url'],
                    col_config={
                        "url": st.column_config.LinkColumn("Link"),
                        "growth": "Traffic"
                    },
                    height=350
                )
            else:
                st.info("No daily trends found. The scraper might be running or blocked.")

        if not daily_df.empty:
            with st.expander("📊 Chart", expanded=False):
                fig_daily = px.bar(daily_df.head(15), x='topic', y='growth',
                                   title=f"Top {trend_type.capitalize()} Trends", color='virality_score', height=350)
                fig_daily.update_layout(margin=dict(t=40, b=10, l=10, r=10), xaxis_tickangle=-45)
                st.plotly_chart(fig_daily, use_container_width=True)

    # ==================== TAB: YouTube ====================
    with tab_yt:
        col_yt1, col_yt2, _ = st.columns([1, 1, 3])
        with col_yt1:
            if st.button("🔄 Refresh", key="refresh_yt"):
                st.cache_data.clear()
        with col_yt2:
            if st.button(f"🚀 Scrape YouTube", key="scrape_yt"):
                with st.spinner("Scraping YouTube trends..."):
                    success = api.trigger_scrape(
                        niche_name=selected_niche, geo=selected_geo,
                        timeframe=selected_timeframe, category=selected_category,
                        scraper_type="youtube"
                    )
                    if success:
                        st.success("✅ YouTube scrape started!")
                        st.cache_data.clear()
                    else:
                        st.error("❌ Scraping failed")

        with st.spinner(f"Fetching YouTube trends for {selected_niche}..."):
            yt_df = api.get_youtube_trends(niche_name=selected_niche, geo=selected_geo)

        if not yt_df.empty:
            data_cols = ['topic', 'channel', 'growth', 'duration', 'published', 'virality_score', 'description', 'url']
            safe_dataframe_display(
                yt_df, data_cols,
                col_config={
                    "url": st.column_config.LinkColumn("Link"),
                    "growth": "Views",
                    "channel": "Channel",
                    "duration": "Duration",
                    "published": "Published",
                    "description": "Description",
                },
                height=350
            )

            with st.expander("📊 Chart", expanded=False):
                fig_yt = px.bar(yt_df.head(15), x='topic', y='virality_score',
                                title="YouTube Virality", height=350)
                fig_yt.update_layout(margin=dict(t=40, b=10, l=10, r=10), xaxis_tickangle=-45)
                st.plotly_chart(fig_yt, use_container_width=True)
        else:
            st.info(f"No YouTube trends found for **{selected_niche}**. Run the scraper to populate data.")

    # ==================== TAB 3: Social Media (X + Threads + Instagram) ====================
    with tab3:
        platform_choice = st.radio("Platform", ["𝕏 X", "💬 Threads", "📸 Instagram", "🎵 TikTok"], horizontal=True)
        platform_map = {"𝕏 X": "X", "💬 Threads": "Threads", "📸 Instagram": "Instagram", "🎵 TikTok": "TikTok"}
        platform_key = platform_map[platform_choice]

        col_s1, col_s2, _ = st.columns([1, 1, 3])
        with col_s1:
            if st.button("🔄 Refresh", key="refresh_social"):
                st.cache_data.clear()
        with col_s2:
            if st.button(f"🚀 Scrape {platform_key}", key="scrape_social"):
                with st.spinner(f"Scraping {platform_key}..."):
                    success = api.trigger_scrape(
                        niche_name=selected_niche, geo=selected_geo,
                        timeframe=selected_timeframe, category=selected_category,
                        scraper_type=platform_key
                    )
                    if success:
                        st.success(f"✅ {platform_key} scrape started!")
                        st.cache_data.clear()
                    else:
                        st.error("❌ Scraping failed")

        with st.spinner(f"Fetching {platform_key} trends for {selected_niche}..."):
            social_df = api.get_social_trends(platform=platform_key, niche_name=selected_niche, geo=selected_geo)

        if not social_df.empty:
            # Pick columns based on platform
            if platform_key == "Threads":
                data_cols = ['topic', 'replies', 'growth', 'virality_score', 'url']
            else:
                data_cols = ['topic', 'posts', 'growth', 'virality_score', 'url']

            safe_dataframe_display(
                social_df, data_cols,
                col_config={
                    "url": st.column_config.LinkColumn("Source"),
                    "growth": "Engagement"
                },
                height=350
            )

            with st.expander("📊 Chart", expanded=False):
                fig_social = px.bar(social_df.head(10), x='topic', y='virality_score',
                                    title=f"{platform_key} Virality", height=350)
                fig_social.update_layout(margin=dict(t=40, b=10, l=10, r=10), xaxis_tickangle=-45)
                st.plotly_chart(fig_social, use_container_width=True)
        else:
            st.info(f"No {platform_key} trends found for **{selected_niche}**. Run the scraper to populate data.")

    # ==================== TAB 4: Community & News (HN + Reddit + News) ====================
    with tab4:
        source_choice = st.radio("Source", ["🧡 Hacker News", "👽 Reddit", "📰 News"], horizontal=True)

        if source_choice == "🧡 Hacker News":
            col_h1, col_h2, _ = st.columns([1, 1, 3])
            with col_h1:
                if st.button("🔄 Refresh", key="refresh_hn"):
                    st.cache_data.clear()
            with col_h2:
                if st.button("🚀 Scrape HN", key="scrape_hn"):
                    with st.spinner("Scraping Hacker News..."):
                        success = api.trigger_scrape(
                            niche_name=selected_niche, geo=selected_geo,
                            timeframe=selected_timeframe, category=selected_category,
                            scraper_type="hackernews"
                        )
                        if success:
                            st.success("✅ HN scrape started!")
                            st.cache_data.clear()
                        else:
                            st.error("❌ Scraping failed")
            with st.spinner("Fetching Hacker News..."):
                hn_df = api.get_hackernews_trends(niche_name=selected_niche, geo=selected_geo)
            if not hn_df.empty:
                safe_dataframe_display(
                    hn_df,
                    ['topic', 'author', 'growth', 'engagement', 'virality_score', 'url'],
                    col_config={
                        "url": st.column_config.LinkColumn("Link"),
                        "growth": "Points", "engagement": "Comments", "author": "By"
                    },
                    height=350
                )
                with st.expander("📊 Chart", expanded=False):
                    fig_hn = px.scatter(hn_df, x='growth', y='engagement', size='virality_score',
                                        color='virality_score', hover_name='topic',
                                        title="Points vs Comments", height=350)
                    fig_hn.update_layout(margin=dict(t=40, b=10, l=10, r=10))
                    st.plotly_chart(fig_hn, use_container_width=True)
            else:
                st.info("No Hacker News trends found.")

        elif source_choice == "👽 Reddit":
            col_r1, col_r2 = st.columns([3, 1])
            with col_r2:
                subreddit = st.text_input("Subreddit", value="all")
            col_rd1, col_rd2, _ = st.columns([1, 1, 3])
            with col_rd1:
                if st.button("🔄 Refresh", key="refresh_reddit"):
                    st.cache_data.clear()
            with col_rd2:
                if st.button("🚀 Scrape Reddit", key="scrape_reddit"):
                    with st.spinner("Scraping Reddit..."):
                        success = api.trigger_scrape(
                            niche_name=selected_niche, geo=selected_geo,
                            timeframe=selected_timeframe, category=selected_category,
                            scraper_type="reddit"
                        )
                        if success:
                            st.success("✅ Reddit scrape started!")
                            st.cache_data.clear()
                        else:
                            st.error("❌ Scraping failed")
            with st.spinner("Fetching Reddit..."):
                reddit_df = api.get_reddit_trends(subreddit=subreddit, niche_name=selected_niche, geo=selected_geo)
            if not reddit_df.empty:
                safe_dataframe_display(
                    reddit_df,
                    ['topic', 'subreddit', 'growth', 'engagement', 'virality_score', 'url'],
                    col_config={
                        "url": st.column_config.LinkColumn("Link"),
                        "growth": "Score", "engagement": "Comments"
                    },
                    height=350
                )
                with st.expander("📊 Chart", expanded=False):
                    fig_reddit = px.scatter(reddit_df, x='growth', y='engagement', size='virality_score',
                                            color='virality_score', hover_name='topic',
                                            title=f"r/{subreddit}: Score vs Comments", height=350)
                    fig_reddit.update_layout(margin=dict(t=40, b=10, l=10, r=10))
                    st.plotly_chart(fig_reddit, use_container_width=True)
            else:
                st.info("No Reddit trends found.")

        elif source_choice == "📰 News":
            news_query = st.text_input("Query", value=selected_niche or "Health")
            col_n1, col_n2, _ = st.columns([1, 1, 3])
            with col_n1:
                if st.button("🔄 Refresh", key="refresh_news"):
                    st.cache_data.clear()
            with col_n2:
                if st.button("🚀 Scrape News", key="scrape_news"):
                    with st.spinner("Scraping News..."):
                        success = api.trigger_scrape(
                            niche_name=selected_niche, geo=selected_geo,
                            timeframe=selected_timeframe, category=selected_category,
                            scraper_type="news"
                        )
                        if success:
                            st.success("✅ News scrape started!")
                            st.cache_data.clear()
                        else:
                            st.error("❌ Scraping failed")
            with st.spinner("Fetching News..."):
                news_df = api.get_news_trends(query=news_query, niche_name=selected_niche, geo=selected_geo)
            if not news_df.empty:
                safe_dataframe_display(
                    news_df,
                    ['topic', 'source', 'virality_score', 'url'],
                    col_config={
                        "url": st.column_config.LinkColumn("Article"),
                        "source": "Source"
                    },
                    height=350
                )
            else:
                st.info("No news trends found.")

    # ==================== TAB 5: Scrape Errors ====================
    with tab5:
        if st.button("🔄 Refresh", key="refresh_errors"):
            st.cache_data.clear()
        errors_df = api.get_scrape_errors()
        if not errors_df.empty:
            st.dataframe(
                errors_df,
                column_config={
                    "url": st.column_config.LinkColumn("Failed URL"),
                    "status": "HTTP Status", "extracted_at": "Timestamp"
                },
                use_container_width=True, hide_index=True, height=400
            )
        else:
            st.success("No scrape errors recorded! 🚀")

    # --- Sidebar Export ---
    with st.sidebar.expander("📥 Export", expanded=False):
        if not df.empty:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Download CSV", data=csv, file_name='trends.csv', mime='text/csv')
            json_data = df.to_json(orient="records")
            st.download_button("Download JSON", data=json_data, file_name='trends.json', mime='application/json')
        else:
            st.caption("No data to export.")

if __name__ == "__main__":
    main()
