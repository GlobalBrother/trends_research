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

def safe_dataframe_display(df, required_cols, col_config=None, cmap='viridis'):
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
                width='stretch'
            )
        else:
            st.dataframe(
                display_df[required_cols],
                column_config=col_config,
                width='stretch'
            )
    except Exception as e:
        # Fallback to plain dataframe if styling fails
        st.dataframe(display_df[required_cols], column_config=col_config, width='stretch')
        st.error(f"Error rendering styled dataframe: {e}")

def main():
    st.set_page_config(page_title="trends research", layout="wide")
    st.title("🚀 trends research")

    # Initialize API Client
    api = APIClient()

    # Sidebar for filters
    st.sidebar.header("Controls")
    refresh = st.sidebar.button("Refresh Trends")
    
    # Country Selection
    countries = {
        "United States": "US",
        "United Kingdom": "GB",
        "Canada": "CA",
        "Australia": "AU",
        "Germany": "DE",
        "France": "FR",
        "Italy": "IT",
        "Spain": "ES",
        "Brazil": "BR",
        "India": "IN",
        "Japan": "JP",
        "Romania": "RO",
        "Netherlands": "NL",
        "Sweden": "SE",
        "Switzerland": "CH",
        "Mexico": "MX",
        "Argentina": "AR",
        "Singapore": "SG",
        "South Korea": "KR",
        "China": "CN",
        "Russia": "RU",
        "South Africa": "ZA",
        "Turkey": "TR",
        "United Arab Emirates": "AE",
        "Poland": "PL",
        "Belgium": "BE",
        "Austria": "AT",
        "Denmark": "DK",
        "Norway": "NO",
        "Finland": "FI",
        "Portugal": "PT",
        "Greece": "GR",
        "Czech Republic": "CZ",
        "Hungary": "HU"
    }
    selected_country_name = st.sidebar.selectbox("Select Country", list(countries.keys()))
    selected_geo = countries[selected_country_name]
    
    # Niche Selection Dropdown
    niches = api.get_niches()
    selected_niche = st.sidebar.selectbox("Select Niche", niches)

    # Scraper Customization
    st.sidebar.subheader("Scraper Settings")
    
    timeframes = {
        "Last 12 Months": "today 12-m",
        "Last hour": "now 1-H",
        "Last 4 hours": "now 4-H",
        "Last day": "now 1-d",
        "Last 7 days": "now 7-d",
        "Last 30 days": "today 1-m",
        "Last 90 days": "today 3-m",
        "Last 5 years": "today 5-y",
        "All (since 2004)": "all"
    }
    selected_timeframe_name = st.sidebar.selectbox("Time Range", list(timeframes.keys()))
    selected_timeframe = timeframes[selected_timeframe_name]
    
    # Common Google Trends Categories
    categories = {
        "All Categories": 0,
        "Arts & Entertainment": 3,
        "Autos & Vehicles": 47,
        "Beauty & Fitness": 44,
        "Books & Literature": 22,
        "Business & Industrial": 12,
        "Computers & Electronics": 5,
        "Finance": 7,
        "Food & Drink": 71,
        "Games": 8,
        "Health": 45,
        "Hobbies & Leisure": 65,
        "Home & Garden": 11,
        "Internet & Telecom": 13,
        "Jobs & Education": 958,
        "Law & Government": 19,
        "News": 16,
        "Online Communities": 299,
        "People & Society": 14,
        "Pets & Animals": 66,
        "Real Estate": 29,
        "Reference": 533,
        "Science": 174,
        "Shopping": 18,
        "Sports": 20,
        "Travel": 67
    }
    selected_category_name = st.sidebar.selectbox("Category", list(categories.keys()))
    selected_category = categories[selected_category_name]
    
    # Run Scraper for selected niche
    if st.sidebar.button(f"Scrape {selected_niche} Details"):
        with st.status(f"🚀 Deep Scraping: {selected_niche}", expanded=True) as status:
            st.write(f"🔍 Analyzing {selected_niche} niche keywords...")
            niche_keywords = api.get_niche_keywords(selected_niche)
            
            st.write(f"📡 Requesting Google Trends data for: {', '.join(niche_keywords[:3])}...")
            success = api.trigger_scrape(
                niche_name=selected_niche,
                geo=selected_geo,
                timeframe=selected_timeframe,
                category=selected_category
            )
            
            if success:
                st.write("📊 Processing and analyzing new trend data...")
                status.update(label=f"✅ {selected_niche} Scrape Complete!", state="complete", expanded=False)
                st.sidebar.success(f"Scraped {selected_niche} successfully!")
                # Force refresh to load new data
                refresh = True
                st.cache_data.clear() # Clear cache to fetch new data
            else:
                status.update(label="❌ Scraping Failed", state="error", expanded=True)
                st.sidebar.error(f"Failed to scrape {selected_niche}. Check logs.")

    # Dashboard Tabs
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
        "🎯 Niche Research", "🎥 YouTube", "𝕏 X", "💬 Threads", "📸 Instagram", "🧡 HN", "👽 Reddit", "📰 News", "💻 StackExchange"
    ])

    with tab1:
        # State management for data
        if refresh or st.session_state.get("last_geo") != selected_geo:
            st.cache_data.clear()
            st.session_state.last_geo = selected_geo

        with st.status(f"📊 Loading Trends for {selected_country_name}...", expanded=False) as status:
            st.write("📂 Requesting trend data from API...")
            df = api.get_trends(geo=selected_geo, niche_name=selected_niche)
            
            if not df.empty:
                status.update(label=f"✅ Trends loaded for {selected_country_name}", state="complete", expanded=False)
            else:
                status.update(label="⚠️ No trends found", state="error", expanded=True)
                st.warning("No trends found for the selected criteria. Please run the scraper to populate data.")

        # Dashboard layout
        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("🔥 Trending Topics & Virality Ranking")
            if not df.empty:
                # Use aggregated_topic if available
                topic_col = 'aggregated_topic' if 'aggregated_topic' in df.columns else 'topic'
                cols_to_show = [topic_col, 'platform', 'growth', 'sentiment', 'virality_score']
                
                safe_dataframe_display(
                    df,
                    cols_to_show,
                    cmap='viridis'
                )
            else:
                st.info(f"No trends found for the selected niche: {selected_niche}. Try another niche or check back later.")

        with col2:
            st.subheader("📊 Virality Distribution")
            if not df.empty:
                topic_col = 'aggregated_topic' if 'aggregated_topic' in df.columns else 'topic'
                fig = px.pie(df, names=topic_col, values='virality_score', title="Virality Score by Topic")
                st.plotly_chart(fig, width='stretch')
            else:
                st.write("No data available for distribution.")

        # Visualization
        st.subheader("📈 Growth Visualization")
        if not df.empty:
            topic_col = 'aggregated_topic' if 'aggregated_topic' in df.columns else 'topic'
            # Convert platform list to string for plotting if it's a list (from aggregation)
            plot_df = df.copy()
            if 'platform' in plot_df.columns and plot_df['platform'].apply(lambda x: isinstance(x, list)).any():
                plot_df['platforms_str'] = plot_df['platform'].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x))
                color_col = 'platforms_str'
            else:
                color_col = 'platform'
                
            fig_bar = px.bar(plot_df, x=topic_col, y='growth', color=color_col, title="Topic Growth by Platform", height=500)
            st.plotly_chart(fig_bar, width='stretch')
        else:
            st.write("No growth data available.")



    with tab2:
        st.subheader(f"🎥 YouTube Trending: {selected_niche}")
        st.write(f"Top performing videos in the **{selected_niche}** niche from the past month.")
        
        if st.button("Refresh YouTube Trends"):
            st.cache_data.clear()
            
        with st.status(f"📡 Fetching YouTube niche trends...", expanded=False) as status:
            yt_df = api.get_youtube_trends(niche_name=selected_niche)
            if not yt_df.empty:
                status.update(label="✅ YouTube data retrieved", state="complete", expanded=False)
            else:
                status.update(label="⚠️ No YouTube trends found", state="error", expanded=True)
                st.info("No YouTube trends found for this niche yet. Click the button to trigger a scan.")
        
        if not yt_df.empty:
            # Display YouTube trends with a link
            yt_df = yt_df.copy()
            # Sort by growth (views)
            if 'growth' in yt_df.columns:
                yt_df = yt_df.sort_values(by='growth', ascending=False)
                yt_df['Views'] = yt_df['growth'].apply(format_views)
            else:
                yt_df['Views'] = "N/A"
            
            safe_dataframe_display(
                yt_df, 
                ['topic', 'Views', 'published', 'url', 'virality_score'],
                col_config={
                    "url": st.column_config.LinkColumn("Video Link"),
                    "topic": "Video Title",
                    "published": "Uploaded"
                },
                cmap='magma'
            )
            
            # Simple bar chart for views
            if 'growth' in yt_df.columns:
                fig_yt = px.bar(yt_df.head(10), x='topic', y='growth', title="Top 10 Videos by Views", labels={'growth': 'Estimated Views', 'topic': 'Video Title'})
                st.plotly_chart(fig_yt, width='stretch')


    with tab3:
        st.subheader(f"𝕏 X Trends: {selected_niche}")
        st.write(f"Trending conversations on X (Twitter) related to **{selected_niche}**.")
        
        if st.button("Refresh X Trends"):
            st.cache_data.clear()
            
        with st.status(f"📡 Fetching X niche trends...", expanded=False) as status:
            x_df = api.get_social_trends(platform="X", niche_name=selected_niche)
            if not x_df.empty:
                status.update(label="✅ X data retrieved", state="complete", expanded=False)
            else:
                status.update(label="⚠️ No X trends found", state="error", expanded=True)
                st.info("No X trends found for this niche yet. Click the button to trigger a scan.")
        
        if not x_df.empty:
            safe_dataframe_display(
                x_df,
                ['topic', 'posts', 'growth', 'virality_score', 'url'],
                col_config={
                    "url": st.column_config.LinkColumn("Source"),
                    "growth": "Engagement Score",
                    "posts": "Post Count"
                },
                cmap='viridis'
            )
            
            fig_x = px.bar(x_df, x='topic', y='virality_score', title="X Topic Virality")
            st.plotly_chart(fig_x, width='stretch')

    with tab4:
        st.subheader(f"💬 Threads Trends: {selected_niche}")
        st.write(f"Trending topics and communities on Threads for **{selected_niche}**.")
        
        if st.button("Refresh Threads Trends"):
            st.cache_data.clear()
            
        with st.status(f"📡 Fetching Threads niche trends...", expanded=False) as status:
            threads_df = api.get_social_trends(platform="Threads", niche_name=selected_niche)
            if not threads_df.empty:
                status.update(label="✅ Threads data retrieved", state="complete", expanded=False)
            else:
                status.update(label="⚠️ No Threads trends found", state="error", expanded=True)
        
        if not threads_df.empty:
            safe_dataframe_display(
                threads_df,
                ['topic', 'replies', 'growth', 'virality_score', 'url'],
                col_config={
                    "url": st.column_config.LinkColumn("Source"),
                    "growth": "Engagement Score",
                    "replies": "Replies"
                },
                cmap='magma'
            )

    with tab5:
        st.subheader(f"📸 Instagram Trends: {selected_niche}")
        st.write(f"Popular hashtags and content on Instagram for **{selected_niche}**.")
        
        if st.button("Refresh Instagram Trends"):
            st.cache_data.clear()
            
        with st.status(f"📡 Fetching Instagram niche trends...", expanded=False) as status:
            ig_df = api.get_social_trends(platform="Instagram", niche_name=selected_niche)
            if not ig_df.empty:
                status.update(label="✅ Instagram data retrieved", state="complete", expanded=False)
            else:
                status.update(label="⚠️ No Instagram trends found", state="error", expanded=True)
        
        if not ig_df.empty:
            safe_dataframe_display(
                ig_df,
                ['topic', 'posts', 'growth', 'virality_score', 'url'],
                col_config={
                    "url": st.column_config.LinkColumn("Source"),
                    "growth": "Engagement Score",
                    "posts": "Total Posts"
                },
                cmap='inferno'
            )

    with tab6:
        st.subheader("🧡 Hacker News: Top Stories")
        st.write("Current top stories from Hacker News, analyzed for virality.")
        
        if st.button("Refresh Hacker News"):
            st.cache_data.clear()
            
        with st.status("📡 Fetching Hacker News stories...", expanded=False) as status:
            hn_df = api.get_hackernews_trends(niche_name=selected_niche)
            if not hn_df.empty:
                status.update(label="✅ Hacker News data retrieved", state="complete", expanded=False)
            else:
                status.update(label="⚠️ No Hacker News trends found", state="error", expanded=True)
        
        if not hn_df.empty:
            safe_dataframe_display(
                hn_df,
                ['topic', 'author', 'growth', 'engagement', 'virality_score', 'url'],
                col_config={
                    "url": st.column_config.LinkColumn("Story Link"),
                    "growth": "Points",
                    "engagement": "Comments Score",
                    "author": "Posted By"
                },
                cmap='magma'
            )
            
            fig_hn = px.scatter(hn_df, x='growth', y='engagement', size='virality_score', color='virality_score', hover_name='topic', title="Hacker News: Points vs Comments")
            st.plotly_chart(fig_hn, width='stretch')

    with tab7:
        st.subheader("👽 Reddit: Hot Posts")
        st.write("Current hot posts from Reddit, analyzed for virality.")
        
        subreddit = st.text_input("Subreddit", value="all")
        if st.button("Refresh Reddit"):
            st.cache_data.clear()
            
        with st.status("📡 Fetching Reddit posts...", expanded=False) as status:
            reddit_df = api.get_reddit_trends(subreddit=subreddit, niche_name=selected_niche)
            if not reddit_df.empty:
                status.update(label=f"✅ Reddit {subreddit} data retrieved", state="complete", expanded=False)
            else:
                status.update(label="⚠️ No Reddit trends found", state="error", expanded=True)
        
        if not reddit_df.empty:
            safe_dataframe_display(
                reddit_df,
                ['topic', 'subreddit', 'growth', 'engagement', 'virality_score', 'url'],
                col_config={
                    "url": st.column_config.LinkColumn("Post Link"),
                    "growth": "Score",
                    "engagement": "Comments",
                    "subreddit": "Subreddit"
                },
                cmap='viridis'
            )
            
            fig_reddit = px.scatter(reddit_df, x='growth', y='engagement', size='virality_score', color='virality_score', hover_name='topic', title=f"Reddit r/{subreddit}: Score vs Comments")
            st.plotly_chart(fig_reddit, width='stretch')

    with tab8:
        st.subheader(f"📰 {selected_niche} News Trends" if selected_niche else "📰 Global News Trends")
        st.write("Top news stories across the web.")
        
        news_query = st.text_input("News Query", value=selected_niche or "Health")
        if st.button("Refresh News"):
            st.cache_data.clear()
            
        with st.status("📡 Fetching News articles...", expanded=False) as status:
            news_df = api.get_news_trends(query=news_query, niche_name=selected_niche)
            if not news_df.empty:
                status.update(label="✅ News data retrieved", state="complete", expanded=False)
            else:
                status.update(label="⚠️ No News trends found", state="error", expanded=True)
        
        if not news_df.empty:
            safe_dataframe_display(
                news_df,
                ['topic', 'source', 'virality_score', 'url'],
                col_config={
                    "url": st.column_config.LinkColumn("Article Link"),
                    "source": "Source"
                },
                cmap='plasma'
            )

    with tab9:
        st.subheader("💻 StackExchange: Hot Questions")
        st.write("Trending technical questions and discussions.")
        
        se_site = st.selectbox("Site", ["stackoverflow", "askubuntu", "superuser", "serverfault", "stats"])
        if st.button("Refresh StackExchange"):
            st.cache_data.clear()
            
        with st.status("📡 Fetching StackExchange questions...", expanded=False) as status:
            se_df = api.get_stackexchange_trends(site=se_site, niche_name=selected_niche)
            if not se_df.empty:
                status.update(label=f"✅ {se_site} data retrieved", state="complete", expanded=False)
            else:
                status.update(label="⚠️ No StackExchange trends found", state="error", expanded=True)
        
        if not se_df.empty:
            safe_dataframe_display(
                se_df,
                ['topic', 'growth', 'engagement', 'virality_score', 'url'],
                col_config={
                    "url": st.column_config.LinkColumn("Question Link"),
                    "growth": "Score",
                    "engagement": "Views Scale"
                },
                cmap='inferno'
            )


    # Export Section
    st.sidebar.subheader("Export Options")
    
    # CSV Export
    csv = df.to_csv(index=False).encode('utf-8')
    st.sidebar.download_button(label="Download as CSV", data=csv, file_name='trends.csv', mime='text/csv')

    # JSON Export
    json_data = df.to_json(orient="records")
    st.sidebar.download_button(label="Download as JSON", data=json_data, file_name='trends.json', mime='application/json')

if __name__ == "__main__":
    main()
