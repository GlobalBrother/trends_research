# Niche Trend Discovery System

A production-ready platform to collect, analyze, and visualize trending topics across multiple platforms. The system discovers emerging micro-niches by aggregating cross-platform signals and computing a normalized "Virality Score" for each topic.

Key goals:
- Quickly surface emerging topics with cross-platform signals
- Provide an extensible backend API for integrations and a Streamlit dashboard for exploration
- Make it easy to add new scrapers and scoring heuristics

---

## Quick Start (Windows - PowerShell)

1) Set PYTHONPATH and start the backend API (from project root):

```powershell
$env:PYTHONPATH = "."
python src/api/main.py
```

2) Start the Streamlit dashboard in a new terminal (from project root):

```powershell
$env:PYTHONPATH = "."
streamlit run src/dashboard/app.py
```

Notes:
- The FastAPI backend defaults to http://127.0.0.1:8000.
- The Streamlit dashboard defaults to http://localhost:8501.

---

## Installation

Prerequisites: Python 3.10+ (check `pyproject.toml` or `requirements.txt`).

Install dependencies:

```powershell
pip install -r requirements.txt
```

Environment configuration
- Create a `.env` file in the repo root or set environment variables directly. Example variables used by the project:

```text
NEWS_API_KEY=your_key_here
BACKEND_URL=http://127.0.0.1:8000
SCRAPY_CONCURRENT_REQUESTS=1
SCRAPY_DOWNLOAD_DELAY=10
DB_PATH=src/collector/trends.db
RESEND_API_KEY=...
RESEND_FROM_EMAIL=noreply@yourdomain.com
```

See `AGENTS.md` for additional developer conventions and architecture notes.

---

## Project Structure (high level)

- `src/api/main.py` — FastAPI application and public endpoints (`/trends`, `/aggregated-topics`, `/niches`).
- `src/collector/trend_collector.py` — Orchestrates scraping, stores to SQLite and runs analysis.
- `src/analytics/analytics_engine.py` — Virality scoring, sentiment, topic clustering (Union-Find).
- `src/niche/niche_discovery.py` — Niche filters and keyword lists.
- `src/dashboard/app.py` — Streamlit UI and tabs.
- `src/scrapers/` — Platform-specific scrapers (EnsembleData, Google Trends, etc.).
- `src/collector/trends.db` — Default SQLite database (development).

---

## Running with Docker

Build and run the full stack with Docker Compose:

```powershell
docker-compose up --build
```

This builds the API and dashboard images and runs them together. Check `docker-compose.yml` for service ports.

---

## Testing

Run the test suite from the project root:

```powershell
python -m pytest tests/
```

If you want to run a single test file (example):

```powershell
python -m pytest tests/test_analytics_engine.py -q
```

---

## Database & Data Model

- Default SQLite: `src/collector/trends.db` (path controlled by `DB_PATH` env var).
- Table: `trends` with fields including `title`, `source`, `viral_score`, `aggregated_topic`, `niche`, `keywords` (JSON), `raw_data` (JSON) and `timestamp`.
- Indexes exist for `source`, `timestamp`, `viral_score`, `aggregated_topic`, and `niche` to speed queries.

---

## Developer Conventions

- Every module adds the project root to `sys.path` so scripts can be run from the repo root. See `AGENTS.md` for the exact snippet.
- Typical workflow from a REPL or script:

```python
from src.collector.trend_collector import TrendCollector
collector = TrendCollector()
collector.collect_all_trends(max_workers=4)
collector.apply_analytics()
collector.apply_niche_discovery()
```

---

## Where to look next (key files)

- `src/collector/trend_collector.py` — Orchestration and persistence
- `src/analytics/analytics_engine.py` — Scoring & clustering
- `src/niche/niche_discovery.py` — Niche filters
- `src/api/main.py` — API endpoints
- `src/dashboard/app.py` — UI

---

## Contributing

Contributions are welcome. Please open issues for bugs or feature requests and submit PRs for changes. Run tests locally before submitting a PR.

---

## License

MIT
