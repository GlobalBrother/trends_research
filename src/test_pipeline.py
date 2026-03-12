import sys
import os
import pandas as pd

# Ensure the project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.collector.trend_collector import TrendCollector
from src.analytics.analytics_engine import AnalyticsEngine

def main():
    print("--- Starting Pipeline Test ---")
    
    # 1. Initialize
    collector = TrendCollector()
    analytics = AnalyticsEngine()
    
    # 2. Collect Data (Collector)
    print("Fetching trends from local output...")
    raw_data = collector.collect_all(geo="US", include_trending_now=True, include_youtube=True)
    
    if raw_data.empty:
        print("No raw data found in the database. Please run scrapers first if needed.")
        return

    print(f"Collected {len(raw_data)} raw trend points.")
    
    # 3. Process Trends (Processor/TrendEngine/ViralCalc)
    print("Processing trends through Analytics Engine...")
    processed_df = analytics.process_trends(raw_data)
    
    print(f"Processed {len(processed_df)} trends.")
    
    # 4. Display top trends
    print("\n--- Top 5 Trending Topics (Viral Factor) ---")
    cols_to_show = ['platform', 'topic', 'growth', 'engagement', 'sentiment', 'virality_score']
    # Filter for columns that actually exist in the result
    available_cols = [c for c in cols_to_show if c in processed_df.columns]
    print(processed_df[available_cols].head(5).to_string(index=False))
    
    print("\n--- Pipeline Test Complete ---")

if __name__ == "__main__":
    main()
