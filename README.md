# Niche Trend Discovery System

A production-ready platform to collect, analyze, and visualize trending topics across multiple platforms. The system identifies emerging niches and calculates a custom **Virality Score** using cross-platform signals and advanced analytics.

## Features

- **Multi-Source Data Collection** — Scrapy-based spiders for Google Trends, YouTube, Reddit, Hacker News, NewsAPI, and social platforms (X/Twitter, Threads, Instagram).
- **Topic Aggregation** — Union-Find keyword-overlap algorithm clusters similar titles across platforms into a single "Aggregated Topic" for a unified view.
- **Virality Scoring** — Composite formula incorporating volume, growth rate, engagement, source diversity, sentiment, and geographic spread, scaled to 1-100.
- **Micro-Niche Discovery** — TF-IDF + KMeans clustering surfaces emerging sub-topics within a niche.
- **Interactive Dashboard** — Streamlit-based UI with KPI cards, treemaps, scatter plots, and per-platform deep dives.
- **FastAPI Backend** — REST API with in-memory caching, background scraping, and automatic freshness checks.

## Project Structure

```
trends_research/
├── src/
│   ├── config.py                  # Centralized configuration (paths, env vars, constants)
│   ├── api/
│   │   └── main.py                # FastAPI backend (v2.0)
│   ├── collector/
│   │   ├── trend_collector.py     # Data orchestration & scraper invocation
│   │   └── trends.db              # SQLite database (WAL mode)
│   ├── analytics/
│   │   └── analytics_engine.py    # Sentiment, virality scoring, topic clustering
│   ├── niche/
│   │   └── niche_discovery.py     # Niche keywords, filtering, micro-niche clustering
│   ├── dashboard/
│   │   ├── app.py                 # Streamlit frontend (v2.0)
│   │   └── utils/
│   │       └── api_client.py      # Typed HTTP client for the backend
│   ├── scrapers/
│   │   └── google_trends_scraper/ # Scrapy project with platform-specific spiders
│   └── utils/
├── requirements.txt
└── README.md
```

## Installation

### 1. Clone and install dependencies

```bash
git clone https://github.com/GlobalBrother/trends_research.git
cd trends_research
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
NEWS_API_KEY=your_newsapi_key
BACKEND_URL=http://127.0.0.1:8000
BACKEND_PORT=8000

# Scraper tunables (optional)
SCRAPY_CONCURRENT_REQUESTS=1
SCRAPY_DOWNLOAD_DELAY=10
SCRAPE_FRESHNESS_HOURS=144

# Cache (optional)
CACHE_TTL_SECONDS=300
```

## How to Run

### Step 1: Start the backend API

```bash
PYTHONPATH=. python src/api/main.py
```

The API will be available at `http://127.0.0.1:8000` with interactive docs at `/docs`.

### Step 2: Start the dashboard

In a separate terminal:

```bash
PYTHONPATH=. streamlit run src/dashboard/app.py
```

## Analytics Methodology

### Virality Score

The score (1-100) represents the "heat" of a topic:

```
base = log(volume) + 2 * norm_growth + engagement_weight
       + diversity_boost + platform_boost + sentiment_bonus + spread_bonus
score = 1 + sigmoid(base) * 99
```

A score above 90 indicates a topic exploding across multiple platforms with high engagement.

### Topic Clustering

The Union-Find algorithm groups titles like "AI Girlfriend App" and "My AI Girlfriend Experience" into a single aggregated topic. This provides a unified view regardless of minor title variations across platforms.

### Source Diversity

Topics appearing on multiple platforms (e.g., YouTube + Reddit + News) receive a significant boost, as cross-platform presence is a strong indicator of a mainstream trend.

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Health check |
| `/niches` | GET | List available niches |
| `/niche_keywords/{name}` | GET | Get seed keywords for a niche |
| `/scrape` | POST | Trigger background comprehensive scrape |
| `/trends` | GET | Aggregated trends (with optional geo/niche filters) |
| `/trending_now` | GET | Google daily/realtime trending searches |
| `/youtube_trends` | GET | YouTube trends for a niche |
| `/social_trends` | GET | X/Threads/Instagram trends |
| `/hackernews_trends` | GET | Hacker News trends |
| `/reddit_trends` | GET | Reddit trends |
| `/news_trends` | GET | NewsAPI trends |
| `/all_trends` | GET | All platforms combined |
| `/scrape_errors` | GET | Scrape error log |

## License

MIT
