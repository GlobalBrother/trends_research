# Trends Research

A professional, full-stack intelligence platform for discovering, tracking, and analyzing emerging trends across multiple data sources. The system scrapes data from Google Trends, YouTube, Reddit, Hacker News, TikTok, Instagram, Threads, and NewsAPI, then processes it through an advanced analytics engine that calculates virality scores, clusters topics into niches, and surfaces actionable insights through a modern React dashboard.

---

## 🏗️ Architecture

```mermaid
graph TD
    A[React Frontend - Vite/Tailwind 4] -->|REST API| B[FastAPI Backend - Gunicorn/Uvicorn]
    B -->|SQLAlchemy| C[Azure SQL Database - MSSQL]
    B -->|Scrapy| D[Google Trends Scraper]
    B -->|EnsembleData API| E[Social Scrapers - TikTok, IG, YT]
    B -->|NewsAPI| F[News Scraper]
    B -->|VADER| G[Analytics Engine]
```

### Key Components

| Component | Location | Description |
|-----------|----------|-------------|
| **React Frontend** | `frontend/` | Built with **React 19**, **Vite**, **Tailwind CSS 4**, and **shadcn/ui**. |
| **FastAPI Backend** | `src/api/` | REST API with 30+ endpoints, serving as the orchestration layer. |
| **Scrapers** | `src/scrapers/` | Custom Scrapy spiders + EnsembleData & NewsAPI clients. |
| **Analytics Engine** | `src/analytics/` | Custom virality scoring and VADER-based sentiment analysis. |
| **Niche Discovery** | `src/niche/` | Topic clustering using Union-Find algorithm and keyword overlap. |
| **Database** | `src/db/` | SQLAlchemy models with robust migration and diagnostic tools. |
| **Infrastructure** | `terraform/` | Fully automated Azure deployment (App Service, SQL, Key Vault). |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **Node.js 22+** with `pnpm`
- **ODBC Driver 18** for SQL Server
- **Azure Subscription** (optional, for cloud deployment)

### 1. Clone and Configure

```bash
git clone https://github.com/GlobalBrother/trends_research.git
cd trends_research
cp .env.example .env
# Edit .env with your database credentials and API keys
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Install and Build the Frontend

```bash
cd frontend
pnpm install
pnpm build
cd ..
```

### 4. Database Setup & Migration

The project uses an idempotent migration system that handles both schema creation and indexing:

```bash
# Initial setup and schema creation
python -m src.db.setup_azure

# Run migration to sync indexes and new columns
python -m src.db.migrate
```

### 5. Start the Application

#### Development Mode (Hot Reload)
- **Terminal 1 (API):** `python src/api/main.py`
- **Terminal 2 (Frontend):** `cd frontend && pnpm dev`

#### Production Mode
The API is configured to serve the built frontend SPA automatically:
```bash
gunicorn src.api.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## 🔐 Authentication & Security

- **OTP-based Login:** Uses Azure Communication Services (ACS) or Resend to send One-Time Passwords.
- **Role-Based Access Control (RBAC):** Two roles: `trends` (viewer) and `admin` (management/settings).
- **JWT-less Session Management:** Secure tokens stored in the database with configurable expiration.
- **Azure Key Vault:** Seamless integration for managing secrets in production environments.

---

## 📊 Analytics Engine

The system uses an advanced, multi-factor virality scoring algorithm:
$$Virality = \text{Freshness} \times (1 + 99 \times \text{sigmoid}(\text{LogVolume} + 2 \times \text{Growth} + \text{Engagement} + (\text{Diversity} + \text{Synergy}) + \text{Platform} + \text{Momentum} + \text{Surprise} + \text{Sentiment} + \text{Spread}))$$

### Core Scoring Factors

- **⏳ Freshness (Time Decay):** Exponential decay factor ($0.5^{age/24}$) that penalizes older trends, ensuring the dashboard surfaces what's breaking *now*.
- **🤝 Cross-Platform Synergy:** A multiplier bonus for trends that resonate across different platform types (e.g., a trend appearing on both TikTok and HackerNews).
- **📈 Momentum (Acceleration):** Measures the rate of change in growth. A trend with increasing speed is prioritized over one with steady high volume.
- **😲 Surprise Factor (Z-Score):** Highlights statistical outliers by comparing current volume to the historical/batch mean, surfacing "under-the-radar" breakouts.
- **🤖 Sentiment Analysis:** Integrated VADER sentiment scoring. Strong sentiment (positive or negative) boosts the virality score.
- **🌐 Geographic Spread:** Bonus points for trends surfacing in multiple regions.
- **🧩 Topic Clustering:** Union-Find algorithm groups similar topics across different platforms into a single "Aggregated Topic" to reduce noise and calculate true cross-platform impact.

---

## ☁️ Infrastructure & Deployment

### Terraform (Azure)
The `terraform/` directory contains everything needed to provision the stack on Azure:
- **Azure SQL:** Serverless database with auto-pause.
- **Azure Container Registry (ACR):** Private registry for Docker images.
- **App Service (Linux):** Web App for Containers hosting the API + Frontend.
- **Key Vault:** Centralized secret management.
- **Managed Identity:** Passwordless authentication between services.

### Docker
```bash
# Build and run with Docker Compose
docker compose up --build
```

---

## 🛤️ Future Roadmap & Next Steps

Based on the current project state, here are the proposed next steps:

1.  **🤖 LLM-Powered Insights:**
    - Integrate GPT-4/Claude to summarize trend clusters.
    - Generate "Market Opportunities" automatically from virality scores and sentiment.
2.  **📈 Advanced Scrapers:**
    - Add Pinterest, Lemon8, and X (Twitter) as data sources.
    - Deep-scrape comments to perform fine-grained audience sentiment analysis.
3.  **🔔 Real-time Notifications:**
    - Implement Webhooks and Slack/Discord integrations for instant alerts on viral trends.
4.  **🤝 Collaborative Research:**
    - Enable shared workspaces for teams to tag, comment, and collaborate on specific trends.
5.  **📑 Professional Exporting:**
    - Generate automated PDF/PowerPoint reports for stakeholders.
6.  **⚡ Task Queue Scalability:**
    - Migrate to Celery/Redis for managing large-scale, distributed scraping jobs.

---

## 🛠️ Maintenance & Diagnostics

Check your database connectivity and Azure configuration:
```bash
python -m src.db.doctor
```

---

## 📋 Daily Meeting Notes

### 2026-04-08 — Sprint Session

**Participants:** Development Team

#### 1. Deployment Pipeline Fix (Docker)
- **Problem:** `deploy.sh` failed with `DOCKER_COMMAND_ERROR` — Docker daemon not available in WSL environment.
- **Solution:** Added runtime check (`docker info`); when Docker is unavailable, the script falls back to `az acr build` (ACR Tasks) which builds and pushes the image server-side without needing a local Docker daemon. Original local build/push flow preserved when Docker is available.
- **Files changed:** `deploy.sh`

#### 2. Azure Resource Auto-Provisioning
- **Problem:** `az webapp restart` failed with `ResourceNotFound` — the App Service `trends-research-app` did not exist in the resource group.
- **Solution:** Replaced bare restart with existence checks for Resource Group, App Service Plan, and Web App. If the Web App doesn't exist, the script now creates it automatically with `az webapp create`, configures `WEBSITES_PORT`, and sets storage settings. If it already exists, it updates the container image and restarts.
- **New configurable env vars:** `APP_SERVICE_PLAN`, `APP_SERVICE_SKU`, `LOCATION` (with sensible defaults).
- **Files changed:** `deploy.sh`

#### 3. Resource Group Configuration
- **Change:** Updated default `RESOURCE_GROUP` from `trends-research-rg` to `GB_Reporting_RG` to match the existing Azure infrastructure.
- **Files changed:** `deploy.sh`

#### 4. Performance Optimization — Scraping Speed
- **Problem:** Frontend reported "Failed to fetch trends: timeout of 60000ms exceeded" — scraping was too slow (sequential execution).
- **Solution (multi-level parallelization):**
  - **Comprehensive scrape** (`trend_collector.py`): All 8 scrapers (Google Trends, YouTube, TikTok, Instagram, Threads, Reddit, HackerNews, News) now run concurrently via `ThreadPoolExecutor` instead of sequentially.
  - **Non-blocking GET endpoints** (`main.py`): `/trending_now`, `/youtube_trends`, `/hackernews_trends`, `/reddit_trends`, `/news_trends` now return existing (possibly stale) data immediately and trigger a background refresh thread if data is stale. Per-platform locks prevent duplicate concurrent scrapes.
  - **Parallelized per-keyword API calls** in all 4 EnsembleData scrapers (`youtube_scraper.py`, `tiktok_scraper.py`, `instagram_scraper.py`, `threads_scraper.py`): keywords fetched concurrently (up to 4 workers) with `threading.Event` stop mechanism for API rate limits.
- **Frontend timeout:** Adjusted from 60s → 300s → settled at 120s (2 min) since responses are now much faster.
- **Files changed:** `src/collector/trend_collector.py`, `src/api/main.py`, `src/scrapers/ensembledata/youtube_scraper.py`, `src/scrapers/ensembledata/tiktok_scraper.py`, `src/scrapers/ensembledata/instagram_scraper.py`, `src/scrapers/ensembledata/threads_scraper.py`, `frontend/src/lib/api.ts`

#### 5. Admin UI — Independent Scraper Loading States
- **Problem:** All scrape buttons in the admin Settings page shared a single loading boolean — triggering one scraper disabled/spun all buttons.
- **Solution:** Replaced shared `syncing` boolean with a per-scraper `scrapingMap` state (`Record<string, boolean>`). Each button now tracks its own loading independently, allowing multiple scrapers to run in parallel from the UI.
- **Files changed:** `frontend/src/pages/Settings.tsx`

#### 6. Per-Platform Scraper Connectivity Test
- **Problem:** No way to diagnose why a specific scraper fails without reading server logs.
- **Solution:**
  - **Backend:** Added `GET /test_scraper/{platform}` endpoint that tests each of the 8 platforms individually by making minimal API calls. Returns `{ok, message}` with normalized human-readable errors for common failures (missing API keys, auth errors, rate limits, timeouts, connection issues).
  - **Frontend:** Added a "Test" button (stethoscope icon) next to each platform's "Scrape" button with per-platform loading state and inline result banner (green for success, red for error with the normalized message).
- **Files changed:** `src/api/main.py`, `frontend/src/lib/api.ts`, `frontend/src/pages/Settings.tsx`

#### Summary of All Files Modified Today
| File | Changes |
|------|---------|
| `deploy.sh` | Docker fallback, auto-provisioning, resource group update |
| `src/api/main.py` | Non-blocking endpoints, `/test_scraper/{platform}` endpoint |
| `src/collector/trend_collector.py` | Parallel comprehensive scrape |
| `src/scrapers/ensembledata/youtube_scraper.py` | Parallel per-keyword fetching |
| `src/scrapers/ensembledata/tiktok_scraper.py` | Parallel per-keyword fetching |
| `src/scrapers/ensembledata/instagram_scraper.py` | Parallel per-keyword fetching |
| `src/scrapers/ensembledata/threads_scraper.py` | Parallel per-keyword fetching |
| `frontend/src/lib/api.ts` | Timeout adjustment, `testScraper()` function |
| `frontend/src/pages/Settings.tsx` | Independent loading states, test buttons |

#### Next Steps / Action Items
- [ ] Rebuild frontend (`pnpm build`) and redeploy (`bash deploy.sh`)
- [ ] Verify all 8 scraper test buttons work end-to-end in production
- [ ] Monitor scraping performance improvements with parallelization
- [ ] Consider adding WebSocket progress reporting for long-running scrapes

---

## 📜 License

Private repository — © 2026 Global Brother SRL. All rights reserved.
