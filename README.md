# Trends Research

A full-stack intelligence platform for discovering, tracking, and analyzing emerging trends across multiple data sources. The system scrapes data from Google Trends, YouTube, Reddit, Hacker News, TikTok, Instagram, Threads, and NewsAPI, then processes it through an analytics engine that calculates virality scores, clusters topics into niches, and surfaces actionable insights through a modern React dashboard.

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                   React Frontend (Vite)                │
│   Dashboard · Trend Explorer · Projects · Reports      │
│   Alerts · Saved Views · Settings                      │
└────────────────────┬───────────────────────────────────┘
                     │  /api/*
┌────────────────────▼───────────────────────────────────┐
│                FastAPI Backend (Gunicorn)               │
│   REST API · Auth (OTP) · Scrape Orchestration         │
│   Analytics Engine · Niche Discovery                   │
└────────────────────┬───────────────────────────────────┘
                     │  SQLAlchemy ORM
┌────────────────────▼───────────────────────────────────┐
│              Azure SQL Database (MSSQL)                 │
│   Trends · Content · Niches · Ads · Token Usage        │
└────────────────────────────────────────────────────────┘
```

### Key Components

| Component | Location | Description |
|-----------|----------|-------------|
| **React Frontend** | `frontend/` | Vite + React 19 + Tailwind CSS 4 + shadcn/ui |
| **FastAPI Backend** | `src/api/main.py` | REST API with 30+ endpoints |
| **Scrapers** | `src/scrapers/` | Scrapy spiders + EnsembleData API clients |
| **Analytics Engine** | `src/analytics/` | Virality scoring, sentiment analysis |
| **Niche Discovery** | `src/niche/` | Union-Find topic clustering |
| **Collector** | `src/collector/` | Orchestrates scraping across all platforms |
| **Database** | `src/db/` | SQLAlchemy models, connection pooling, migrations |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 22+ with pnpm
- ODBC Driver 18 for SQL Server
- Azure SQL Database (or local SQL Server)

### 1. Clone and configure

```bash
git clone https://github.com/GlobalBrother/trends_research.git
cd trends_research
cp .env.example .env
# Edit .env with your database credentials and API keys
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install and build the frontend

```bash
cd frontend
pnpm install
pnpm build
cd ..
```

### 4. Run the database migration

```bash
python -m src.db.setup_azure
```

### 5. Start the application

```bash
# Option A: Development (API + frontend dev server with hot reload)
# Terminal 1: Start the API
python src/api/main.py

# Terminal 2: Start the frontend dev server (proxies /api to localhost:8000)
cd frontend && pnpm dev

# Option B: Production (API serves the built frontend)
gunicorn src.api.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

The application will be available at `http://localhost:8000` (production) or `http://localhost:5173` (development).

---

## Docker Deployment

The project includes a multi-stage Dockerfile that builds the React frontend and bundles it with the Python API.

```bash
# Build and run with Docker Compose
docker compose up --build

# Or build manually
docker build -f Dockerfile.api -t trends-research .
docker run -p 8000:8000 --env-file .env trends-research
```

---

## Database Connection

The system supports multiple authentication strategies for Azure SQL, auto-detected in this order:

| Strategy | Required `.env` Variables |
|----------|---------------------------|
| **Full Connection String** | `AZURE_SQL_CONNECTIONSTRING` |
| **SQL Auth (user/pass)** | `AZURE_SQL_SERVER`, `AZURE_SQL_DATABASE`, `AZURE_SQL_USER`, `AZURE_SQL_PASS` |
| **Azure AD (passwordless)** | `AZURE_SQL_SERVER`, `AZURE_SQL_DATABASE` (uses `az login` credentials) |

### Troubleshooting

Run the built-in diagnostic tool:

```bash
python -m src.db.doctor
```

This checks DNS resolution, TCP connectivity, ODBC driver availability, Azure AD token validity, and connection string formatting.

---

## API Endpoints

### Trends and Content

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/trends` | Processed trends with virality scores |
| `GET` | `/trending_now` | Real-time Google Trends |
| `GET` | `/all_trends` | All trends across platforms |
| `GET` | `/youtube_trends` | YouTube-specific trends |
| `GET` | `/reddit_trends` | Reddit-specific trends |
| `GET` | `/hackernews_trends` | Hacker News trends |
| `GET` | `/news_trends` | NewsAPI trends |
| `GET` | `/youtube_videos` | YouTube video content |
| `GET` | `/tiktok_videos` | TikTok video content |
| `GET` | `/instagram_posts` | Instagram post content |
| `GET` | `/reddit_posts` | Reddit post content |
| `GET` | `/threads_posts` | Threads post content |
| `GET` | `/ads_insight` | Ad creative insights |

### Niche Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/niches` | List all niches |
| `GET` | `/niche_keywords/{niche}` | Keywords for a niche |
| `POST` | `/niches` | Create a new niche |
| `POST` | `/niches/{niche}/keywords` | Add keywords to a niche |
| `DELETE` | `/niches/{niche}` | Delete a niche |

### Scraping

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/scrape` | Trigger a scrape job |
| `POST` | `/scrape_ads` | Trigger ad scraping |
| `GET` | `/scrape_errors` | View scrape errors |

### Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/admin/azure/status` | Database connection status |
| `GET` | `/admin/azure/diagnose` | Full connection diagnostic |
| `POST` | `/admin/azure/migrate` | Run database migration |
| `GET` | `/admin/token_usage` | API token usage stats |

---

## Frontend Pages

| Page | Route | Description |
|------|-------|-------------|
| **Dashboard** | `/` | KPI overview, trend charts, platform breakdown, recent activity |
| **Trend Explorer** | `/explorer` | Deep-dive research with filters, charts, and content tables |
| **Research Projects** | `/projects` | Track research initiatives with progress and team info |
| **Reports** | `/reports` | Generate and export trend analysis reports |
| **Saved Views** | `/saved` | Bookmarked filter configurations for quick access |
| **Alerts** | `/alerts` | Configure notification rules and review alert history |
| **Settings** | `/settings` | Data sources, API keys, database management |

---

## Project Structure

```
trends_research/
├── frontend/                    # React frontend (Vite + Tailwind + shadcn/ui)
│   ├── src/
│   │   ├── components/          # Reusable UI components
│   │   │   ├── layout/          # DashboardLayout (sidebar + header)
│   │   │   └── ui/              # shadcn/ui primitives
│   │   ├── pages/               # Page-level components
│   │   ├── hooks/               # Custom React hooks (useApi, useLazyApi)
│   │   ├── lib/                 # API client, utilities
│   │   ├── contexts/            # Theme context
│   │   ├── App.tsx              # Routes & layout
│   │   └── index.css            # Design system tokens
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── src/
│   ├── api/
│   │   └── main.py              # FastAPI application (30+ endpoints)
│   ├── analytics/
│   │   └── analytics_engine.py  # Virality scoring and sentiment analysis
│   ├── collector/
│   │   └── trend_collector.py   # Scrape orchestrator
│   ├── config.py                # Centralized configuration
│   ├── db/
│   │   ├── connection.py        # Connection pooling and auto-detection
│   │   ├── doctor.py            # CLI diagnostic tool
│   │   ├── migrate.py           # Idempotent schema migration
│   │   ├── models.py            # SQLAlchemy ORM models (indexed)
│   │   ├── setup_azure.py       # Initial schema setup
│   │   └── sql_compat.py        # Cross-DB query helpers
│   ├── niche/
│   │   └── niche_discovery.py   # Union-Find topic clustering
│   └── scrapers/
│       ├── ensembledata/        # TikTok, Instagram, Threads, Reddit, YouTube
│       ├── gethookedai/         # Ad creative scraping
│       └── google_trends_scraper/ # Scrapy spider for Google Trends
├── tests/                       # Test suite
├── docker-compose.yml           # Single-service deployment
├── Dockerfile.api               # Multi-stage build (frontend + API)
├── requirements.txt             # Python dependencies
└── .env.example                 # Configuration template
```

---

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_SQL_CONNECTIONSTRING` | Yes* | Full Azure SQL connection string |
| `AZURE_SQL_SERVER` | Yes* | Azure SQL server hostname |
| `AZURE_SQL_DATABASE` | Yes* | Database name |
| `NEWS_API_KEY` | No | NewsAPI.org API key |
| `ENSEMBLEDATA_TOKEN` | No | EnsembleData API token (TikTok, Instagram, etc.) |
| `TIKTOK_CLIENT_KEY` | No | TikTok API client key |
| `GETHOOKEDAI_TOKEN` | No | GetHookdAI ad scraping token |
| `RESEND_API_KEY` | No | Resend email API key (for OTP auth) |

*At least one database connection method is required.

---

## Testing

Run the test suite from the project root:

```bash
python -m pytest tests/
```

---

## License

Private repository — Global Brother SRL.
