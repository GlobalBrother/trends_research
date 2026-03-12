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
    print("--- Starting HackerNews Integration Test ---")
    
    # 1. Initialize
    collector = TrendCollector()
    analytics = AnalyticsEngine()
    
    # 2. Run HackerNews Scraper
    print("Running HackerNews scraper...")
    if collector.run_hackernews_scraper():
        print("Scraper finished successfully.")
    else:
        print("Scraper failed.")
        return

    # 3. Collect Data (Collector)
    print("Fetching trends including HackerNews...")
    raw_data = collector.collect_all(geo="US", include_hackernews=True)
    
    if raw_data.empty:
        print("No raw data found.")
        return

    # Filter to see only HackerNews if possible
    hn_data = raw_data[raw_data['platform'] == 'HackerNews']
    print(f"Collected {len(hn_data)} HackerNews trend points.")
    
    if hn_data.empty:
        print("HackerNews data not found in collector output.")
        return
    
    # 4. Process Trends (Processor/TrendEngine/ViralCalc)
    print("Processing trends through Analytics Engine...")
    processed_df = analytics.process_trends(raw_data)
    
    # Filter for HackerNews in processed results
    hn_processed = processed_df[processed_df['platform'] == 'HackerNews']
    print(f"Processed {len(hn_processed)} HackerNews trends.")
    
    # 5. Display top trends
    print("\n--- Top 5 HackerNews Stories (Viral Factor) ---")
    cols_to_show = ['platform', 'topic', 'growth', 'engagement', 'virality_score']
    # Filter for columns that actually exist in the result
    available_cols = [c for c in cols_to_show if c in hn_processed.columns]
    print(hn_processed[available_cols].head(5).to_string(index=False))
    
    print("\n--- HackerNews Integration Test Complete ---")

if __name__ == "__main__":
    main()
