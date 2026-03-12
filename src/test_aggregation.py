import sys
import os
import pandas as pd

# Ensure the project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.analytics.analytics_engine import AnalyticsEngine

def main():
    print("--- Testing Cross-Platform Topic Aggregation ---")
    
    analytics = AnalyticsEngine(cluster_threshold=0.3)
    
    # Simulate data from multiple platforms with similar topics
    data = [
        {"platform": "Reddit", "topic": "AI girlfriend apps are exploding", "growth": 1000},
        {"platform": "YouTube", "topic": "Why AI Girlfriend Apps are the Future", "growth": 5000},
        {"platform": "X (Twitter)", "topic": "AI girlfriend app trend", "growth": 200},
        {"platform": "HackerNews", "topic": "Show HN: My AI girlfriend bot", "growth": 300},
        {"platform": "News", "topic": "The rise of AI companions and virtual relationships", "growth": 100},
        {"platform": "Reddit", "topic": "Survival kits for 2026", "growth": 800},
        {"platform": "YouTube", "topic": "Best survival kit for emergency preparedness", "growth": 2000},
    ]
    
    df = pd.DataFrame(data)
    print(f"Input data size: {len(df)}")
    
    # Process
    processed_df = analytics.process_trends(df)
    
    print(f"\nProcessed data size (after aggregation): {len(processed_df)}")
    print("\n--- Top Aggregated Trends ---")
    cols = ['aggregated_topic', 'source_diversity', 'volume', 'virality_score', 'platform']
    print(processed_df[cols].to_string(index=False))
    
    # Verify aggregation
    ai_girlfriend_trends = processed_df[processed_df['aggregated_topic'].str.contains('AI girlfriend', case=False)]
    if not ai_girlfriend_trends.empty:
        diversity = ai_girlfriend_trends.iloc[0]['source_diversity']
        print(f"\nAI Girlfriend Diversity Score: {diversity}")
        if diversity >= 3:
            print("✅ Successfully aggregated AI girlfriend topic across platforms!")
        else:
            print("❌ Failed to aggregate AI girlfriend topic sufficiently.")
    
    survival_trends = processed_df[processed_df['aggregated_topic'].str.contains('survival', case=False)]
    if not survival_trends.empty:
        diversity = survival_trends.iloc[0]['source_diversity']
        print(f"Survival Kit Diversity Score: {diversity}")

if __name__ == "__main__":
    main()
