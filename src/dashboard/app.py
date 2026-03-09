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
    st.set_page_config(page_title="Trend Research Tool", layout="wide")
    st.title("🚀 Python Trend Research & Viral Insights Tool")

    # Initialize modules
    collector = TrendCollector()
    analytics = AnalyticsEngine()
    niche = NicheDiscovery()

    # Sidebar for filters
    st.sidebar.header("Controls")
    refresh = st.sidebar.button("Refresh Trends")
    niche_input = st.sidebar.text_input("Niche or Industry Keyword (e.g., AI, Tech)")
    
    # State management for data
    if "data" not in st.session_state or refresh:
        with st.spinner("Collecting and analyzing trends..."):
            raw_data = collector.collect_all()
            st.session_state.data = analytics.process_trends(raw_data)

    df = st.session_state.data

    # Filter data if niche keyword is provided
    if niche_input:
        df = niche.filter_by_niche(df, niche_input)

    # Dashboard layout
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("🔥 Trending Topics & Virality Ranking")
        st.dataframe(df[['platform', 'topic', 'growth', 'sentiment', 'virality_score']].style.background_gradient(subset=['virality_score'], cmap='viridis'), use_container_width=True)

    with col2:
        st.subheader("📊 Virality Distribution")
        fig = px.pie(df, names='platform', values='virality_score', title="Platform Influence by Virality")
        st.plotly_chart(fig, use_container_width=True)

    # Visualization
    st.subheader("📈 Growth Visualization")
    fig_bar = px.bar(df, x='topic', y='growth', color='platform', title="Topic Growth by Platform", height=500)
    st.plotly_chart(fig_bar, use_container_width=True)

    # Keyword Expansion / Niche Clustering
    st.subheader("🧩 Niche Clustering (Micro-Niches)")
    if len(df) >= 5:
        df_clustered = niche.discover_micro_niches(df)
        st.write("Topics clustered by semantic similarity:")
        st.dataframe(df_clustered[['topic', 'niche_cluster', 'platform']], use_container_width=True)

    # Content Opportunities
    st.subheader("💡 Content Opportunities")
    top_topics = df.head(5)
    opportunities = niche.suggest_content_opportunities(top_topics)
    for op in opportunities[:10]:
        st.markdown(f"- {op}")

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
