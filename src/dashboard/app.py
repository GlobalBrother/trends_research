import sys
import os
import streamlit as st
import pandas as pd
import plotly.express as px

# Ensure the project root (the directory containing 'src') is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.collector.trend_collector import TrendCollector
from src.analytics.analytics_engine import AnalyticsEngine
from src.niche.niche_discovery import NicheDiscovery
import io

def main():
    st.set_page_config(page_title="trends research", layout="wide")
    st.title("🚀 trends research")

    # Initialize modules
    collector = TrendCollector()
    analytics = AnalyticsEngine()
    niche = NicheDiscovery()

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
        "Romania": "RO"
    }
    selected_country_name = st.sidebar.selectbox("Select Country", list(countries.keys()))
    selected_geo = countries[selected_country_name]
    
    # Niche Selection Dropdown
    niches = ["Survival", "Health", "Preppers", "Sustainability", "Homesteading"]
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
            # Get specific keywords for the niche if they exist in NicheDiscovery
            niche_keywords = niche.get_niche_keywords(selected_niche)
            
            st.write(f"📡 Requesting Google Trends data for: {', '.join(niche_keywords[:3])}...")
            success = collector.run_google_trends_scraper(
                keywords=niche_keywords, 
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
            else:
                status.update(label="❌ Scraping Failed", state="error", expanded=True)
                st.sidebar.error(f"Failed to scrape {selected_niche}. Check logs.")

    # State management for data
    if "data" not in st.session_state or refresh or st.session_state.get("last_geo") != selected_geo:
        with st.status(f"📊 Loading Trends for {selected_country_name}...", expanded=False) as status:
            st.write("📂 Reading trend data from local cache...")
            raw_data = collector.collect_all(geo=selected_geo)
            st.session_state.last_geo = selected_geo
            
            if not raw_data.empty:
                st.write("🧠 Performing analytics and virality scoring...")
                st.session_state.data = analytics.process_trends(raw_data)
                status.update(label=f"✅ Trends loaded for {selected_country_name}", state="complete", expanded=False)
            else:
                st.session_state.data = pd.DataFrame(columns=['platform', 'topic', 'growth', 'sentiment', 'virality_score'])
                status.update(label="⚠️ No trends found", state="error", expanded=True)
                st.warning("No trends found in the local cache. Please run the scraper to populate data.")

    # Show info about Scrapy data
    if os.path.exists(collector.scrapy_output_path):
        st.sidebar.success(f"Loaded Scrapy trends from local cache.")
    else:
        st.sidebar.warning("Scrapy trends not found. Run the scraper to populate.")

    df = st.session_state.data

    # Filter data by selected niche
    df = niche.filter_by_niche(df, selected_niche)

    # Dashboard layout
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("🔥 Trending Topics & Virality Ranking")
        if not df.empty:
            st.dataframe(df[['platform', 'topic', 'growth', 'sentiment', 'virality_score']].style.background_gradient(subset=['virality_score'], cmap='viridis'), width='stretch')
        else:
            st.info(f"No trends found for the selected niche: {selected_niche}. Try another niche or check back later.")

    with col2:
        st.subheader("📊 Virality Distribution")
        if not df.empty:
            fig = px.pie(df, names='platform', values='virality_score', title="Platform Influence by Virality")
            st.plotly_chart(fig, width='stretch')
        else:
            st.write("No data available for distribution.")

    # Visualization
    st.subheader("📈 Growth Visualization")
    if not df.empty:
        fig_bar = px.bar(df, x='topic', y='growth', color='platform', title="Topic Growth by Platform", height=500)
        st.plotly_chart(fig_bar, width='stretch')
    else:
        st.write("No growth data available.")

    # Keyword Expansion / Niche Clustering
    st.subheader("🧩 Niche Clustering (Micro-Niches)")
    if len(df) >= 5:
        df_clustered = niche.discover_micro_niches(df)
        st.write("Topics clustered by semantic similarity:")
        st.dataframe(df_clustered[['topic', 'niche_cluster', 'platform']], width='stretch')


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
