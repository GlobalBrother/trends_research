/**
 * API Client for the Trends Research FastAPI backend.
 *
 * In development, Vite proxies `/api/*` → `http://localhost:8000/*`.
 * In production (Docker), nginx proxies `/api/*` → `http://api:8000/*`.
 */
import axios, { type AxiosInstance } from "axios";

const client: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "",
  timeout: 60_000,
  headers: { "Content-Type": "application/json" },
});

// Automatically attach auth token to every request
client.interceptors.request.use((config) => {
  const token = localStorage.getItem("auth_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
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
  external_id?: string;
  title?: string;
  body?: string;
  platform?: string;
  display_format?: string;
  landing_page?: string;
  cta_type?: string;
  cta_text?: string;
  start_date?: string;
  end_date?: string;
  days_active?: number;
  active_in_library?: number;
  performance_score?: number;
  performance_score_title?: string;
  used_count?: number;
  age_audience_min?: number;
  age_audience_max?: number;
  gender_audience?: string;
  eu_total_reach?: number;
  ad_spend_range_score?: number;
  ad_spend_range_score_title?: string;
  brand_name?: string;
  brand_logo_url?: string;
  brand_active_ads?: number;
  media?: string;
  ad_cards?: string;
  share_url?: string;
  search_keyword?: string;
  extracted_at?: string;
  [key: string]: unknown;
}

export interface AdsInsightParams {
  niche_name?: string;
  geo?: string;
  limit?: number;
  offset?: number;
  date_from?: string;
  date_to?: string;
  platform_filter?: string;
  format_filter?: string;
  keyword_filter?: string;
  brand_filter?: string;
  perf_filter?: string;
  sort_by?: string;
  sort_dir?: string;
}

export interface AdsInsightFilters {
  platforms: string[];
  formats: string[];
  keywords: string[];
  performance_tiers: string[];
  brands: string[];
  date_range: { min: string | null; max: string | null };
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

// ─── Auth helpers ───────────────────────────────────────────────────────────

/** Get the current user's role from localStorage */
export const getUserRole = (): string => localStorage.getItem("auth_role") || "trends";

/** Check if the current user is an admin */
export const isAdmin = (): boolean => getUserRole() === "admin";

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
export const getAdsInsight = (params?: AdsInsightParams) =>
  client.get<{ data: AdsInsightRow[]; total: number }>("/ads_insight", { params });

/** Ads insight filter options */
export const getAdsInsightFilters = () =>
  client.get<AdsInsightFilters>("/ads_insight/filters");

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

// ─── My Brands ──────────────────────────────────────────────────────────────

export interface MyBrandRow {
  id: number;
  brand_name: string;
  brand_external_id?: string;
  brand_logo_url?: string;
  brand_active_ads?: number;
  added_at?: string;
}

export interface MyBrandAdsParams {
  limit?: number;
  offset?: number;
  brand_name?: string;
  date_from?: string;
  date_to?: string;
  platform_filter?: string;
  sort_by?: string;
  sort_dir?: string;
}

/** List tracked brands */
export const getMyBrands = () =>
  client.get<{ data: MyBrandRow[] }>("/my_brands");

/** Add a brand to track */
export const addMyBrand = (body: {
  brand_name: string;
  brand_external_id?: string;
  brand_logo_url?: string;
  brand_active_ads?: number;
}) => client.post<{ message: string; id: number }>("/my_brands", body);

/** Remove a tracked brand */
export const removeMyBrand = (brandId: number) =>
  client.delete("/my_brands/" + brandId);

/** Get ads for tracked brands */
export const getMyBrandAds = (params?: MyBrandAdsParams) =>
  client.get<{ data: AdsInsightRow[]; total: number; tracked_brands: string[] }>("/my_brands/ads", { params });

/** Refresh ads for all tracked brands */
export const refreshMyBrandAds = () =>
  client.post<{ message: string }>("/my_brands/refresh");

/** Search brands via GetHooked */
export const searchBrands = (query: string) =>
  client.get<{ data: { external_id: string; name: string; logo_url?: string; active_ads?: number }[] }>("/search_brands", { params: { query } });

// ─── Auth ──────────────────────────────────────────────────────────────────

export interface AuthUser {
  email: string;
  role: string;
  created_at?: string;
}

/** Request OTP for login */
export const requestOtp = (email: string) =>
  client.post<{ message: string; email: string }>("/auth/request_otp", null, { params: { email } });

/** Verify OTP and get auth token */
export const verifyOtp = (email: string, code: string) =>
  client.post<{ message: string; email: string; role: string; token: string }>("/auth/verify_otp", null, { params: { email, code } });

/** Validate an existing auth token */
export const validateToken = (token: string) =>
  client.get<{ email: string; role: string }>("/auth/validate_token", { params: { token } });

/** List all whitelisted users */
export const listUsers = () =>
  client.get<AuthUser[]>("/auth/users");

/** Add a whitelisted user */
export const addUser = (email: string, role: string = "trends") =>
  client.post<{ message: string; email: string; role: string }>("/auth/users", { email, role });

/** Update a user's role */
export const updateUserRole = (email: string, role: string) =>
  client.put<{ message: string; email: string; role: string }>("/auth/users", null, { params: { email, role } });

/** Delete a whitelisted user */
export const deleteUser = (email: string) =>
  client.delete<{ message: string; email: string }>("/auth/users", { params: { email } });

// ─── Import Tokens ─────────────────────────────────────────────────────────

/** Import Google Trends JSON tokens file */
export const importTokens = (file: File, geo: string = "US") => {
  const formData = new FormData();
  formData.append("file", file);
  return client.post<{ message: string }>("/import_tokens", formData, {
    params: { geo },
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export default client;
