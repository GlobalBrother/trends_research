# Trends Collection Redesign — Multi-Provider Resilient Pipeline

**Date:** 2026-04-23
**Status:** Approved design, ready for implementation planning
**Primary target:** Google Trends (extensible pattern for other sources later)

## 1. Summary

Replace the current Scrapy-only Google Trends collection path with a **multi-provider resilient pipeline**. Rather than anointing a single vendor, we treat providers as **interchangeable adapters** behind one Protocol and configure an **ordered chain** at runtime. The recommended default chain mixes provider categories so we are never single-vendor-dependent:

- **Tier 1 — Paid SERP-style APIs (primary, full 4-widget Explore parity):**
  - **SerpAPI** (`engine=google_trends`) — mature, predictable JSON shape, fixed-plan pricing.
  - **SearchAPI.io** (`engine=google_trends`) — near-identical shape to SerpAPI, ~30–50% cheaper, used as paid-tier failover so we are not locked to one vendor.
- **Tier 2 — Paid scraping-infrastructure APIs (fallback, also full Explore):**
  - **Bright Data SERP API** *or* **Oxylabs SERP Scraper API** — pay-per-success Google Trends endpoints. Pick whichever you already have a contract with; they are interchangeable in the chain.
- **Tier 3 — Managed actor (bulk / warmup, latency-tolerant):**
  - **Apify `google-trends-scraper` actor** — pay per compute unit; ideal for scheduled warmup where the user is not waiting.
- **Tier 4 — Last-resort, free/in-house:**
  - The existing **Scrapy spider** (kept as `LegacyScrapyProvider`), optionally augmented by **pytrends** in the same provider for a second free path.
- **Side-channel (free, scheduled-only seed data, not Explore):**
  - **Google Trends BigQuery public dataset** — used by `WarmupJob` to discover *which* keywords are surging in each geo before we spend Tier-1 budget on Explore widgets.

Any subset of the above can be enabled per environment via `TRENDS_PROVIDER_CHAIN`; the router doesn't care how many providers there are, only that each implements the `TrendsProvider` Protocol. We deliberately ship with **at least two paid providers in the chain at all times** so a single-vendor outage or pricing change never blacks out collection.

Jobs run on an **arq + Redis** queue so they survive restarts, scale beyond the single gunicorn worker, and can stream partial results to the frontend via **Server-Sent Events (SSE)**. A nightly scheduled **warmup job** refreshes the top N keywords per geo so the dashboard is never empty on first paint.

The design preserves the existing DB schema and `save_trend()` ingestion helper; the only changes are **additive columns** for provider/cost attribution and a normalization layer that maps each provider's response shape to the same four canonical `data_type` rows the rest of the system already consumes (`interest_over_time`, `interest_by_region`, `related_queries`, `related_topics`).

## 2. Goals & Non-Goals

**Goals**
- Eliminate 429 rate-limit blackouts on the user-triggered hot path.
- Cut total failure rate of Google Trends collection below 1% per burst.
- Keep median burst-completion latency under 5 minutes for a 250-keyword burst (all four widgets per keyword).
- Stream per-keyword results to the UI as they complete.
- Track per-provider spend against a monthly budget; auto-pause if exceeded.
- Keep monthly Trends-related paid spend at or below **$150/mo** at the 30k-request target.

**Non-goals**
- Replacing EnsembleData (YouTube/TikTok/IG/Reddit/Threads) — out of scope.
- Replacing the GetHookd.ai ad library integration — out of scope.
- Changing the downstream virality scoring, niche discovery, or insights layer.
- Horizontal scaling of the API tier (still one gunicorn worker for now; Redis makes it *possible* later but is not a goal of this spec).
- Building a UI for provider-admin beyond a read-only status endpoint.

## 3. Current State (Reference)

Key files the redesign touches:

- `src/scrapers/google_trends_scraper/google_trends/spiders/trends_spider.py` — will be wrapped as `LegacyScrapyProvider`, otherwise unchanged.
- `src/scrapers/google_trends_scraper/google_trends/pipelines.py` — `DatabasePipeline` logic moves into the shared `save_trend()` path the new providers call directly.
- `src/collector/trend_collector.py` — `run_google_trends_scraper` is reimplemented on top of the provider router; the subprocess/Scrapy machinery is only invoked by the legacy provider.
- `src/api/routes/scrape.py` — adds `/scrape/v2` (enqueue) and `/scrape/stream/{job_id}` (SSE). The existing `/scrape` endpoint stays routable during migration, backed by the new pipeline behind a feature flag.
- `src/db/models.py` — add four columns to `ScrapeRun` (see §7). No new tables.
- `src/ingestion/service.py` — already exposes `start_run/finish_run` and `record_error`; the new provider calls use it directly.

Primary weaknesses being addressed (from the current-state audit):
1. `/trends/api/explore` returns 429 often; only workaround is a manual JSON import.
2. No scheduled refresh — data goes stale until a user triggers a scrape.
3. Freshness logic is duplicated between `SkipRecentlyScrapedMiddleware` and `trends.py:_needs_scrape()`.
4. Batch concurrency capped at 2 workers for large keyword sets.
5. No per-widget failure attribution.

## 4. Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                         FastAPI (gunicorn -w 1)                    │
│                                                                    │
│   POST /scrape/v2 ───► enqueue arq job ──► returns { job_id }      │
│   GET  /scrape/stream/{job_id} ◄──► SSE ◄── Redis pub/sub channel  │
│   GET  /scrape/status/{job_id} ────────► Redis job registry        │
└──────────────────────────────────────────┬─────────────────────────┘
                                           │
                                     Redis (arq queue + pub/sub + cache)
                                           │
┌──────────────────────────────────────────▼─────────────────────────┐
│                       arq worker process(es)                       │
│                                                                    │
│    TrendsCollectionJob(keywords, geo, timeframe, category)         │
│      ├─ for keyword in keywords:  (bounded asyncio.gather)         │
│      │    ├─ ProviderRouter.fetch(keyword, …)                      │
│      │    │    ├─ 1) SerpAPIProvider        ─┐                     │
│      │    │    ├─ 2) SearchAPIProvider      ─┤                     │
│      │    │    ├─ 3) BrightDataProvider     ─┤ ordered             │
│      │    │    │    (or OxylabsProvider)     │ fallback chain      │
│      │    │    ├─ 4) ApifyTrendsProvider    ─┤ (configurable)      │
│      │    │    └─ 5) LegacyScrapyProvider   ─┘                     │
│      │    ├─ normalize → list[CanonicalTrendResult]                │
│      │    ├─ save_trend(...) × N   (existing helper)               │
│      │    └─ publish {keyword, status, counts} → pub/sub           │
│      └─ finish_run(ScrapeRun)                                      │
└────────────────────────────────────────────────────────────────────┘
```

Cron (arq scheduled task, nightly 02:00 UTC):
`WarmupJob` picks the top 50 keywords per configured geo (by recent virality score, optionally seeded by the **BigQuery `bigquery-public-data.google_trends.top_terms` dataset**) and enqueues a low-priority `TrendsCollectionJob` against the same queue.

## 5. Components & Interfaces

### 5.1 `TrendsProvider` (abstract)

```
# src/collection/trends/providers/base.py
class TrendsProvider(Protocol):
    name: str                          # "serpapi", "searchapi", "brightdata", "oxylabs", "apify", "legacy_scrapy"
    supports: frozenset[DataType]      # which widgets this provider returns
    cost_per_keyword_usd: float        # for budget tracking (0 for legacy)

    async def fetch(
        self,
        keyword: str,
        geo: str,
        timeframe: str,
        category: int,
    ) -> list[CanonicalTrendResult]: ...
```

`CanonicalTrendResult` is a dataclass with `data_type` (one of `interest_over_time | interest_by_region | related_queries | related_topics`), `keyword`, `geo`, `time_range`, `category`, `results: list[dict]`, and `raw_payload: dict`. Shape of `results[i]` matches what the existing pipeline already writes for each `data_type` — so downstream code is untouched.

### 5.2 Concrete providers (the catalog)

All providers below implement the same `TrendsProvider` Protocol and emit `CanonicalTrendResult` rows. The chain is configured per-environment via `TRENDS_PROVIDER_CHAIN`; ship at least two paid providers in front of the legacy spider.

- **`SerpAPIProvider`** — GET `https://serpapi.com/search.json?engine=google_trends&data_type=<one of four>`. One HTTP call per widget (4 per keyword). Auth: `SERPAPI_KEY`. Fixed-plan pricing (~$50/mo Developer = 5k searches; ~$130/mo Production = 30k). Strength: most mature shape, well-documented, includes `google_trends_trending_now` engine for warmup. Weakness: 4 calls per keyword inflates request count.
- **`SearchAPIProvider`** — GET `https://www.searchapi.io/api/v1/search?engine=google_trends&data_type=<one of four>`. Response shape is intentionally SerpAPI-compatible, so the normalizer is a thin variant. Auth: `SEARCHAPI_KEY`. Pricing: ~$40/mo for 10k searches, ~$80/mo for 30k. Used as **paid-tier failover** for SerpAPI so a SerpAPI outage or quota-exhaustion does not collapse the chain to the legacy spider.
- **`BrightDataProvider`** — Bright Data SERP API, Google Trends collector. Pay-per-success (~$1.50–$3 per 1k requests on the Pay-As-You-Go plan). Auth: `BRIGHTDATA_API_TOKEN` + zone name. Strength: highest success rate against Google's anti-bot, no fixed monthly minimum if you have a contract. Weakness: heavier integration (zones, snapshots), and account onboarding is slow.
- **`OxylabsProvider`** — Oxylabs SERP Scraper API with `source=google_trends_explore`. Pay-per-success (~$2 per 1k results on starter, lower on volume). Auth: `OXYLABS_USERNAME` + `OXYLABS_PASSWORD`. Functionally interchangeable with `BrightDataProvider` — pick whichever vendor the company already has procurement for. We document both so the chain can be reordered without code changes.
- **`ApifyTrendsProvider`** — calls the **Apify `emastra/google-trends-scraper`** (or equivalent) actor via the Apify API, polls until the run finishes, then reads dataset items. Auth: `APIFY_TOKEN` + actor id. Pricing: ~$0.25 per 1k results on the free tier's overage, cheap in bulk. Strength: ideal for the **warmup job** where we are issuing 100s of keywords overnight and don't care about per-keyword latency. Weakness: actor cold-start adds 10–30s per run, so it is unsuitable for the user-triggered hot path — keep it late in the chain, or restrict it to the `trigger_source="warmup"` code path.
- **`LegacyScrapyProvider`** — wraps the existing Scrapy spider via `subprocess` + temp JSONL output (or `CrawlerRunner` if we are willing to bring Scrapy into the same process; default to subprocess to match current behavior). Optionally, the same provider can fall through to **`pytrends`** as a second free attempt before giving up. Only invoked when all paid providers are unavailable or budget-exhausted.
- **`BigQueryTrendsProvider`** *(seed-only, not in the main chain)* — queries `bigquery-public-data.google_trends.top_terms` to get Google's published top-25 daily/weekly trending terms per US DMA. Returns *only* a degenerate `interest_over_time` shape and is **not** a substitute for Explore. Used by `WarmupJob` to discover candidate keywords cheaply before spending Tier-1 budget on full widgets. Free (BigQuery sandbox quota is sufficient at our volume). Auth: GCP service-account JSON.

#### Why this set, and not DataForSEO

DataForSEO was considered and dropped: their per-call pricing is competitive but they impose tight per-second caps that complicate the burst path, and adopting them as the single primary would re-introduce the single-vendor-dependency we are explicitly trying to eliminate. The two SERP-style providers (SerpAPI + SearchAPI.io) give us a like-for-like swap on the hot path; the two scraping-infra providers (Bright Data / Oxylabs) give us a fundamentally *different* underlying technique as deeper fallback; Apify covers the bulk/warmup case; the legacy spider remains the floor.

### 5.3 `ProviderRouter`

- Holds an ordered list of providers from config.
- Per-provider circuit breaker (`pybreaker`): opens after N consecutive failures, stays open for a cooldown, half-open probe.
- Budget guard: before a call, checks `ProviderSpend.month_to_date < ProviderSpend.monthly_cap`. If over, skips that provider and records a `budget_exhausted` error.
- On each provider error, logs a `scrape_errors` row tagged with provider, then moves to the next in the chain. If all providers fail, the keyword is recorded as a dead-letter (`scrape_dead_letters`) and the job continues with the remaining keywords.

### 5.4 Queue & streaming

- **arq** with Redis (Azure Cache for Redis Basic C0, $16/mo). One `TrendsCollectionJob` per burst. Concurrency inside the job: `asyncio.gather` with `Semaphore(MAX_CONCURRENT_KEYWORDS=8)` — tuned to the strictest per-second cap among the configured providers (SerpAPI: 5/s on Developer; SearchAPI: similar; Bright Data / Oxylabs: effectively unbounded for our volume). The semaphore value is configurable per environment.
- **Redis pub/sub** channel per job: `job:{job_id}:events`. Workers publish `{keyword, status: "started|completed|failed", counts, error}` as they go.
- **SSE endpoint** `/scrape/stream/{job_id}` subscribes to the channel and proxies events to the client until a terminal `{event: "done"}` message arrives or the connection times out.

### 5.5 Scheduled warmup

- arq cron entry `warmup_trends` at `cron(hour=2, minute=0)`.
- Reads the top-50-by-virality keywords per configured geo (`WARMUP_GEOS` env, default `US,UK,DE`) from the `trends` table.
- Skips any keyword whose latest `canonical_trend_signals.time_bucket_start` is within `WARMUP_FRESHNESS_HOURS` (default 18h).
- Enqueues a single `TrendsCollectionJob` with `priority=low` and `source="warmup"`.

### 5.6 Unified freshness signal

One authoritative freshness check: `canonical_trend_signals.time_bucket_start >= now() - freshness_hours` for `(source='google_trends', entity_id=<keyword>, country=<geo>)`. The existing `SkipRecentlyScrapedMiddleware` is removed; `trends.py:_needs_scrape()` is rewritten against canonical signals. This resolves the duplicated-freshness-logic pain point.

## 6. Data Flow

1. User hits `POST /scrape/v2 {niche, geo, timeframe, category, scraper_type}`.
2. API resolves niche → keywords, calls `arq.enqueue("trends_collection_job", ...)`, returns `{job_id}`.
3. Frontend opens `EventSource("/scrape/stream/{job_id}")`.
4. Worker executes the job: per keyword it calls `ProviderRouter.fetch`, receives up to 4 canonical results, calls `save_trend(...)` for each, publishes an event to Redis, increments `ScrapeRun` counters.
5. On done, worker publishes `{event: "done", summary: {...}}`. SSE endpoint closes the stream.
6. Frontend refreshes trends as it receives events, or re-queries `GET /trends` at the end.

## 7. Database Changes

**Additive only.** Four new columns on `ScrapeRun`:

- `provider VARCHAR(32)` — `serpapi | searchapi | brightdata | oxylabs | apify | legacy_scrapy | mixed`
- `cost_usd FLOAT DEFAULT 0` — sum of provider costs for the run
- `job_id VARCHAR(64) NULL` — arq job id for correlation
- `trigger_source VARCHAR(32) DEFAULT 'on_demand'` — `on_demand | warmup | api`

One new column on `canonical_trend_signals`:

- `provider VARCHAR(32) NULL` — which provider produced the signal

Migrations go through the existing idempotent `src/db/migrate.py` pattern. No table renames, no type changes, no backfill required.

## 8. Error Handling & Observability

- **Per-provider errors** → `scrape_errors` table (existing), with `platform` set to `"Google Trends:<provider>"` so we can split dashboards by provider.
- **Dead letters** — a keyword that fails against *all* providers is written to `scrape_dead_letters` (existing table) with `error_type="all_providers_exhausted"`.
- **Budget tracking** — a new lightweight `ProviderSpend` (in-process, Redis-persisted) tracks month-to-date USD per provider. `GET /admin/providers/spend` returns it.
- **Run-level health** — the existing `ScrapeRun` already captures `fetched_count`, `parsed_count`, `inserted_count`, `duplicate_ratio`, `failed_count`, `top_error_types`. We add `provider`, `cost_usd`.
- **Circuit breaker state** is exposed via `GET /admin/providers/status` for the on-call screen.
- **Logging** — structured `logger.info("provider=serpapi keyword=… ms=… status=ok")` so log aggregation can group by provider.

## 9. Configuration & Secrets

New env vars (added to `.env.example`):

```
# Provider selection
# Comma-separated, ordered. Any provider listed here must have its credentials
# below; missing credentials cause the provider to be silently skipped (with a
# warning at startup). Keep at least two paid providers ahead of legacy_scrapy.
TRENDS_PROVIDER_CHAIN=serpapi,searchapi,brightdata,apify,legacy_scrapy
TRENDS_MONTHLY_BUDGET_USD=150
TRENDS_WARMUP_ENABLED=true
TRENDS_WARMUP_GEOS=US,UK,DE
TRENDS_WARMUP_FRESHNESS_HOURS=18
TRENDS_WARMUP_TOP_N=50
# Override the chain for the warmup job (latency-tolerant, prefer cheap bulk).
TRENDS_WARMUP_PROVIDER_CHAIN=apify,searchapi,legacy_scrapy

# SerpAPI
SERPAPI_KEY=
SERPAPI_MONTHLY_CAP_USD=60

# SearchAPI.io
SEARCHAPI_KEY=
SEARCHAPI_MONTHLY_CAP_USD=40

# Bright Data SERP API (optional — leave blank to disable)
BRIGHTDATA_API_TOKEN=
BRIGHTDATA_ZONE=serp_api1
BRIGHTDATA_MONTHLY_CAP_USD=30

# Oxylabs SERP Scraper API (optional — interchangeable with Bright Data)
OXYLABS_USERNAME=
OXYLABS_PASSWORD=
OXYLABS_MONTHLY_CAP_USD=30

# Apify (warmup / bulk)
APIFY_TOKEN=
APIFY_TRENDS_ACTOR=emastra/google-trends-scraper
APIFY_MONTHLY_CAP_USD=20

# BigQuery seed (warmup keyword discovery, free at our volume)
BIGQUERY_TRENDS_ENABLED=false
GOOGLE_APPLICATION_CREDENTIALS=

# (Per-provider caps above must sum to ≤ TRENDS_MONTHLY_BUDGET_USD.)

# Queue / streaming
REDIS_URL=redis://localhost:6379/0
ARQ_MAX_JOBS=4
ARQ_CONCURRENT_KEYWORDS_PER_JOB=8
```

Secrets go through the existing `src/runtime/secrets.py`; no new secret backend.

## 10. Testing Strategy

- **Unit — providers**: each concrete provider has a contract test against recorded cassettes (use `vcrpy` or a hand-rolled JSON fixture loader). No paid API calls in CI.
- **Unit — router**: circuit breaker opens after N failures, budget guard skips over-budget providers, fallback chain returns from the second provider when the first raises.
- **Unit — normalizer**: feed each provider's raw payload into the normalizer and assert output matches the canonical shape the existing pipeline expects.
- **Integration — queue + SSE**: spin up a local Redis (docker-compose service or `fakeredis` for CI), enqueue a job with a stub provider that yields 3 keywords, assert SSE client receives 3 `completed` events and 1 `done`.
- **Integration — DB**: after a stubbed run, assert new rows exist in `trends`, `canonical_trend_signals`, `scrape_runs`, with correct `provider` attribution.
- **Smoke — live providers**: one opt-in test (`pytest -m live`) that calls each paid provider with a single keyword and asserts shape. Excluded from default CI; run manually during rollout.

## 11. Migration Plan (phased rollout)

Each phase is a mergeable slice; the legacy path stays alive until phase 6.

1. **Infra** — Redis dependency, `arq` dependency, `src/collection/trends/` module skeleton, config surface. No behavior change.
2. **First paid provider** — implement *one* Tier-1 provider end-to-end (recommend **SerpAPI** because of the most stable documentation) + normalizer + `TrendsCollectionJob` + enqueue path behind `TRENDS_V2_ENABLED=false` feature flag. The same task pattern is reused verbatim for every subsequent provider — only the response-shape adapter changes.
3. **Streaming** — SSE endpoint + Redis pub/sub; frontend wiring (or a minimal test harness) to verify events flow.
4. **Second paid provider + router** — add **SearchAPI.io** (or your preferred Tier-2 vendor), implement `ProviderRouter` with circuit breaker + budget guard, expose `/admin/providers/*` endpoints. Chain is now `serpapi,searchapi,...` with real failover behavior.
5. **Scraping-infra fallback** — add **Bright Data** *or* **Oxylabs** (whichever the company has procurement for) as Tier-2 deep fallback.
6. **Bulk / warmup provider** — add **Apify** provider, wire it into `TRENDS_WARMUP_PROVIDER_CHAIN`. Optionally add the BigQuery seed query for keyword discovery.
7. **Legacy provider** — wrap the existing Scrapy spider as `LegacyScrapyProvider`; place it at the end of every chain.
8. **Cutover** — flip `TRENDS_V2_ENABLED=true` in staging, then prod. `/scrape` continues to work but routes through the new pipeline.
9. **Warmup cron** — enable nightly warmup once prod has been on V2 for ~1 week with clean error rates.
10. **Cleanup** — remove `SkipRecentlyScrapedMiddleware`, remove `/import_tokens`, remove `token_import_spider.py`, delete the legacy `/scrape` code path. Trim `.env.example`.

## 12. Budget & Cost Model (30k requests/month target)

The chain is built to **stay under $150/mo even if the cheapest paid provider is unavailable for an entire month**. Numbers below are list prices from each vendor's published plans (Apr 2026), assuming the on-demand path consumes ~25k requests/mo and warmup/scheduled traffic adds ~5k.

| Line item | Cost/mo |
|---|---|
| SerpAPI Developer plan (5k searches) — *Tier-1 primary, hot path* | $50 |
| SearchAPI.io Starter (10k searches) — *Tier-1 failover* | $40 |
| Bright Data SERP API PAYG (~$2/1k × ~5k fallback) — *Tier-2, only on circuit-open* | ~$10 |
| Apify (~$0.25/1k × ~5k warmup results) — *Tier-3, scheduled* | ~$5 |
| Azure Cache for Redis Basic C0 | $16 |
| **Total (typical)** | **~$121** |

**Worst-case scenario** (SerpAPI completely down for the month, traffic falls through to SearchAPI + Bright Data): SearchAPI alone scales to ~$80 at 30k, Bright Data adds ~$60 if it absorbs the overflow → total ~$176. To prevent that, `TRENDS_MONTHLY_BUDGET_USD=150` is enforced by the budget guard, which will route to `LegacyScrapyProvider` (free) once the cap is hit.

**Best-case scenario** (chain stays on Tier-1 only): ~$90/mo total. Comfortable buffer.

If you have an existing contract with Bright Data or Oxylabs you can drop one of the SERP-style vendors and rely on scraping-infra pricing entirely; the math still lands under $150/mo at our volume.

## 13. Open Questions / Deferred

- **Chain ordering tuning**: ship with `serpapi,searchapi,brightdata,apify,legacy_scrapy` and measure per-provider success rate / latency / cost-per-success over the first 2 weeks. Reorder based on real numbers; the router supports this via env var alone.
- **Bright Data vs Oxylabs**: pick one based on existing procurement; both expose Google Trends and both have an adapter in the catalog. Don't ship both unless you actually need the redundancy.
- **`related_topics` data quality**: SerpAPI and SearchAPI.io occasionally return empty `related_topics` for low-volume keywords; Bright Data tends to return more. If quality matters more than cost for that widget, the router can be configured to *always* prefer the scraping-infra provider for `related_topics` only — deferred until we have measurements.
- **In-process cache eviction**: once Redis is available, the in-memory response cache that forced `workers=1` can be swapped for a Redis-backed cache. Tracked as a follow-up.
- **Multi-tenancy / per-user budget caps**: deferred. Single global budget for now.
- **Web dashboard for provider health**: current plan is JSON endpoints only; a UI can come later.
- **pytrends inside `LegacyScrapyProvider`**: open question whether the extra free-path attempt is worth the maintenance cost. Defer until we observe how often the chain actually falls all the way through to legacy.

## 14. Success Criteria

Rollout is complete when, over a 7-day window post-cutover:
- ≥ 99% of per-keyword fetches succeed on the primary provider.
- 0 manual `/import_tokens` invocations were required.
- Scheduled warmup runs nightly with failure rate < 2%.
- Monthly provider spend is ≤ $150.
- Median burst latency (250 keywords, all widgets) is ≤ 5 minutes.

---

# Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Scrapy-only Google Trends path with a multi-provider resilient pipeline running on an arq + Redis queue with SSE streaming. The default chain is `SerpAPI → SearchAPI.io → Bright Data (or Oxylabs) → Apify → Legacy Scrapy`; any subset can be enabled per environment.

**Architecture:** Adapter pattern behind a `TrendsProvider` Protocol; a `ProviderRouter` orchestrates fallback, circuit-breaking, and budget enforcement. Jobs run in an arq worker process; partial results stream to the UI via Redis pub/sub + SSE. Existing `save_trend()` ingestion and canonical-signal schema remain untouched.

**Tech Stack:** Python 3.11, FastAPI, arq, Redis (Azure Cache for Redis Basic C0), httpx, pybreaker, pytest, fakeredis, Scrapy (legacy-only), SQLAlchemy, Azure SQL.

---

## ⚡ Master Execution Order (read this first)

**Important:** Task numbers (1–25) below are **stable identifiers**, not execution order. The original plan was drafted with DataForSEO as the primary provider; that decision has been reversed (see §1). Tasks 6 and 7 are **SKIPPED**. The execution order below reflects the new multi-provider chain `SerpAPI → SearchAPI.io → Bright Data → Apify → Legacy`.

| Step | Task | Phase | Title | Notes |
|---|---|---|---|---|
| 1 | Task 1 | 1 | Dependencies & env scaffolding | Provider-agnostic |
| 2 | Task 2 | 1 | Redis client + arq worker settings | Provider-agnostic |
| 3 | Task 3 | 1 | Canonical types + `TrendsProvider` Protocol | Provider-agnostic |
| 4 | Task 4 | 1 | Typed config object | **Use the new env vars from §9** (no `DATAFORSEO_*`) |
| 5 | Task 5 | 1 | DB migrations — new columns | Provider-agnostic |
| 6 | **Task 14** | 5 | **SerpAPI normalizer + cassettes** | **Promoted to first paid provider** |
| 7 | **Task 15** | 5 | **SerpAPIProvider** | **Promoted to first paid provider** |
| 8 | Task 8 | 2 | `ProviderSpend` (Redis-backed MTD tracker) | Provider-agnostic |
| 9 | Task 9 | 3 | Pub/sub event publisher | Provider-agnostic |
| 10 | Task 10 | 3 | `TrendsCollectionJob` (arq) | Provider-agnostic |
| 11 | Task 11 | 3 | `/scrape/v2` enqueue + `/scrape/status/{job_id}` | Provider-agnostic |
| 12 | Task 12 | 4 | Circuit breaker wrapper | Provider-agnostic |
| 13 | Task 13 | 4 | `ProviderRouter` (chain + budget + breaker) | Provider-agnostic |
| 14 | Task 16 | 5 | Admin provider endpoints | Provider-agnostic |
| 15 | **Task 22** | 5b | **SearchAPIProvider** (Tier-1 failover) | **NEW** — modeled on Task 14/15 |
| 16 | **Task 23** | 5b | **BrightDataProvider OR OxylabsProvider** (Tier-2) | **NEW** — pick one based on procurement |
| 17 | **Task 24** | 5b | **ApifyTrendsProvider** (bulk / warmup) | **NEW** |
| 18 | Task 17 | 6 | `LegacyScrapyProvider` | Wraps existing spider — no behavior change for legacy path |
| 19 | Task 18 | 7 | Unified freshness check | Replaces duplicated freshness logic |
| 20 | Task 19 | 7 | Feature-flag `/scrape` through V2 + frontend SSE | Cutover behind `TRENDS_V2_ENABLED` |
| 21 | Task 20 | 8 | `WarmupJob` cron | Enable only after 1 week of clean V2 prod |
| 22 | **Task 25** | 8 | **BigQuery seed for warmup keyword discovery** | **NEW**, optional |
| 23 | Task 21 | 9 | Cleanup deprecated paths | Final |

**Skipped tasks:** ~~Task 6 (DataForSEO cassette + normalizer)~~, ~~Task 7 (DataForSEOProvider)~~. Do **not** implement these — DataForSEO is no longer in the chain. The Phase 2 heading is preserved for stable cross-references; Tasks 6/7 are replaced by the SerpAPI tasks listed in the table above.

---

## 🚀 Start Prompt (paste this to begin implementation)

> **Role:** You are an autonomous implementation agent for the `trends_research` repository. You have read access to the full design document at `docs/superpowers/specs/2026-04-23-trends-collection-redesign-design.md`.
>
> **Your job:** Implement the multi-provider Google Trends collection pipeline described in that document, following the **Master Execution Order** table at the top of the Implementation Plan section. Work one task at a time, in execution-order (not task-number order). For each task:
>
> 1. Re-read the task body in the design doc (use the stable Task N anchor).
> 2. Run the existing test suite as a baseline: `& "C:\Users\MarianCraciun\anaconda3\python.exe" -m pytest tests/ -q 2>&1 | Select-Object -Last 30`. Record the failing/erroring counts. Per `.github/copilot-instructions.md`, the baseline is **2 failures + 23 errors** in `tests/test_ads_insight.py`, `tests/test_trend_collector.py`, `tests/test_all_sources.py` — these are pre-existing and **not** your responsibility to fix.
> 3. Implement the task. **Never edit `src/scrapers/`, `src/ingestion/service.py` public API, `src/db/models.py` columns other than the additive ones in §7, or any existing route handler signatures.** All new code lives under `src/collection/` and `src/api/routes/scrape_v2.py` / `admin_providers.py`. Existing routes are *only* modified at the explicit step in Task 19 (feature flag).
> 4. Add tests as described in the task body. Use `fakeredis` (never a real Redis in CI) and static JSON cassettes (never live API calls in CI).
> 5. Run the targeted new tests until green: `& "C:\Users\MarianCraciun\anaconda3\python.exe" -m pytest tests/collection/ tests/api/test_scrape_v2.py tests/api/test_admin_providers.py tests/db/test_migrate_v2_columns.py -v`.
> 6. Re-run the **full** suite and confirm the failure/error counts have **not increased** vs the baseline you recorded in step 2. If they have, you have introduced a regression — diagnose and fix before committing.
> 7. Commit with the message format from the task body. One commit per task.
> 8. Move to the next execution-order step. Do **not** skip ahead.
>
> **Hard rules:**
> - **Do not** implement DataForSEO (Task 6, Task 7). Skip them entirely.
> - **Do not** make live calls to any paid provider in CI. All HTTP must go through cassettes or `httpx.MockTransport`.
> - **Do not** flip `TRENDS_V2_ENABLED=true` until Task 19 is complete and all tests pass.
> - **Do not** delete any file before Task 21 (final cleanup).
> - **Stop and ask the user** if a task requires a credential you don't have (`SERPAPI_KEY`, `SEARCHAPI_KEY`, `BRIGHTDATA_API_TOKEN`, `OXYLABS_*`, `APIFY_TOKEN`, BigQuery service account). Implementation can proceed against cassettes; the live smoke test (`pytest -m live`) is run manually by the user once credentials are provisioned.
>
> **Begin** with Step 1 (Task 1: Dependencies & env scaffolding). After each completed step, post a short status update: `Step N/23 complete: <task title>. Tests: baseline=X/Y, current=X/Y. Commit: <hash>.`

---

## ✅ Completion Prompt (paste this when you believe you are done)

> **Role:** You are the same implementation agent. You believe all 23 execution-order steps are complete. Before reporting completion to the user, run this verification protocol and only declare done if **every** check passes.
>
> **1. Test parity with baseline**
> ```powershell
> & "C:\Users\MarianCraciun\anaconda3\python.exe" -m pytest tests/ -q 2>&1 | Select-Object -Last 30
> ```
> Failures + errors must be **≤ baseline** (2 failures + 23 errors in the three known files). Any new failure or error is a blocker.
>
> **2. New test surface coverage**
> ```powershell
> & "C:\Users\MarianCraciun\anaconda3\python.exe" -m pytest tests/collection/ tests/api/test_scrape_v2.py tests/api/test_admin_providers.py tests/db/test_migrate_v2_columns.py -v
> ```
> All new tests must pass. Coverage of `src/collection/trends/` must be ≥ 85% (`--cov=src.collection.trends --cov-report=term-missing`).
>
> **3. Backward-compatibility checklist** (every box must be ✅):
> - [ ] `GET /trends`, `GET /trends/{id}`, `GET /niches`, `GET /insights/*` return identical JSON shapes to `main` branch (compare with `git stash && curl … && git stash pop && curl …`).
> - [ ] `POST /scrape` (the legacy endpoint) still works when `TRENDS_V2_ENABLED=false` — same request/response contract as before.
> - [ ] `POST /scrape` with `TRENDS_V2_ENABLED=true` returns `{job_id}` and the SSE stream emits `done` within the timeout for a 3-keyword test payload.
> - [ ] `src/db/migrate.py` is idempotent — running it twice in a row produces no errors.
> - [ ] `src/scrapers/google_trends_scraper/` files are **unchanged on disk** (verify with `git diff --stat main..HEAD -- src/scrapers/`). The Scrapy spider is reachable via `LegacyScrapyProvider` only.
> - [ ] `src/ingestion/service.py` public functions (`start_run`, `finish_run`, `record_error`, `save_trend`) have unchanged signatures (verify with `git diff main..HEAD -- src/ingestion/service.py`).
> - [ ] No existing test in `tests/test_aggregation.py`, `tests/test_analytics_engine.py`, `tests/test_api.py`, `tests/test_auth_guard.py`, `tests/test_hn_integration.py`, `tests/test_ingestion_service.py`, `tests/test_insights_pipeline.py`, `tests/test_niche_discovery.py`, `tests/test_pipeline.py`, `tests/test_reddit_integration.py` was modified.
> - [ ] `requirements.txt` only **adds** dependencies (no removals other than DataForSEO if it was speculatively added).
> - [ ] `.env.example` is a strict superset of the previous version — no env var the user already has in their `.env` was removed.
> - [ ] `frontend/` build still passes: `cd frontend; pnpm build` (or per `_build_in_wsl.sh`).
>
> **4. Operational sanity** (run by the user with real credentials, not in CI):
> - [ ] Start a local Redis (`docker compose up redis`), start the arq worker, hit `POST /scrape/v2` with a 3-keyword payload, observe the SSE stream emit 3 `completed` events and 1 `done`.
> - [ ] Inspect `scrape_runs` table: latest row has `provider="serpapi"` (or whichever Tier-1 fired), `cost_usd > 0`, `job_id` populated, `trigger_source="on_demand"`.
> - [ ] Hit `GET /admin/providers/spend` — JSON returns per-provider month-to-date USD.
> - [ ] Hit `GET /admin/providers/status` — JSON returns circuit-breaker state per provider (all `closed` on first run).
> - [ ] Force a SerpAPI failure (set `SERPAPI_KEY=invalid`) and confirm the chain falls through to SearchAPI.io within one keyword.
>
> **5. Documentation**
> - [ ] `README.md` has a new "Trends Collection v2" section pointing to this design doc.
> - [ ] `.env.example` block from §9 of the design is present verbatim.
> - [ ] CHANGELOG entry (or release notes file) summarizes the change for ops.
>
> **If every box above is ✅,** report: `Implementation complete. Baseline tests: <X>/<Y>. New tests: <N> passing. Backward-compat: 11/11. Operational: 5/5. Ready for staging cutover (Task 19 has flag default off).`
>
> **If any box is ❌,** post: `Implementation incomplete. Failing checks: <list>. Diagnosing.` and continue work.

---

## 🛡️ Non-Regression Guardrails (in force for every task)

These rules apply to **every** commit on this initiative. The agent must self-check them before each commit.

| # | Rule | Enforcement |
|---|---|---|
| G1 | **Never modify** `src/scrapers/google_trends_scraper/google_trends/spiders/trends_spider.py` until Task 17 — and even then, only wrap it from outside via subprocess. | `git diff` check in the commit hook. |
| G2 | **Never modify** the public function signatures in `src/ingestion/service.py` (`start_run`, `finish_run`, `record_error`, `save_trend`). New functionality is consumed *through* these helpers. | Diff inspection. |
| G3 | **Never alter** existing columns in `src/db/models.py`. Only the four additive columns from §7 may be introduced. | Migration is idempotent; existing rows have NULL `provider`. |
| G4 | **Never break** the legacy `/scrape` endpoint contract while `TRENDS_V2_ENABLED=false` (the default during rollout). | Integration test in `tests/api/test_scrape_v2.py` covers both flag states. |
| G5 | **Never make** live API calls in CI. All HTTP goes through `httpx.MockTransport` or static JSON cassettes. | `pytest -m "not live"` is the default; the live smoke marker is opt-in. |
| G6 | **Never enable** the warmup cron (`TRENDS_WARMUP_ENABLED=true`) before Task 20 is complete *and* prod has been on V2 ≥7 days with clean error rates. | Default in `.env.example` is `false`. |
| G7 | **Never delete** the legacy code paths (`SkipRecentlyScrapedMiddleware`, `/import_tokens`, `token_import_spider.py`) until Task 21, and only after all of Tasks 1–20 are merged to main. | Final cleanup task is gated. |
| G8 | **Never lower** test coverage of `src/collection/` below 85%. | CI enforces. |
| G9 | **Stop and ask** if a paid-provider credential is missing. Cassette-based dev work can continue; the smoke test is owner-run. | Agent must not invent dummy keys. |
| G10 | **One task per commit.** Commit messages follow the format in each task body (e.g. `feat(trends): SerpAPI normalizer + cassettes`). | Reviewer rejects multi-task commits. |

---

## ✅ Definition of Done (per task)

Every task in this plan is considered **complete** only when **all** of the following are simultaneously true. The agent must self-verify each item before committing; the reviewer must re-verify before merging.

### Universal DoD (applies to every task, 1–25)

- [ ] **U1 — Code compiles / imports cleanly.** `python -c "import <new_module>"` succeeds with no `ImportError`, `SyntaxError`, or `ModuleNotFoundError`.
- [ ] **U2 — All new tests pass.** Tests written in this task pass locally with `& "C:\Users\MarianCraciun\anaconda3\python.exe" -m pytest <new_test_paths> -v`.
- [ ] **U3 — Baseline preserved.** Full suite (`pytest tests/ -q`) shows failure/error count **≤ baseline** (2F + 23E in the three documented files). No new failures, no new errors.
- [ ] **U4 — No regression in existing test files.** `git diff main..HEAD -- tests/` shows only **new** test files; no edits to pre-existing tests except where the task body explicitly authorizes one (e.g. Task 18 modifies `tests/test_trend_collector.py`'s freshness expectations).
- [ ] **U5 — No edits to forbidden surfaces.** `git diff main..HEAD` does not touch `src/scrapers/` (until Task 17), `src/ingestion/service.py` public API (ever), or any non-additive `src/db/models.py` columns (ever).
- [ ] **U6 — Type-check clean.** `mypy --ignore-missing-imports src/collection/` (and any other touched paths) reports no new errors.
- [ ] **U7 — Lint clean.** `ruff check src/collection/ tests/collection/` (or the project's configured linter) is clean.
- [ ] **U8 — Public functions are typed and docstring'd.** Every new public function/class has a type annotation on every parameter + return, and a one-line docstring describing intent.
- [ ] **U9 — Logging follows the structured format.** Any new `logger.info/warn/error` call uses key=value pairs (e.g. `provider=serpapi keyword=… ms=… status=ok`) so log aggregation can group on them.
- [ ] **U10 — Secrets never logged.** No `print()`, no `logger.*` call writes the value of `*_KEY`, `*_TOKEN`, `*_PASSWORD`, or any field with `cassette` containing redacted credentials.
- [ ] **U11 — Cassettes (if any) contain no live credentials.** `git diff` of any new `.json` cassette is grep'd for the value of every `_KEY` / `_TOKEN` / `_PASSWORD` env var; matches block the commit.
- [ ] **U12 — `.env.example` updated** if the task introduces a new env var, with a comment explaining its purpose and default.
- [ ] **U13 — One commit, conventional message.** Single commit per task, message matches the format from the task body (`feat(trends): …`, `chore(trends): …`, etc.).
- [ ] **U14 — Status update posted.** Agent reports: `Step N/23 complete: <title>. Tests: baseline=X/Y, current=X/Y. Commit: <hash>.`

### Per-task acceptance criteria

Each row lists the **task-specific** criteria that must pass *in addition to* the universal DoD above. "Coverage" targets are measured with `pytest --cov=<path>`.

| Task | Title | Specific Acceptance Criteria |
|---|---|---|
| **1** | Dependencies & env scaffolding | `requirements.txt` contains `arq`, `httpx`, `pybreaker`, `redis`, `fakeredis` at pinned versions. `.env.example` contains the full §9 block verbatim. `pip install -r requirements.txt` succeeds in a fresh venv. `import arq, httpx, pybreaker, redis, fakeredis` all succeed. |
| **2** | Redis client + arq worker settings | `from src.collection.queue.redis_client import get_redis` returns an `aioredis.Redis` instance pointing at `REDIS_URL`. `WorkerSettings` class is importable. Test using `fakeredis` confirms PING returns OK. `docker-compose up redis` works locally. |
| **3** | Canonical types + provider Protocol | `DataType` enum has exactly 4 members. `CanonicalTrendResult` is a frozen dataclass with all fields from §5.1. `TrendsProvider` is a `runtime_checkable` Protocol; `isinstance(stub, TrendsProvider)` works. Coverage of `types.py` ≥ 95%. |
| **4** | Typed config object | Pydantic `Settings` loads every env var from §9 with correct defaults. Loading with no env vars set still produces a valid object (with empty provider chain — providers without creds are silently dropped). Validation rejects per-provider caps that sum > `TRENDS_MONTHLY_BUDGET_USD`. |
| **5** | DB migrations — new columns | Migration is **idempotent** (running twice → no error, no duplicate column). `ScrapeRun` model has all four new columns; `CanonicalTrendSignal` has `provider`. Existing rows have `NULL` `provider` after migrate (no backfill). All existing DB tests still pass. |
| **6** | ~~DataForSEO cassette + normalizer~~ | **SKIPPED** — execute Task 14 here instead. DoD = Task 14's DoD. |
| **7** | ~~DataForSEOProvider~~ | **SKIPPED** — execute Task 15 here instead. DoD = Task 15's DoD. |
| **8** | `ProviderSpend` (Redis-backed MTD tracker) | `add(provider, usd)` and `month_to_date(provider)` work against `fakeredis`. Spend is keyed by `YYYY-MM` so it auto-resets on month rollover (test by patching `datetime`). `over_cap(provider)` returns True when MTD ≥ configured cap. Coverage ≥ 95%. |
| **9** | Pub/sub event publisher | `publish(job_id, event)` writes to channel `job:{job_id}:events`. Subscriber receives every published message in order. Channel name constant exported. Coverage ≥ 95%. |
| **10** | `TrendsCollectionJob` (arq) | Job accepts `(keywords, geo, timeframe, category, trigger_source)`. Per-keyword work goes through `ProviderRouter.fetch`. Calls `save_trend()` for each `CanonicalTrendResult`. Publishes `started` / `completed` / `failed` events. Final `done` event includes `summary` dict. Updates `ScrapeRun` with `provider` and `cost_usd`. Bounded by `Semaphore(ARQ_CONCURRENT_KEYWORDS_PER_JOB)`. Integration test enqueues a 3-keyword job against a stub provider and asserts 3 events + 1 `done`. |
| **11** | `/scrape/v2` enqueue + `/scrape/status/{job_id}` | `POST /scrape/v2` validates payload (Pydantic model), enqueues an arq job, returns `{job_id}` in < 100 ms. `GET /scrape/status/{job_id}` returns `{state, progress, summary?}`. Both routes registered in `src/api/main.py`. OpenAPI schema includes both. Auth respects whatever middleware already protects `/scrape`. |
| **12** | Circuit breaker wrapper | Breaker opens after N consecutive failures (configurable, default 5). Cooldown defaults to 60 s. Half-open probe lets exactly one call through. Test all three states (closed → open → half-open → closed) with a fake clock. Coverage ≥ 95%. |
| **13** | `ProviderRouter` (chain + budget + breaker) | `fetch()` walks the chain in order: skip if breaker open, skip if `ProviderSpend.over_cap`, try otherwise. On success, increments spend by `provider.cost_per_keyword_usd`. On all-providers-failure, writes `scrape_dead_letters` row with `error_type="all_providers_exhausted"` and raises `AllProvidersFailed`. `build_default_chain()` and `build_warmup_chain()` are independently exposed. Tests cover: happy path, fallback, budget skip, breaker skip, all-fail dead-letter. Coverage ≥ 90%. |
| **14** | SerpAPI normalizer + cassettes | 4 cassettes checked in (one per `data_type`) at `tests/collection/providers/cassettes/serpapi_python_us_*.json`. Cassettes contain no `api_key` value. `normalize_serpapi(payload, data_type)` returns a `CanonicalTrendResult` whose `results` shape matches what `save_trend()` expects (verify by feeding the output through the existing pipeline in a unit test). Coverage of `normalizers/serpapi.py` ≥ 90%. |
| **15** | `SerpAPIProvider` | Implements `TrendsProvider` Protocol. `name="serpapi"`. `cost_per_keyword_usd = 0.01` (4 calls × ~$0.0025). `fetch()` issues 4 parallel GETs via `asyncio.gather`. Tests cover: happy path against cassettes, 4xx → `ProviderError`, 429 → retry-with-backoff (capped). `httpx.MockTransport` is used; **no live calls in CI**. Coverage ≥ 90%. |
| **16** | Admin provider endpoints | `GET /admin/providers/spend` returns `{provider: {month_to_date_usd, monthly_cap_usd, over_cap}}` for every configured provider. `GET /admin/providers/status` returns `{provider: {circuit_state, last_failure_at, recent_error_count}}`. Both inherit existing `/admin/*` auth (do not add new auth). Both have unit tests using `fakeredis`-backed `ProviderSpend` and a stub circuit-breaker registry. |
| **17** | `LegacyScrapyProvider` | Wraps existing Scrapy spider via `subprocess` + temp JSONL output. **`trends_spider.py` is not modified** (verify with `git diff`). `name="legacy_scrapy"`, `cost_per_keyword_usd=0.0`. `fetch()` returns the same 4 canonical rows the paid providers do, by parsing the JSONL and feeding it through `normalizers/legacy_scrapy.py`. On subprocess timeout (default 120 s), raises `ProviderError("legacy_scrapy_timeout")`. Tests use a fake subprocess (monkey-patched `asyncio.create_subprocess_exec`). |
| **18** | Unified freshness check | `_needs_scrape(keyword, geo)` in `src/api/routes/trends.py` is rewritten to query `canonical_trend_signals.time_bucket_start >= now() - freshness_hours`. `SkipRecentlyScrapedMiddleware` is **not yet deleted** (that is Task 21) but is **bypassed** when `TRENDS_V2_ENABLED=true`. New unit tests cover both freshness paths. Existing `test_trend_collector.py` freshness tests are updated to match (this is the only authorized edit to existing tests). |
| **19** | Feature-flag `/scrape` through V2 + frontend SSE | When `TRENDS_V2_ENABLED=false` (default), `POST /scrape` behaves byte-identically to `main` branch. When `true`, it enqueues an arq job and returns `{job_id}`. Frontend's `scrape.ts` opens an `EventSource` against `/scrape/stream/{job_id}` and dispatches per-event UI updates. Cypress/Vitest test (or equivalent) covers both flag states. **Flag default stays `false` until staging cutover.** |
| **20** | `WarmupJob` cron | arq cron entry `cron(hour=2, minute=0)`. Picks top-N keywords per geo from `WARMUP_GEOS`. Skips keywords with fresh data (`< WARMUP_FRESHNESS_HOURS`). Enqueues a `TrendsCollectionJob` with `trigger_source="warmup"` and `priority=low`. Disabled by default (`TRENDS_WARMUP_ENABLED=false`). Test: stub the time, stub the trends-table query, assert correct enqueue payload. |
| **21** | Cleanup deprecated paths | `SkipRecentlyScrapedMiddleware` class removed from `middlewares.py`. `/import_tokens` route removed from `src/api/routes/scrape.py`. `token_import_spider.py` deleted. `.env.example` trimmed of any obsolete vars. `git grep -i "import_tokens\|SkipRecentlyScrapedMiddleware\|token_import_spider"` returns zero matches. Full suite still green. **Gate:** only proceed if Tasks 1–20 are merged to `main` and prod has been on V2 for ≥ 7 days with clean error rates. |
| **22** | `SearchAPIProvider` (Tier-1 failover) | 4 cassettes checked in. `name="searchapi"`, `cost_per_keyword_usd = 0.016`. Normalizer reuses 80%+ of `serpapi.py` via shared mapper. **Router fallback test:** force SerpAPI → `ProviderError`, assert SearchAPI is invoked next and returns canonical results. Provider listed in `build_default_chain()` after SerpAPI when `SEARCHAPI_KEY` is set. |
| **23** | `BrightDataProvider` **OR** `OxylabsProvider` (Tier-2) | **One vendor only**, chosen by user before starting. Cassette captured from a real run, credentials stripped. Normalizer maps single consolidated payload → 4 canonical rows. For Bright Data: trigger-then-poll loop with configurable timeout (test uses 1 s). **Router test:** simulate both Tier-1 providers failing → assert Tier-2 invoked. Provider listed in `build_default_chain()` after Tier-1 when credentials are set. |
| **24** | `ApifyTrendsProvider` (bulk/warmup) | `warmup_only = True` class attribute. **Router unit tests cover both branches:** (a) `trigger_source="on_demand"` → Apify is **skipped** (never invoked); (b) `trigger_source="warmup"` → Apify **is** invoked. `build_warmup_chain()` exposed and includes Apify ahead of fallback providers. `build_default_chain()` does **not** include Apify. Cassette-based happy-path test passes. |
| **25** | BigQuery seed (optional) | Gated by `BIGQUERY_TRENDS_ENABLED=true`; default off. `fetch_top_terms(geo, limit)` returns `list[str]`. **Graceful degradation:** missing creds, BigQuery API errors, or empty result set → returns `[]` and logs a warning, never raises. Unit test stubs the BigQuery client. `WarmupJob` integration test asserts BigQuery seeds are prepended to virality-based seeds and deduped. |

### Phase-level DoD (gates between phases)

In addition to per-task DoD, advancing to the next **phase** requires:

| Phase | Gate |
|---|---|
| 1 → 2 | All of Tasks 1–5 merged. `python -c "from src.collection.trends.types import CanonicalTrendResult, DataType; from src.collection.trends.providers.base import TrendsProvider"` works. Migration is idempotent on a fresh DB and on the prod DB. |
| 2 → 3 | Task 8 (ProviderSpend) merged. SerpAPI provider (Task 15, executed in Phase 2) returns canonical rows for at least one cassette. **Gate test:** `pytest tests/collection/providers/test_serpapi.py tests/collection/test_budget.py -v` is green. |
| 3 → 4 | Tasks 9–11 merged. End-to-end smoke: enqueue a 1-keyword job against `SerpAPIProvider` (cassette transport), assert SSE stream receives 1 `completed` + 1 `done`, assert `scrape_runs` row written with `provider="serpapi"` and `cost_usd > 0`. |
| 4 → 5 | Tasks 12–13 merged. **Gate test:** `pytest tests/collection/test_router.py -v` is green; circuit breaker, budget guard, and dead-letter paths all covered. |
| 5 → 5b | Tasks 14–16 merged. `/admin/providers/spend` and `/admin/providers/status` return live data in dev. |
| 5b → 6 | Task 22 + (Task 23 OR Task 23-alt) + Task 24 merged. **Gate test:** simulate cascading failures across all paid providers and assert eventual fallthrough to a stub legacy provider. |
| 6 → 7 | Task 17 merged. `LegacyScrapyProvider` returns canonical rows in a manual smoke test against the existing spider. **`src/scrapers/` diff vs main is empty.** |
| 7 → 8 | Tasks 18–19 merged. Staging has `TRENDS_V2_ENABLED=true` for ≥ 48 h with no new errors. |
| 8 → 9 | Task 20 (and optionally Task 25) merged. Prod has `TRENDS_V2_ENABLED=true` for ≥ 7 days with clean error rates and warmup runs visible in `scrape_runs` with `trigger_source="warmup"`. |
| 9 → done | Task 21 merged. `git grep` for deprecated symbols returns empty. README + CHANGELOG updated. Completion Prompt's verification protocol passes 100%. |

---

## File Structure (locked-in)

**New files (create):**

```
src/collection/__init__.py
src/collection/queue/__init__.py
src/collection/queue/redis_client.py              # shared async Redis pool
src/collection/queue/settings.py                  # arq WorkerSettings
src/collection/trends/__init__.py
src/collection/trends/types.py                    # DataType, CanonicalTrendResult
src/collection/trends/config.py                   # pydantic Settings
src/collection/trends/events.py                   # pub/sub publish helper
src/collection/trends/budget.py                   # ProviderSpend (Redis-backed)
src/collection/trends/circuit_breaker.py          # per-provider breaker
src/collection/trends/router.py                   # ProviderRouter
src/collection/trends/jobs.py                     # TrendsCollectionJob, WarmupJob
src/collection/trends/providers/__init__.py
src/collection/trends/providers/base.py           # TrendsProvider Protocol
src/collection/trends/providers/serpapi.py        # Tier-1 primary
src/collection/trends/providers/searchapi.py      # Tier-1 failover (NEW)
src/collection/trends/providers/brightdata.py     # Tier-2 (NEW; or oxylabs.py — pick one)
src/collection/trends/providers/oxylabs.py        # Tier-2 alternative (NEW; ship one of brightdata/oxylabs)
src/collection/trends/providers/apify.py          # Bulk/warmup (NEW)
src/collection/trends/providers/bigquery_seed.py  # Warmup keyword seed (NEW, optional)
src/collection/trends/providers/legacy_scrapy.py  # Last resort
src/collection/trends/normalizers/__init__.py
src/collection/trends/normalizers/serpapi.py
src/collection/trends/normalizers/searchapi.py    # NEW
src/collection/trends/normalizers/brightdata.py   # NEW (or oxylabs.py)
src/collection/trends/normalizers/oxylabs.py      # NEW
src/collection/trends/normalizers/apify.py        # NEW
src/collection/trends/normalizers/legacy_scrapy.py
src/api/routes/scrape_v2.py                       # /scrape/v2, /scrape/status, /scrape/stream
src/api/routes/admin_providers.py                 # /admin/providers/{spend,status}

tests/collection/__init__.py
tests/collection/conftest.py                      # fakeredis + fixtures
tests/collection/test_types.py
tests/collection/test_config.py
tests/collection/test_events.py
tests/collection/test_budget.py
tests/collection/test_circuit_breaker.py
tests/collection/test_router.py
tests/collection/test_jobs.py
tests/collection/queue/test_redis_client.py
tests/collection/providers/__init__.py
tests/collection/providers/cassettes/serpapi_python_us_*.json
tests/collection/providers/cassettes/searchapi_python_us_*.json     # NEW
tests/collection/providers/cassettes/brightdata_python_us.json      # NEW
tests/collection/providers/cassettes/oxylabs_python_us.json         # NEW (if shipping)
tests/collection/providers/cassettes/apify_python_us.json           # NEW
tests/collection/providers/test_serpapi.py
tests/collection/providers/test_searchapi.py                        # NEW
tests/collection/providers/test_brightdata.py                       # NEW
tests/collection/providers/test_oxylabs.py                          # NEW (if shipping)
tests/collection/providers/test_apify.py                            # NEW
tests/collection/providers/test_legacy_scrapy.py
tests/collection/normalizers/__init__.py
tests/collection/normalizers/test_serpapi.py
tests/collection/normalizers/test_searchapi.py                      # NEW
tests/collection/normalizers/test_brightdata.py                     # NEW
tests/collection/normalizers/test_oxylabs.py                        # NEW (if shipping)
tests/collection/normalizers/test_apify.py                          # NEW
tests/collection/normalizers/test_legacy_scrapy.py
tests/api/test_scrape_v2.py
tests/api/test_admin_providers.py
tests/db/test_migrate_v2_columns.py
```

**Files to modify:**

```
requirements.txt              # add arq, httpx, pybreaker, fakeredis, redis,
                              #   apify-client, google-cloud-bigquery (optional)
.env.example                  # add the full §9 block (no DATAFORSEO_*)
docker-compose.yml            # add redis service for local dev
src/db/models.py              # ScrapeRun: +provider, +cost_usd, +job_id, +trigger_source
                              # CanonicalTrendSignal: +provider
src/db/migrate.py             # idempotent ALTER TABLE for the columns above
src/api/main.py               # register scrape_v2 + admin_providers routers
src/api/routes/scrape.py      # feature-flag branch to V2 pipeline (Task 19 only)
src/api/routes/trends.py      # _needs_scrape() against canonical_trend_signals (Task 18)
src/collector/trend_collector.py  # run_google_trends_scraper → V2 enqueue when flag on
frontend/src/api/scrape.ts    # SSE EventSource wiring (Task 19)
```

**Files to delete (final cleanup task — Task 21 only):**

```
src/scrapers/google_trends_scraper/google_trends/spiders/token_import_spider.py
(+ remove SkipRecentlyScrapedMiddleware class from middlewares.py)
(+ remove /import_tokens from src/api/routes/scrape.py)
```

---

## Phase 1 — Infrastructure

### Task 1: Add dependencies & environment scaffolding

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Append to `requirements.txt`**

```
arq==0.26.3
redis==5.0.8
httpx==0.27.2
pybreaker==1.2.0
fakeredis==2.24.1
```

- [ ] **Step 2: Append the env block to `.env.example`**

```
# ─── Trends Collection V2 ──────────────────────────────────
TRENDS_V2_ENABLED=false
TRENDS_PROVIDER_CHAIN=dataforseo,serpapi,legacy_scrapy
TRENDS_MONTHLY_BUDGET_USD=150
TRENDS_MAX_CONCURRENT_KEYWORDS_PER_JOB=8
TRENDS_WARMUP_ENABLED=false
TRENDS_WARMUP_GEOS=US,UK,DE
TRENDS_WARMUP_FRESHNESS_HOURS=18
TRENDS_WARMUP_TOP_N=50

DATAFORSEO_LOGIN=
DATAFORSEO_PASSWORD=
DATAFORSEO_MONTHLY_CAP_USD=100

SERPAPI_KEY=
SERPAPI_MONTHLY_CAP_USD=50

REDIS_URL=redis://localhost:6379/0
ARQ_MAX_JOBS=4
```

- [ ] **Step 3: Add a Redis service to `docker-compose.yml`**

```yaml
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "6379:6379"
    command: ["redis-server", "--appendonly", "no", "--save", ""]
```

- [ ] **Step 4: Install and verify**

```bash
pip install -r requirements.txt
python -c "import arq, httpx, pybreaker, fakeredis, redis; print('ok')"
```
Expected: `ok`

- [x] **Step 5: Commit**

```bash
git add requirements.txt .env.example docker-compose.yml
git commit -m "feat(trends): add V2 collection dependencies and env scaffold"
```

**Prompt for subagent:**
> Add dependencies and environment scaffolding for the Trends V2 collection pipeline. Follow Task 1 in `docs/superpowers/specs/2026-04-23-trends-collection-redesign-design.md` exactly. Do not install additional packages. Do not modify `.env` (only `.env.example`). After committing, print `git log -1 --stat`.

---

### Task 2: Redis client + arq worker settings

**Files:**
- Create: `src/collection/__init__.py` (empty)
- Create: `src/collection/queue/__init__.py` (empty)
- Create: `src/collection/queue/redis_client.py`
- Create: `src/collection/queue/settings.py`
- Create: `tests/collection/__init__.py` (empty)
- Create: `tests/collection/queue/__init__.py` (empty)
- Create: `tests/collection/conftest.py`
- Create: `tests/collection/queue/test_redis_client.py`

- [ ] **Step 1: Write `tests/collection/conftest.py`**

```python
import os
import pytest
import fakeredis.aioredis

@pytest.fixture
def fake_redis():
    """Fresh in-memory Redis per test."""
    client = fakeredis.aioredis.FakeRedis()
    yield client
    # FakeRedis cleans up on GC; explicit close keeps the loop happy.

@pytest.fixture(autouse=True)
def _set_redis_url(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
```

- [ ] **Step 2: Write `tests/collection/queue/test_redis_client.py`**

```python
import pytest
from src.collection.queue.redis_client import get_redis, close_redis

@pytest.mark.asyncio
async def test_get_redis_returns_same_instance():
    a = await get_redis()
    b = await get_redis()
    assert a is b
    await close_redis()

@pytest.mark.asyncio
async def test_close_redis_is_idempotent():
    await get_redis()
    await close_redis()
    await close_redis()  # must not raise
```

- [ ] **Step 3: Run — expect failure**

```bash
pytest tests/collection/queue/test_redis_client.py -v
```
Expected: `ModuleNotFoundError: src.collection.queue.redis_client`

- [ ] **Step 4: Implement `src/collection/queue/redis_client.py`**

```python
"""Shared async Redis connection pool for the collection layer."""
from __future__ import annotations
import os
from redis.asyncio import Redis, ConnectionPool

_pool: ConnectionPool | None = None
_client: Redis | None = None

async def get_redis() -> Redis:
    global _pool, _client
    if _client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _pool = ConnectionPool.from_url(url, max_connections=20, decode_responses=True)
        _client = Redis(connection_pool=_pool)
    return _client

async def close_redis() -> None:
    global _pool, _client
    if _client is not None:
        await _client.aclose()
        _client = None
    if _pool is not None:
        await _pool.aclose()
        _pool = None
```

- [ ] **Step 5: Implement `src/collection/queue/settings.py`**

```python
"""arq WorkerSettings — imported by `arq src.collection.queue.settings.WorkerSettings`."""
from __future__ import annotations
import os
from arq.connections import RedisSettings

from src.collection.trends import jobs  # noqa: F401 — registers functions

def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

class WorkerSettings:
    redis_settings = _redis_settings()
    functions: list = []   # populated by src.collection.trends.jobs (Task 10)
    cron_jobs: list = []   # populated by WarmupJob (Task 23)
    max_jobs = int(os.getenv("ARQ_MAX_JOBS", "4"))
    job_timeout = 60 * 30  # 30 min hard cap per job
    keep_result = 60 * 60  # 1 h
```

> NOTE: `src.collection.trends.jobs` does not exist yet. Temporarily comment out the import; Task 10 adds it.

Replace line `from src.collection.trends import jobs  # noqa: F401 — registers functions` with `# from src.collection.trends import jobs  # enabled in Task 10`.

- [ ] **Step 6: Run tests — expect pass**

```bash
pytest tests/collection/queue/test_redis_client.py -v
```
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add src/collection tests/collection
git commit -m "feat(trends): redis client + arq worker settings skeleton"
```

**Prompt for subagent:**
> Implement Task 2 from the plan in `docs/superpowers/specs/2026-04-23-trends-collection-redesign-design.md`: a shared async Redis client and a minimal arq `WorkerSettings`. The `src.collection.trends.jobs` import in `settings.py` must remain commented out — Task 10 adds that module. Run `pytest tests/collection/queue/test_redis_client.py -v` and confirm both tests pass before committing. Do not touch any other files.

---

### Task 3: Canonical types + provider Protocol

**Files:**
- Create: `src/collection/trends/__init__.py` (empty)
- Create: `src/collection/trends/types.py`
- Create: `src/collection/trends/providers/__init__.py` (empty)
- Create: `src/collection/trends/providers/base.py`
- Create: `tests/collection/test_types.py`

- [ ] **Step 1: Write `tests/collection/test_types.py`**

```python
from datetime import datetime
from src.collection.trends.types import DataType, CanonicalTrendResult

def test_datatype_members():
    assert {d.value for d in DataType} == {
        "interest_over_time",
        "interest_by_region",
        "related_queries",
        "related_topics",
    }

def test_canonical_result_defaults():
    r = CanonicalTrendResult(
        data_type=DataType.INTEREST_OVER_TIME,
        keyword="python",
        geo="US",
        time_range="today 12-m",
        category=0,
        results=[{"time": "2026-04-01", "value": 75}],
        raw_payload={},
    )
    assert r.provider is None
    assert isinstance(r.extracted_at, datetime)
    assert r.results[0]["value"] == 75
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/collection/test_types.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/collection/trends/types.py`**

```python
"""Canonical trend result types consumed by every provider."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

class DataType(str, Enum):
    INTEREST_OVER_TIME = "interest_over_time"
    INTEREST_BY_REGION = "interest_by_region"
    RELATED_QUERIES = "related_queries"
    RELATED_TOPICS = "related_topics"

@dataclass
class CanonicalTrendResult:
    data_type: DataType
    keyword: str
    geo: str
    time_range: str
    category: int
    results: list[dict[str, Any]]
    raw_payload: dict[str, Any]
    provider: str | None = None
    cost_usd: float = 0.0
    extracted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 4: Implement `src/collection/trends/providers/base.py`**

```python
"""TrendsProvider Protocol — every provider implements this."""
from __future__ import annotations
from typing import Protocol, runtime_checkable

from src.collection.trends.types import CanonicalTrendResult, DataType

@runtime_checkable
class TrendsProvider(Protocol):
    name: str
    supports: frozenset[DataType]
    cost_per_keyword_usd: float

    async def fetch(
        self,
        keyword: str,
        geo: str,
        timeframe: str,
        category: int,
    ) -> list[CanonicalTrendResult]: ...

class ProviderError(Exception):
    """Raised by a provider when a fetch fails in a way the router should see."""
    def __init__(self, provider: str, message: str, *, retriable: bool = True):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.retriable = retriable
```

- [ ] **Step 5: Run tests — expect pass**

```bash
pytest tests/collection/test_types.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/collection/trends tests/collection/test_types.py
git commit -m "feat(trends): canonical types and TrendsProvider Protocol"
```

**Prompt for subagent:**
> Implement Task 3: canonical `DataType` enum, `CanonicalTrendResult` dataclass, and the `TrendsProvider` Protocol. Include the `ProviderError` exception. Paths and code are specified verbatim in Task 3 of the plan. Run `pytest tests/collection/test_types.py -v` (both tests must pass) before committing.

---

### Task 4: Typed config object

**Files:**
- Create: `src/collection/trends/config.py`
- Create: `tests/collection/test_config.py`

- [ ] **Step 1: Write `tests/collection/test_config.py`**

```python
import pytest
from src.collection.trends.config import TrendsConfig

def test_defaults(monkeypatch):
    for k in ("DATAFORSEO_LOGIN", "SERPAPI_KEY"):
        monkeypatch.delenv(k, raising=False)
    c = TrendsConfig.from_env()
    assert c.v2_enabled is False
    assert c.chain == ("dataforseo", "serpapi", "legacy_scrapy")
    assert c.monthly_budget_usd == 150.0
    assert c.max_concurrent_keywords_per_job == 8

def test_chain_parses_csv(monkeypatch):
    monkeypatch.setenv("TRENDS_PROVIDER_CHAIN", "serpapi, dataforseo")
    c = TrendsConfig.from_env()
    assert c.chain == ("serpapi", "dataforseo")

def test_per_provider_caps_must_not_exceed_total(monkeypatch):
    monkeypatch.setenv("TRENDS_MONTHLY_BUDGET_USD", "100")
    monkeypatch.setenv("DATAFORSEO_MONTHLY_CAP_USD", "80")
    monkeypatch.setenv("SERPAPI_MONTHLY_CAP_USD", "40")
    with pytest.raises(ValueError, match="exceed"):
        TrendsConfig.from_env()
```

- [ ] **Step 2: Run — expect failure** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `src/collection/trends/config.py`**

```python
"""Typed env-driven config for the trends collection layer."""
from __future__ import annotations
import os
from dataclasses import dataclass

def _env_bool(k: str, default: bool) -> bool:
    v = os.getenv(k)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

def _env_float(k: str, default: float) -> float:
    v = os.getenv(k)
    return float(v) if v not in (None, "") else default

def _env_int(k: str, default: int) -> int:
    v = os.getenv(k)
    return int(v) if v not in (None, "") else default

@dataclass(frozen=True)
class TrendsConfig:
    v2_enabled: bool
    chain: tuple[str, ...]
    monthly_budget_usd: float
    max_concurrent_keywords_per_job: int
    warmup_enabled: bool
    warmup_geos: tuple[str, ...]
    warmup_freshness_hours: int
    warmup_top_n: int
    dataforseo_login: str
    dataforseo_password: str
    dataforseo_monthly_cap_usd: float
    serpapi_key: str
    serpapi_monthly_cap_usd: float

    @classmethod
    def from_env(cls) -> "TrendsConfig":
        chain = tuple(
            x.strip() for x in os.getenv("TRENDS_PROVIDER_CHAIN",
                                        "dataforseo,serpapi,legacy_scrapy").split(",") if x.strip()
        )
        geos = tuple(
            x.strip().upper() for x in os.getenv("TRENDS_WARMUP_GEOS", "US,UK,DE").split(",") if x.strip()
        )
        total = _env_float("TRENDS_MONTHLY_BUDGET_USD", 150.0)
        ds_cap = _env_float("DATAFORSEO_MONTHLY_CAP_USD", 100.0)
        sa_cap = _env_float("SERPAPI_MONTHLY_CAP_USD", 50.0)
        if ds_cap + sa_cap > total:
            raise ValueError(
                f"Per-provider caps ({ds_cap} + {sa_cap}) exceed TRENDS_MONTHLY_BUDGET_USD ({total})"
            )
        return cls(
            v2_enabled=_env_bool("TRENDS_V2_ENABLED", False),
            chain=chain,
            monthly_budget_usd=total,
            max_concurrent_keywords_per_job=_env_int("TRENDS_MAX_CONCURRENT_KEYWORDS_PER_JOB", 8),
            warmup_enabled=_env_bool("TRENDS_WARMUP_ENABLED", False),
            warmup_geos=geos,
            warmup_freshness_hours=_env_int("TRENDS_WARMUP_FRESHNESS_HOURS", 18),
            warmup_top_n=_env_int("TRENDS_WARMUP_TOP_N", 50),
            dataforseo_login=os.getenv("DATAFORSEO_LOGIN", ""),
            dataforseo_password=os.getenv("DATAFORSEO_PASSWORD", ""),
            dataforseo_monthly_cap_usd=ds_cap,
            serpapi_key=os.getenv("SERPAPI_KEY", ""),
            serpapi_monthly_cap_usd=sa_cap,
        )
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/collection/test_config.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/collection/trends/config.py tests/collection/test_config.py
git commit -m "feat(trends): typed config object loaded from env"
```

**Prompt for subagent:**
> Implement Task 4: a `TrendsConfig` dataclass built from environment variables, with a `from_env()` classmethod that raises `ValueError` if per-provider caps exceed the global ceiling. Full code in Task 4 of `docs/superpowers/specs/2026-04-23-trends-collection-redesign-design.md`. All three tests must pass before committing.

---

### Task 5: DB migrations — new columns

**Files:**
- Modify: `src/db/models.py` (add columns to `ScrapeRun` and `CanonicalTrendSignal`)
- Modify: `src/db/migrate.py` (idempotent ALTER TABLE)
- Create: `tests/db/test_migrate_v2_columns.py`

- [ ] **Step 1: Write `tests/db/test_migrate_v2_columns.py`**

```python
"""Verifies the V2 columns are present after migrate runs."""
import pytest
from sqlalchemy import inspect
from src.db.connection import engine
from src.db.migrate import migrate

@pytest.fixture(scope="module", autouse=True)
def _run_migrate():
    migrate()

def test_scrape_runs_has_v2_columns():
    cols = {c["name"] for c in inspect(engine).get_columns("scrape_runs")}
    assert {"provider", "cost_usd", "job_id", "trigger_source"}.issubset(cols)

def test_canonical_signals_has_provider():
    cols = {c["name"] for c in inspect(engine).get_columns("canonical_trend_signals")}
    assert "provider" in cols
```

- [ ] **Step 2: Run — expect failure** (columns missing).

- [ ] **Step 3: Add columns to `src/db/models.py` — in the `ScrapeRun` class, append:**

```python
    provider = Column(String(32))
    cost_usd = Column(Float, nullable=False, default=0.0)
    job_id = Column(String(64))
    trigger_source = Column(String(32), nullable=False, default="on_demand")
```

And in the `CanonicalTrendSignal` class, append before `__table_args__`:

```python
    provider = Column(String(32))
```

- [ ] **Step 4: Add idempotent migrations to `src/db/migrate.py`**

Inside the main `migrate()` function, after existing column additions, append:

```python
    _ensure_column("scrape_runs", "provider", "VARCHAR(32) NULL")
    _ensure_column("scrape_runs", "cost_usd", "FLOAT NOT NULL DEFAULT 0")
    _ensure_column("scrape_runs", "job_id", "VARCHAR(64) NULL")
    _ensure_column("scrape_runs", "trigger_source", "VARCHAR(32) NOT NULL DEFAULT 'on_demand'")
    _ensure_column("canonical_trend_signals", "provider", "VARCHAR(32) NULL")
```

(If `_ensure_column` does not already exist in `migrate.py`, add it; follow the idempotent pattern already used for other columns in that file. Inspect the file first and match its style.)

- [ ] **Step 5: Run migrate + tests**

```bash
python -m src.db.migrate
pytest tests/db/test_migrate_v2_columns.py -v
```
Expected: migrate prints no errors; 2 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/db/models.py src/db/migrate.py tests/db/test_migrate_v2_columns.py
git commit -m "feat(db): add V2 columns to scrape_runs and canonical_trend_signals"
```

**Prompt for subagent:**
> Implement Task 5: add `provider`, `cost_usd`, `job_id`, `trigger_source` columns to the `scrape_runs` table and `provider` to `canonical_trend_signals`, both via SQLAlchemy models (`src/db/models.py`) and idempotent migrations (`src/db/migrate.py`). Inspect `src/db/migrate.py` first to match the existing `_ensure_column`-style pattern; if that helper does not exist, define it following the idempotent convention already in the file. Run migrate on the dev DB and confirm `tests/db/test_migrate_v2_columns.py` passes.

---

## Phase 2 — First paid provider (recommended: SerpAPI)

> ⚠️ **Tasks 6 and 7 below are SKIPPED.** They were drafted for DataForSEO, which has been removed from the chain (see §1 / §5.2). The first paid provider is now **SerpAPI**, implemented by **Task 14** (normalizer + cassettes) and **Task 15** (`SerpAPIProvider`) in Phase 5. **Execute Tasks 14 and 15 here in Phase 2 order**, then proceed to Task 8 below. The Task 6/7 anchors are preserved only so that downstream cross-references in the document do not break — do not implement their bodies.

### Task 6: ~~DataForSEO cassette + normalizer~~ — **SKIPPED**

> **SKIPPED.** Implement **Task 14** (SerpAPI normalizer + cassettes) here instead. The pattern (cassette → normalizer → unit tests against the cassette) is identical; only the JSON shape and URL change. The DataForSEO-specific snippets below are retained as historical reference for the structure of a future provider task and **must not be implemented as-is**.



**Files:**
- Create: `tests/collection/providers/cassettes/dataforseo_python_us.json`
- Create: `src/collection/trends/normalizers/__init__.py` (empty)
- Create: `src/collection/trends/normalizers/dataforseo.py`
- Create: `tests/collection/normalizers/__init__.py` (empty)
- Create: `tests/collection/normalizers/test_dataforseo.py`

- [ ] **Step 1: Save a canned DataForSEO response at `tests/collection/providers/cassettes/dataforseo_python_us.json`**

Use the canonical shape from DataForSEO's `/v3/keywords_data/google_trends/explore/live` docs. Minimum viable cassette:

```json
{
  "tasks": [{
    "status_code": 20000,
    "result": [{
      "keywords": ["python"],
      "location_code": 2840,
      "items": [
        {"type": "google_trends_graph",
         "data": [{"date_from": "2025-05-01", "date_to": "2025-05-07", "values": [75]}]},
        {"type": "google_trends_map",
         "data": [{"geo_id": "US-CA", "geo_name": "California", "values": [100]},
                  {"geo_id": "US-NY", "geo_name": "New York",   "values": [80]}]},
        {"type": "google_trends_topics_list",
         "data": {"top":    [{"topic_title": "Python (language)", "value": 100}],
                  "rising": [{"topic_title": "Python 3.13",       "value": 5000, "is_breakout": true}]}},
        {"type": "google_trends_queries_list",
         "data": {"top":    [{"query": "python tutorial", "value": 100}],
                  "rising": [{"query": "python 3.13",     "value": 2500}]}}
      ]
    }]
  }]
}
```

- [ ] **Step 2: Write `tests/collection/normalizers/test_dataforseo.py`**

```python
import json
from pathlib import Path
from src.collection.trends.types import DataType
from src.collection.trends.normalizers.dataforseo import normalize

CASSETTE = Path(__file__).parent.parent / "providers" / "cassettes" / "dataforseo_python_us.json"

def _payload():
    return json.loads(CASSETTE.read_text())

def test_normalize_returns_four_widgets():
    results = normalize(_payload(), keyword="python", geo="US",
                        timeframe="today 12-m", category=0)
    types = {r.data_type for r in results}
    assert types == {DataType.INTEREST_OVER_TIME, DataType.INTEREST_BY_REGION,
                     DataType.RELATED_QUERIES, DataType.RELATED_TOPICS}

def test_interest_over_time_shape():
    results = normalize(_payload(), keyword="python", geo="US",
                        timeframe="today 12-m", category=0)
    iot = next(r for r in results if r.data_type == DataType.INTEREST_OVER_TIME)
    assert iot.results[0]["time"] == "2025-05-01"
    assert iot.results[0]["value"] == 75

def test_related_queries_marks_rising_breakout():
    results = normalize(_payload(), keyword="python", geo="US",
                        timeframe="today 12-m", category=0)
    rq = next(r for r in results if r.data_type == DataType.RELATED_QUERIES)
    rising = [r for r in rq.results if r["type"] == "rising"]
    assert rising and rising[0]["query"] == "python 3.13"
```

- [ ] **Step 3: Run — expect failure**

- [ ] **Step 4: Implement `src/collection/trends/normalizers/dataforseo.py`**

```python
"""Normalize DataForSEO Google Trends Explore Live → CanonicalTrendResult list."""
from __future__ import annotations
from typing import Any

from src.collection.trends.types import CanonicalTrendResult, DataType

_TYPE_MAP = {
    "google_trends_graph":        DataType.INTEREST_OVER_TIME,
    "google_trends_map":          DataType.INTEREST_BY_REGION,
    "google_trends_queries_list": DataType.RELATED_QUERIES,
    "google_trends_topics_list":  DataType.RELATED_TOPICS,
}

def normalize(
    payload: dict[str, Any],
    *,
    keyword: str,
    geo: str,
    timeframe: str,
    category: int,
) -> list[CanonicalTrendResult]:
    out: list[CanonicalTrendResult] = []
    tasks = payload.get("tasks") or []
    if not tasks or tasks[0].get("status_code") != 20000:
        return out
    for res in tasks[0].get("result") or []:
        for item in res.get("items") or []:
            kind = item.get("type")
            dt = _TYPE_MAP.get(kind)
            if dt is None:
                continue
            rows = _convert(dt, item.get("data") or [])
            out.append(CanonicalTrendResult(
                data_type=dt, keyword=keyword, geo=geo,
                time_range=timeframe, category=category,
                results=rows, raw_payload=item, provider="dataforseo",
            ))
    return out

def _convert(dt: DataType, data: Any) -> list[dict[str, Any]]:
    if dt == DataType.INTEREST_OVER_TIME:
        return [
            {"time": e.get("date_from"),
             "value": (e.get("values") or [0])[0],
             "isPartial": False}
            for e in data
        ]
    if dt == DataType.INTEREST_BY_REGION:
        return [
            {"geoName": e.get("geo_name"), "geoCode": e.get("geo_id"),
             "value": (e.get("values") or [0])[0]}
            for e in data
        ]
    # related queries / topics share the same structure: {"top": [...], "rising": [...]}
    rows: list[dict[str, Any]] = []
    for bucket in ("top", "rising"):
        for entry in (data or {}).get(bucket) or []:
            rows.append({
                "query": entry.get("query"),
                "topic": entry.get("topic_title"),
                "value": 5000 if entry.get("is_breakout") else entry.get("value"),
                "type": bucket,
            })
    return rows
```

- [ ] **Step 5: Run — expect 3 passes.**

- [ ] **Step 6: Commit**

```bash
git add src/collection/trends/normalizers tests/collection
git commit -m "feat(trends): DataForSEO normalizer + cassette"
```

**Prompt for subagent:**
> Implement Task 6: DataForSEO response cassette, normalizer, and tests. The normalizer must produce exactly one `CanonicalTrendResult` per widget type (4 total) with `provider="dataforseo"`. All three tests must pass before committing. Do not add VCR or any recording library — the cassette is a static JSON file hand-checked into the repo.

---

### Task 7: ~~DataForSEOProvider~~ — **SKIPPED**

> **SKIPPED.** Implement **Task 15** (`SerpAPIProvider`) here instead. The DataForSEO-specific snippets that follow are retained as historical reference and **must not be implemented as-is**.

**Files (skipped):**
- ~~Create: `src/collection/trends/providers/dataforseo.py`~~
- ~~Create: `tests/collection/providers/test_dataforseo.py`~~

- [ ] **Step 1: Write `tests/collection/providers/test_dataforseo.py`**

```python
import json
from pathlib import Path
import httpx
import pytest
from src.collection.trends.providers.base import ProviderError
from src.collection.trends.providers.dataforseo import DataForSEOProvider

CASSETTE = Path(__file__).parent / "cassettes" / "dataforseo_python_us.json"

@pytest.mark.asyncio
async def test_fetch_returns_four_results(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "keywords_data/google_trends/explore/live" in str(request.url)
        return httpx.Response(200, text=CASSETTE.read_text())
    transport = httpx.MockTransport(handler)
    provider = DataForSEOProvider(login="u", password="p", transport=transport)
    out = await provider.fetch("python", geo="US", timeframe="today 12-m", category=0)
    assert len(out) == 4
    assert all(r.provider == "dataforseo" for r in out)
    await provider.close()

@pytest.mark.asyncio
async def test_non_200_raises_provider_error():
    def handler(request):
        return httpx.Response(503, text="boom")
    provider = DataForSEOProvider(login="u", password="p",
                                  transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError):
        await provider.fetch("x", geo="US", timeframe="today 12-m", category=0)
    await provider.close()

@pytest.mark.asyncio
async def test_task_error_raises_provider_error():
    body = json.dumps({"tasks": [{"status_code": 40400, "status_message": "bad"}]})
    provider = DataForSEOProvider(
        login="u", password="p",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body)),
    )
    with pytest.raises(ProviderError):
        await provider.fetch("x", geo="US", timeframe="today 12-m", category=0)
    await provider.close()
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Implement `src/collection/trends/providers/dataforseo.py`**

```python
"""DataForSEO Google Trends Explore Live provider."""
from __future__ import annotations
import base64
import httpx

from src.collection.trends.providers.base import ProviderError, TrendsProvider
from src.collection.trends.types import CanonicalTrendResult, DataType
from src.collection.trends.normalizers.dataforseo import normalize

# DataForSEO expects numeric location codes; keep a small map, fall back to 2840 (US).
_GEO_CODE = {
    "US": 2840, "UK": 2826, "GB": 2826, "DE": 2276, "FR": 2250,
    "RO": 2642, "ES": 2724, "IT": 2380, "CA": 2124, "AU": 2036,
}

class DataForSEOProvider:
    name = "dataforseo"
    supports = frozenset(DataType)
    cost_per_keyword_usd = 0.002  # 4 widgets in one request

    _URL = "https://api.dataforseo.com/v3/keywords_data/google_trends/explore/live"

    def __init__(self, *, login: str, password: str,
                 transport: httpx.AsyncBaseTransport | None = None,
                 timeout: float = 30.0) -> None:
        if not (login and password):
            raise ValueError("DataForSEOProvider requires login and password")
        token = base64.b64encode(f"{login}:{password}".encode()).decode()
        self._client = httpx.AsyncClient(
            base_url="https://api.dataforseo.com",
            headers={"Authorization": f"Basic {token}",
                     "Content-Type": "application/json"},
            timeout=timeout, transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch(
        self, keyword: str, geo: str, timeframe: str, category: int,
    ) -> list[CanonicalTrendResult]:
        body = [{
            "keywords": [keyword],
            "location_code": _GEO_CODE.get(geo.upper(), 2840),
            "time_range": _map_timeframe(timeframe),
            "category_code": category or None,
        }]
        try:
            resp = await self._client.post(self._URL, json=body)
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"transport: {e}", retriable=True) from e
        if resp.status_code >= 500 or resp.status_code == 429:
            raise ProviderError(self.name, f"http {resp.status_code}", retriable=True)
        if resp.status_code >= 400:
            raise ProviderError(self.name, f"http {resp.status_code}", retriable=False)
        payload = resp.json()
        tasks = payload.get("tasks") or []
        if not tasks:
            raise ProviderError(self.name, "empty tasks", retriable=False)
        task_status = tasks[0].get("status_code")
        if task_status != 20000:
            raise ProviderError(self.name,
                                f"task status {task_status}: {tasks[0].get('status_message')}",
                                retriable=(task_status in (40602, 50000, 50200)))
        results = normalize(payload, keyword=keyword, geo=geo,
                            timeframe=timeframe, category=category)
        for r in results:
            r.cost_usd = self.cost_per_keyword_usd / 4  # attribute evenly across the 4 widgets
        return results

def _map_timeframe(tf: str) -> str:
    """Map Google Trends timeframes to DataForSEO's time_range values."""
    lookup = {
        "today 1-m": "past_30_days",
        "today 3-m": "past_90_days",
        "today 12-m": "past_12_months",
        "today 5-y": "past_5_years",
        "now 1-d": "past_day",
        "now 7-d": "past_7_days",
    }
    return lookup.get(tf, "past_12_months")

# Protocol conformance assertion (fail fast at import time).
_: TrendsProvider = DataForSEOProvider.__new__(DataForSEOProvider)  # noqa: E731
```

- [ ] **Step 4: Run — expect 3 passes.**

- [ ] **Step 5: Commit**

```bash
git add src/collection/trends/providers tests/collection/providers
git commit -m "feat(trends): DataForSEO provider with httpx + ProviderError mapping"
```

**Prompt for subagent:**
> Implement Task 7: `DataForSEOProvider` class using `httpx.AsyncClient`. Use `httpx.MockTransport` in tests (do NOT hit the real API). The provider must raise `ProviderError(retriable=True)` on 5xx/429 and on transient DataForSEO task errors; `ProviderError(retriable=False)` on 4xx and on permanent task errors. All three tests must pass before committing.

---

### Task 8: ProviderSpend (Redis-backed month-to-date tracker)

**Files:**
- Create: `src/collection/trends/budget.py`
- Create: `tests/collection/test_budget.py`

- [ ] **Step 1: Write `tests/collection/test_budget.py`**

```python
import pytest
from src.collection.trends.budget import ProviderSpend

@pytest.mark.asyncio
async def test_add_and_get(fake_redis):
    s = ProviderSpend(fake_redis)
    await s.add("dataforseo", 0.01)
    await s.add("dataforseo", 0.02)
    assert await s.month_to_date("dataforseo") == pytest.approx(0.03)

@pytest.mark.asyncio
async def test_within_cap(fake_redis):
    s = ProviderSpend(fake_redis)
    await s.add("dataforseo", 0.50)
    assert await s.within_cap("dataforseo", cap=1.00) is True
    await s.add("dataforseo", 0.60)
    assert await s.within_cap("dataforseo", cap=1.00) is False

@pytest.mark.asyncio
async def test_snapshot(fake_redis):
    s = ProviderSpend(fake_redis)
    await s.add("dataforseo", 0.10)
    await s.add("serpapi", 0.05)
    snap = await s.snapshot()
    assert snap == {"dataforseo": pytest.approx(0.10), "serpapi": pytest.approx(0.05)}
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Implement `src/collection/trends/budget.py`**

```python
"""Month-to-date spend tracker per provider, backed by Redis."""
from __future__ import annotations
from datetime import datetime, timezone
from redis.asyncio import Redis

class ProviderSpend:
    _HASH_KEY_FMT = "trends:spend:{year}-{month:02d}"

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self) -> str:
        now = datetime.now(timezone.utc)
        return self._HASH_KEY_FMT.format(year=now.year, month=now.month)

    async def add(self, provider: str, amount_usd: float) -> float:
        if amount_usd <= 0:
            return await self.month_to_date(provider)
        # hincrbyfloat returns the new value as a string.
        val = await self._redis.hincrbyfloat(self._key(), provider, amount_usd)
        await self._redis.expire(self._key(), 60 * 60 * 24 * 40)  # trim old months
        return float(val)

    async def month_to_date(self, provider: str) -> float:
        v = await self._redis.hget(self._key(), provider)
        return float(v) if v else 0.0

    async def within_cap(self, provider: str, *, cap: float) -> bool:
        return await self.month_to_date(provider) < cap

    async def snapshot(self) -> dict[str, float]:
        raw = await self._redis.hgetall(self._key())
        return {k: float(v) for k, v in raw.items()}
```

- [ ] **Step 4: Run — expect 3 passes.**

- [ ] **Step 5: Commit**

```bash
git add src/collection/trends/budget.py tests/collection/test_budget.py
git commit -m "feat(trends): Redis-backed ProviderSpend month-to-date tracker"
```

**Prompt for subagent:**
> Implement Task 8: `ProviderSpend` with `add`, `month_to_date`, `within_cap`, `snapshot` methods, keyed by `trends:spend:{YYYY-MM}`. Use `fake_redis` fixture from `tests/collection/conftest.py`. All three tests must pass before committing.

---

## Phase 3 — Queue + Streaming

### Task 9: Pub/sub event publisher

**Files:**
- Create: `src/collection/trends/events.py`
- Create: `tests/collection/test_events.py`

- [ ] **Step 1: Write `tests/collection/test_events.py`**

```python
import json
import pytest
from src.collection.trends.events import publish_event, channel_for

@pytest.mark.asyncio
async def test_publish_and_read(fake_redis):
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(channel_for("job-1"))
    await publish_event(fake_redis, "job-1",
                        {"event": "keyword_completed", "keyword": "python", "n": 4})
    # drain subscribe confirmation + payload
    msg = None
    async for m in pubsub.listen():
        if m["type"] == "message":
            msg = m
            break
    assert msg is not None
    assert json.loads(msg["data"])["keyword"] == "python"
    await pubsub.unsubscribe()
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Implement `src/collection/trends/events.py`**

```python
"""Tiny JSON publish helper and channel naming for job event streams."""
from __future__ import annotations
import json
from typing import Any
from redis.asyncio import Redis

def channel_for(job_id: str) -> str:
    return f"job:{job_id}:events"

async def publish_event(redis: Redis, job_id: str, payload: dict[str, Any]) -> int:
    return await redis.publish(channel_for(job_id), json.dumps(payload))
```

- [ ] **Step 4: Run — expect pass.**

- [ ] **Step 5: Commit**

```bash
git add src/collection/trends/events.py tests/collection/test_events.py
git commit -m "feat(trends): Redis pub/sub event publisher"
```

**Prompt for subagent:**
> Implement Task 9: `channel_for(job_id)` + `publish_event(redis, job_id, payload)`. The test uses the `fake_redis` fixture. One test must pass before committing.

---

### Task 10: TrendsCollectionJob (arq)

**Files:**
- Create: `src/collection/trends/jobs.py`
- Create: `tests/collection/test_jobs.py`
- Modify: `src/collection/queue/settings.py` — uncomment the `jobs` import and register functions.

- [ ] **Step 1: Write `tests/collection/test_jobs.py`**

```python
import json
import pytest
from unittest.mock import AsyncMock

from src.collection.trends.types import CanonicalTrendResult, DataType
from src.collection.trends.jobs import trends_collection_job, _channel_events

class _StubProvider:
    name = "stub"
    supports = frozenset(DataType)
    cost_per_keyword_usd = 0.0

    async def fetch(self, keyword, geo, timeframe, category):
        return [CanonicalTrendResult(
            data_type=DataType.INTEREST_OVER_TIME,
            keyword=keyword, geo=geo, time_range=timeframe, category=category,
            results=[{"time": "2026-04-01", "value": 50}], raw_payload={},
            provider=self.name,
        )]

@pytest.mark.asyncio
async def test_job_processes_all_keywords_and_publishes_events(fake_redis, monkeypatch):
    # Stub out save_trend and router resolution so the test is pure.
    saved = []
    monkeypatch.setattr("src.collection.trends.jobs.save_trend",
                        lambda **kw: saved.append(kw))
    monkeypatch.setattr("src.collection.trends.jobs.build_router_from_config",
                        lambda cfg, redis: _StubRouter())
    ctx = {"redis": fake_redis, "job_id": "job-xyz"}
    out = await trends_collection_job(
        ctx, keywords=["python", "scrapy"],
        geo="US", timeframe="today 12-m", category=0,
        trigger_source="on_demand",
    )
    assert out["keyword_count"] == 2
    assert out["failed"] == 0
    # save_trend called at least once per keyword:
    assert len({k["keyword"] for k in saved}) == 2

class _StubRouter:
    async def fetch(self, keyword, geo, timeframe, category):
        return await _StubProvider().fetch(keyword, geo, timeframe, category)
    async def close(self): ...
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Implement `src/collection/trends/jobs.py`**

```python
"""arq job functions for trends collection."""
from __future__ import annotations
import asyncio
import logging
from typing import Any

from src.collection.queue.redis_client import get_redis
from src.collection.trends.config import TrendsConfig
from src.collection.trends.events import publish_event, channel_for
from src.collection.trends.router import build_router_from_config
from src.ingestion import IngestionService
from src.scrapers.ensembledata.db_helper import save_trend

logger = logging.getLogger(__name__)

async def trends_collection_job(
    ctx: dict[str, Any],
    *,
    keywords: list[str],
    geo: str,
    timeframe: str,
    category: int,
    trigger_source: str = "on_demand",
) -> dict[str, Any]:
    redis = ctx.get("redis") or await get_redis()
    job_id = ctx.get("job_id") or ctx.get("job_try", "unknown")
    cfg = TrendsConfig.from_env()
    router = build_router_from_config(cfg, redis)
    ingestion = IngestionService()
    run = ingestion.start_run(
        "google_trends", acquisition_mode="api", country=geo, language="en",
    )
    run.trigger_source = trigger_source
    run.job_id = str(job_id)

    await publish_event(redis, str(job_id), {
        "event": "job_started", "keywords": keywords, "geo": geo,
    })

    sem = asyncio.Semaphore(cfg.max_concurrent_keywords_per_job)
    failed = 0
    total_cost = 0.0
    providers_used: set[str] = set()

    async def _one(kw: str) -> None:
        nonlocal failed, total_cost
        async with sem:
            await publish_event(redis, str(job_id), {
                "event": "keyword_started", "keyword": kw,
            })
            try:
                results = await router.fetch(kw, geo=geo, timeframe=timeframe, category=category)
            except Exception as e:
                failed += 1
                run.record_error("all_providers_failed")
                await publish_event(redis, str(job_id), {
                    "event": "keyword_failed", "keyword": kw, "error": str(e),
                })
                return
            for r in results:
                total_cost += r.cost_usd
                providers_used.add(r.provider or "unknown")
                # Legacy save_trend signature — preserves existing pipeline.
                save_trend(
                    platform=_platform_for(r.data_type),
                    topic=r.keyword,
                    growth=_growth_from(r),
                    keyword=r.keyword, geo=r.geo,
                    extra_data={"data_type": r.data_type.value,
                                "provider": r.provider,
                                "results": r.results},
                    entity_type="trend", entity_id=f"{r.provider}:{r.keyword}:{r.geo}",
                    sampled_content_refs=[],
                    fetch_metadata={"timeframe": r.time_range, "provider": r.provider},
                    raw_payload=r.raw_payload, run=run,
                )
            await publish_event(redis, str(job_id), {
                "event": "keyword_completed", "keyword": kw,
                "widgets": len(results),
            })

    await asyncio.gather(*[_one(k) for k in keywords])
    await router.close()

    run.provider = ",".join(sorted(providers_used)) or None
    run.cost_usd = round(total_cost, 6)
    ingestion.finish_run(run)

    summary = {"keyword_count": len(keywords), "failed": failed,
               "providers": sorted(providers_used), "cost_usd": round(total_cost, 4)}
    await publish_event(redis, str(job_id), {"event": "job_completed", **summary})
    return summary

def _platform_for(dt) -> str:
    from src.collection.trends.types import DataType
    return {
        DataType.INTEREST_OVER_TIME: "Google Interest",
        DataType.INTEREST_BY_REGION: "Google Regions",
        DataType.RELATED_QUERIES: "Google Related Queries",
        DataType.RELATED_TOPICS: "Google Related Topics",
    }[dt]

def _growth_from(r) -> float:
    vals = [x.get("value") for x in r.results if isinstance(x.get("value"), (int, float))]
    return float(max(vals)) if vals else 0.0

# Expose a constant other modules can import for channel discovery
_channel_events = channel_for
```

- [ ] **Step 4: Uncomment the job import in `src/collection/queue/settings.py` and register:**

```python
from src.collection.trends import jobs  # noqa: F401

class WorkerSettings:
    # ...existing...
    functions = [jobs.trends_collection_job]
```

- [ ] **Step 5: Run — expect pass.**

- [ ] **Step 6: Commit**

```bash
git add src/collection/trends/jobs.py src/collection/queue/settings.py tests/collection/test_jobs.py
git commit -m "feat(trends): TrendsCollectionJob with event publishing and run accounting"
```

**Prompt for subagent:**
> Implement Task 10: `trends_collection_job` arq function. It must: (1) iterate keywords under a semaphore bounded by `TrendsConfig.max_concurrent_keywords_per_job`, (2) call `router.fetch` per keyword, (3) call the existing `save_trend()` helper (from `src.scrapers.ensembledata.db_helper`) for each returned `CanonicalTrendResult`, (4) publish `job_started`, `keyword_started`, `keyword_completed|failed`, `job_completed` pub/sub events, (5) update `ScrapeRun.provider`, `cost_usd`, `job_id`, `trigger_source`. Register it in `WorkerSettings.functions`. One test must pass before committing.

---

### Task 11: `/scrape/v2` enqueue + `/scrape/status/{job_id}`

**Files:**
- Create: `src/api/routes/scrape_v2.py`
- Create: `tests/api/test_scrape_v2.py`

- [ ] **Step 1: Write `tests/api/test_scrape_v2.py`**

```python
import pytest
from fastapi.testclient import TestClient
from src.api.main import app

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TRENDS_V2_ENABLED", "true")
    with TestClient(app) as c:
        yield c

def test_enqueue_returns_job_id(client, monkeypatch):
    async def _fake_enqueue(name, **kw):
        class J: job_id = "job-abc"
        return J()
    monkeypatch.setattr("src.api.routes.scrape_v2._enqueue", _fake_enqueue)
    r = client.post("/scrape/v2", json={
        "keywords": ["python", "scrapy"],
        "geo": "US", "timeframe": "today 12-m", "category": 0,
    })
    assert r.status_code == 202
    assert r.json()["job_id"] == "job-abc"

def test_enqueue_rejects_empty_keywords(client):
    r = client.post("/scrape/v2", json={"keywords": [], "geo": "US"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Implement `src/api/routes/scrape_v2.py`**

```python
"""V2 scrape endpoints: enqueue, status, stream."""
from __future__ import annotations
import json
import uuid
from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from arq import create_pool
from arq.connections import RedisSettings
import os

from src.collection.queue.redis_client import get_redis
from src.collection.trends.events import channel_for

router = APIRouter(prefix="/scrape", tags=["scrape-v2"])

class EnqueueRequest(BaseModel):
    keywords: list[str] = Field(..., min_length=1)
    geo: str = "US"
    timeframe: str = "today 12-m"
    category: int = 0
    trigger_source: str = "on_demand"

async def _enqueue(name: str, **kwargs) -> Any:
    pool = await create_pool(RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://localhost:6379/0")))
    try:
        return await pool.enqueue_job(name, **kwargs, _job_id=f"job-{uuid.uuid4().hex[:12]}")
    finally:
        await pool.aclose()

@router.post("/v2", status_code=202)
async def enqueue(req: EnqueueRequest):
    kws = [k.strip() for k in req.keywords if k.strip()]
    if not kws:
        raise HTTPException(400, "keywords must be non-empty")
    job = await _enqueue(
        "trends_collection_job",
        keywords=kws, geo=req.geo, timeframe=req.timeframe,
        category=req.category, trigger_source=req.trigger_source,
    )
    return {"job_id": job.job_id, "keyword_count": len(kws)}

@router.get("/status/{job_id}")
async def status(job_id: str) -> dict[str, Any]:
    redis = await get_redis()
    # arq stores job state under `arq:job:<id>` but we only need a "known/unknown" check.
    exists = await redis.exists(f"arq:result:{job_id}") or await redis.exists(f"arq:job:{job_id}")
    return {"job_id": job_id, "known": bool(exists)}

@router.get("/stream/{job_id}")
async def stream(job_id: str) -> StreamingResponse:
    redis = await get_redis()

    async def _gen():
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel_for(job_id))
        try:
            yield "event: open\ndata: {}\n\n"
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                data = msg["data"]
                if isinstance(data, (bytes, bytearray)):
                    data = data.decode("utf-8")
                yield f"data: {data}\n\n"
                # Terminate on job_completed.
                try:
                    if json.loads(data).get("event") == "job_completed":
                        yield "event: close\ndata: {}\n\n"
                        return
                except Exception:
                    pass
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    return StreamingResponse(_gen(), media_type="text/event-stream")
```

- [ ] **Step 4: Register in `src/api/main.py`**

Find where other routers are mounted (e.g. `app.include_router(scrape.router)`) and add below:

```python
from src.api.routes import scrape_v2 as _scrape_v2
if os.getenv("TRENDS_V2_ENABLED", "false").lower() in ("1", "true", "yes"):
    app.include_router(_scrape_v2.router)
```

- [ ] **Step 5: Run tests — expect pass.**

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/scrape_v2.py src/api/main.py tests/api/test_scrape_v2.py
git commit -m "feat(api): /scrape/v2, /scrape/status, /scrape/stream (SSE) endpoints"
```

**Prompt for subagent:**
> Implement Task 11: three endpoints under `/scrape/v2`, `/scrape/status/{job_id}`, `/scrape/stream/{job_id}` (SSE). SSE stream terminates on `job_completed`. Register the router in `src/api/main.py` behind `TRENDS_V2_ENABLED`. Both tests must pass before committing.

---

## Phase 4 — Router + Resilience

### Task 12: Circuit breaker wrapper

**Files:**
- Create: `src/collection/trends/circuit_breaker.py`
- Create: `tests/collection/test_circuit_breaker.py`

- [ ] **Step 1: Write `tests/collection/test_circuit_breaker.py`**

```python
import pytest
from src.collection.trends.circuit_breaker import ProviderBreaker, BreakerOpen

@pytest.mark.asyncio
async def test_opens_after_n_failures():
    b = ProviderBreaker("x", fail_max=2, reset_timeout=60)
    async def fail(): raise RuntimeError("boom")
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await b.call(fail)
    with pytest.raises(BreakerOpen):
        await b.call(fail)

@pytest.mark.asyncio
async def test_success_resets_failure_count():
    b = ProviderBreaker("x", fail_max=2, reset_timeout=60)
    async def fail(): raise RuntimeError("boom")
    async def ok(): return "ok"
    with pytest.raises(RuntimeError):
        await b.call(fail)
    assert await b.call(ok) == "ok"
    # Counter reset; still closed after one fresh failure.
    with pytest.raises(RuntimeError):
        await b.call(fail)
    with pytest.raises(RuntimeError):  # the 2nd in the new streak
        await b.call(fail)
    with pytest.raises(BreakerOpen):
        await b.call(fail)
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Implement `src/collection/trends/circuit_breaker.py`**

```python
"""Minimal async-compatible circuit breaker per provider."""
from __future__ import annotations
import asyncio
import time
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")

class BreakerOpen(Exception):
    def __init__(self, name: str):
        super().__init__(f"circuit open: {name}")
        self.name = name

class ProviderBreaker:
    def __init__(self, name: str, *, fail_max: int = 3, reset_timeout: float = 120.0) -> None:
        self.name = name
        self._fail_max = fail_max
        self._reset = reset_timeout
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    async def call(self, fn: Callable[[], Awaitable[T]]) -> T:
        async with self._lock:
            if self._opened_at is not None:
                if time.monotonic() - self._opened_at < self._reset:
                    raise BreakerOpen(self.name)
                # Half-open: allow one probe.
                self._opened_at = None
                self._failures = self._fail_max - 1
        try:
            out = await fn()
        except Exception:
            async with self._lock:
                self._failures += 1
                if self._failures >= self._fail_max:
                    self._opened_at = time.monotonic()
            raise
        async with self._lock:
            self._failures = 0
        return out

    def state(self) -> dict:
        return {"name": self.name, "failures": self._failures,
                "open": self._opened_at is not None}
```

- [ ] **Step 4: Run — expect pass.**

- [ ] **Step 5: Commit**

```bash
git add src/collection/trends/circuit_breaker.py tests/collection/test_circuit_breaker.py
git commit -m "feat(trends): async circuit breaker per provider"
```

**Prompt for subagent:**
> Implement Task 12: `ProviderBreaker` with `call(coro_factory)`, `state()`, and `BreakerOpen` exception. Both tests must pass before committing. Do not depend on `pybreaker` for this — keep it in-house so we can make it fully async.

---

### Task 13: ProviderRouter (chain + budget + breaker)

**Files:**
- Create: `src/collection/trends/router.py`
- Create: `tests/collection/test_router.py`

- [ ] **Step 1: Write `tests/collection/test_router.py`**

```python
import pytest
from src.collection.trends.router import ProviderRouter
from src.collection.trends.budget import ProviderSpend
from src.collection.trends.circuit_breaker import ProviderBreaker
from src.collection.trends.types import CanonicalTrendResult, DataType
from src.collection.trends.providers.base import ProviderError

class _Dummy:
    def __init__(self, name, raise_with=None, cost=0.0):
        self.name = name
        self.supports = frozenset(DataType)
        self.cost_per_keyword_usd = cost
        self._raise = raise_with
    async def fetch(self, keyword, geo, timeframe, category):
        if self._raise:
            raise self._raise
        return [CanonicalTrendResult(
            data_type=DataType.INTEREST_OVER_TIME,
            keyword=keyword, geo=geo, time_range=timeframe, category=category,
            results=[{"value": 1}], raw_payload={}, provider=self.name,
            cost_usd=self.cost_per_keyword_usd,
        )]
    async def close(self): ...

@pytest.mark.asyncio
async def test_first_provider_succeeds(fake_redis):
    router = ProviderRouter(
        providers=[_Dummy("a"), _Dummy("b")],
        spend=ProviderSpend(fake_redis), breakers={}, caps={"a": 10.0, "b": 10.0},
    )
    out = await router.fetch("k", "US", "today 12-m", 0)
    assert [r.provider for r in out] == ["a"]

@pytest.mark.asyncio
async def test_fallback_on_provider_error(fake_redis):
    router = ProviderRouter(
        providers=[_Dummy("a", raise_with=ProviderError("a", "x")), _Dummy("b")],
        spend=ProviderSpend(fake_redis), breakers={}, caps={"a": 10.0, "b": 10.0},
    )
    out = await router.fetch("k", "US", "today 12-m", 0)
    assert [r.provider for r in out] == ["b"]

@pytest.mark.asyncio
async def test_budget_exhausted_skips_provider(fake_redis):
    spend = ProviderSpend(fake_redis)
    await spend.add("a", 999.0)
    router = ProviderRouter(
        providers=[_Dummy("a"), _Dummy("b")],
        spend=spend, breakers={}, caps={"a": 1.0, "b": 10.0},
    )
    out = await router.fetch("k", "US", "today 12-m", 0)
    assert [r.provider for r in out] == ["b"]

@pytest.mark.asyncio
async def test_all_fail_raises(fake_redis):
    router = ProviderRouter(
        providers=[_Dummy("a", raise_with=ProviderError("a", "x")),
                   _Dummy("b", raise_with=ProviderError("b", "y"))],
        spend=ProviderSpend(fake_redis), breakers={}, caps={"a": 10.0, "b": 10.0},
    )
    with pytest.raises(RuntimeError):
        await router.fetch("k", "US", "today 12-m", 0)
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Implement `src/collection/trends/router.py`**

```python
"""ProviderRouter: fallback chain with per-provider circuit breakers and budget caps."""
from __future__ import annotations
import logging
from dataclasses import dataclass

from redis.asyncio import Redis

from src.collection.trends.budget import ProviderSpend
from src.collection.trends.circuit_breaker import ProviderBreaker, BreakerOpen
from src.collection.trends.config import TrendsConfig
from src.collection.trends.providers.base import ProviderError, TrendsProvider
from src.collection.trends.types import CanonicalTrendResult

logger = logging.getLogger(__name__)

@dataclass
class ProviderRouter:
    providers: list[TrendsProvider]
    spend: ProviderSpend
    breakers: dict[str, ProviderBreaker]
    caps: dict[str, float]

    async def fetch(
        self, keyword: str, geo: str, timeframe: str, category: int,
    ) -> list[CanonicalTrendResult]:
        last_err: Exception | None = None
        for p in self.providers:
            if not await self.spend.within_cap(p.name, cap=self.caps.get(p.name, float("inf"))):
                logger.warning("provider=%s skipped (budget_exhausted)", p.name)
                continue
            breaker = self.breakers.get(p.name)
            try:
                if breaker is not None:
                    results = await breaker.call(
                        lambda: p.fetch(keyword, geo, timeframe, category)
                    )
                else:
                    results = await p.fetch(keyword, geo, timeframe, category)
            except BreakerOpen as e:
                logger.warning("provider=%s breaker_open", p.name)
                last_err = e
                continue
            except ProviderError as e:
                logger.warning("provider=%s failed: %s", p.name, e)
                last_err = e
                continue
            except Exception as e:  # non-provider error — don't fall through; bubble up
                logger.exception("provider=%s unexpected", p.name)
                raise
            total = sum(r.cost_usd for r in results)
            if total > 0:
                await self.spend.add(p.name, total)
            return results
        raise RuntimeError(f"all providers exhausted for keyword={keyword!r}: {last_err}")

    async def close(self) -> None:
        for p in self.providers:
            close = getattr(p, "close", None)
            if close:
                await close()

def build_router_from_config(cfg: TrendsConfig, redis: Redis) -> ProviderRouter:
    """Factory: construct ProviderRouter from TrendsConfig + Redis."""
    from src.collection.trends.providers.dataforseo import DataForSEOProvider
    # Tasks 17–18 / 20 will add SerpAPI and LegacyScrapy.
    # For now, this factory returns DataForSEO only if configured.
    providers: list[TrendsProvider] = []
    caps: dict[str, float] = {}
    breakers: dict[str, ProviderBreaker] = {}
    for name in cfg.chain:
        if name == "dataforseo" and cfg.dataforseo_login and cfg.dataforseo_password:
            providers.append(DataForSEOProvider(
                login=cfg.dataforseo_login, password=cfg.dataforseo_password,
            ))
            caps[name] = cfg.dataforseo_monthly_cap_usd
            breakers[name] = ProviderBreaker(name, fail_max=3, reset_timeout=120)
        # serpapi + legacy_scrapy wired in later tasks
    if not providers:
        raise RuntimeError("No trends provider is configured. Set DATAFORSEO_LOGIN/PASSWORD.")
    return ProviderRouter(providers=providers, spend=ProviderSpend(redis),
                          breakers=breakers, caps=caps)
```

- [ ] **Step 4: Run tests — expect 4 passes.**

- [ ] **Step 5: Commit**

```bash
git add src/collection/trends/router.py tests/collection/test_router.py
git commit -m "feat(trends): ProviderRouter with fallback, breaker, and budget guard"
```

**Prompt for subagent:**
> Implement Task 13: `ProviderRouter.fetch()` walks `providers` in order, skipping any over budget cap or with open breaker, and returns the first successful result. Raises `RuntimeError` if all exhausted. The `build_router_from_config` factory wires **only DataForSEO** for now (Tasks 17–18 / 20 add the others). All four tests must pass before committing.

---

## Phase 5 — SerpAPI + admin endpoints

### Task 14: SerpAPI normalizer + cassettes

**Files:**
- Create: `tests/collection/providers/cassettes/serpapi_python_us_timeseries.json`
- Create: `tests/collection/providers/cassettes/serpapi_python_us_geo.json`
- Create: `tests/collection/providers/cassettes/serpapi_python_us_related.json`
- Create: `src/collection/trends/normalizers/serpapi.py`
- Create: `tests/collection/normalizers/test_serpapi.py`

- [ ] **Step 1: Create cassettes (minimal viable shape per SerpAPI Google Trends docs)**

`serpapi_python_us_timeseries.json`:
```json
{"search_metadata": {"status": "Success"},
 "interest_over_time": {"timeline_data": [
   {"date": "2026-04-01", "values": [{"extracted_value": 75}]}
 ]}}
```
`serpapi_python_us_geo.json`:
```json
{"search_metadata": {"status": "Success"},
 "interest_by_region": [
   {"location": "California", "value": "100", "extracted_value": 100, "geo": "US-CA"}
 ]}
```
`serpapi_python_us_related.json`:
```json
{"search_metadata": {"status": "Success"},
 "related_queries": {
   "top":    [{"query": "python tutorial", "extracted_value": 100}],
   "rising": [{"query": "python 3.13", "extracted_value": 2500}]
 },
 "related_topics": {
   "top":    [{"topic": {"title": "Python (language)"}, "extracted_value": 100}],
   "rising": [{"topic": {"title": "Python 3.13"},      "extracted_value": 5000}]
 }}
```

- [ ] **Step 2: Write `tests/collection/normalizers/test_serpapi.py`**

```python
import json
from pathlib import Path
import pytest
from src.collection.trends.types import DataType
from src.collection.trends.normalizers.serpapi import (
    normalize_timeseries, normalize_geo, normalize_related,
)

CASSETTES = Path(__file__).parent.parent / "providers" / "cassettes"

def _load(name): return json.loads((CASSETTES / name).read_text())

def test_timeseries():
    r = normalize_timeseries(_load("serpapi_python_us_timeseries.json"),
                             keyword="python", geo="US",
                             timeframe="today 12-m", category=0)
    assert r.data_type == DataType.INTEREST_OVER_TIME
    assert r.results[0]["value"] == 75

def test_geo():
    r = normalize_geo(_load("serpapi_python_us_geo.json"), keyword="python", geo="US",
                      timeframe="today 12-m", category=0)
    assert r.data_type == DataType.INTEREST_BY_REGION
    assert r.results[0]["geoName"] == "California"

def test_related_splits_queries_and_topics():
    q, t = normalize_related(_load("serpapi_python_us_related.json"), keyword="python",
                             geo="US", timeframe="today 12-m", category=0)
    assert q.data_type == DataType.RELATED_QUERIES
    assert t.data_type == DataType.RELATED_TOPICS
    assert {row["type"] for row in q.results} == {"top", "rising"}
```

- [ ] **Step 3: Run — expect failure.**

- [ ] **Step 4: Implement `src/collection/trends/normalizers/serpapi.py`**

```python
"""Normalize SerpAPI Google Trends responses → CanonicalTrendResult."""
from __future__ import annotations
from typing import Any

from src.collection.trends.types import CanonicalTrendResult, DataType

def _wrap(dt: DataType, rows: list[dict[str, Any]], raw: dict[str, Any],
          keyword: str, geo: str, timeframe: str, category: int) -> CanonicalTrendResult:
    return CanonicalTrendResult(
        data_type=dt, keyword=keyword, geo=geo, time_range=timeframe, category=category,
        results=rows, raw_payload=raw, provider="serpapi",
    )

def normalize_timeseries(payload, *, keyword, geo, timeframe, category):
    tl = payload.get("interest_over_time", {}).get("timeline_data") or []
    rows = [{"time": e.get("date"),
             "value": (e.get("values") or [{}])[0].get("extracted_value", 0),
             "isPartial": False} for e in tl]
    return _wrap(DataType.INTEREST_OVER_TIME, rows, payload, keyword, geo, timeframe, category)

def normalize_geo(payload, *, keyword, geo, timeframe, category):
    rows = [{"geoName": e.get("location"),
             "geoCode": e.get("geo"),
             "value":   e.get("extracted_value", 0)}
            for e in payload.get("interest_by_region", [])]
    return _wrap(DataType.INTEREST_BY_REGION, rows, payload, keyword, geo, timeframe, category)

def normalize_related(payload, *, keyword, geo, timeframe, category):
    def _rows(section, label_field):
        out = []
        for bucket in ("top", "rising"):
            for e in (payload.get(section) or {}).get(bucket) or []:
                out.append({
                    "query": e.get("query"),
                    "topic": (e.get("topic") or {}).get("title"),
                    "value": e.get("extracted_value", 0),
                    "type": bucket,
                })
        return out
    q = _wrap(DataType.RELATED_QUERIES, _rows("related_queries", "query"),
              payload, keyword, geo, timeframe, category)
    t = _wrap(DataType.RELATED_TOPICS, _rows("related_topics", "topic"),
              payload, keyword, geo, timeframe, category)
    return q, t
```

- [ ] **Step 5: Run — expect pass.**

- [ ] **Step 6: Commit**

```bash
git add tests/collection/providers/cassettes tests/collection/normalizers src/collection/trends/normalizers/serpapi.py
git commit -m "feat(trends): SerpAPI cassettes + normalizer"
```

**Prompt for subagent:**
> Implement Task 14: three cassette JSON files + `src/collection/trends/normalizers/serpapi.py` with `normalize_timeseries`, `normalize_geo`, `normalize_related` (the last returns a `(queries, topics)` tuple). Three tests must pass before committing.

---

### Task 15: SerpAPIProvider

**Files:**
- Create: `src/collection/trends/providers/serpapi.py`
- Create: `tests/collection/providers/test_serpapi.py`

- [ ] **Step 1: Write `tests/collection/providers/test_serpapi.py`**

```python
import json
from pathlib import Path
import httpx
import pytest
from src.collection.trends.providers.serpapi import SerpAPIProvider

CASSETTES = Path(__file__).parent / "cassettes"

def _route(request: httpx.Request) -> httpx.Response:
    params = dict(request.url.params)
    dt = params.get("data_type")
    fname = {
        "TIMESERIES":          "serpapi_python_us_timeseries.json",
        "GEO_MAP":             "serpapi_python_us_geo.json",
        "RELATED_QUERIES":     "serpapi_python_us_related.json",
        "RELATED_TOPICS":      "serpapi_python_us_related.json",
    }.get(dt)
    return httpx.Response(200, text=(CASSETTES / fname).read_text())

@pytest.mark.asyncio
async def test_fetch_returns_four_results():
    p = SerpAPIProvider(api_key="k", transport=httpx.MockTransport(_route))
    out = await p.fetch("python", geo="US", timeframe="today 12-m", category=0)
    assert len(out) == 4
    assert {r.data_type.value for r in out} == {
        "interest_over_time", "interest_by_region",
        "related_queries", "related_topics",
    }
    await p.close()
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Implement `src/collection/trends/providers/serpapi.py`**

```python
"""SerpAPI Google Trends provider (1 call per widget)."""
from __future__ import annotations
import asyncio
import httpx

from src.collection.trends.normalizers.serpapi import (
    normalize_timeseries, normalize_geo, normalize_related,
)
from src.collection.trends.providers.base import ProviderError, TrendsProvider
from src.collection.trends.types import CanonicalTrendResult, DataType

class SerpAPIProvider:
    name = "serpapi"
    supports = frozenset(DataType)
    cost_per_keyword_usd = 0.004  # 4 widgets × ~$0.001 each on Developer tier

    _URL = "https://serpapi.com/search.json"

    def __init__(self, *, api_key: str,
                 transport: httpx.AsyncBaseTransport | None = None,
                 timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("SerpAPIProvider requires api_key")
        self._key = api_key
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def close(self) -> None:
        await self._client.aclose()

    async def _one(self, params: dict) -> dict:
        params = {**params, "engine": "google_trends", "api_key": self._key}
        try:
            resp = await self._client.get(self._URL, params=params)
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"transport: {e}", retriable=True) from e
        if resp.status_code == 429 or resp.status_code >= 500:
            raise ProviderError(self.name, f"http {resp.status_code}", retriable=True)
        if resp.status_code >= 400:
            raise ProviderError(self.name, f"http {resp.status_code}", retriable=False)
        return resp.json()

    async def fetch(self, keyword, geo, timeframe, category) -> list[CanonicalTrendResult]:
        base = {"q": keyword, "geo": geo, "date": timeframe, "cat": str(category or 0)}
        ts, gm, rel = await asyncio.gather(
            self._one({**base, "data_type": "TIMESERIES"}),
            self._one({**base, "data_type": "GEO_MAP"}),
            self._one({**base, "data_type": "RELATED_QUERIES"}),
        )
        # RELATED_TOPICS is the same cassette in tests; in prod it's a second call.
        topics = await self._one({**base, "data_type": "RELATED_TOPICS"})

        results: list[CanonicalTrendResult] = []
        results.append(normalize_timeseries(ts, keyword=keyword, geo=geo,
                                            timeframe=timeframe, category=category))
        results.append(normalize_geo(gm, keyword=keyword, geo=geo,
                                     timeframe=timeframe, category=category))
        q, _ = normalize_related(rel, keyword=keyword, geo=geo,
                                 timeframe=timeframe, category=category)
        _, t = normalize_related(topics, keyword=keyword, geo=geo,
                                 timeframe=timeframe, category=category)
        results.extend([q, t])
        for r in results:
            r.cost_usd = self.cost_per_keyword_usd / 4
        return results

_: TrendsProvider = SerpAPIProvider.__new__(SerpAPIProvider)  # noqa
```

- [ ] **Step 4: Update `build_router_from_config` in `src/collection/trends/router.py` to add SerpAPI**

Inside the for loop, after the DataForSEO branch:

```python
        elif name == "serpapi" and cfg.serpapi_key:
            from src.collection.trends.providers.serpapi import SerpAPIProvider
            providers.append(SerpAPIProvider(api_key=cfg.serpapi_key))
            caps[name] = cfg.serpapi_monthly_cap_usd
            breakers[name] = ProviderBreaker(name, fail_max=3, reset_timeout=120)
```

- [ ] **Step 5: Run tests — expect pass.**

- [ ] **Step 6: Commit**

```bash
git add src/collection/trends/providers/serpapi.py src/collection/trends/router.py tests/collection/providers/test_serpapi.py
git commit -m "feat(trends): SerpAPI provider + wire into router factory"
```

**Prompt for subagent:**
> Implement Task 15: `SerpAPIProvider` that fetches TIMESERIES, GEO_MAP, RELATED_QUERIES, RELATED_TOPICS concurrently with `asyncio.gather`. Use `httpx.MockTransport` in tests. Also extend `build_router_from_config` to append SerpAPI when configured. One test must pass before committing.

---

### Task 16: Admin provider endpoints

**Files:**
- Create: `src/api/routes/admin_providers.py`
- Create: `tests/api/test_admin_providers.py`
- Modify: `src/api/main.py` — register the admin router behind `TRENDS_V2_ENABLED`

- [ ] **Step 1: Write `tests/api/test_admin_providers.py`**

```python
import pytest
from fastapi.testclient import TestClient
from src.api.main import app

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TRENDS_V2_ENABLED", "true")
    with TestClient(app) as c:
        yield c

def test_spend_returns_snapshot(client, monkeypatch):
    async def _snap(): return {"dataforseo": 1.23}
    monkeypatch.setattr(
        "src.api.routes.admin_providers._spend_snapshot", _snap,
    )
    r = client.get("/admin/providers/spend")
    assert r.status_code == 200
    assert r.json()["month_to_date"]["dataforseo"] == 1.23

def test_status_returns_breaker_states(client, monkeypatch):
    async def _stat(): return [{"name": "dataforseo", "failures": 0, "open": False}]
    monkeypatch.setattr(
        "src.api.routes.admin_providers._breaker_states", _stat,
    )
    r = client.get("/admin/providers/status")
    assert r.status_code == 200
    assert r.json()["providers"][0]["name"] == "dataforseo"
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Implement `src/api/routes/admin_providers.py`**

```python
"""Read-only provider health + spend endpoints."""
from __future__ import annotations
from fastapi import APIRouter

from src.collection.queue.redis_client import get_redis
from src.collection.trends.budget import ProviderSpend
from src.collection.trends.config import TrendsConfig

router = APIRouter(prefix="/admin/providers", tags=["admin"])

# These are module-level functions so tests can monkey-patch them cleanly.
async def _spend_snapshot() -> dict[str, float]:
    redis = await get_redis()
    return await ProviderSpend(redis).snapshot()

async def _breaker_states() -> list[dict]:
    # Breaker state is in-process per worker; this endpoint reports the API
    # process's view. The worker has its own view (out of scope here).
    from src.collection.trends import router as _router_mod
    return [b.state() for b in getattr(_router_mod, "_REGISTERED_BREAKERS", [])]

@router.get("/spend")
async def spend():
    cfg = TrendsConfig.from_env()
    return {
        "monthly_budget_usd": cfg.monthly_budget_usd,
        "caps": {
            "dataforseo": cfg.dataforseo_monthly_cap_usd,
            "serpapi":    cfg.serpapi_monthly_cap_usd,
        },
        "month_to_date": await _spend_snapshot(),
    }

@router.get("/status")
async def status():
    return {"providers": await _breaker_states()}
```

- [ ] **Step 4: Register in `src/api/main.py`, right beside the `scrape_v2` registration:**

```python
from src.api.routes import admin_providers as _admin_providers
if os.getenv("TRENDS_V2_ENABLED", "false").lower() in ("1", "true", "yes"):
    app.include_router(_admin_providers.router)
```

- [ ] **Step 5: Run tests — expect pass.**

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/admin_providers.py src/api/main.py tests/api/test_admin_providers.py
git commit -m "feat(api): /admin/providers/spend + /status"
```

**Prompt for subagent:**
> Implement Task 16: two GET endpoints under `/admin/providers/`. Both tests must pass before committing. Do not add auth gates here — the endpoints inherit whatever global admin-auth middleware already protects `/admin/*` (check `src/api/main.py` for existing admin guards and make sure this router is included after any such middleware).

---

## Phase 5b — Additional providers (multi-vendor depth)

> **Why a separate phase:** Tasks 14–16 deliver a working *single-paid-provider* pipeline (SerpAPI + router + admin endpoints). Phase 5b widens the chain so that a single-vendor outage cannot collapse collection. Each task here follows the same template (cassette → normalizer → provider → tests) and adds **one** provider to the chain. Tasks 22–24 are independent and may be tackled in any order; Task 25 is optional and only relevant once Phase 8 (warmup) is in motion.

### Task 22: SearchAPIProvider (Tier-1 paid failover)

**Files:**
- Create: `tests/collection/providers/cassettes/searchapi_python_us_timeseries.json` (and one cassette per `data_type` — 4 total)
- Create: `src/collection/trends/normalizers/searchapi.py`
- Create: `src/collection/trends/providers/searchapi.py`
- Create: `tests/collection/normalizers/test_searchapi.py`
- Create: `tests/collection/providers/test_searchapi.py`

**API surface to implement:**
- Endpoint: `GET https://www.searchapi.io/api/v1/search`
- Query params: `engine=google_trends`, `q=<keyword>`, `data_type=TIMESERIES|GEO_MAP_0|RELATED_QUERIES|RELATED_TOPICS`, `geo=<geo>`, `time=<timeframe>`, `cat=<category>`, `api_key=<SEARCHAPI_KEY>`
- Response shape: intentionally **SerpAPI-compatible**. Top-level keys (`interest_over_time`, `interest_by_region`, `related_queries`, `related_topics`) mirror SerpAPI 1:1 in most cases.
- Auth: `SEARCHAPI_KEY` env var (URL query param, **not** a header).
- Cost per call (for `cost_per_keyword_usd`): `0.004` × 4 = `0.016` per keyword (Starter plan, 10k searches at $40).

- [ ] **Step 1: Capture 4 real-shape cassettes**
  Make one live call per `data_type` against `q=python&geo=US`, save the raw JSON. Strip the `api_key` from any echoed request URL before committing.

- [ ] **Step 2: Implement the normalizer**
  Because the shape is SerpAPI-compatible, start by copy-paste-importing from `src/collection/trends/normalizers/serpapi.py`. The differences are typically: (a) `interest_by_region` may be nested under `region_interest` instead of `interest_by_region` in some response variants — handle both; (b) `geo_map` is sometimes called `geo_map_0`; (c) `related_topics` items use `topic_title` rather than `title`. Write a small `_compat()` helper to normalize the key differences and then delegate to a shared mapper.

- [ ] **Step 3: Implement `SearchAPIProvider`**
  Subclass nothing — implement the `TrendsProvider` Protocol directly. Construction: `SearchAPIProvider(api_key: str, transport: httpx.AsyncBaseTransport | None = None)`. The transport parameter is required so tests can inject `httpx.MockTransport`. `name = "searchapi"`. `supports = frozenset({DataType.TIMESERIES, DataType.GEO, DataType.RELATED_QUERIES, DataType.RELATED_TOPICS})`. `cost_per_keyword_usd = 0.016`. `fetch()` issues 4 parallel GETs via `asyncio.gather` (one per `data_type`), feeds each response into the normalizer, and concatenates results.

- [ ] **Step 4: Tests**
  Mirror `tests/collection/providers/test_serpapi.py` exactly: a happy-path test that asserts 4 `CanonicalTrendResult` rows, a 4xx error test, a 429 retry test (with backoff capped at 1s in tests).

- [ ] **Step 5: Wire into router config**
  In `src/collection/trends/router.py`'s `build_default_chain()`, append `SearchAPIProvider` after `SerpAPIProvider` (when `SEARCHAPI_KEY` is set). In `tests/collection/test_router.py`, add a test asserting fallback from SerpAPI → SearchAPI on a `ProviderError` from SerpAPI.

- [ ] **Step 6: Commit**
```bash
git add -A
git commit -m "feat(trends): SearchAPI.io provider as Tier-1 failover"
```

**Prompt for subagent:**
> Implement Task 22: SearchAPI.io provider end-to-end (cassettes + normalizer + provider + tests + router wiring). Reuse Task 14/15 (SerpAPI) as the structural template — SearchAPI.io's response shape is SerpAPI-compatible with a few key renames documented in the task. All tests must pass and the router-fallback integration test must demonstrate SerpAPI → SearchAPI fallback. Cassettes must contain no live API keys.

---

### Task 23: BrightDataProvider OR OxylabsProvider (Tier-2 deep fallback)

> **Decision required from owner before starting:** which scraping-infra vendor are we using? **Pick ONE.** Both are documented; only ship the one matching your procurement.

**Files (Bright Data variant):**
- Create: `tests/collection/providers/cassettes/brightdata_python_us.json`
- Create: `src/collection/trends/normalizers/brightdata.py`
- Create: `src/collection/trends/providers/brightdata.py`
- Create: `tests/collection/normalizers/test_brightdata.py`
- Create: `tests/collection/providers/test_brightdata.py`

**Files (Oxylabs variant):**
- Create: `tests/collection/providers/cassettes/oxylabs_python_us.json`
- Create: `src/collection/trends/normalizers/oxylabs.py`
- Create: `src/collection/trends/providers/oxylabs.py`
- Create: `tests/collection/normalizers/test_oxylabs.py`
- Create: `tests/collection/providers/test_oxylabs.py`

**API surface — Bright Data:**
- Endpoint: `POST https://api.brightdata.com/dca/trigger?collector=<COLLECTOR_ID>` then poll `GET https://api.brightdata.com/dca/dataset?id=<snapshot_id>`.
- Auth: `Authorization: Bearer $BRIGHTDATA_API_TOKEN` + `BRIGHTDATA_ZONE` for zone selection.
- Returns all four widgets in a single dataset row per keyword. Cost: `~$0.002/req` (PAYG).

**API surface — Oxylabs:**
- Endpoint: `POST https://realtime.oxylabs.io/v1/queries` with body `{"source": "google_trends_explore", "query": "<keyword>", "geo_location": "<geo>"}`.
- Auth: HTTP Basic with `OXYLABS_USERNAME:OXYLABS_PASSWORD`.
- Returns all four widgets in `results[0].content`. Cost: `~$0.002/req`.

- [ ] **Step 1: Capture one cassette** by issuing a single live request and saving the response. **Strip credentials.**

- [ ] **Step 2: Implement the normalizer.** Both vendors return one consolidated payload per keyword (unlike SerpAPI's 4-call pattern). The normalizer therefore returns 4 `CanonicalTrendResult` rows from a *single* input dict. Map each widget block carefully — the field names differ from SerpAPI (e.g. Bright Data uses `interest_over_time.timeline_data[].values[].value` for the int value).

- [ ] **Step 3: Implement the provider.** `BrightDataProvider(api_token, zone, collector_id, transport=None)` or `OxylabsProvider(username, password, transport=None)`. `name = "brightdata"` or `"oxylabs"`. `supports = frozenset(DataType)` (all four). `cost_per_keyword_usd = 0.002`. For Bright Data, `fetch()` is a trigger + poll pattern with a 60s timeout and 2s poll interval; expose the timeout as a constructor arg so tests can shrink it.

- [ ] **Step 4: Tests.** Same shape as Task 22's tests, plus a Bright-Data-specific test for the trigger-then-poll loop using a fake transport that returns "pending" twice and then "ready".

- [ ] **Step 5: Router wiring.** Append after `SearchAPIProvider` in the default chain when credentials are present. Add an integration test in `tests/collection/test_router.py`: simulate both SerpAPI *and* SearchAPI failing → assert Bright Data (or Oxylabs) is invoked.

- [ ] **Step 6: Commit**
```bash
git commit -m "feat(trends): Bright Data SERP API provider as Tier-2 deep fallback"
# OR
git commit -m "feat(trends): Oxylabs SERP Scraper API provider as Tier-2 deep fallback"
```

**Prompt for subagent:**
> Implement Task 23 against **<Bright Data | Oxylabs>** — the user must tell you which one. Follow the trigger-then-poll pattern for Bright Data, or the synchronous realtime endpoint for Oxylabs. Cassette must be vendored with credentials stripped. Router fallback test must show Tier-1 (SerpAPI + SearchAPI) failure correctly cascades to Tier-2.

---

### Task 24: ApifyTrendsProvider (bulk / warmup)

**Files:**
- Create: `tests/collection/providers/cassettes/apify_python_us.json`
- Create: `src/collection/trends/normalizers/apify.py`
- Create: `src/collection/trends/providers/apify.py`
- Create: `tests/collection/normalizers/test_apify.py`
- Create: `tests/collection/providers/test_apify.py`

**API surface:**
- Use the `apify-client` Python SDK (`pip install apify-client`).
- Actor: `emastra/google-trends-scraper` (or whichever the team standardizes on; the actor id is configurable via `APIFY_TRENDS_ACTOR`).
- Pattern: `client.actor(actor_id).call(run_input={...})` returns when the actor finishes; then `client.dataset(default_dataset_id).list_items()` yields the rows. There is a 10–30 s cold-start.
- Auth: `APIFY_TOKEN` env var.
- Cost: actor consumes Apify compute units; bill at ~$0.25/1k results.

- [ ] **Step 1: Capture a cassette.** Trigger one live actor run, copy the dataset items JSON, save as the cassette. The provider's tests will replay this without hitting the Apify API.

- [ ] **Step 2: Normalizer** maps actor output rows → `CanonicalTrendResult`. The actor returns one row per keyword with nested widget data; map to 4 canonical rows.

- [ ] **Step 3: Provider** wraps `apify_client.ApifyClientAsync`. **Important:** because of the cold-start, this provider must declare `cost_per_keyword_usd = 0.001` but also expose a `warmup_only: bool = True` class attribute. The router must respect this attribute and only invoke `ApifyTrendsProvider` when `trigger_source == "warmup"`. Add the corresponding gate in `ProviderRouter.fetch()` and a unit test for it in `tests/collection/test_router.py`.

- [ ] **Step 4: Tests** — happy path against the cassette, plus a router test confirming Apify is **skipped** for `trigger_source="on_demand"`.

- [ ] **Step 5: Wire into the warmup chain.** In `src/collection/trends/router.py`, expose `build_warmup_chain()` that returns `[ApifyTrendsProvider, SearchAPIProvider, LegacyScrapyProvider]`. The on-demand `build_default_chain()` does **not** include Apify.

- [ ] **Step 6: Commit**
```bash
git commit -m "feat(trends): Apify google-trends-scraper provider for bulk/warmup runs"
```

**Prompt for subagent:**
> Implement Task 24: Apify provider gated to `trigger_source="warmup"` only. The hot-path on-demand chain must not include Apify (cold-start would blow the latency SLO). Router unit tests must cover both the "skipped on on_demand" and "invoked on warmup" branches.

---

### Task 25: BigQuery seed for warmup keyword discovery (optional)

> **Optional and deferrable.** Only implement if Phase 8 (warmup) is being prioritized and the team wants Google's official top-25 trending list as the warmup seed (rather than relying solely on internal virality scores). Free at our volume.

**Files:**
- Create: `src/collection/trends/seeds/__init__.py`
- Create: `src/collection/trends/seeds/bigquery.py`
- Create: `tests/collection/seeds/test_bigquery.py`

**Implementation:**
- Single function `async def fetch_top_terms(geo: str, limit: int = 50) -> list[str]` that queries `bigquery-public-data.google_trends.top_terms` for the given country (US-only is supported by the public dataset; other geos return empty and the warmup falls back to the existing virality-based seed).
- Auth via `google-cloud-bigquery` SDK + service account JSON (`GOOGLE_APPLICATION_CREDENTIALS` env var).
- Gated by `BIGQUERY_TRENDS_ENABLED=true` config flag — default off.

- [ ] **Step 1: Test with a stubbed BigQuery client returning a fake row iterator.**
- [ ] **Step 2: Implement the query** (`SELECT term FROM \`bigquery-public-data.google_trends.top_terms\` WHERE refresh_date = CURRENT_DATE() AND country_name = @country GROUP BY term ORDER BY MAX(score) DESC LIMIT @limit`).
- [ ] **Step 3: Wire into `WarmupJob`** (Task 20): if `BIGQUERY_TRENDS_ENABLED`, prepend BigQuery-seeded keywords to the virality-based list, deduplicating.
- [ ] **Step 4: Commit**
```bash
git commit -m "feat(trends): optional BigQuery seed for warmup keyword discovery"
```

**Prompt for subagent:**
> Implement Task 25 only if the user has set `BIGQUERY_TRENDS_ENABLED=true` and provided a service-account JSON. Otherwise stop and report that the task is intentionally deferred. The function must degrade gracefully (return `[]` and log a warning) when BigQuery is misconfigured — never crash the warmup job.

---

## Phase 6 — Legacy Scrapy provider

### Task 17: LegacyScrapyProvider (subprocess wrapper → canonical)

**Files:**
- Create: `src/collection/trends/providers/legacy_scrapy.py`
- Create: `src/collection/trends/normalizers/legacy_scrapy.py`
- Create: `tests/collection/providers/test_legacy_scrapy.py`
- Create: `tests/collection/normalizers/test_legacy_scrapy.py`

- [ ] **Step 1: Write `tests/collection/normalizers/test_legacy_scrapy.py`**

```python
from src.collection.trends.types import DataType
from src.collection.trends.normalizers.legacy_scrapy import from_scrapy_item

def test_interest_over_time_item():
    item = {"data_type": "interest_over_time", "keyword": "python",
            "geo": "US", "time_range": "today 12-m", "category": 0,
            "results": [{"time": "2026-04-01", "value": 50, "isPartial": False}]}
    r = from_scrapy_item(item)
    assert r.provider == "legacy_scrapy"
    assert r.data_type == DataType.INTEREST_OVER_TIME
    assert r.results[0]["value"] == 50
```

- [ ] **Step 2: Implement `src/collection/trends/normalizers/legacy_scrapy.py`**

```python
"""Convert the existing GoogleTrendsItem dict into CanonicalTrendResult."""
from __future__ import annotations
from src.collection.trends.types import CanonicalTrendResult, DataType

def from_scrapy_item(item: dict) -> CanonicalTrendResult:
    dt = DataType(item["data_type"])
    return CanonicalTrendResult(
        data_type=dt,
        keyword=item.get("keyword", ""),
        geo=item.get("geo", ""),
        time_range=item.get("time_range", ""),
        category=item.get("category", 0) or 0,
        results=item.get("results") or [],
        raw_payload=item,
        provider="legacy_scrapy",
    )
```

- [ ] **Step 3: Write `tests/collection/providers/test_legacy_scrapy.py`**

```python
import asyncio
import pytest
from src.collection.trends.providers.legacy_scrapy import LegacyScrapyProvider
from src.collection.trends.providers.base import ProviderError

@pytest.mark.asyncio
async def test_fetch_reads_items_from_stub_runner(monkeypatch):
    async def fake_run(keyword, geo, timeframe, category, project_dir):
        return [
            {"data_type": "interest_over_time", "keyword": keyword, "geo": geo,
             "time_range": timeframe, "category": category,
             "results": [{"time": "2026-04-01", "value": 25}]},
        ]
    p = LegacyScrapyProvider(runner=fake_run)
    out = await p.fetch("python", geo="US", timeframe="today 12-m", category=0)
    assert len(out) == 1
    assert out[0].provider == "legacy_scrapy"

@pytest.mark.asyncio
async def test_fetch_raises_provider_error_on_runner_failure():
    async def boom(*a, **kw):
        raise RuntimeError("scrapy died")
    p = LegacyScrapyProvider(runner=boom)
    with pytest.raises(ProviderError):
        await p.fetch("python", geo="US", timeframe="today 12-m", category=0)
```

- [ ] **Step 4: Implement `src/collection/trends/providers/legacy_scrapy.py`**

```python
"""Wrap the existing Scrapy google_trends spider as a TrendsProvider.

Invokes the spider via subprocess, reads JSONL output from a temp file, and
normalizes each item to CanonicalTrendResult. Intended as a last-resort
fallback; cost_per_keyword_usd=0 but latency is high.
"""
from __future__ import annotations
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from typing import Awaitable, Callable

from src.collection.trends.normalizers.legacy_scrapy import from_scrapy_item
from src.collection.trends.providers.base import ProviderError, TrendsProvider
from src.collection.trends.types import CanonicalTrendResult, DataType

Runner = Callable[[str, str, str, int, str], Awaitable[list[dict]]]

async def _default_runner(keyword, geo, timeframe, category, project_dir) -> list[dict]:
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        out_path = f.name
    cmd = [
        sys.executable, "-m", "scrapy", "crawl", "google_trends",
        "-a", f"keywords={keyword}",
        "-a", f"geo={geo}",
        "-a", f"timeframe={timeframe}",
        "-a", f"category={category}",
        "-O", f"{out_path}:jsonlines",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=project_dir,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    _, err = await asyncio.wait_for(proc.communicate(), timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"scrapy exit {proc.returncode}: {err.decode('utf-8', 'ignore')[:500]}")
    items: list[dict] = []
    try:
        with open(out_path, encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass
    return items

class LegacyScrapyProvider:
    name = "legacy_scrapy"
    supports = frozenset(DataType)
    cost_per_keyword_usd = 0.0

    def __init__(self, *, runner: Runner | None = None,
                 project_dir: str | None = None) -> None:
        self._runner = runner or _default_runner
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        self._project_dir = project_dir or os.path.join(root, "src", "scrapers", "google_trends_scraper")

    async def close(self) -> None:
        pass

    async def fetch(self, keyword, geo, timeframe, category) -> list[CanonicalTrendResult]:
        try:
            items = await self._runner(keyword, geo, timeframe, category, self._project_dir)
        except Exception as e:
            raise ProviderError(self.name, f"runner: {e}", retriable=True) from e
        return [from_scrapy_item(it) for it in items if it.get("data_type")]

_: TrendsProvider = LegacyScrapyProvider.__new__(LegacyScrapyProvider)  # noqa
```

- [ ] **Step 5: Update `build_router_from_config` to append legacy last**

Inside the for loop:

```python
        elif name == "legacy_scrapy":
            from src.collection.trends.providers.legacy_scrapy import LegacyScrapyProvider
            providers.append(LegacyScrapyProvider())
            caps[name] = float("inf")  # free; no cap
            breakers[name] = ProviderBreaker(name, fail_max=2, reset_timeout=300)
```

- [ ] **Step 6: Run tests — expect pass.**

- [ ] **Step 7: Commit**

```bash
git add src/collection/trends/providers/legacy_scrapy.py src/collection/trends/normalizers/legacy_scrapy.py src/collection/trends/router.py tests/collection/providers/test_legacy_scrapy.py tests/collection/normalizers/test_legacy_scrapy.py
git commit -m "feat(trends): LegacyScrapyProvider as last-resort fallback"
```

**Prompt for subagent:**
> Implement Task 17: `LegacyScrapyProvider` that invokes the existing Scrapy spider via `asyncio.create_subprocess_exec` and reads JSONL output. Pass a `runner` callable so tests can stub it. Extend `build_router_from_config` to append it when `legacy_scrapy` is in the chain. All three tests must pass before committing.

---

## Phase 7 — Cutover

### Task 18: Unified freshness check

**Files:**
- Modify: `src/api/routes/trends.py` (rewrite `_needs_scrape`)
- Create: `tests/api/test_needs_scrape_v2.py`

- [ ] **Step 1: Locate the current `_needs_scrape` function** (`grep -n '_needs_scrape' src/api/routes/trends.py`) and read it.

- [ ] **Step 2: Write `tests/api/test_needs_scrape_v2.py`**

```python
from datetime import datetime, timedelta, timezone
import pytest
from src.api.routes.trends import _needs_scrape
from src.db.models import CanonicalTrendSignal
from src.db.connection import session_scope

@pytest.fixture
def _fresh_signal():
    with session_scope() as s:
        sig = CanonicalTrendSignal(
            source="google_trends", entity_type="keyword",
            entity_id="unit-test-python", label="python", normalized_label="python",
            country="US", time_bucket_start=datetime.now(timezone.utc),
            granularity="hour", retrieved_at=datetime.now(timezone.utc),
            idempotency_key="unit-test-python-US-now",
        )
        s.add(sig)
        s.commit()
        yield sig
        s.delete(sig); s.commit()

def test_fresh_signal_means_no_scrape(_fresh_signal):
    assert _needs_scrape(keyword="python", geo="US", freshness_hours=24) is False

def test_missing_signal_means_scrape():
    assert _needs_scrape(keyword="does-not-exist", geo="US", freshness_hours=24) is True
```

- [ ] **Step 3: Rewrite `_needs_scrape` in `src/api/routes/trends.py`**

```python
def _needs_scrape(keyword: str, geo: str, freshness_hours: int = 24) -> bool:
    """True if no canonical signal for (google_trends, keyword, geo) within the window."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import and_
    from src.db.connection import session_scope
    from src.db.models import CanonicalTrendSignal

    threshold = datetime.now(timezone.utc) - timedelta(hours=freshness_hours)
    with session_scope() as s:
        row = (s.query(CanonicalTrendSignal.id)
               .filter(and_(
                   CanonicalTrendSignal.source == "google_trends",
                   CanonicalTrendSignal.entity_id == keyword,
                   CanonicalTrendSignal.country == geo,
                   CanonicalTrendSignal.time_bucket_start >= threshold,
               ))
               .first())
    return row is None
```

Adjust existing callers if they passed a different signature — the skill here is mechanical find/replace.

- [ ] **Step 4: Run tests — expect 2 passes.**

- [ ] **Step 5: Commit**

```bash
git add src/api/routes/trends.py tests/api/test_needs_scrape_v2.py
git commit -m "refactor(api): unify freshness on canonical_trend_signals"
```

**Prompt for subagent:**
> Implement Task 18: rewrite `_needs_scrape()` in `src/api/routes/trends.py` to query `canonical_trend_signals` instead of the existing `trends`-table check. Preserve the function's current signature if it differs from `(keyword, geo, freshness_hours)` — adapt the implementation to match. Update any callers accordingly. Both tests must pass before committing.

---

### Task 19: Feature-flag `/scrape` through V2 + frontend SSE client

**Files:**
- Modify: `src/api/routes/scrape.py` — when `TRENDS_V2_ENABLED` and `scraper_type in ("google_trends", "all")`, enqueue the V2 job instead of running the subprocess collector.
- Modify: `frontend/src/api/scrape.ts` (or equivalent) — add an `EventSource` helper.

- [ ] **Step 1: In `src/api/routes/scrape.py`, at the top of `scrape_niche`, insert:**

```python
import os
if os.getenv("TRENDS_V2_ENABLED", "false").lower() in ("1", "true", "yes") \
        and request.scraper_type in ("google_trends", "all"):
    from src.api.routes.scrape_v2 import _enqueue
    niche_keywords = _get_niche_keywords_from_db(request.niche)
    job = await _enqueue(
        "trends_collection_job",
        keywords=niche_keywords, geo=request.geo,
        timeframe=request.timeframe, category=request.category,
        trigger_source="on_demand",
    )
    return {"message": f"Scraping ({request.scraper_type}) enqueued as {job.job_id}.",
            "job_id": job.job_id}
```

NOTE: `scrape_niche` is currently a `def` (sync); promote it to `async def` and update the `BackgroundTasks` flow accordingly. (Existing non-V2 branches can run the `BackgroundTasks` code unchanged via `background_tasks.add_task(...)`.)

- [ ] **Step 2: In `frontend/src/api/scrape.ts` add:**

```ts
export type ScrapeEvent =
  | { event: "job_started"; keywords: string[]; geo: string }
  | { event: "keyword_started"; keyword: string }
  | { event: "keyword_completed"; keyword: string; widgets: number }
  | { event: "keyword_failed"; keyword: string; error: string }
  | { event: "job_completed"; keyword_count: number; failed: number; providers: string[]; cost_usd: number };

export function openScrapeStream(jobId: string, onEvent: (e: ScrapeEvent) => void): () => void {
  const es = new EventSource(`/scrape/stream/${jobId}`);
  es.onmessage = (msg) => {
    try { onEvent(JSON.parse(msg.data)); } catch { /* ignore non-JSON */ }
  };
  es.addEventListener("close", () => es.close());
  return () => es.close();
}
```

Wire `openScrapeStream` into the scrape-trigger UI component; on `job_completed`, refetch `GET /trends`. (Exact component path depends on current UI structure — locate the existing scrape-trigger call site via `grep -r "POST.*scrape" frontend/src` and add the SSE wiring there.)

- [ ] **Step 3: Smoke-test manually**

```bash
TRENDS_V2_ENABLED=true python -m arq src.collection.queue.settings.WorkerSettings &
TRENDS_V2_ENABLED=true DATAFORSEO_LOGIN=... DATAFORSEO_PASSWORD=... python -m src.api.main &
curl -X POST http://localhost:8000/scrape -H 'content-type: application/json' \
  -d '{"niche":"tech","geo":"US","scraper_type":"google_trends"}'
# → {"job_id":"job-xxxx"}
curl -N http://localhost:8000/scrape/stream/job-xxxx
```

Expected: SSE stream emits `keyword_started`, `keyword_completed`, and finally `job_completed`.

- [ ] **Step 4: Commit**

```bash
git add src/api/routes/scrape.py frontend/src/api/scrape.ts
git commit -m "feat(scrape): route through V2 pipeline when TRENDS_V2_ENABLED"
```

**Prompt for subagent:**
> Implement Task 19: when `TRENDS_V2_ENABLED=true` and the requested `scraper_type` is `google_trends` or `all`, the existing `/scrape` endpoint must enqueue a V2 job instead of running the legacy collector subprocess, returning `{"job_id": ...}` in the response body. Also add the `openScrapeStream` helper to the frontend API module and wire it into the existing scrape-trigger component (locate via `grep -r "scrape" frontend/src/api`). Run the manual smoke test in Step 3 and confirm the SSE stream closes after `job_completed`.

---

## Phase 8 — Warmup

### Task 20: WarmupJob cron

**Files:**
- Modify: `src/collection/trends/jobs.py` — add `warmup_trends` function.
- Modify: `src/collection/queue/settings.py` — register cron if warmup enabled.
- Create: `tests/collection/test_warmup.py`

- [ ] **Step 1: Write `tests/collection/test_warmup.py`**

```python
import pytest
from src.collection.trends.jobs import _top_keywords_for_warmup

def test_top_keywords_query_returns_expected_rows(monkeypatch):
    # Stub session to return 3 deterministic rows
    class _Row:
        def __init__(self, k, g): self.keyword = k; self.geo = g
    class _Q:
        def limit(self, n): return self
        def all(self): return [_Row("python", "US"), _Row("scrapy", "US")]
    class _S:
        def query(self, *a, **kw): return self
        def filter(self, *a, **kw): return self
        def outerjoin(self, *a, **kw): return self
        def order_by(self, *a, **kw): return _Q()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr("src.collection.trends.jobs.session_scope", lambda: _S())
    out = _top_keywords_for_warmup(geos=("US",), top_n=50, freshness_hours=18)
    assert ("US", ["python", "scrapy"]) in out
```

- [ ] **Step 2: Append to `src/collection/trends/jobs.py`**

```python
from src.db.connection import session_scope
from src.db.models import CanonicalTrendSignal, Trend, Platform
from datetime import datetime, timedelta, timezone
from sqlalchemy import desc, func

def _top_keywords_for_warmup(
    *, geos: tuple[str, ...], top_n: int, freshness_hours: int,
) -> list[tuple[str, list[str]]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=freshness_hours)
    out: list[tuple[str, list[str]]] = []
    with session_scope() as s:
        for geo in geos:
            rows = (
                s.query(Trend.keyword)
                 .join(Platform, Platform.id == Trend.platform_id)
                 .filter(Platform.name == "Google Interest", Trend.geo == geo)
                 .outerjoin(
                     CanonicalTrendSignal,
                     (CanonicalTrendSignal.source == "google_trends") &
                     (CanonicalTrendSignal.entity_id == Trend.keyword) &
                     (CanonicalTrendSignal.country == geo) &
                     (CanonicalTrendSignal.time_bucket_start >= cutoff),
                 )
                 .filter(CanonicalTrendSignal.id.is_(None))
                 .order_by(desc(Trend.growth))
                 .limit(top_n)
                 .all()
            )
            out.append((geo, [r.keyword for r in rows]))
    return out

async def warmup_trends(ctx) -> dict:
    cfg = TrendsConfig.from_env()
    if not cfg.warmup_enabled:
        return {"skipped": "warmup_disabled"}
    redis = await get_redis()
    from src.collection.trends.events import publish_event
    summary = {}
    for geo, keywords in _top_keywords_for_warmup(
        geos=cfg.warmup_geos, top_n=cfg.warmup_top_n,
        freshness_hours=cfg.warmup_freshness_hours,
    ):
        if not keywords:
            continue
        result = await trends_collection_job(
            {"redis": redis, "job_id": f"warmup-{geo}"},
            keywords=keywords, geo=geo, timeframe="today 12-m",
            category=0, trigger_source="warmup",
        )
        summary[geo] = result
    return summary
```

- [ ] **Step 3: Register the cron in `src/collection/queue/settings.py`**

```python
from arq.cron import cron

class WorkerSettings:
    # ...existing...
    functions = [jobs.trends_collection_job, jobs.warmup_trends]
    cron_jobs = [cron(jobs.warmup_trends, hour={2}, minute={0}, run_at_startup=False)]
```

- [ ] **Step 4: Run tests — expect pass.**

- [ ] **Step 5: Commit**

```bash
git add src/collection/trends/jobs.py src/collection/queue/settings.py tests/collection/test_warmup.py
git commit -m "feat(trends): nightly warmup of top keywords per geo"
```

**Prompt for subagent:**
> Implement Task 20: `_top_keywords_for_warmup` query (top-N virality per geo excluding fresh) and `warmup_trends` arq cron function. Register cron at 02:00 UTC daily. One test must pass before committing.

---

## Phase 9 — Cleanup

### Task 21: Remove deprecated code paths

**Files:**
- Delete: `src/scrapers/google_trends_scraper/google_trends/spiders/token_import_spider.py`
- Modify: `src/scrapers/google_trends_scraper/google_trends/middlewares.py` — remove `SkipRecentlyScrapedMiddleware` class + its entry in `settings.py::DOWNLOADER_MIDDLEWARES`.
- Modify: `src/api/routes/scrape.py` — remove `/import_tokens` endpoint + `import_tokens` handler.
- Modify: `src/collector/trend_collector.py` — remove `run_token_import` method.
- Modify: `.env.example` — remove stale comment about manual token import if present.

- [ ] **Step 1: Precondition — V2 must be the default**

Flip `TRENDS_V2_ENABLED=true` in production `.env` first. Only proceed after a 7-day clean run (see §14 Success Criteria).

- [ ] **Step 2: Delete files and references**

```bash
git rm src/scrapers/google_trends_scraper/google_trends/spiders/token_import_spider.py
```

Edit `middlewares.py`: remove the `SkipRecentlyScrapedMiddleware` class. Edit `settings.py`: remove the line `'google_trends.middlewares.SkipRecentlyScrapedMiddleware': 300,`.

Edit `src/api/routes/scrape.py`: delete the `/import_tokens` endpoint and its handler (`import_tokens` function).

Edit `src/collector/trend_collector.py`: delete `run_token_import` method.

- [ ] **Step 3: Run the full test suite**

```bash
pytest -q
```
Expected: all green. If any test references the deleted symbols, fix or delete that test.

- [ ] **Step 4: Smoke: the legacy-Scrapy-only path still works as last-resort**

```bash
TRENDS_V2_ENABLED=true TRENDS_PROVIDER_CHAIN=legacy_scrapy \
  curl -X POST http://localhost:8000/scrape -H 'content-type: application/json' \
  -d '{"niche":"tech","geo":"US","scraper_type":"google_trends"}'
```
Expected: `job_id` returned, SSE stream completes with `job_completed` and `providers: ["legacy_scrapy"]`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore(trends): remove deprecated token-import + freshness middleware"
```

**Prompt for subagent:**
> Implement Task 21: delete the deprecated code paths as listed. DO NOT run this task unless V2 has been the default path for at least 7 days in production and the Success Criteria in §14 of the design doc are met. Run `pytest -q` after deletions and ensure the suite is green.

---

## Self-Review

**Spec coverage:**
- §4 Architecture ↔ Tasks 2, 10, 11, 13 (Redis, arq, SSE, router)
- §5.1 TrendsProvider Protocol ↔ Task 3
- §5.2 DataForSEO / SerpAPI / Legacy ↔ Tasks 6–7 / 14–15 / 17
- §5.3 ProviderRouter ↔ Tasks 12–13
- §5.4 Queue & streaming ↔ Tasks 9–11
- §5.5 Warmup ↔ Task 20
- §5.6 Unified freshness ↔ Task 18
- §6 Data flow ↔ Tasks 10, 11, 19
- §7 DB changes ↔ Task 5
- §8 Error handling / observability ↔ Tasks 13 (router logs) + 16 (admin endpoints) + 10 (ScrapeRun attribution)
- §9 Configuration ↔ Tasks 1, 4
- §10 Testing strategy ↔ every task (TDD)
- §11 Migration plan ↔ Phases 1-9 map 1:1
- §12 Budget ↔ Tasks 4 (cap validation) + 8 (tracker) + 13 (guard)
- §14 Success criteria ↔ Task 21 gate

**Gaps:** none identified. The live-provider smoke test from §10 is not in the plan as a task — it's an ops check during rollout, not code.

**Placeholder scan:** none found (all `TODO`s are specifically about out-of-scope items in §13 and are explicitly deferred).

**Type consistency:** `CanonicalTrendResult`, `DataType`, `ProviderError`, `TrendsProvider`, `ProviderBreaker`, `ProviderSpend`, `ProviderRouter`, and `TrendsConfig` names are used consistently across Tasks 3, 6–20.

---

## Execution Handoff

Plan is complete and written into this same document. Two execution options:

**1. Subagent-driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Uses the `superpowers:subagent-driven-development` skill.

**2. Inline execution** — Execute tasks in this session with checkpoints. Uses the `superpowers:executing-plans` skill.

Which approach?
