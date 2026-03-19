/**
 * API Client for the Trends Research FastAPI backend.
 *
 * In development, Vite proxies `/api/*` → `http://localhost:8000/*`.
 * In production (Docker), nginx proxies `/api/*` → `http://api:8000/*`.
 */
import axios, { type AxiosInstance } from "axios";

const client: AxiosInstance = axios.create({
  baseURL: "/api",
  timeout: 60_000,
  headers: { "Content-Type": "application/json" },
});

// ─── Types ───────────────────────────────────────────────────────────────────

export interface TrendRow {
  title?: string;
  keyword?: string;
  platform?: string;
  search_volume?: number;
  virality_score?: number;
  sentiment_score?: number;
  topic?: string;
  niche_cluster?: number;
  geo?: string;
  extracted_at?: string;
  [key: string]: unknown;
}

export interface ContentRow {
  external_id?: string;
  text_content?: string;
  keyword?: string;
  geo?: string;
  url?: string;
  created_at?: string;
  username?: string;
  likes?: number;
  comments?: number;
  shares?: number;
  views?: number;
  platform?: string;
  [key: string]: unknown;
}

export interface AdsInsightRow {
  hookd_id?: string;
  title?: string;
  body?: string;
  platform?: string;
  brand_name?: string;
  performance_score?: number;
  days_active?: number;
  search_keyword?: string;
  [key: string]: unknown;
}

export interface TokenUsageRow {
  platform: string;
  keyword?: string;
  units_charged: number;
  geo?: string;
  created_at?: string;
  provider?: string;
}

export interface TokenUsageSummary {
  platform: string;
  total_units: number;
  request_count: number;
  provider?: string;
}

export interface AzureStatus {
  connected: boolean;
  tables?: Record<string, number | string>;
  error?: string;
  diagnostic?: Record<string, unknown> | null;
}

export interface ScrapeRequest {
  niche: string;
  geo?: string;
  timeframe?: string;
  category?: number;
  scraper_type?: string;
}

// ─── API Functions ───────────────────────────────────────────────────────────

/** Health check */
export const getHealth = () => client.get<{ message: string }>("/");

/** Get list of niche names */
export const getNiches = () => client.get<string[]>("/niches");

/** Get keywords for a niche */
export const getNicheKeywords = (niche: string) =>
  client.get<{ niche: string; keywords: string[] }>(`/niche_keywords/${encodeURIComponent(niche)}`);

/** Create a new niche */
export const createNiche = (niche_name: string, keywords: string[] = []) =>
  client.post("/niches", { niche_name, keywords });

/** Add keywords to a niche */
export const addKeywords = (niche: string, keywords: string[]) =>
  client.post(`/niches/${encodeURIComponent(niche)}/keywords`, { keywords });

/** Delete a niche */
export const deleteNiche = (niche: string) =>
  client.delete(`/niches/${encodeURIComponent(niche)}`);

/** Delete a keyword from a niche */
export const deleteKeyword = (niche: string, keyword: string) =>
  client.delete(`/niches/${encodeURIComponent(niche)}/keywords/${encodeURIComponent(keyword)}`);

/** Get processed trends */
export const getTrends = (params?: { geo?: string; niche_name?: string }) =>
  client.get<{ data: TrendRow[] }>("/trends", { params });

/** Get trending now (Google Trends) */
export const getTrendingNow = (params?: { geo?: string; trend_type?: string }) =>
  client.get<{ data: TrendRow[] }>("/trending_now", { params });

/** Get all trends (all platforms) */
export const getAllTrends = () =>
  client.get<{ data: TrendRow[] }>("/all_trends");

/** Platform-specific trends */
export const getYoutubeTrends = (params?: { niche_name?: string; geo?: string }) =>
  client.get<{ data: TrendRow[] }>("/youtube_trends", { params });

export const getHackerNewsTrends = (params?: { niche_name?: string; geo?: string }) =>
  client.get<{ data: TrendRow[] }>("/hackernews_trends", { params });

export const getRedditTrends = (params?: { niche_name?: string; geo?: string }) =>
  client.get<{ data: TrendRow[] }>("/reddit_trends", { params });

export const getNewsTrends = (params?: { niche_name?: string; geo?: string; query?: string }) =>
  client.get<{ data: TrendRow[] }>("/news_trends", { params });

/** Platform-specific content */
export const getYoutubeVideos = (params?: { niche_name?: string; geo?: string; limit?: number }) =>
  client.get<{ data: ContentRow[] }>("/youtube_videos", { params });

export const getTiktokVideos = (params?: { niche_name?: string; geo?: string; limit?: number }) =>
  client.get<{ data: ContentRow[] }>("/tiktok_videos", { params });

export const getInstagramPosts = (params?: { niche_name?: string; geo?: string; limit?: number }) =>
  client.get<{ data: ContentRow[] }>("/instagram_posts", { params });

export const getRedditPosts = (params?: { niche_name?: string; geo?: string; limit?: number }) =>
  client.get<{ data: ContentRow[] }>("/reddit_posts", { params });

export const getThreadsPosts = (params?: { niche_name?: string; geo?: string; limit?: number }) =>
  client.get<{ data: ContentRow[] }>("/threads_posts", { params });

/** Ads insight */
export const getAdsInsight = (params?: { niche_name?: string; geo?: string; limit?: number }) =>
  client.get<{ data: AdsInsightRow[] }>("/ads_insight", { params });

/** Trigger scraping */
export const triggerScrape = (body: ScrapeRequest) =>
  client.post<{ message: string }>("/scrape", body);

/** Trigger ads scraping */
export const triggerAdsScrape = (keywords: string, max_pages?: number) =>
  client.post<{ message: string }>("/scrape_ads", null, { params: { keywords, max_pages } });

/** Scrape errors */
export const getScrapeErrors = (platform?: string) =>
  client.get<{ data: unknown[] }>("/scrape_errors", { params: platform ? { platform } : {} });

export const clearScrapeErrors = () => client.delete("/scrape_errors");

/** Table filters */
export const getTableFilters = (table_name: string) =>
  client.get<{ geos: string[]; keywords: string[] }>("/table_filters", { params: { table_name } });

/** Admin: Token usage */
export const getTokenUsage = () =>
  client.get<{ data: TokenUsageRow[]; summary: TokenUsageSummary[]; provider_summary: TokenUsageSummary[] }>("/admin/token_usage");

/** Admin: Azure status */
export const getAzureStatus = () =>
  client.get<AzureStatus>("/admin/azure/status");

/** Admin: Azure diagnose */
export const getAzureDiagnose = () =>
  client.get<Record<string, unknown>>("/admin/azure/diagnose");

/** Admin: Run migration */
export const runMigration = (dry_run = false) =>
  client.post("/admin/azure/migrate", null, { params: { dry_run } });

/** Admin: Setup schema */
export const setupSchema = () => client.post("/admin/azure/setup_schema");

/** Convenience wrappers used by Settings page */
export const triggerMigration = () =>
  client.post<{ message: string }>("/admin/azure/migrate");

export const triggerDiagnose = () =>
  client.get<{ checks: { name: string; passed: boolean; detail?: string }[] }>("/admin/azure/diagnose");

export default client;
