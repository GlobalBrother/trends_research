# Niche Trend Discovery System

A production-ready platform to collect, analyze, and visualize trending topics across multiple platforms. This system identifies emerging niches and calculates a custom **Virality Score** using cross-platform signals and advanced analytics.

## 🚀 Features

- **Multi-Source Data Collection**:
  - **Google Trends**: Interest over time, related queries, and regions.
  - **YouTube**: Trending videos and niche-specific search results.
  - **Reddit**: Real-time trending posts from `r/all/hot`.
  - **Hacker News**: Top tech stories and startup trends.
  - **NewsAPI**: Global news spikes and headlines (requires `NEWS_API_KEY`).
  - **Stack Exchange**: Hot questions and emerging developer tools.
- **Topic Aggregation (Micro-Niches)**: Automatically clusters similar titles across different platforms into a single "Aggregated Topic" using a Union-Find keyword-based algorithm.
- **Advanced Virality Scoring**:
  - Uses a sophisticated formula incorporating: **Volume**, **Growth**, **Engagement**, **Source Diversity**, and **Sentiment**.
  - Formula: `ViralScore = log(mentions) + 2 * growth_rate + engagement_weight + source_diversity_boost`.
  - Scaled to a 1-100 range for easy interpretation.
- **Interactive Dashboard**: Streamlit-based interface with 10+ tabs for deep dives into specific platforms or overall niche research.
- **FastAPI Backend**: Robust API serving analyzed trend data with sub-second response times.

## 🏗 Project Structure

- `src/api`: FastAPI backend and endpoint definitions.
- `src/collector`: Primary data orchestration layer (`TrendCollector`).
- `src/analytics`: `AnalyticsEngine` for virality scoring, clustering, and sentiment analysis.
- `src/niche`: `NicheDiscovery` for filtering and micro-niche identification.
- `src/dashboard`: Streamlit frontend application.
- `src/scrapers`: Specialized Scrapy spiders for each platform.

## 🛠 Installation

### 1. Clone & Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Create a `.env` file in the root directory (refer to `.env.example`):
```env
NEWS_API_KEY=your_key_here
BACKEND_URL=http://127.0.0.1:8000
SCRAPY_CONCURRENT_REQUESTS=1
SCRAPY_DOWNLOAD_DELAY=10
```

## 🚦 How to Run

### Step 1: Start the Backend API
From the project root:
```powershell
$env:PYTHONPATH="."
python src/api/main.py
```
The API will be available at `http://127.0.0.1:8000`.

### Step 2: Start the Dashboard
Open a new terminal and run:
```powershell
$env:PYTHONPATH="."
streamlit run src/dashboard/app.py
```

## 📊 Analytics Methodology

### Virality Score
The score represents the "heat" of a topic. A high score (90+) indicates a topic is exploding across multiple platforms with high engagement and rapid growth.

### Topic Clustering
The system groups titles like "AI Girlfriend App" and "My AI Girlfriend Experience" into a single topic "AI girlfriend". This allows for a unified view of a trend regardless of minor variations in titles across platforms.

### Source Diversity
Topics appearing on multiple platforms (e.g., YouTube + Reddit + News) receive a significant boost, as cross-platform presence is a strong indicator of a mainstream trend.

## 📝 License
MIT
