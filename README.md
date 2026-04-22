# Trends Research

A full-stack intelligence platform for discovering, tracking, and analyzing emerging trends across multiple data sources. The system scrapes data from Google Trends, YouTube, Reddit, Hacker News, TikTok, Instagram, Threads, NewsAPI, and the GetHookd.ai ad library, then processes it through an analytics engine that calculates virality scores, clusters topics into niches, and surfaces actionable insights through a React dashboard.

> **Status:** Internal product — Global Brother SRL · Python 3.11 · FastAPI · React 19 · Azure SQL · Docker

### What it does, in one screen

| | |
|---|---|
| **9 data sources** | Google Trends, YouTube, Reddit, Hacker News, TikTok, Instagram, Threads, NewsAPI, GetHookd.ai ads |
| **Virality scoring** | VADER sentiment + platform-weighted sigmoid aggregation → [1–100] score per keyword |
| **Niche discovery** | Rule-based filtering into 5 seed niches + TF-IDF/KMeans micro-clusters |
| **Ads intelligence** | 21M+ ad library searchable by brand, keyword, performance score |
| **Auth** | OTP email login (Resend) + 12h bearer tokens, role-based admin |
| **40+ REST endpoints** | Full OpenAPI at `/docs` — trends, content, ads, niches, scraping, admin |
| **7 frontend pages** | Dashboard, Trend Explorer, Projects, Reports, Saved Views, Alerts, Settings |
| **Deployable today** | Single Docker image (node build → python runtime) + Terraform for Azure SQL |

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                   React Frontend (Vite)                │
│   Dashboard · Trend Explorer · Projects · Reports      │
│   Alerts · Saved Views · Settings                      │
└────────────────────┬───────────────────────────────────┘
                     │  /api/*  (Axios, proxied in dev)
┌────────────────────▼───────────────────────────────────┐
│              FastAPI Backend (Gunicorn + Uvicorn)      │
│   REST API · OTP Auth · Scrape Orchestration           │
│   Analytics Engine · Niche Discovery · In-mem Cache    │
└────────────────────┬───────────────────────────────────┘
                     │  SQLAlchemy ORM + pyodbc
┌────────────────────▼───────────────────────────────────┐
│              Azure SQL Database (MSSQL)                │
│   trends · content · content_metrics · authors         │
│   niches · ads_insight · token_usage · auth_tokens     │
└────────────────────────────────────────────────────────┘
          ▲
          │ background jobs (FastAPI BackgroundTasks)
┌─────────┴──────────────────────────────────────────────┐
│   Scrapers: Scrapy spiders (Google Trends, HN, News)   │
│   API clients: EnsembleData (TikTok/IG/YT/Reddit/      │
│   Threads), GetHookd.ai (ad library), Resend (email)   │
└────────────────────────────────────────────────────────┘
```

### Key Components

| Component | Location | Description |
|-----------|----------|-------------|
| React Frontend | `frontend/` | Vite 7 + React 19 + TypeScript + Tailwind 4 + shadcn/ui, Wouter routing |
| FastAPI Backend | `src/api/main.py` | REST API (40+ endpoints), OTP auth, admin diagnostics, background scrape jobs |
| Scrapers | `src/scrapers/` | Scrapy spiders + EnsembleData + GetHookd.ai API clients |
| Analytics Engine | `src/analytics/analytics_engine.py` | VADER sentiment + sigmoid-weighted virality scoring |
| Niche Discovery | `src/niche/niche_discovery.py` | Rule-based niche filtering + TF-IDF + KMeans micro-niche clustering |
| Collector | `src/collector/trend_collector.py` | Orchestrates scraping across all platforms |
| Database | `src/db/` | SQLAlchemy models, connection pooling, idempotent migrations, doctor tool |

---

## Quick Start

### Prerequisites

- Python 3.11 (the Docker image and `pyproject.toml` target 3.11)
- Node.js 22+ with pnpm
- Microsoft ODBC Driver 18 for SQL Server
- Azure SQL Database (or a reachable MSSQL instance)

### 1. Clone and configure

```bash
git clone https://github.com/GlobalBrother/trends_research.git
cd trends_research
cp .env.example .env
# Edit .env — at minimum configure one database auth method
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
cd frontend && pnpm install && pnpm build && cd ..
```

### 3. Initialize the database

```bash
python -m src.db.setup_azure     # one-time: creates tables + indexes
python -m src.db.doctor          # verify connectivity (DNS, TCP, ODBC, auth)
```

### 4. Run

**Development** (hot reload on both tiers):

```bash
# Terminal 1 — API
python src/api/main.py

# Terminal 2 — frontend dev server (proxies /api → localhost:8000)
cd frontend && pnpm dev
```

**Production** (API serves the built frontend):

```bash
gunicorn src.api.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

App is available at `http://localhost:8000` (prod) or `http://localhost:5173` (dev).

---

## Docker

Multi-stage image: node:22 builds the React app, python:3.11-slim runs Gunicorn and serves the bundled frontend.

```bash
docker compose up --build

# or manually
docker build -f Dockerfile.api -t trends-research .
docker run -p 8000:8000 --env-file .env trends-research
```

`docker-compose.yml` runs a single service and connects to an external Azure SQL instance — no database container.

---

## Database Connection

Three auth strategies, auto-detected in this order:

| Strategy | Required env vars |
|----------|---------------------------|
| Full connection string | `AZURE_SQL_CONNECTIONSTRING` (ADO.NET format is auto-converted to ODBC) |
| SQL Auth | `AZURE_SQL_SERVER`, `AZURE_SQL_DATABASE`, `AZURE_SQL_USER`, `AZURE_SQL_PASS` |
| Azure AD passwordless | `AZURE_SQL_SERVER`, `AZURE_SQL_DATABASE` (uses `az login` or Managed Identity) |

### Tools

| Command | Purpose |
|---------|---------|
| `python -m src.db.doctor` | Full diagnostic: DNS, TCP, ODBC driver, AD token, connection string |
| `python -m src.db.setup_azure` | Create schema from SQLAlchemy models |
| `python -m src.db.migrate` | Idempotent: add missing tables, columns, indexes |

Migration and diagnostic endpoints are also exposed under `/admin/azure/*`.

---

## API Endpoints

### Auth (OTP via Resend)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/request_otp` | Send OTP email |
| POST | `/auth/verify_otp` | Verify code, return 12h bearer token |
| GET  | `/auth/validate_token` | Check token validity |
| GET/POST/PUT/DELETE | `/auth/users` | User management (admin only) |

### Trends & Content

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/trends` | Processed trends with virality + sentiment scores |
| GET | `/all_trends` | Combined trends across all platforms |
| GET | `/trending_now` | Real-time Google Trends |
| GET | `/youtube_trends`, `/reddit_trends`, `/hackernews_trends`, `/news_trends` | Per-platform trends |
| GET | `/youtube_videos`, `/tiktok_videos`, `/instagram_posts`, `/reddit_posts`, `/threads_posts` | Per-platform content |
| GET | `/ads_insight` | GetHookd.ai ad creatives, filterable |
| GET | `/search_brands` | Search GetHookd.ai brand catalogue |

### Niches

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/niches` | List niches |
| GET    | `/niche_keywords/{niche}` | Seed keywords for a niche |
| POST   | `/niches` | Create niche |
| POST   | `/niches/{niche}/keywords` | Add keyword |
| DELETE | `/niches/{niche}` | Delete niche |
| DELETE | `/niches/{niche}/keywords/{keyword}` | Remove keyword |

### Scraping

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST   | `/scrape` | Trigger a scrape job (niche, geo, timeframe, category, scraper_type) |
| POST   | `/scrape_ads` | Trigger a GetHookd.ai ad scrape |
| POST   | `/scrape_brand_ads` | Scrape ads for a specific brand |
| GET    | `/scrape_errors` | View failed scrape attempts |
| DELETE | `/scrape_errors` | Clear error log |

### Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET  | `/admin/token_usage` | Scraper API unit consumption by platform |
| GET  | `/admin/azure/status` | Connection status + per-table row counts |
| GET  | `/admin/azure/diagnose` | Full connectivity diagnostic |
| POST | `/admin/azure/setup_schema` | Initialize schema |
| POST | `/admin/azure/migrate` | Run migration |

---

## Frontend Pages

| Page | Route | Description |
|------|-------|-------------|
| Dashboard | `/` | KPI strip, platform breakdown, ads insight, recent activity |
| Trend Explorer | `/explorer` | Deep-dive research with filters, charts, content tables |
| Research Projects | `/projects` | Track research initiatives with progress and team info |
| Reports | `/reports` | Generate and export trend analysis |
| Saved Views | `/saved` | Bookmarked filter configurations |
| Alerts | `/alerts` | Configure notification rules |
| Settings | `/settings` | Data sources, API keys, database management |

State management: React Context (`ThemeContext`) + custom hooks (`useApi`, `useLazyApi`, `useComposition`). Routing: Wouter. Forms: React Hook Form + Zod. Charts: Recharts.

---

## Project Structure

```
trends_research/
├── frontend/                    # React frontend
│   └── src/
│       ├── components/          # layout/ + shadcn/ui primitives
│       ├── pages/               # Dashboard, TrendExplorer, ResearchProjects, Reports, SavedViews, Alerts, Settings, NotFound
│       ├── hooks/               # useApi, useLazyApi, useComposition, useMobile, usePersistFn
│       ├── lib/api.ts           # Typed Axios client
│       ├── contexts/            # ThemeContext
│       └── App.tsx              # Wouter routes + DashboardLayout
├── src/
│   ├── api/main.py              # FastAPI app (40+ endpoints, in-memory cache, BackgroundTasks)
│   ├── analytics/
│   │   └── analytics_engine.py  # Virality scoring (sigmoid + platform weights), VADER sentiment
│   ├── collector/
│   │   └── trend_collector.py   # Cross-platform scrape orchestrator
│   ├── config.py                # Central env config + platform weights
│   ├── db/
│   │   ├── connection.py        # Auto-detecting auth, connection pooling
│   │   ├── doctor.py            # CLI connectivity diagnostic
│   │   ├── migrate.py           # Idempotent schema migration
│   │   ├── models.py            # SQLAlchemy ORM (20+ tables with indexes)
│   │   ├── setup_azure.py       # Initial schema setup
│   │   └── sql_compat.py        # Cross-DB helpers
│   ├── niche/
│   │   └── niche_discovery.py   # Seed-keyword niches + TF-IDF + KMeans micro-clustering
│   └── scrapers/
│       ├── ensembledata/        # TikTok, Instagram, Threads, Reddit, YouTube (API)
│       ├── gethookedai/         # ads_insight.py — GetHookd.ai REST client
│       └── google_trends_scraper/ # Scrapy project: Google Trends, HN, NewsAPI, social trends
├── tests/                       # pytest suite (analytics, API, scrapers, pipeline)
├── terraform/                   # Azure infra (resource group, MSSQL server + DB, firewall)
├── docker-compose.yml
├── Dockerfile.api               # Multi-stage: node:22 build → python:3.11 runtime
├── requirements.txt
├── pyproject.toml
└── .env.example
```

---

## Environment Variables

See `.env.example` for the full, commented list. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_SQL_CONNECTIONSTRING` or `AZURE_SQL_SERVER`+`AZURE_SQL_DATABASE` | Yes | Database connection (one of three auth strategies) |
| `BACKEND_HOST`, `BACKEND_PORT`, `BACKEND_URL` | No | API bind/host settings |
| `CORS_ORIGINS` | No | Comma-separated origins, `*` for all |
| `CACHE_TTL_SECONDS` | No | In-memory response cache TTL (default 300) |
| `SCRAPE_FRESHNESS_HOURS` | No | Skip scraping content newer than this |
| `SCRAPY_CONCURRENT_REQUESTS`, `SCRAPY_DOWNLOAD_DELAY`, `SCRAPY_AUTOTHROTTLE_ENABLED`, `SCRAPY_PROXIES` | No | Scrapy throttling |
| `NEWS_API_KEY` | No | NewsAPI.org |
| `ENSEMBLEDATA_TOKEN` | No | TikTok/Instagram/Threads/Reddit/YouTube scraping |
| `GETHOOKEDAI_TOKEN` | No | GetHookd.ai ad library |
| `RESEND_API_KEY`, `RESEND_FROM_EMAIL` | No | OTP email delivery |
| `TEST_ACCOUNT_EMAIL`, `TEST_ACCOUNT_OTP` | No | Dev-only OTP bypass — **never set in production** |
| `DB_POOL_SIZE`, `DB_POOL_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE` | No | SQLAlchemy pool tuning |
| `CLUSTER_THRESHOLD`, `DEFAULT_N_CLUSTERS` | No | Niche clustering tuning |

---

## Testing

```bash
python -m pytest tests/
```

Tests cover the analytics engine, niche discovery, API routes, trend collector, ads-insight client, and per-platform scrape integration. No frontend unit tests yet.

---

## Roadmap — Planned Improvements

The items below are concrete, committed improvements derived from a full audit of the codebase. Each one names the problem, the fix, the expected impact, and a rough effort estimate so reviewers can judge priority and cost. Effort is calibrated for one engineer, uninterrupted.

> **Conventions for every "Prompt for Opus 4.7" below — read this first.**
>
> Before executing any of the prompts in this roadmap, the AI agent **must**:
>
> 1. Read [`.github/copilot-instructions.md`](.github/copilot-instructions.md) in full and follow the environment rules it documents — in particular, **always invoke Python via the full Anaconda path** (`& "C:\Users\MarianCraciun\anaconda3\python.exe" -m pytest tests/`) instead of `python` / `python3` / `py` / `.\.venv\Scripts\python.exe`, all of which are broken on this machine for the reasons documented there.
> 2. Honour the PowerShell 5.1 quirks listed in that file (`;` instead of `&&`, `& "path with spaces"` for executables, `git --no-pager`, pipe long output through `Select-Object -Last N`).
> 3. Treat the **2 failures + 23 errors** baseline in `tests/test_ads_insight.py`, `tests/test_trend_collector.py`, and `tests/test_all_sources.py` as pre-existing — only flag a regression if those counts change.
>
> Each prompt below assumes these conventions are already in effect; they are not repeated per-prompt.

### Tier 1 — Quick wins (≤ 1 day total, ship this week)

These are mechanical cleanups that eliminate drift, dead code, and minor supply-chain bloat. Low risk, high readability win.

#### 1.1 Remove the Streamlit legacy

- **Problem.** `requirements.txt` lists `streamlit` and the repo ships a `.streamlit/` directory, even though no Streamlit code exists in the tree — the UI is React-only. New contributors waste time wondering which dashboard is canonical; the package adds ~200 MB to every Docker image build.
- **Fix.** Remove `streamlit` from `requirements.txt`; delete `.streamlit/`; add both patterns to `.dockerignore`.
- **Impact.** ~200 MB smaller image, faster CI, no more ambiguity about the UI stack.
- **Effort.** 10 minutes.
- **Prompt for Opus 4.7.**
  > The project at the current working directory is a React + FastAPI app. The React frontend is canonical; Streamlit is legacy and must be fully removed. Do the following and then verify:
  > 1. Confirm with `grep -rn "streamlit" src/ tests/` that no Python code imports streamlit. If any import exists, stop and report it.
  > 2. Remove the `streamlit` line from `requirements.txt`.
  > 3. `git rm -r .streamlit/` if the directory exists.
  > 4. Add `.streamlit/` to `.dockerignore` and `.gitignore` as a defensive measure.
  > 5. Run `python -m pytest tests/` to verify nothing breaks.
  > 6. Stage the changes and print a summary diff. Do not commit.

#### 1.2 Delete empty and dead packages

- **Problem.** `src/utils/` is empty, `src/dashboard/` contains only `utils/__pycache__/`, and `frontend/src/pages/Home.tsx` is an unused duplicate of `Dashboard.tsx` (App.tsx only mounts `Dashboard`).
- **Fix.** `git rm -r src/utils src/dashboard frontend/src/pages/Home.tsx`. Verify no imports reference them (they don't) and run the test suite.
- **Impact.** Smaller surface area; no "which one do I edit" ambiguity.
- **Effort.** 15 minutes including test run.
- **Prompt for Opus 4.7.**
  > Dead-code cleanup in a Python/React monorepo. The goal is to remove three dead paths: `src/utils/`, `src/dashboard/`, and `frontend/src/pages/Home.tsx`.
  > 1. Prove each is dead. For `src/utils` and `src/dashboard`: run `grep -rn "from src.utils\|import src.utils\|from src.dashboard\|import src.dashboard" src/ tests/`. For `Home.tsx`: `grep -rn "Home" frontend/src --include="*.tsx" --include="*.ts"` and confirm no route or import uses it (only `Dashboard` is mounted in `frontend/src/App.tsx`).
  > 2. If any proof fails, STOP and report the surviving import — do not delete.
  > 3. Otherwise `git rm -r src/utils src/dashboard frontend/src/pages/Home.tsx`.
  > 4. Run `python -m pytest tests/` and `cd frontend && pnpm build` — both must succeed.
  > 5. Print a one-paragraph summary of what was removed and the test results.

#### 1.3 Purge local SQLite artefacts from the source tree

- **Problem.** `src/collector/trends.db` and `src/collector/trends_backup.db` are committed (or at least present in working copies) — left over from the pre-Azure SQLite era. They ship into Docker images and could contain stale scraped data.
- **Fix.** Delete the files, add `*.db` to `.gitignore` and `.dockerignore`, and add a one-line comment in `trend_collector.py` documenting that the project uses Azure SQL.
- **Impact.** Prevents accidental data leaks and confusion over which database is authoritative.
- **Effort.** 10 minutes.
- **Prompt for Opus 4.7.**
  > The project uses Azure SQL in production but the working copy contains leftover SQLite files. Purge them and prevent re-introduction.
  > 1. Confirm no code references them: `grep -rn "trends.db\|trends_backup.db\|sqlite" src/ tests/`. If any live code path depends on a local SQLite file, STOP and report it — the cleanup is unsafe.
  > 2. `rm -f src/collector/trends.db src/collector/trends_backup.db` (and `git rm` them if tracked — check with `git ls-files src/collector/`).
  > 3. Append `*.db` and `*.sqlite*` to both `.gitignore` and `.dockerignore`. Check for existing patterns first to avoid duplicates.
  > 4. Do NOT add comments to `trend_collector.py` — there's no ambiguity worth commenting on.
  > 5. Run `python -m pytest tests/` and report results.

#### 1.4 Single source of truth for `PLATFORM_WEIGHTS`

- **Problem.** The platform-weight dictionary is defined twice: [src/config.py](src/config.py) and [src/analytics/analytics_engine.py](src/analytics/analytics_engine.py). Changing weights in one place silently has no effect, which has already bitten us once (per git history).
- **Fix.** Delete the duplicate in `analytics_engine.py`; `from src.config import PLATFORM_WEIGHTS`. Same for `ALWAYS_INCLUDED_PLATFORMS`.
- **Impact.** Eliminates a class of silent config bugs.
- **Effort.** 15 minutes.
- **Prompt for Opus 4.7.**
  > Eliminate a duplicated constant between `src/config.py` and `src/analytics/analytics_engine.py`.
  > 1. Read both files. Identify every module-level constant that is defined in both (at minimum `PLATFORM_WEIGHTS` and `ALWAYS_INCLUDED_PLATFORMS`; there may be more — list them all before editing).
  > 2. For each duplicate: treat `src/config.py` as the canonical source. If the values differ, surface the diff and ASK before proceeding — do not silently pick one.
  > 3. Once values match, remove the duplicate from `analytics_engine.py` and replace with `from src.config import <NAME>`. Place the import at the top of the file, grouped with other project imports.
  > 4. Run `python -m pytest tests/test_analytics_engine.py -v` and confirm all tests still pass.
  > 5. Run `grep -rn "PLATFORM_WEIGHTS\s*=" src/` to verify only one definition remains.
  > 6. Report what was changed and the test outcome.

#### 1.5 Commit `pnpm-lock.yaml` and enforce frozen installs

- **Problem.** `frontend/pnpm-lock.yaml` is currently untracked (visible in `git status`). Builds are non-deterministic; two CI runs can install different transitive versions.
- **Fix.** `git add frontend/pnpm-lock.yaml`; update [Dockerfile.api](Dockerfile.api) to use `pnpm install --frozen-lockfile` instead of `pnpm install`.
- **Impact.** Reproducible builds; blocks "works on my machine" drift.
- **Effort.** 5 minutes.
- **Prompt for Opus 4.7.**
  > Make the frontend build reproducible.
  > 1. Check `git status` — confirm `frontend/pnpm-lock.yaml` is untracked. If it is already tracked, STOP and report.
  > 2. Check `.gitignore` for any entry that would ignore the lockfile (e.g. `pnpm-lock.yaml`, `*.yaml`). Remove the offending line if present — comment the removal.
  > 3. `git add frontend/pnpm-lock.yaml`.
  > 4. Edit `Dockerfile.api`: find the `pnpm install` line in the frontend build stage and replace with `pnpm install --frozen-lockfile`. Only change that one flag.
  > 5. Build the image with `docker build -f Dockerfile.api -t trends-research-test .` to verify the frozen install succeeds. If it fails, the lockfile is out of sync — report and do not commit.
  > 6. Print the final diff for review.

#### 1.6 Remove unused Python dependencies

- **Problem.** `requirements.txt` carries `matplotlib`, `plotly`, `beautifulsoup4`, and `textblob`. The frontend renders with Recharts, Scrapy parses HTML natively, and sentiment uses VADER. None of these packages are imported in `src/`.
- **Fix.** Confirm with `grep -r "import <pkg>" src/ tests/` per package, then remove from `requirements.txt` and rebuild the image.
- **Impact.** Smaller image, smaller attack surface, faster `pip install`.
- **Effort.** 30 minutes including verification.
- **Prompt for Opus 4.7.**
  > Remove unused Python dependencies from `requirements.txt`. Candidates: `matplotlib`, `plotly`, `beautifulsoup4` (and `bs4`), `textblob`.
  > 1. For EACH candidate, run the usage check with ALL known import forms — for `beautifulsoup4` that means checking for both `import bs4`, `from bs4`, and string references. Do: `grep -rn "import matplotlib\|from matplotlib\|import plotly\|from plotly\|import bs4\|from bs4\|import textblob\|from textblob" src/ tests/ scripts/ 2>/dev/null`.
  > 2. Also check Scrapy settings and pipelines — these can reference packages dynamically via string config.
  > 3. For any candidate with ZERO hits, remove it from `requirements.txt`. For any with hits, keep it and list the consumers in your report.
  > 4. Rebuild: `pip install -r requirements.txt` into a throwaway venv (`python -m venv /tmp/verify-venv && /tmp/verify-venv/bin/pip install -r requirements.txt`) to confirm the file still resolves.
  > 5. Run `python -m pytest tests/` against the main venv to confirm nothing breaks.
  > 6. Report: which packages were removed, which were kept with consumers named, and test results.

### Tier 2 — Correctness and safety (1–3 days)

These close real failure modes that will embarrass us in production. Ship before any external rollout.

#### 2.1 Fail-loudly guard on the OTP test-account bypass

- **Problem.** Setting `TEST_ACCOUNT_EMAIL` + `TEST_ACCOUNT_OTP` bypasses email verification entirely. There is no runtime check that refuses to apply this in production — an accidental env-var leak is an authentication bypass.
- **Fix.** In [src/api/main.py](src/api/main.py), on application startup: if `os.getenv("ENV", "dev") == "production"` and `TEST_ACCOUNT_EMAIL` is set, raise `RuntimeError` and abort boot. Also log a WARNING on every dev start when it is active.
- **Impact.** Eliminates a realistic auth-bypass vector; makes the feature safe to keep.
- **Effort.** 1 hour, including a test case.
- **Prompt for Opus 4.7.**
  > The FastAPI backend at `src/api/main.py` supports a dev-only OTP bypass via `TEST_ACCOUNT_EMAIL` + `TEST_ACCOUNT_OTP`. This must be blocked in production. Implement a fail-loud guard.
  > 1. Read `src/api/main.py` and locate the OTP verification logic (search for `TEST_ACCOUNT_EMAIL`). Understand how the bypass works before changing anything.
  > 2. Add a startup check. Use FastAPI's `@app.on_event("startup")` (or the equivalent lifespan handler if one already exists — use whatever the file uses). The check:
  >    - If `os.getenv("ENV", "").lower() in {"production", "prod"}` AND `os.getenv("TEST_ACCOUNT_EMAIL")` is non-empty → raise `RuntimeError("Refusing to start: TEST_ACCOUNT_EMAIL is set in a production environment.")`.
  >    - If `TEST_ACCOUNT_EMAIL` is set in any other environment → log a single `logger.warning(...)` stating that the OTP bypass is active and naming the email.
  > 3. Add `ENV=development` to `.env.example` with a comment explaining valid values.
  > 4. Add a pytest test in `tests/test_api.py` (or a new `tests/test_auth_guard.py`) that:
  >    - Sets `ENV=production` and `TEST_ACCOUNT_EMAIL=foo@bar.com` via `monkeypatch.setenv`, then asserts that app startup raises.
  >    - Sets `ENV=development` and the same email, asserts startup succeeds.
  > 5. Run `python -m pytest tests/` and confirm all tests pass. Report the diff and test output.

#### 2.2 Fail-loudly on missing GetHookd.ai module

- **Problem.** [src/api/main.py](src/api/main.py) wraps the GetHookd.ai import in a try/except, setting `HAS_GETHOOKEDAI = False` on failure. When the token is configured but the module fails to load, `/scrape_ads` and `/ads_insight` silently return empty — users see "no data" with no error.
- **Fix.** If `GETHOOKEDAI_TOKEN` is set, the import MUST succeed; on failure, raise at startup with a clear message. If the token is unset, continue with the graceful-degradation path.
- **Impact.** Converts a silent, hard-to-diagnose failure into a boot-time error with actionable context.
- **Effort.** 1 hour.
- **Prompt for Opus 4.7.**
  > `src/api/main.py` currently has an optional import pattern for `src/scrapers/gethookedai/ads_insight.py` that silently degrades if the import fails. Change the behaviour: graceful degradation only when the user has explicitly opted out (by not configuring the token). When the token IS configured, import failure must crash the app with a clear message.
  > 1. Read `src/api/main.py` and find the try/except around the `gethookedai` import. Note the exact pattern and the `HAS_GETHOOKEDAI` flag.
  > 2. Replace it with logic equivalent to:
  >    ```python
  >    GETHOOKEDAI_TOKEN = os.getenv("GETHOOKEDAI_TOKEN", "").strip()
  >    if GETHOOKEDAI_TOKEN:
  >        from src.scrapers.gethookedai import ads_insight  # no try/except
  >        HAS_GETHOOKEDAI = True
  >    else:
  >        ads_insight = None
  >        HAS_GETHOOKEDAI = False
  >        logger.info("GETHOOKEDAI_TOKEN not set — /scrape_ads and /ads_insight will return empty responses.")
  >    ```
  > 3. Leave the `HAS_GETHOOKEDAI` checks in the endpoints as-is (they handle the unset-token case correctly).
  > 4. Verify there is no other silent fallback in `src/scrapers/gethookedai/__init__.py` or `ads_insight.py` that would hide import errors.
  > 5. Run `python -m pytest tests/test_ads_insight.py tests/test_api.py -v` and confirm pass.
  > 6. Sanity-check boot: with `GETHOOKEDAI_TOKEN=test` in env, start the app briefly and confirm no silent degradation if imports work.

#### 2.3 Reconcile hardcoded niche seeds with database niches

- **Problem.** [src/niche/niche_discovery.py](src/niche/niche_discovery.py) hardcodes 5 niches with seed keywords; on startup, `_init_niches_table()` seeds them into the `niches` table. Users can edit niches via the `/niches` API, but the next seeding pass can overwrite their work. Ownership is ambiguous.
- **Fix.** Mark DB rows with an `is_seed BOOLEAN` column. Seeding only inserts rows where `is_seed = TRUE` and skips existing rows. User edits set `is_seed = FALSE`. Add a DB migration and matching admin endpoint to "reset to defaults."
- **Impact.** User customisation becomes durable; defaults stay recoverable.
- **Effort.** 3 hours (migration + seeding logic + endpoint + test).
- **Prompt for Opus 4.7.**
  > The `niches` table is seeded on startup from a Python dict in `src/niche/niche_discovery.py::NICHE_SEED_KEYWORDS`. Users can edit niches via REST endpoints, but the next startup can overwrite their edits. Make user edits durable by adding an ownership flag.
  > 1. Read `src/db/models.py` (find the `Niche` class), `src/niche/niche_discovery.py` (find `NICHE_SEED_KEYWORDS` and any `_init_niches_table` / seeding function), and every niche-related endpoint in `src/api/main.py` (search `@app.get.*niches\|@app.post.*niches\|@app.delete.*niches`).
  > 2. Add an `is_seed` column to the `Niche` ORM model: `is_seed = Column(Boolean, nullable=False, default=False, server_default=text("0"))`. Also add a matching idempotent migration step in `src/db/migrate.py` that does `ALTER TABLE niches ADD is_seed BIT NOT NULL CONSTRAINT DF_niches_is_seed DEFAULT 0` guarded by an existence check — match the T-SQL-compatible idempotent pattern already used in that file.
  > 3. Update the seeding logic: on startup, for each `(niche, keyword)` pair in `NICHE_SEED_KEYWORDS`, INSERT only if no row with that (niche, keyword) already exists, and set `is_seed=True` on inserted rows. Never UPDATE existing rows.
  > 4. In the POST/PUT endpoints that create or modify niches, set `is_seed=False` on the new/updated row.
  > 5. Add a new endpoint `POST /admin/niches/reset_defaults` (admin-only, same auth dependency used by other admin endpoints) that deletes all rows where `is_seed=True` and re-runs the seeder. Do NOT touch user-created rows.
  > 6. Add a test in `tests/test_niche_discovery.py` proving: (a) seeding twice is idempotent; (b) a user-created niche survives a re-seed; (c) reset_defaults restores seed rows without touching user rows.
  > 7. Run the full suite. Report the migration step, new endpoint path, and test outcomes.

#### 2.4 Multi-worker cache coherence

- **Problem.** Response cache is an in-memory `_cache` dict in [src/api/main.py](src/api/main.py). [Dockerfile.api](Dockerfile.api) runs Gunicorn with `--workers 2`, so each worker has its own copy. Users see two different stale versions depending on which worker serves them.
- **Fix (short-term).** Until Redis (Tier 3) lands, drop `--workers 2` to `--workers 1` in production and document the single-worker requirement in the README's Docker section.
- **Fix (proper, Tier 3).** Back the cache with Redis — see item 3.1.
- **Impact.** Removes visible flicker between stale states during demos and in production.
- **Effort.** 5 minutes for the short-term; see 3.1 for the proper fix.
- **Prompt for Opus 4.7.**
  > Short-term fix only (the Redis-backed cache lands in a separate task). The app has a per-process in-memory response cache that is incoherent across Gunicorn workers. Drop to a single worker until Redis ships.
  > 1. Edit `Dockerfile.api`: find the `gunicorn` CMD line and change `--workers 2` to `--workers 1`. Keep `--timeout 120` and the worker class.
  > 2. Add a comment above the line: `# TODO: restore --workers >1 once the response cache is backed by Redis (see README Roadmap 3.1).`
  > 3. Update the Docker section of `README.md` to note "The in-memory response cache requires `--workers 1` until Redis is introduced. Do not raise worker count without first completing Roadmap item 3.1."
  > 4. Rebuild the image to confirm the CMD still parses: `docker build -f Dockerfile.api -t trends-research-test .`
  > 5. Report the diff.

#### 2.5 Split the monolithic API file into routers

- **Problem.** [src/api/main.py](src/api/main.py) is 1,446 lines covering auth, niches, trends, content, ads, admin, and background jobs. Merge conflicts concentrate here; onboarding is slow.
- **Fix.** Create `src/api/routes/` with one `APIRouter` per concern: `auth.py`, `trends.py`, `content.py`, `ads.py`, `niches.py`, `scrape.py`, `admin.py`. `main.py` becomes ~100 lines of app wiring and startup hooks. No logic changes.
- **Impact.** Dramatically lower diff noise; easier parallel work.
- **Effort.** 1 day, purely mechanical.
- **Prompt for Opus 4.7.**
  > Refactor the 1,446-line `src/api/main.py` into FastAPI routers. This is a PURE refactor — no behavioural changes, no new features, no new error handling. Every endpoint must remain at the exact same path with the exact same signature.
  > 1. Create `src/api/routes/__init__.py` and one file per concern: `auth.py`, `niches.py`, `trends.py`, `content.py`, `ads.py`, `scrape.py`, `admin.py`. Each file defines `router = APIRouter()` with the matching prefix and tags.
  > 2. Move endpoints by concern:
  >    - `auth.py`: `/auth/*` routes
  >    - `niches.py`: `/niches`, `/niche_keywords/*`, `/niches/*/keywords`, `/niches/*/keywords/*`
  >    - `trends.py`: `/trends`, `/all_trends`, `/trending_now`, `/youtube_trends`, `/reddit_trends`, `/hackernews_trends`, `/news_trends`
  >    - `content.py`: `/youtube_videos`, `/tiktok_videos`, `/instagram_posts`, `/reddit_posts`, `/threads_posts`
  >    - `ads.py`: `/ads_insight`, `/search_brands`
  >    - `scrape.py`: `/scrape`, `/scrape_ads`, `/scrape_brand_ads`, `/scrape_errors` (both GET and DELETE)
  >    - `admin.py`: `/admin/*`
  > 3. Move any helper functions used by only one router into that router's module. Anything shared goes into a new `src/api/dependencies.py` (auth dependency, cache helper, `_JSONEncoder`, DB session getter).
  > 4. Reduce `main.py` to: app construction, middleware, startup/shutdown hooks, `app.include_router(...)` for each router, and the root `/` handler.
  > 5. Preserve the in-memory cache: if multiple routers share `_cache`, move it into `src/api/dependencies.py` as a module-level singleton and import from there. No Redis yet.
  > 6. Run `python -m pytest tests/` — ALL tests must pass with zero modifications.
  > 7. Start the server and hit `/docs`. Confirm the OpenAPI page lists every endpoint that existed before, under sensible tag groupings.
  > 8. Report: old line count vs new `main.py` line count, per-file line counts, and test output.

#### 2.6 Pydantic response models for every endpoint

- **Problem.** The custom `_JSONEncoder` for numpy/pandas/datetime in `main.py` handles common cases but fails unpredictably on edge cases (e.g., `NaN` nested in dicts, circular refs). There's no OpenAPI schema for responses.
- **Fix.** Define `response_model=` on every route with a Pydantic model. Keep the encoder as a belt-and-braces fallback but log when it triggers.
- **Impact.** Frontend gets proper typing; bugs surface in tests rather than in the UI; OpenAPI docs become authoritative.
- **Effort.** 1 day (mostly mechanical; ~40 endpoints).
- **Prompt for Opus 4.7.**
  > Add Pydantic response models to every FastAPI endpoint in `src/api/` (assume the router split in Roadmap 2.5 has already been done; if not, do that FIRST or work in `main.py` directly).
  > 1. Create `src/api/schemas/` with submodules mirroring the router split: `trends.py`, `content.py`, `ads.py`, `niches.py`, `auth.py`, `admin.py`, `scrape.py`. Add `__init__.py` that re-exports the public models.
  > 2. For each endpoint, read the current code to determine the return shape (it will be a dict, list of dicts, or DataFrame-to-dict-records). Derive a Pydantic v2 `BaseModel`. For list endpoints, model the row type and use `list[RowModel]` as the response.
  > 3. Match the shape of `frontend/src/lib/api.ts` interfaces (`TrendRow`, `ContentRow`, `AdsInsightRow`, `TokenUsageRow`) byte-for-byte — field names, types, optionality. Flag any mismatch between backend output and frontend interface as a bug in the report; do NOT silently change either side.
  > 4. On each route decorator, add `response_model=<Model>`. For endpoints that currently return raw DataFrames, convert with `df.to_dict(orient="records")` first and wrap in the model.
  > 5. Keep `_JSONEncoder` as a fallback for Starlette's default encoder but wrap its overrides in a `logger.warning` so we can track where non-Pydantic data still flows.
  > 6. Run `python -m pytest tests/` and `cd frontend && pnpm build`. Both must succeed. Fix any assertion in tests that relied on fields Pydantic coerced (e.g. `None` vs missing key).
  > 7. Open `/docs` and confirm every endpoint now shows a response schema.
  > 8. Report: number of endpoints covered, list of frontend/backend contract mismatches found, test results.

### Tier 3 — Architectural initiatives (1–2 weeks)

These are the investments that unlock durability and production operability. The scope is deliberately tuned for an **internal research tool** (5–20 users, no external SLA) — Redis has been intentionally scoped out; Azure SQL is re-used as the backing store for everything.

#### 3.1 Redis — intentionally deferred

- **Decision (2026-04-22).** Not shipping. This is an internal research tool with low, predictable user count. The three things Redis would have solved are all addressable without it:
  1. **Response cache coherence** — already mitigated by `--workers 1` (Roadmap 2.4). At internal-tool traffic levels, identical requests rarely hit within the cache TTL anyway; the cache is a minor optimisation.
  2. **OTP storage** — stays in the `otp_codes` DB table, which already has a 10-minute TTL enforced by a cleanup pass. No hot path.
  3. **Job queue backing store** — moved to Azure SQL (see 3.2).
- **Cost avoided.** ~$200/year (Azure Cache for Redis Basic C0) plus the operational burden of one more managed service.
- **When to revisit.** If any of the following become true, re-open this ticket: (a) we need > 1 Gunicorn worker for real throughput reasons, (b) login traffic exceeds ~1 OTP/sec sustained, (c) we expose the tool externally with an SLA, or (d) we need durable rate-limiting across instances.
- **No prompt — nothing to implement.**

#### 3.2 Durable job queue on Azure SQL (no Redis)

- **Problem.** Scrape jobs run via FastAPI `BackgroundTasks`, which die with the worker. If the API restarts mid-scrape (deploy, OOM, Azure maintenance), the job is lost with no resume path. There is also no endpoint to poll job status — `POST /scrape` returns an ID that's effectively opaque.
- **Fix.** Use Azure SQL as the queue backend. A `scrape_jobs` table holds the work; a separate worker process polls for `status='queued'` rows using `UPDATE ... WITH (READPAST, UPDLOCK, ROWLOCK)` for safe multi-worker concurrency. Add `GET /scrape/{job_id}` for status polling and a progress widget in the frontend.
- **Why not Redis/RQ/Celery.** For an internal tool with a handful of concurrent scrapes per hour, MSSQL polling adds ~100 ms of latency but saves us a dependency we'd otherwise have to run, monitor, and pay for. Azure SQL is already paid and monitored.
- **Impact.** Users see scrape progress in the UI; jobs survive restarts; no new infrastructure.
- **Effort.** 3–4 days including frontend integration.
- **Prompt for Opus 4.7.**
  > Replace FastAPI `BackgroundTasks` with a durable job queue backed by Azure SQL (no Redis). This is an internal research tool; MSSQL polling is the intended design, not a workaround.
  > 1. Create a `scrape_jobs` ORM model in `src/db/models.py`:
  >    - `id` (UUID PK, server default `NEWID()`)
  >    - `kind` (nvarchar(50): `scrape`, `scrape_ads`, `scrape_brand_ads`)
  >    - `payload` (nvarchar(max), JSON — the request body)
  >    - `status` (nvarchar(20): `queued`, `running`, `success`, `failed`)
  >    - `progress_pct` (int, default 0)
  >    - `error` (nvarchar(max), nullable)
  >    - `created_at` (datetime2, default `SYSUTCDATETIME()`)
  >    - `started_at`, `finished_at` (datetime2, nullable)
  >    - `worker_id` (nvarchar(100), nullable — which worker claimed the job, for observability)
  >    - `heartbeat_at` (datetime2, nullable — last time the worker confirmed it was still alive)
  >    - Index on `(status, created_at)` for the dequeue query.
  >  Add the idempotent migration to `src/db/migrate.py` (or Alembic if 3.3 has shipped).
  > 2. Create `src/jobs/__init__.py` and `src/jobs/queue.py` with two functions:
  >    - `enqueue(session, kind: str, payload: dict) -> UUID` — inserts a `scrape_jobs` row with `status='queued'` and returns the id.
  >    - `claim_next(session, worker_id: str) -> ScrapeJob | None` — atomically picks the oldest queued row. Use a single UPDATE with OUTPUT clause to avoid a TOCTOU race:
  >      ```sql
  >      WITH cte AS (
  >          SELECT TOP (1) * FROM scrape_jobs WITH (READPAST, UPDLOCK, ROWLOCK)
  >          WHERE status = 'queued' ORDER BY created_at
  >      )
  >      UPDATE cte SET status='running', started_at=SYSUTCDATETIME(),
  >                     worker_id=:worker_id, heartbeat_at=SYSUTCDATETIME()
  >      OUTPUT inserted.*;
  >      ```
  >      This pattern is safe under concurrent workers — `READPAST` skips locked rows so workers don't block each other.
  > 3. Create `src/jobs/worker.py` with a dispatch table: `{"scrape": run_scrape, "scrape_ads": run_scrape_ads, "scrape_brand_ads": run_scrape_brand_ads}`. Each handler: loads the `scrape_jobs` row, invokes the existing scraper function (do NOT rewrite scraper logic), updates `progress_pct` at sensible checkpoints via a short-lived session (commit each update), on success sets `status='success'` + `finished_at`, on exception sets `status='failed'` + error text + `finished_at`.
  > 4. Create `src/jobs/entrypoint.py` — a CLI that runs a poll loop: every 2 seconds, call `claim_next`. If a job was claimed, dispatch it. While running, update `heartbeat_at` every 30s. On SIGTERM, stop claiming new jobs; finish the current one if possible. Exit cleanly.
  > 5. Add a "reaper" path: on worker startup, run `UPDATE scrape_jobs SET status='failed', error='worker died' WHERE status='running' AND heartbeat_at < DATEADD(minute, -5, SYSUTCDATETIME())`. This recovers jobs whose worker crashed.
  > 6. Modify `/scrape`, `/scrape_ads`, `/scrape_brand_ads` endpoints in `src/api/routes/scrape.py` (or `main.py` if 2.5 not done): replace the `BackgroundTask` with a call to `enqueue(...)`. Return `{job_id, status: "queued"}`.
  > 7. Add `GET /scrape/{job_id}` returning the full job row as a Pydantic model (reuse `ScrapeJob` from 2.6 if done). Auth: same dependency as `POST /scrape`.
  > 8. Add a `worker` service to `docker-compose.yml` using the same image as `app` but with `command: python -m src.jobs.entrypoint`. `depends_on: [app]` with `condition: service_started`. Same env as `app` (DB credentials).
  > 9. Frontend work in `frontend/src/`:
  >    - `lib/api.ts`: add `ScrapeJob` interface + `getScrapeJob(id)` + `useScrapeJob(id)` hook that polls every 2s and stops on terminal states.
  >    - After `POST /scrape`, keep the returned `job_id` in page state.
  >    - Render a compact `<Progress>` (shadcn) with the percentage, a status badge, and elapsed time below the scrape button.
  >    - Add a small "Recent Jobs" table on the Settings page (last 20 jobs, refresh every 5s while visible).
  > 10. Tests:
  >    - `tests/test_jobs_queue.py`: enqueue + claim_next with two workers in threads → assert each claims a different row, no double-claim (use a short-lived SQLite MSSQL-compatible harness OR mark as integration and require a live MSSQL).
  >    - API test: `POST /scrape` then `GET /scrape/{id}` returns the queued row.
  >    - Frontend Vitest: the polling hook stops on `success` and `failed`.
  > 11. Manual verification: `docker compose up --build`. Trigger a small scrape. Watch progress update in the UI. Kill the worker container with `docker kill`. Wait 6 minutes. Restart the worker. Confirm the reaper marks the abandoned job as `failed` with `error='worker died'`.
  > 12. Report: schema, dispatch flow, reaper behaviour, test results, screenshots of the progress UI.

#### 3.3 Alembic-based migrations

- **Problem.** Schema today is managed by two ad-hoc scripts (`setup_azure.py` and `migrate.py`) that only know how to create things. There's no version table, no downgrade, no diff — and no way to know whether a deployed database matches the code.
- **Fix.** Adopt Alembic. Generate an initial revision from the current models, then use `autogenerate` for future changes. Run `alembic upgrade head` at container boot and fail fast if migrations error. Keep `doctor.py` — it's orthogonal.
- **Impact.** Production-grade schema management; safe rollbacks; clear drift detection.
- **Effort.** 3 days.
- **Prompt for Opus 4.7.**
  > Replace the hand-rolled `src/db/migrate.py` + `src/db/setup_azure.py` schema management with Alembic. This is invasive — read carefully before touching anything.
  > 1. Add `alembic` to `requirements.txt`.
  > 2. `alembic init -t async migrations/` at the repo root (use the sync template if the project's SQLAlchemy usage is sync — check `src/db/connection.py` first).
  > 3. Configure `migrations/env.py` to:
  >    - Import `Base` from `src.db.models` and set `target_metadata = Base.metadata`.
  >    - Read the DB URL via the existing connection-building logic in `src/db/connection.py` — do NOT duplicate it. Call whatever helper constructs the URL. Fail fast if the URL cannot be resolved.
  >    - Use the `mssql` dialect compare_type and compare_server_default settings so autogenerate handles SQL Server types correctly.
  > 4. Baseline: run `alembic revision --autogenerate -m "baseline"` against a database that is already at the current schema (created by the legacy `setup_azure.py`). Inspect the generated revision — it should be empty or contain only safe cosmetic fixes. If it wants to drop/create real tables, STOP and reconcile the model vs DB drift before proceeding.
  > 5. Create a second revision that is purely `pass` in both `upgrade()` and `downgrade()` but stamps `alembic_version` — this is the anchor for fresh DBs.
  > 6. Modify application startup in `src/api/main.py`: on boot, run `alembic upgrade head` programmatically (via `alembic.config.Config` + `command.upgrade`). If it errors, raise and abort startup.
  > 7. Modify `src/db/setup_azure.py` to be a thin wrapper that calls `alembic upgrade head`. Keep the filename for backward compat with docs.
  > 8. Delete the contents of `src/db/migrate.py` and replace with a thin wrapper calling `alembic upgrade head`. Keep the `/admin/azure/migrate` endpoint wired to this wrapper.
  > 9. Keep `src/db/doctor.py` untouched — it diagnoses connectivity, not schema.
  > 10. Update the README Quick Start: step 3 becomes `alembic upgrade head` (or the wrapper). Update the Roadmap to tick 3.3 complete.
  > 11. Test: fresh DB → `alembic upgrade head` → all tables present with correct indexes. Run full pytest suite. Manually verify `/admin/azure/status` still reports row counts.
  > 12. Report any drift reconciled in step 4 — this is the most common place real bugs hide.

#### 3.4 Structured logging with request correlation

- **Problem.** Logs today are `print`-based and free-form. Tracing a single scrape request through the API → collector → scraper → DB is impractical.
- **Fix.** Adopt `structlog` with a JSON renderer in production. Middleware assigns a `request_id` (UUID4) per HTTP request and propagates it into background tasks. Log entries carry `request_id`, `user_id`, `endpoint`, `duration_ms`.
- **Impact.** Debuggable production; usable Azure Log Analytics queries.
- **Effort.** 2 days.
- **Prompt for Opus 4.7.**
  > Introduce structured logging with request correlation across the full backend.
  > 1. Add `structlog` to `requirements.txt`.
  > 2. Create `src/logging_config.py` with `configure_logging(env: str)`. In `production`, render JSON (`structlog.processors.JSONRenderer`). In `development`, render `ConsoleRenderer(colors=True)`. Always include timestamp, level, logger name, event. Configure stdlib `logging` to route through structlog so third-party libraries (SQLAlchemy, Scrapy, urllib3) are captured too.
  > 3. Call `configure_logging(os.getenv("ENV", "development"))` at the top of `src/api/main.py` and `src/jobs/entrypoint.py` (if 3.2 is done).
  > 4. Add a FastAPI middleware that:
  >    - On request: generates `request_id = uuid4().hex`, reads `X-Request-ID` if present and uses that instead.
  >    - Binds `request_id`, `method`, `path`, and `user_id` (from auth dep if available, else None) to `structlog.contextvars` via `bind_contextvars`.
  >    - On response: logs `request.finished` with `status_code` and `duration_ms`.
  >    - On exception: logs `request.failed` with exception info.
  >    - Sets `X-Request-ID` on the response.
  > 5. When enqueueing RQ jobs (Roadmap 3.2), pass the current `request_id` into the job payload. The job's entry function should `bind_contextvars(request_id=..., job_id=...)` before calling scraper code.
  > 6. Replace every `print(` in `src/` with `logger.info(` / `logger.warning(` / `logger.error(` as appropriate. Use `grep -rn "print(" src/` to find them — audit every match; `print()` for CLI scripts like `doctor.py` can stay (those are user-facing tools, not services).
  > 7. Log levels policy: INFO for normal lifecycle (app started, scrape queued, scrape succeeded), WARNING for recoverable surprises (cache miss on expected key, rate-limited retry), ERROR for failures that need attention, DEBUG for high-volume diagnostic detail.
  > 8. Add a test that exercises one endpoint and asserts the resulting log record contains request_id, path, status, duration_ms (use `structlog.testing.capture_logs`).
  > 9. Update the README's Deployment section with a short note on the `X-Request-ID` contract and the JSON log format.
  > 10. Report: number of `print` calls replaced, new dependencies, example log record from a test run.

#### 3.5 Frontend test coverage

- **Problem.** Zero frontend tests. Pages call API endpoints whose names are strings; a backend rename silently breaks a page until someone clicks through.
- **Fix.**
  1. Vitest + React Testing Library for unit tests on the API client (`frontend/src/lib/api.ts`) and every custom hook (`useApi`, `useLazyApi`, `useComposition`).
  2. One Playwright E2E that boots the stack against a seeded test DB and walks through: login with test OTP → trigger a small scrape → view trends → open Trend Explorer → export a report.
- **Impact.** Catches the most common regression class (API contract drift) in CI instead of on the demo screen.
- **Effort.** 1 week including CI wiring.
- **Prompt for Opus 4.7.**
  > Add frontend test coverage to a Vite + React 19 + TypeScript project at `frontend/`. The app uses Wouter, Axios, shadcn/ui, and custom hooks in `frontend/src/hooks/`.
  > 1. Install dev deps with pnpm: `vitest`, `@vitest/ui`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`, `msw` (Mock Service Worker). Versions compatible with React 19.
  > 2. Add Vitest config to `vite.config.ts` (or a `vitest.config.ts`): `test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], globals: true }`. Add path alias to match the existing Vite alias.
  > 3. Create `frontend/src/test/setup.ts` with `import "@testing-library/jest-dom/vitest"` and MSW `server.listen()` / `server.close()` lifecycle.
  > 4. Create `frontend/src/test/mocks/handlers.ts` with MSW handlers covering every endpoint used in `frontend/src/lib/api.ts`. Keep these aligned with the Pydantic response models from Roadmap 2.6 — if the shapes diverge later, tests break first.
  > 5. Unit tests:
  >    - `frontend/src/lib/api.test.ts`: one test per exported function asserting the URL, method, query params, and return shape using MSW.
  >    - `frontend/src/hooks/useApi.test.tsx`: loading state, success state, error state, re-fetch on key change.
  >    - `frontend/src/hooks/useLazyApi.test.tsx`, `useComposition.test.tsx`: same pattern.
  > 6. Component smoke tests for each page (`Dashboard`, `TrendExplorer`, `ResearchProjects`, `Reports`, `SavedViews`, `Alerts`, `Settings`): render with MSW-mocked API, assert the key data element is visible. Do not snapshot-test the whole tree — brittle.
  > 7. Playwright E2E (separate `frontend/e2e/` folder, `@playwright/test`):
  >    - One scenario named `happy-path.spec.ts` that: logs in with the TEST_ACCOUNT OTP, triggers a minimal scrape (mock the backend if needed), navigates to Trend Explorer, verifies at least one row in the trends table.
  >    - Config: targets `http://localhost:5173` when `pnpm dev` is running. Playwright's `webServer` option auto-starts it.
  > 8. Update `frontend/package.json` scripts: `"test": "vitest"`, `"test:ui": "vitest --ui"`, `"test:e2e": "playwright test"`.
  > 9. Add a CI workflow (`.github/workflows/frontend-tests.yml`) running `pnpm install --frozen-lockfile`, `pnpm test --run`, `pnpm test:e2e` on PRs touching `frontend/**`.
  > 10. Report: files added, count of tests, CI passing, and any API contract mismatches discovered between frontend types and backend behaviour.

#### 3.6 Local-dev MSSQL via Docker

- **Problem.** New contributors need Azure SQL credentials just to run the stack. Onboarding time is measured in days.
- **Fix.** Add `docker-compose.override.yml` with `mcr.microsoft.com/mssql/server:2022-latest`, an init script that runs `setup_azure.py`, and a documented `DEV_DB_CONNECTIONSTRING`. The doctor tool already handles both.
- **Impact.** Onboarding drops to `docker compose up`; demos can run offline.
- **Effort.** 1 day.
- **Prompt for Opus 4.7.**
  > Make local development possible without Azure SQL credentials by adding a dockerised MSSQL instance. Do not change the default production flow — the override file must be opt-in.
  > 1. Create `docker-compose.override.yml` at the repo root. Docker Compose picks this up automatically when running locally but it is NOT used in CI/production.
  > 2. Add a `mssql` service using `mcr.microsoft.com/mssql/server:2022-latest`:
  >    - Env: `ACCEPT_EULA=Y`, `MSSQL_SA_PASSWORD=YourStrong!Passw0rd` (document this is a dev-only value), `MSSQL_PID=Developer`.
  >    - Port: `1433:1433` on localhost only.
  >    - Volume: named volume `mssql-data` for `/var/opt/mssql`.
  >    - Healthcheck: `/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $$MSSQL_SA_PASSWORD -C -Q 'SELECT 1'` (note the escaped `$$`). Interval 10s, retries 10.
  > 3. Add an `mssql-init` service (image `mcr.microsoft.com/mssql-tools`) that depends on `mssql` healthy and runs a script creating the `TrendsDev` database and a `trends_user` with password.
  > 4. Override the `app` service in the same file to:
  >    - depend_on `mssql-init` with `condition: service_completed_successfully`.
  >    - inject env `AZURE_SQL_SERVER=mssql`, `AZURE_SQL_DATABASE=TrendsDev`, `AZURE_SQL_USER=trends_user`, `AZURE_SQL_PASS=<dev password>`.
  > 5. Add a `frontend/.env.development.local.example` with `VITE_API_URL=http://localhost:8000` (document copying to `.env.development.local`).
  > 6. Update the README Quick Start with a new section "Option 2: Local-only with Docker MSSQL" explaining `docker compose up` is now enough. Call out that this uses a local MSSQL dev container and is NOT for production.
  > 7. Verify: `docker compose down -v && docker compose up --build`. The stack must come up without any Azure credentials and `/admin/azure/status` must return non-empty tables after `alembic upgrade head` (Roadmap 3.3) or the legacy setup runs.
  > 8. Ensure `docker-compose.override.yml` is in `.gitignore`... actually NO — commit it. The override is the intended dev experience. But add a comment at the top stating it is dev-only.
  > 9. Report: start time from `docker compose up` to `/admin/azure/status` returning 200, any quirks of the SQL Server Linux image on Windows/macOS hosts (memory limits, arm64 caveats).

### Tier 4 — Observability and polish (nice-to-have)

#### 4.1 Response-time metrics (Prometheus + Grafana)

- Expose latency, request count, and status-code histograms per endpoint.
- **Prompt for Opus 4.7.**
  > Add Prometheus metrics to the FastAPI app.
  > 1. Add `prometheus-fastapi-instrumentator` to `requirements.txt`.
  > 2. In `src/api/main.py` (or wherever the app is constructed after Roadmap 2.5), `Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)`.
  > 3. Ensure `/metrics` is NOT behind auth and NOT cached. Add a firewall note in README.
  > 4. Add a `prometheus` service and a `grafana` service to `docker-compose.override.yml`. Provision a default dashboard (JSON file in `infra/grafana/dashboards/`) with panels for p50/p95/p99 latency per route and error rate.
  > 5. Add a test that `/metrics` returns text-format metrics including `http_requests_total`.

#### 4.2 Type-safe frontend routing

- Replace Wouter string paths with a typed route registry.
- **Prompt for Opus 4.7.**
  > The frontend uses Wouter with stringly-typed routes in `frontend/src/App.tsx`. Replace with a typed registry so `navigate("/explorerr")` becomes a compile error.
  > 1. Keep Wouter (don't migrate to a new router). Add `frontend/src/lib/routes.ts` exporting a `const routes = { home: "/", explorer: "/explorer", ... } as const;` and a `type RouteKey = keyof typeof routes;`.
  > 2. Add a typed `navigate(key: RouteKey, params?: Record<string, string>)` helper.
  > 3. Replace all `<Link href="/...">` and `useLocation()[1]("/...")` calls to use the helper / the `routes` object. Use `grep -rn "href=\"/\|setLocation(\"/" frontend/src` to find them.
  > 4. Run `pnpm build` — the TypeScript compiler must catch any stray string.

#### 4.3 Expanded health endpoint

- Move health to `/healthz`; check DB and API-key presence.
- **Prompt for Opus 4.7.**
  > The current `/` handler serves the React index and doubles as a health check. Split responsibilities.
  > 1. Add `GET /healthz` returning `{status: "ok"|"degraded"|"unhealthy", checks: {...}}`. Checks: `db` (run `SELECT 1`), `worker` (is there a `scrape_jobs` row with `heartbeat_at` within the last 2 minutes — if 3.2 is merged), `gethookedai_token` (presence-only, no outbound call), `ensembledata_token` (same), `news_api_key` (same). A `degraded` status (non-critical check fails) still returns 200; `unhealthy` returns 503.
  > 2. Add `GET /readyz` returning 200 only when DB migrations have run (read `alembic_version` table if 3.3 merged).
  > 3. Update the Docker healthcheck in `docker-compose.yml` to hit `/healthz` instead of `/`.
  > 4. Leave `/` serving the React app unchanged.
  > 5. Add tests that each check fails independently and the aggregate status reflects the worst check.

#### 4.4 Scraper uptime dashboard

- Track `/scrape` success rate per platform; alert on regression before users notice.
- **Prompt for Opus 4.7.**
  > Build a scraper-health dashboard so we catch platform regressions (Google Trends breaks often) before users do.
  > 1. Extend the `scrape_jobs` table (Roadmap 3.2) with `platform` (str) and `item_count` (int) columns + migration.
  > 2. Populate them from the worker: each scraper reports the platform it hit and how many rows it produced.
  > 3. New endpoint `GET /admin/scraper_health?days=7` returning per-platform rolling stats: success rate, median item_count, p95 duration, error breakdown grouped by error message.
  > 4. Add a new frontend page `ScraperHealth.tsx` at `/health` (admin-only) rendering the data as a table with a 7-day sparkline per platform using Recharts.
  > 5. Emit a structured-log WARN when success rate for any platform drops below 80% over a rolling 24h window. This log event can later feed an alertmanager rule.
  > 6. Add a test that covers 2 successful + 1 failed job and asserts the resulting stats.

### Progress log

Status as of 2026-04-22, demo target 2026-04-24.

- [x] **Tier 1 — Quick wins (1.1–1.6)** — shipped
- [x] **Tier 2.1** — OTP test-account production guard
- [x] **Tier 2.2** — GetHookd.ai fail-loud imports
- [x] **Tier 2.3** — Niche seed reconciliation
- [x] **Tier 2.4 (short-term)** — Gunicorn `--workers 1` until a proper cache backend is in place
- [x] **Tier 2.5** — API split into routers
- [x] **Tier 2.6** — Pydantic response models
- [x] **Tier 3.1** — decision recorded: **not shipping Redis** (internal tool; cost and complexity not justified)
- [ ] 3.2 Azure-SQL-backed job queue — next up after the demo; unblocks visible scrape progress in the UI
- [ ] 3.3 Alembic migrations
- [ ] 3.4 Structured logging with request correlation
- [ ] 3.5 Frontend test coverage
- [ ] 3.6 Local-dev MSSQL via Docker
- [ ] Tier 4 items (observability + polish)

### Demo-day checklist (remaining)

- [ ] Seed the demo database with 2–3 niches' worth of fresh scraped data the night before, so nothing demo-critical depends on a live scrape
- [ ] Verify every linked endpoint in the README renders at `/docs` without 500s
- [ ] Walk the demo path end-to-end once, from login through Trend Explorer to Reports, so the muscle memory is fresh

---

## License

Private repository — Global Brother SRL. See `LICENSE.txt` (Business Source License 1.1).
