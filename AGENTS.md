# Niche Trend Discovery System - AI Agent Guidelines

## Architecture Overview
This is a multi-platform trend aggregation system that collects data from social media sources, applies analytics to calculate virality scores, and presents insights through a web dashboard.

**Core Components:**
- `src/collector/trend_collector.py`: Orchestrates data collection from all sources using ThreadPoolExecutor
- `src/analytics/analytics_engine.py`: Calculates custom virality scores using `log(mentions) + 2*growth_rate + engagement_weight + source_diversity`
- `src/niche/niche_discovery.py`: Filters trends into predefined niches (Survival, Health, Preppers, Sustainability, Homesteading)
- `src/api/main.py`: FastAPI backend with CORS enabled
- `src/dashboard/app.py`: Streamlit frontend with authentication

**Data Flow:**
1. Scrapers collect raw trends → stored in SQLite `trends` table
2. AnalyticsEngine processes all records to add `viral_score`, `aggregated_topic` (Union-Find clustering)
3. NicheDiscovery assigns `niche` field based on keyword matching
4. API serves filtered/sorted data to dashboard

## Critical Workflows

### Running the System
Always set `PYTHONPATH="."` before executing Python scripts - all modules modify `sys.path` to include project root.

**Backend:**
```powershell
$env:PYTHONPATH="."
python src/api/main.py
```

**Dashboard:**
```powershell
$env:PYTHONPATH="."
streamlit run src/dashboard/app.py
```

**Docker:**
```bash
docker-compose up --build
```

### Database Operations
- Database: `src/collector/trends.db` (SQLite)
- Schema: `trends` table with fields: `title`, `source`, `viral_score`, `aggregated_topic`, `niche`, `keywords` (JSON), `raw_data` (JSON)
- Indexes on `source`, `timestamp`, `viral_score`, `aggregated_topic`, `niche`

### Testing
Run tests from project root:
```bash
python -m pytest tests/
```

## Project Conventions

### Imports & Path Management
Every module adds project root to `sys.path`:
```python
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
```

### TrendCollector Usage
```python
from src.collector.trend_collector import TrendCollector
collector = TrendCollector()
results = collector.collect_all_trends(max_workers=4)  # Concurrent scraping
collector.apply_analytics()  # Calculate viral scores
collector.apply_niche_discovery()  # Assign niches
```

### AnalyticsEngine Patterns
- `calculate_virality_score()`: Formula scales to 1-100 range using sigmoid
- `group_topics()`: Union-Find algorithm clusters similar titles (e.g., "AI Girlfriend App" → "AI girlfriend")
- Sentiment analysis uses VADER (`analyzer.polarity_scores(text)['compound']`)

### NicheDiscovery Filtering
Predefined niches with include/exclude keyword lists. Example:
```python
discovery = NicheDiscovery()
filtered_df = discovery.filter_by_niche(df, "Survival")  # Filters trends by survival-related keywords
```

### Scraper Integration
- EnsembleData scrapers: `src/scrapers/ensembledata/` (Instagram, Reddit, YouTube, TikTok, Threads)
- Google Trends: Scrapy spider in `src/scrapers/google_trends_scraper/`
- All scrapers inherit from base classes and store to database directly

## Integration Points

### External Dependencies
- **NewsAPI**: Requires `NEWS_API_KEY` env var
- **Resend**: Email service, `RESEND_API_KEY` and `RESEND_FROM_EMAIL`
- **EnsembleData API**: Used by social media scrapers
- **Streamlit Auth**: OTP-based login with cookie persistence

### Environment Variables (.env)
```
NEWS_API_KEY=your_key_here
BACKEND_URL=http://127.0.0.1:8000
SCRAPY_CONCURRENT_REQUESTS=1
SCRAPY_DOWNLOAD_DELAY=10
DB_PATH=src/collector/trends.db
RESEND_API_KEY=...
RESEND_FROM_EMAIL=noreply@yourdomain.com
```

### API Endpoints
- `GET /trends`: Filtered trends with pagination
- `GET /aggregated-topics`: Clustered topics with avg scores
- `GET /niches`: Discovered niche statistics
- `POST /auth/*`: Authentication endpoints

## Key Files to Reference
- `src/collector/trend_collector.py`: Main orchestration logic
- `src/analytics/analytics_engine.py`: Virality scoring implementation
- `src/niche/niche_discovery.py`: Niche filtering rules
- `src/api/main.py`: API structure and endpoints
- `requirements.txt`: All dependencies
- `docker-compose.yml`: Containerized deployment</content>
<parameter name="filePath">C:\Users\MarianCraciun\OneDrive - Global Brother SRL\Documents\GitHub\trends_research\AGENTS.md
