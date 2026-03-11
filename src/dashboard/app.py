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
        "Romania": "RO"
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
            st.dataframe(df[['platform', 'topic', 'growth', 'sentiment', 'virality_score']].style.background_gradient(subset=['virality_score'], cmap='viridis'), width='stretch', use_container_width=True)
        else:
            st.info(f"No trends found for the selected niche: {selected_niche}. Try another niche or check back later.")

    with col2:
        st.subheader("📊 Virality Distribution")
        if not df.empty:
            fig = px.pie(df, names='topic', values='virality_score', title="Virality Score by Topic")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.write("No data available for distribution.")

    # Visualization
    st.subheader("📈 Growth Visualization")
    if not df.empty:
        fig_bar = px.bar(df, x='topic', y='growth', color='platform', title="Topic Growth by Platform", height=500)
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.write("No growth data available.")

    # Keyword Expansion / Niche Clustering
    st.subheader("🧩 Niche Clustering (Micro-Niches)")
    if not df.empty and 'niche_cluster' in df.columns:
        st.write("Topics clustered by semantic similarity:")
        st.dataframe(df[['topic', 'niche_cluster', 'platform']], width='stretch', use_container_width=True)
    elif not df.empty:
        st.info("Insufficient data for clustering.")


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
