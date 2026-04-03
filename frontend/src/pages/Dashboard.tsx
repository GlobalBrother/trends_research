/**
 * Dashboard — Overview page
 * Fetches real data from the FastAPI backend.
 * Design: KPI strip → Main trend chart + Activity → Top Trends + Momentum
 *         → Ads Insight section (HookedAI data)
 */
import { useMemo, useState, useCallback } from "react";
import {
  TrendingUp,
  Activity,
  BarChart3,
  Globe,
  Zap,
  Loader2,
  AlertCircle,
  RefreshCw,
  Megaphone,
  Eye,
  Target,
  ExternalLink,
  Calendar,
  Filter,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  MousePointerClick,
  Clock,
  X,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  Cell,
  PieChart,
  Pie,
  Legend,
} from "recharts";
import { useApi } from "@/hooks/useApi";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  getTrends,
  getAllTrends,
  getAzureStatus,
  getNiches,
  getAdsInsight,
  getAdsInsightFilters,
  type TrendRow,
  type AdsInsightRow,
  type AdsInsightParams,
} from "@/lib/api";

const HERO_IMG =
  "https://d2xsxph8kpxj0f.cloudfront.net/310519663454788231/FytdQNpTpcXmkbaLV4kBSe/hero-data-grid_2468fa04.png";

/* ── helpers ─────────────────────────────────────────────────────────────── */

function groupByMonth(rows: TrendRow[]) {
  const buckets: Record<string, Record<string, number>> = {};
  for (const r of rows) {
    const d = r.extracted_at || (r as Record<string, unknown>).created_at;
    if (!d) continue;
    const dt = new Date(String(d));
    if (isNaN(dt.getTime())) continue;
    const key = dt.toLocaleString("en", { month: "short", year: "2-digit" });
    if (!buckets[key]) buckets[key] = {};
    // platform may be a list (after analytics aggregation) or a string
    const rawPlatform = r.platform;
    const platformList: string[] = Array.isArray(rawPlatform)
      ? rawPlatform.map((p: unknown) => String(p).toLowerCase())
      : [String(rawPlatform || "other").toLowerCase()];
    for (const platform of platformList) {
      buckets[key][platform] = (buckets[key][platform] || 0) + 1;
    }
  }
  return Object.entries(buckets)
    .sort(([a], [b]) => new Date(`1 ${a}`).getTime() - new Date(`1 ${b}`).getTime())
    .map(([date, platforms]) => ({ date, ...platforms }));
}

function topTrends(rows: TrendRow[], n = 8) {
  const scored = rows
    .filter((r) => r.topic || r.title || r.keyword)
    .map((r) => ({
      name: r.topic || r.title || r.keyword || "—",
      score: r.virality_score ?? r.search_volume ?? 0,
      platform: Array.isArray(r.platform)
        ? (r.platform as string[]).join(", ")
        : String(r.platform || "—"),
      geo: Array.isArray(r.geo)
        ? (r.geo as string[]).join(", ")
        : String(r.geo || "—"),
    }));
  scored.sort((a, b) => (b.score as number) - (a.score as number));
  return scored.slice(0, n);
}

/* ── Ads helpers ─────────────────────────────────────────────────────────── */

function topAds(rows: AdsInsightRow[], n = 10) {
  return [...rows]
    .filter((r) => r.title || r.body)
    .sort((a, b) => (b.performance_score ?? 0) - (a.performance_score ?? 0))
    .slice(0, n);
}

/**
 * Parse comma-separated platform strings into individual platform counts.
 * e.g. "FACEBOOK, INSTAGRAM, MESSENGER" → counts FACEBOOK +1, INSTAGRAM +1, MESSENGER +1
 */
function adsPlatformBreakdown(rows: AdsInsightRow[]) {
  const counts: Record<string, number> = {};
  for (const r of rows) {
    const raw = String(r.platform || "unknown");
    const parts = raw.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
    for (const p of parts) {
      counts[p] = (counts[p] || 0) + 1;
    }
  }
  return Object.entries(counts)
    .sort(([, a], [, b]) => b - a)
    .map(([name, value]) => ({ name: name.charAt(0).toUpperCase() + name.slice(1).toLowerCase(), value }));
}

function topBrands(
  rows: AdsInsightRow[],
  n = 8,
) {
  const brands: Record<
    string,
    { count: number; active_ads: number; logo?: string; avgScore: number; totalScore: number }
  > = {};
  for (const r of rows) {
    const name = r.brand_name;
    if (!name) continue;
    if (!brands[name]) {
      brands[name] = { count: 0, active_ads: 0, logo: undefined, avgScore: 0, totalScore: 0 };
    }
    brands[name].count += 1;
    brands[name].active_ads = Math.max(brands[name].active_ads, Number(r.brand_active_ads) || 0);
    brands[name].logo = r.brand_logo_url as string | undefined;
    brands[name].totalScore += r.performance_score ?? 0;
    brands[name].avgScore = brands[name].totalScore / brands[name].count;
  }
  return Object.entries(brands)
    .sort(([, a], [, b]) => b.count - a.count)
    .slice(0, n)
    .map(([name, data]) => ({ name, ...data }));
}

function adsFormatBreakdown(rows: AdsInsightRow[]) {
  const counts: Record<string, number> = {};
  for (const r of rows) {
    const f = String(r.display_format || "unknown").toUpperCase();
    counts[f] = (counts[f] || 0) + 1;
  }
  return Object.entries(counts)
    .sort(([, a], [, b]) => b - a)
    .map(([name, value]) => ({ name, value }));
}

function performanceDistribution(rows: AdsInsightRow[]) {
  const buckets: Record<string, number> = {};
  for (const r of rows) {
    const label = String(r.performance_score_title || "Unknown");
    buckets[label] = (buckets[label] || 0) + 1;
  }
  return Object.entries(buckets)
    .sort(([, a], [, b]) => b - a)
    .map(([name, value]) => ({ name, value }));
}

function ctaBreakdown(rows: AdsInsightRow[]) {
  const counts: Record<string, number> = {};
  for (const r of rows) {
    const cta = String(r.cta_type || "None").replace(/_/g, " ");
    counts[cta] = (counts[cta] || 0) + 1;
  }
  return Object.entries(counts)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 8)
    .map(([name, value]) => ({ name, value }));
}

function daysActiveDistribution(rows: AdsInsightRow[]) {
  const buckets: Record<string, number> = {
    "0-1d": 0,
    "2-7d": 0,
    "8-14d": 0,
    "15-30d": 0,
    "31-60d": 0,
    "60d+": 0,
  };
  for (const r of rows) {
    const d = r.days_active ?? 0;
    if (d <= 1) buckets["0-1d"]++;
    else if (d <= 7) buckets["2-7d"]++;
    else if (d <= 14) buckets["8-14d"]++;
    else if (d <= 30) buckets["15-30d"]++;
    else if (d <= 60) buckets["31-60d"]++;
    else buckets["60d+"]++;
  }
  return Object.entries(buckets).map(([name, value]) => ({ name, value }));
}

const PERF_COLORS: Record<string, string> = {
  winning: "oklch(0.65 0.17 165)",
  optimized: "oklch(0.50 0.20 260)",
  scaling: "oklch(0.72 0.17 70)",
  growing: "oklch(0.60 0.22 25)",
  testing: "oklch(0.55 0.015 260)",
  unknown: "oklch(0.75 0.01 260)",
};

const PIE_COLORS = [
  "oklch(0.50 0.20 260)",
  "oklch(0.65 0.17 165)",
  "oklch(0.72 0.17 70)",
  "oklch(0.55 0.18 300)",
  "oklch(0.60 0.22 25)",
  "oklch(0.60 0.22 340)",
  "oklch(0.55 0.25 320)",
  "oklch(0.65 0.15 170)",
  "oklch(0.45 0.15 200)",
  "oklch(0.70 0.12 100)",
];

const PLATFORM_COLORS_ADS: Record<string, string> = {
  Facebook: "oklch(0.50 0.20 260)",
  Instagram: "oklch(0.60 0.22 340)",
  Messenger: "oklch(0.55 0.18 300)",
  Threads: "oklch(0.55 0.25 320)",
  "Audience_network": "oklch(0.65 0.15 170)",
};

const PAGE_SIZE_OPTIONS = [
  { label: "100", value: "100" },
  { label: "250", value: "250" },
  { label: "500", value: "500" },
  { label: "1000", value: "1000" },
  { label: "All", value: "0" },
];

/* ── Custom Pie Label ────────────────────────────────────────────────────── */

function renderCustomPieLabel({
  cx,
  cy,
  midAngle,
  innerRadius,
  outerRadius,
  name,
  percent,
}: {
  cx: number;
  cy: number;
  midAngle: number;
  innerRadius: number;
  outerRadius: number;
  name: string;
  percent: number;
}) {
  if (percent < 0.03) return null; // hide labels for tiny slices
  const RADIAN = Math.PI / 180;
  const radius = outerRadius + 22;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  return (
    <text
      x={x}
      y={y}
      fill="oklch(0.45 0.015 260)"
      textAnchor={x > cx ? "start" : "end"}
      dominantBaseline="central"
      fontSize={10}
      fontWeight={500}
    >
      {name} {(percent * 100).toFixed(0)}%
    </text>
  );
}

/* ── component ───────────────────────────────────────────────────────────── */

export default function Dashboard() {
  /* ── Ads filter state ──────────────────────────────────────────────── */
  const [adsPageSize, setAdsPageSize] = useState("500");
  const [adsOffset, setAdsOffset] = useState(0);
  const [adsDateFrom, setAdsDateFrom] = useState("");
  const [adsDateTo, setAdsDateTo] = useState("");
  const [adsPlatformFilter, setAdsPlatformFilter] = useState("");
  const [adsFormatFilter, setAdsFormatFilter] = useState("");
  const [adsKeywordFilter, setAdsKeywordFilter] = useState("");
  const [adsPerfFilter, setAdsPerfFilter] = useState("");
  const [adsSortBy, setAdsSortBy] = useState("extracted_at");
  const [adsSortDir, setAdsSortDir] = useState("desc");

  /* ── Build params object ───────────────────────────────────────────── */
  const adsParams: AdsInsightParams = useMemo(() => {
    const p: AdsInsightParams = {
      limit: Number(adsPageSize),
      offset: adsOffset,
      sort_by: adsSortBy,
      sort_dir: adsSortDir,
    };
    if (adsDateFrom) p.date_from = adsDateFrom;
    if (adsDateTo) p.date_to = adsDateTo;
    if (adsPlatformFilter) p.platform_filter = adsPlatformFilter;
    if (adsFormatFilter) p.format_filter = adsFormatFilter;
    if (adsKeywordFilter) p.keyword_filter = adsKeywordFilter;
    if (adsPerfFilter) p.perf_filter = adsPerfFilter;
    return p;
  }, [adsPageSize, adsOffset, adsDateFrom, adsDateTo, adsPlatformFilter, adsFormatFilter, adsKeywordFilter, adsPerfFilter, adsSortBy, adsSortDir]);

  /* ── data fetching ──────────────────────────────────────────────────── */
  const {
    data: trendsData,
    loading: trendsLoading,
    error: trendsError,
    refetch: refetchTrends,
  } = useApi(() => getTrends(), []);
  const { data: allTrendsData, loading: allLoading } = useApi(() => getAllTrends(), []);
  const { data: azureData } = useApi(() => getAzureStatus(), []);
  const { data: nichesData } = useApi(() => getNiches(), []);
  const {
    data: adsData,
    loading: adsLoading,
    refetch: refetchAds,
  } = useApi(
    () => getAdsInsight(adsParams),
    [adsParams]
  );
  const { data: adsFiltersData } = useApi(() => getAdsInsightFilters(), []);

  const trends = trendsData?.data ?? [];
  const allTrends = allTrendsData?.data ?? [];
  const ads = adsData?.data ?? [];
  const adsTotal = adsData?.total ?? 0;
  const adsFilters = adsFiltersData ?? null;

  /* ── Ads pagination helpers ────────────────────────────────────────── */
  const currentPageSize = Number(adsPageSize) || adsTotal;
  const currentPage = currentPageSize > 0 ? Math.floor(adsOffset / currentPageSize) + 1 : 1;
  const totalPages = currentPageSize > 0 ? Math.max(1, Math.ceil(adsTotal / currentPageSize)) : 1;

  const goNextPage = useCallback(() => {
    if (currentPage < totalPages) {
      setAdsOffset((prev) => prev + currentPageSize);
    }
  }, [currentPage, totalPages, currentPageSize]);

  const goPrevPage = useCallback(() => {
    if (currentPage > 1) {
      setAdsOffset((prev) => Math.max(0, prev - currentPageSize));
    }
  }, [currentPage, currentPageSize]);

  const resetAdsFilters = useCallback(() => {
    setAdsDateFrom("");
    setAdsDateTo("");
    setAdsPlatformFilter("");
    setAdsFormatFilter("");
    setAdsKeywordFilter("");
    setAdsPerfFilter("");
    setAdsOffset(0);
  }, []);

  const hasActiveFilters = adsDateFrom || adsDateTo || adsPlatformFilter || adsFormatFilter || adsKeywordFilter || adsPerfFilter;

  /* ── Trends KPIs ────────────────────────────────────────────────────── */
  const totalTrends = trends.length;
  const avgScore =
    trends.length > 0
      ? (trends.reduce((s, r) => s + (r.virality_score ?? 0), 0) / trends.length).toFixed(1)
      : "—";
  const nicheCount = nichesData ? (Array.isArray(nichesData) ? nichesData.length : 0) : 0;
  const dbConnected = azureData?.connected ?? false;
  const tableCount = azureData?.tables ? Object.keys(azureData.tables).length : 0;

  /* ── Ads KPIs ───────────────────────────────────────────────────────── */
  const totalAds = adsTotal;
  const displayedAds = ads.length;
  const adsWithScore = ads.filter((a) => a.performance_score != null && a.performance_score > 0);
  const avgPerfScore =
    adsWithScore.length > 0
      ? (adsWithScore.reduce((s, r) => s + (r.performance_score ?? 0), 0) / adsWithScore.length).toFixed(1)
      : "—";
  const adsWithDays = ads.filter((a) => a.days_active != null && a.days_active > 0);
  const avgDaysActive =
    adsWithDays.length > 0
      ? Math.round(adsWithDays.reduce((s, r) => s + (r.days_active ?? 0), 0) / adsWithDays.length)
      : 0;
  const uniqueBrands = new Set(ads.map((a) => a.brand_name).filter(Boolean)).size;
  const winningAds = ads.filter((a) => String(a.performance_score_title || "").toLowerCase() === "winning").length;

  /* ── Chart data ─────────────────────────────────────────────────────── */
  const chartData = useMemo(() => groupByMonth(allTrends), [allTrends]);
  const platforms = useMemo(() => {
    const set = new Set<string>();
    for (const r of allTrends) {
      if (r.platform) {
        const rawPlatform = r.platform;
        if (Array.isArray(rawPlatform)) {
          for (const p of rawPlatform) set.add(String(p).toLowerCase());
        } else {
          set.add(String(rawPlatform).toLowerCase());
        }
      }
    }
    return Array.from(set).slice(0, 9);
  }, [allTrends]);

  const PLATFORM_COLORS: Record<string, string> = {
    // DB platform names (lowercased) — spaces preserved
    "google trends": "oklch(0.50 0.20 260)",
    "google interest": "oklch(0.50 0.18 260)",
    "google regions": "oklch(0.55 0.16 260)",
    "google related queries": "oklch(0.48 0.18 260)",
    "google related topics": "oklch(0.52 0.16 260)",
    youtube: "oklch(0.60 0.22 25)",
    reddit: "oklch(0.55 0.20 30)",
    hackernews: "oklch(0.65 0.15 70)",
    tiktok: "oklch(0.55 0.25 320)",
    instagram: "oklch(0.60 0.22 340)",
    threads: "oklch(0.50 0.15 200)",
    news: "oklch(0.65 0.15 170)",
    gethookdai: "oklch(0.60 0.20 145)",
    // Legacy underscore variants (fallback)
    google_trends: "oklch(0.50 0.20 260)",
  };

  /* ── Top trends ─────────────────────────────────────────────────────── */
  const top = useMemo(() => topTrends(trends), [trends]);

  /* ── Momentum (weekly count of new trends) ──────────────────────────── */
  const momentumData = useMemo(() => {
    const weeks: Record<string, number> = {};
    for (const r of trends) {
      const d = r.extracted_at;
      if (!d) continue;
      const dt = new Date(String(d));
      if (isNaN(dt.getTime())) continue;
      const weekStart = new Date(dt);
      weekStart.setDate(weekStart.getDate() - weekStart.getDay());
      const key = `W${weekStart.toISOString().slice(5, 10)}`;
      weeks[key] = (weeks[key] || 0) + 1;
    }
    return Object.entries(weeks)
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-8)
      .map(([date, count]) => ({ date, score: count }));
  }, [trends]);

  const latestMomentum = momentumData.length > 0 ? momentumData[momentumData.length - 1].score : 0;

  /* ── Collapsible ad groups state ────────────────────────────────────── */
  const [expandedAdGroups, setExpandedAdGroups] = useState<Set<string>>(new Set());
  const toggleAdGroup = useCallback((key: string) => {
    setExpandedAdGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  /* ── Ads derived data ───────────────────────────────────────────────── */
  const topAdsList = useMemo(() => topAds(ads), [ads]);
  const platformBreakdown = useMemo(() => adsPlatformBreakdown(ads), [ads]);
  const brandList = useMemo(() => topBrands(ads), [ads]);
  const formatBreakdown = useMemo(() => adsFormatBreakdown(ads), [ads]);
  const perfDist = useMemo(() => performanceDistribution(ads), [ads]);
  const ctaDist = useMemo(() => ctaBreakdown(ads), [ads]);
  const daysActiveDist = useMemo(() => daysActiveDistribution(ads), [ads]);

  /** Group ads by (brand_name + title/body) for collapsible display */
  const groupedTopAds = useMemo(() => {
    const groups: { key: string; primary: AdsInsightRow; duplicates: AdsInsightRow[] }[] = [];
    const keyMap = new Map<string, number>();
    for (const ad of topAdsList) {
      const title = (ad.title || (ad.body ? String(ad.body).slice(0, 60) : "")).trim().toLowerCase();
      const brand = (ad.brand_name || "").trim().toLowerCase();
      const key = `${brand}|||${title}`;
      const existing = keyMap.get(key);
      if (existing != null) {
        groups[existing].duplicates.push(ad);
      } else {
        keyMap.set(key, groups.length);
        groups.push({ key, primary: ad, duplicates: [] });
      }
    }
    return groups;
  }, [topAdsList]);

  /* ── KPI card configs ───────────────────────────────────────────────── */
  const kpiData = [
    { label: "Active Trends", value: totalTrends.toLocaleString(), change: `${trends.length} rows`, up: totalTrends > 0, icon: TrendingUp },
    { label: "Avg Virality", value: String(avgScore), change: "virality score", up: Number(avgScore) > 0, icon: Activity },
    { label: "Niches", value: String(nicheCount), change: `${nicheCount} configured`, up: nicheCount > 0, icon: BarChart3 },
    { label: "Database", value: dbConnected ? "Online" : "Offline", change: `${tableCount} tables`, up: dbConnected, icon: Globe },
  ];

  const adsKpiData = [
    { label: "Total Ads", value: totalAds.toLocaleString(), change: `${displayedAds} displayed`, up: totalAds > 0, icon: Megaphone },
    { label: "Avg Performance", value: String(avgPerfScore), change: `${winningAds} winning`, up: Number(avgPerfScore) > 50, icon: Target },
    { label: "Avg Days Active", value: String(avgDaysActive), change: "days running", up: avgDaysActive > 7, icon: Eye },
    { label: "Unique Brands", value: String(uniqueBrands), change: "brands tracked", up: uniqueBrands > 0, icon: BarChart3 },
  ];

  const isLoading = trendsLoading || allLoading;

  /* ── render ─────────────────────────────────────────────────────────── */
  return (
    <div className="p-4 lg:p-6 space-y-6">
      {/* Hero banner */}
      <div
        className="relative overflow-hidden rounded-sm p-6 lg:p-8"
        style={{
          backgroundImage: `url(${HERO_IMG})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      >
        <div className="relative z-10 flex items-center justify-between">
          <div>
            <h1 className="text-2xl lg:text-3xl font-bold text-white tracking-tight">
              Intelligence Dashboard
            </h1>
            <p className="mt-1 text-sm text-white/70 max-w-lg">
              Real-time overview of trend signals across all monitored sources and topics.
            </p>
          </div>
          <button
            onClick={() => {
              refetchTrends();
              refetchAds();
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white text-xs rounded transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading || adsLoading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error banner */}
      {trendsError && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-destructive/10 border border-destructive/20 rounded-sm text-sm text-destructive">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>Failed to fetch trends: {trendsError}</span>
          <button onClick={refetchTrends} className="ml-auto text-xs underline">
            Retry
          </button>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════
          TRENDS SECTION
          ═══════════════════════════════════════════════════════════════════ */}

      {/* KPI Strip — Trends */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {kpiData.map((kpi) => (
          <div key={kpi.label} className="kpi-card">
            <div className="flex items-center justify-between mb-2">
              <span className="section-label">{kpi.label}</span>
              <kpi.icon className="w-4 h-4 text-muted-foreground" />
            </div>
            <p className="text-2xl font-bold font-mono tracking-tight">
              {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : kpi.value}
            </p>
            <div className="flex items-center gap-1 mt-1">
              <span className={`status-dot ${kpi.up ? "status-dot-success" : "status-dot-danger"}`} />
              <span className={`text-xs font-medium ${kpi.up ? "text-success" : "text-danger"}`}>
                {kpi.change}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Main content: Chart + Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Trend Over Time Chart */}
        <div className="lg:col-span-8 bg-card border border-border p-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-semibold">Trend Volume Over Time</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Monthly data points by platform
              </p>
            </div>
            <div className="flex items-center gap-4 text-xs flex-wrap">
              {platforms.map((p) => (
                <span key={p} className="flex items-center gap-1.5">
                  <span
                    className="w-3 h-0.5 rounded"
                    style={{ backgroundColor: PLATFORM_COLORS[p] || "oklch(0.6 0.1 200)" }}
                  />
                  {p}
                </span>
              ))}
            </div>
          </div>
          <div className="h-64">
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.91 0.005 260)" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="oklch(0.55 0.015 260)" />
                  <YAxis tick={{ fontSize: 11 }} stroke="oklch(0.55 0.015 260)" />
                  <Tooltip
                    contentStyle={{
                      fontSize: 12,
                      borderRadius: 4,
                      border: "1px solid oklch(0.91 0.005 260)",
                    }}
                  />
                  {platforms.map((p) => (
                    <Line
                      key={p}
                      type="monotone"
                      dataKey={p}
                      stroke={PLATFORM_COLORS[p] || "oklch(0.6 0.1 200)"}
                      strokeWidth={2}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                {isLoading ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  "No trend data available. Run a scrape to populate."
                )}
              </div>
            )}
          </div>
        </div>

        {/* Top Trends Feed */}
        <div className="lg:col-span-4 bg-card border border-border p-4">
          <h2 className="text-sm font-semibold mb-3">Top Signals</h2>
          <div className="space-y-2.5">
            {isLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : top.length > 0 ? (
              top.map((t, i) => (
                <div key={i} className="flex items-center gap-3 py-1.5 border-b border-border/50 last:border-0">
                  <span className="text-xs font-mono text-muted-foreground w-4">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">{t.name}</p>
                    <p className="text-[10px] text-muted-foreground">{t.platform}</p>
                  </div>
                  <span className="text-xs font-mono font-semibold">
                    {typeof t.score === "number" ? t.score.toFixed(1) : t.score}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-xs text-muted-foreground py-4 text-center">
                No trends yet. Run a scrape to get started.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Bottom panels: Top Trends Table + Momentum */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Top Trends Table */}
        <div className="lg:col-span-7 bg-card border border-border p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold">Trend Details</h2>
            <span className="section-label">{trends.length} records</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 text-xs font-medium text-muted-foreground">Topic</th>
                  <th className="text-left py-2 text-xs font-medium text-muted-foreground">Platform</th>
                  <th className="text-right py-2 text-xs font-medium text-muted-foreground">Virality</th>
                  <th className="text-right py-2 text-xs font-medium text-muted-foreground">Geo</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={4} className="py-8 text-center">
                      <Loader2 className="w-5 h-5 animate-spin mx-auto text-muted-foreground" />
                    </td>
                  </tr>
                ) : top.length > 0 ? (
                  top.map((trend, i) => (
                    <tr
                      key={i}
                      className="border-b border-border/50 last:border-0 hover:bg-muted/30 transition-colors"
                    >
                      <td className="py-2.5 font-medium text-xs">{trend.name}</td>
                      <td className="py-2.5 text-muted-foreground text-xs">{trend.platform}</td>
                      <td className="py-2.5 text-right font-mono font-medium text-xs">
                        {typeof trend.score === "number" ? trend.score.toFixed(1) : trend.score}
                      </td>
                      <td className="py-2.5 text-right text-xs text-muted-foreground">{trend.geo}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="py-6 text-center text-xs text-muted-foreground">
                      No data available
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Momentum Score */}
        <div className="lg:col-span-5 bg-card border border-border p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-semibold">Weekly Momentum</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                New trend entries per week
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              <Zap className="w-4 h-4 text-warning" />
              <span className="text-lg font-bold font-mono">{latestMomentum}</span>
            </div>
          </div>
          <div className="h-40">
            {momentumData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={momentumData}>
                  <defs>
                    <linearGradient id="momentumGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="oklch(0.50 0.20 260)" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="oklch(0.50 0.20 260)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <YAxis tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
                  <Area
                    type="monotone"
                    dataKey="score"
                    stroke="oklch(0.50 0.20 260)"
                    strokeWidth={2}
                    fill="url(#momentumGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "No momentum data yet"}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════
          ADS INSIGHT SECTION — HookedAI Data
          ═══════════════════════════════════════════════════════════════════ */}

      {/* Section divider */}
      <div className="flex items-center gap-3 pt-2">
        <div className="flex items-center gap-2">
          <Megaphone className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-bold tracking-tight">Ads Intelligence</h2>
        </div>
        <div className="flex-1 h-px bg-border" />
        <span className="section-label">{totalAds} ads tracked via HookedAI</span>
      </div>

      {/* ── Ads Filter Bar ───────────────────────────────────────────────── */}
      <div className="bg-card border border-border p-3 rounded-sm">
        <div className="flex items-center gap-2 mb-2">
          <Filter className="w-4 h-4 text-muted-foreground" />
          <span className="text-xs font-semibold">Filters &amp; Controls</span>
          {hasActiveFilters && (
            <button
              onClick={resetAdsFilters}
              className="ml-2 flex items-center gap-1 text-[10px] text-destructive hover:text-destructive/80 transition-colors"
            >
              <X className="w-3 h-3" /> Clear filters
            </button>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          {/* Page Size */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-muted-foreground font-medium">Show</label>
            <Select
              value={adsPageSize}
              onValueChange={(v) => {
                setAdsPageSize(v);
                setAdsOffset(0);
              }}
            >
              <SelectTrigger size="sm" className="w-[80px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Date From */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-muted-foreground font-medium flex items-center gap-1">
              <Calendar className="w-3 h-3" /> From
            </label>
            <input
              type="date"
              value={adsDateFrom}
              onChange={(e) => {
                setAdsDateFrom(e.target.value);
                setAdsOffset(0);
              }}
              min={(adsFilters?.date_range?.min ?? undefined)}
              max={adsDateTo || (adsFilters?.date_range?.max ?? undefined)}
              className="h-8 px-2 text-xs border border-input rounded-md bg-transparent focus:outline-none focus:ring-2 focus:ring-ring/50"
            />
          </div>

          {/* Date To */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-muted-foreground font-medium flex items-center gap-1">
              <Calendar className="w-3 h-3" /> To
            </label>
            <input
              type="date"
              value={adsDateTo}
              onChange={(e) => {
                setAdsDateTo(e.target.value);
                setAdsOffset(0);
              }}
              min={adsDateFrom || (adsFilters?.date_range?.min ?? undefined)}
              max={(adsFilters?.date_range?.max ?? undefined)}
              className="h-8 px-2 text-xs border border-input rounded-md bg-transparent focus:outline-none focus:ring-2 focus:ring-ring/50"
            />
          </div>

          {/* Platform Filter */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-muted-foreground font-medium">Platform</label>
            <Select
              value={adsPlatformFilter || "__all__"}
              onValueChange={(v) => {
                setAdsPlatformFilter(v === "__all__" ? "" : v);
                setAdsOffset(0);
              }}
            >
              <SelectTrigger size="sm" className="w-[130px]">
                <SelectValue placeholder="All" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All Platforms</SelectItem>
                {(adsFilters?.platforms ?? []).map((p) => (
                  <SelectItem key={p} value={p}>
                    {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Format Filter */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-muted-foreground font-medium">Format</label>
            <Select
              value={adsFormatFilter || "__all__"}
              onValueChange={(v) => {
                setAdsFormatFilter(v === "__all__" ? "" : v);
                setAdsOffset(0);
              }}
            >
              <SelectTrigger size="sm" className="w-[100px]">
                <SelectValue placeholder="All" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All Formats</SelectItem>
                {(adsFilters?.formats ?? []).map((f) => (
                  <SelectItem key={f} value={f}>
                    {f}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Performance Filter */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-muted-foreground font-medium">Performance</label>
            <Select
              value={adsPerfFilter || "__all__"}
              onValueChange={(v) => {
                setAdsPerfFilter(v === "__all__" ? "" : v);
                setAdsOffset(0);
              }}
            >
              <SelectTrigger size="sm" className="w-[110px]">
                <SelectValue placeholder="All" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All Tiers</SelectItem>
                {(adsFilters?.performance_tiers ?? []).map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Keyword Filter */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-muted-foreground font-medium">Keyword</label>
            <Select
              value={adsKeywordFilter || "__all__"}
              onValueChange={(v) => {
                setAdsKeywordFilter(v === "__all__" ? "" : v);
                setAdsOffset(0);
              }}
            >
              <SelectTrigger size="sm" className="w-[150px]">
                <SelectValue placeholder="All" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All Keywords</SelectItem>
                {(adsFilters?.keywords ?? []).map((k) => (
                  <SelectItem key={k} value={k}>
                    {k}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Sort */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-muted-foreground font-medium">Sort by</label>
            <div className="flex gap-1">
              <Select value={adsSortBy} onValueChange={(v) => { setAdsSortBy(v); setAdsOffset(0); }}>
                <SelectTrigger size="sm" className="w-[120px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="extracted_at">Date Added</SelectItem>
                  <SelectItem value="start_date">Start Date</SelectItem>
                  <SelectItem value="performance_score">Score</SelectItem>
                  <SelectItem value="days_active">Days Active</SelectItem>
                  <SelectItem value="brand_name">Brand</SelectItem>
                </SelectContent>
              </Select>
              <Select value={adsSortDir} onValueChange={(v) => { setAdsSortDir(v); setAdsOffset(0); }}>
                <SelectTrigger size="sm" className="w-[70px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="desc">Desc</SelectItem>
                  <SelectItem value="asc">Asc</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
      </div>

      {/* Ads KPI Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {adsKpiData.map((kpi) => (
          <div key={kpi.label} className="kpi-card">
            <div className="flex items-center justify-between mb-2">
              <span className="section-label">{kpi.label}</span>
              <kpi.icon className="w-4 h-4 text-muted-foreground" />
            </div>
            <p className="text-2xl font-bold font-mono tracking-tight">
              {adsLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : kpi.value}
            </p>
            <div className="flex items-center gap-1 mt-1">
              <span className={`status-dot ${kpi.up ? "status-dot-success" : "status-dot-danger"}`} />
              <span className={`text-xs font-medium ${kpi.up ? "text-success" : "text-danger"}`}>
                {kpi.change}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Ads Charts Row 1: Performance Distribution + Platform Breakdown + Format Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Performance Score Distribution */}
        <div className="lg:col-span-4 bg-card border border-border p-4">
          <h2 className="text-sm font-semibold mb-1">Performance Distribution</h2>
          <p className="text-xs text-muted-foreground mb-3">Ads by performance tier</p>
          <div className="h-52">
            {perfDist.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={perfDist} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.91 0.005 260)" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <YAxis
                    dataKey="name"
                    type="category"
                    tick={{ fontSize: 10 }}
                    stroke="oklch(0.55 0.015 260)"
                    width={70}
                  />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
                  <Bar dataKey="value" radius={[0, 3, 3, 0]}>
                    {perfDist.map((entry, idx) => (
                      <Cell
                        key={idx}
                        fill={PERF_COLORS[entry.name.toLowerCase()] || PIE_COLORS[idx % PIE_COLORS.length]}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                {adsLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "No ads data yet"}
              </div>
            )}
          </div>
        </div>

        {/* Ads by Platform (Pie) — FIXED: individual platforms */}
        <div className="lg:col-span-4 bg-card border border-border p-4">
          <h2 className="text-sm font-semibold mb-1">Ads by Platform</h2>
          <p className="text-xs text-muted-foreground mb-3">Individual platform presence across ads</p>
          <div className="h-52">
            {platformBreakdown.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={platformBreakdown}
                    cx="50%"
                    cy="50%"
                    innerRadius={35}
                    outerRadius={65}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                    label={renderCustomPieLabel}
                    labelLine={true}
                  >
                    {platformBreakdown.map((entry, idx) => (
                      <Cell
                        key={idx}
                        fill={PLATFORM_COLORS_ADS[entry.name] || PIE_COLORS[idx % PIE_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 4 }}
                    formatter={(value: number, name: string) => [`${value} ads`, name]}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                {adsLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "No ads data yet"}
              </div>
            )}
          </div>
        </div>

        {/* Ad Format Breakdown */}
        <div className="lg:col-span-4 bg-card border border-border p-4">
          <h2 className="text-sm font-semibold mb-1">Ad Formats</h2>
          <p className="text-xs text-muted-foreground mb-3">Creative format distribution</p>
          <div className="h-52">
            {formatBreakdown.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={formatBreakdown}>
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.91 0.005 260)" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <YAxis tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
                  <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                    {formatBreakdown.map((_, idx) => (
                      <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                {adsLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "No ads data yet"}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Ads Charts Row 2: CTA Breakdown + Days Active Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* CTA Type Breakdown */}
        <div className="lg:col-span-6 bg-card border border-border p-4">
          <div className="flex items-center gap-2 mb-1">
            <MousePointerClick className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">CTA Type Breakdown</h2>
          </div>
          <p className="text-xs text-muted-foreground mb-3">Call-to-action distribution across ads</p>
          <div className="h-52">
            {ctaDist.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={ctaDist} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.91 0.005 260)" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <YAxis
                    dataKey="name"
                    type="category"
                    tick={{ fontSize: 9 }}
                    stroke="oklch(0.55 0.015 260)"
                    width={90}
                  />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
                  <Bar dataKey="value" radius={[0, 3, 3, 0]}>
                    {ctaDist.map((_, idx) => (
                      <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                {adsLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "No ads data yet"}
              </div>
            )}
          </div>
        </div>

        {/* Days Active Distribution */}
        <div className="lg:col-span-6 bg-card border border-border p-4">
          <div className="flex items-center gap-2 mb-1">
            <Clock className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Ad Longevity</h2>
          </div>
          <p className="text-xs text-muted-foreground mb-3">Distribution of how long ads have been running</p>
          <div className="h-52">
            {daysActiveDist.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={daysActiveDist}>
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.91 0.005 260)" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <YAxis tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
                  <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                    {daysActiveDist.map((_, idx) => (
                      <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                {adsLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "No ads data yet"}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Top Performing Ads Table + Brand Intelligence */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Top Performing Ads */}
        <div className="lg:col-span-7 bg-card border border-border p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold">Top Performing Ads</h2>
            <span className="section-label">{topAdsList.length} top ads</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 text-xs font-medium text-muted-foreground">Ad Title</th>
                  <th className="text-left py-2 text-xs font-medium text-muted-foreground">Brand</th>
                  <th className="text-left py-2 text-xs font-medium text-muted-foreground">Format</th>
                  <th className="text-right py-2 text-xs font-medium text-muted-foreground">Score</th>
                  <th className="text-center py-2 text-xs font-medium text-muted-foreground">Tier</th>
                  <th className="text-right py-2 text-xs font-medium text-muted-foreground">Days</th>
                  <th className="text-center py-2 text-xs font-medium text-muted-foreground">CTA</th>
                  <th className="text-left py-2 text-xs font-medium text-muted-foreground">Start</th>
                  <th className="text-center py-2 text-xs font-medium text-muted-foreground">Link</th>
                </tr>
              </thead>
              <tbody>
                {adsLoading ? (
                  <tr>
                    <td colSpan={9} className="py-8 text-center">
                      <Loader2 className="w-5 h-5 animate-spin mx-auto text-muted-foreground" />
                    </td>
                  </tr>
                ) : groupedTopAds.length > 0 ? (
                  groupedTopAds.map((group) => {
                    const ad = group.primary;
                    const hasDupes = group.duplicates.length > 0;
                    const isExpanded = expandedAdGroups.has(group.key);
                    const allInGroup = [ad, ...group.duplicates];

                    const renderAdRow = (rowAd: AdsInsightRow, idx: number, isChild: boolean) => (
                      <tr
                        key={rowAd.hookd_id || `${group.key}-${idx}`}
                        className={`border-b border-border/50 last:border-0 hover:bg-muted/30 transition-colors ${
                          isChild ? "bg-muted/10" : ""
                        }`}
                      >
                        <td className="py-2.5 font-medium text-xs max-w-[180px]">
                          <div className="flex items-center gap-1.5">
                            {!isChild && hasDupes && (
                              <button
                                onClick={() => toggleAdGroup(group.key)}
                                className="shrink-0 p-0.5 rounded hover:bg-muted transition-colors"
                              >
                                <ChevronDown
                                  className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${
                                    isExpanded ? "rotate-0" : "-rotate-90"
                                  }`}
                                />
                              </button>
                            )}
                            {isChild && <span className="w-3.5 shrink-0" />}
                            <span className="truncate">
                              {rowAd.title || (rowAd.body ? String(rowAd.body).slice(0, 60) + "..." : "\u2014")}
                            </span>
                            {!isChild && hasDupes && (
                              <span className="shrink-0 text-[9px] font-mono px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                                {allInGroup.length}x
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-2.5 text-xs text-muted-foreground max-w-[100px] truncate">{rowAd.brand_name || "\u2014"}</td>
                        <td className="py-2.5 text-xs text-muted-foreground">{rowAd.display_format || "\u2014"}</td>
                        <td className="py-2.5 text-right font-mono font-semibold text-xs">
                          <span
                            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold"
                            style={{
                              backgroundColor:
                                (rowAd.performance_score ?? 0) >= 80
                                  ? "oklch(0.65 0.17 165 / 0.15)"
                                  : (rowAd.performance_score ?? 0) >= 50
                                    ? "oklch(0.72 0.17 70 / 0.15)"
                                    : "oklch(0.55 0.015 260 / 0.15)",
                              color:
                                (rowAd.performance_score ?? 0) >= 80
                                  ? "oklch(0.45 0.17 165)"
                                  : (rowAd.performance_score ?? 0) >= 50
                                    ? "oklch(0.52 0.17 70)"
                                    : "oklch(0.45 0.015 260)",
                            }}
                          >
                            {rowAd.performance_score ?? "\u2014"}
                          </span>
                        </td>
                        <td className="py-2.5 text-center text-[10px] text-muted-foreground">
                          {rowAd.performance_score_title || "\u2014"}
                        </td>
                        <td className="py-2.5 text-right font-mono text-xs">{rowAd.days_active ?? "\u2014"}</td>
                        <td className="py-2.5 text-center text-xs text-muted-foreground">
                          {rowAd.cta_type ? rowAd.cta_type.replace(/_/g, " ") : "\u2014"}
                        </td>
                        <td className="py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                          {rowAd.start_date || "\u2014"}
                        </td>
                        <td className="py-2.5 text-center">
                          {rowAd.share_url ? (
                            <a
                              href={String(rowAd.share_url)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center text-primary hover:text-primary/80"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          ) : (
                            <span className="text-xs text-muted-foreground">\u2014</span>
                          )}
                        </td>
                      </tr>
                    );

                    return (
                      <>
                        {renderAdRow(ad, 0, false)}
                        {hasDupes && isExpanded &&
                          group.duplicates.map((dup, di) => renderAdRow(dup, di + 1, true))
                        }
                      </>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={9} className="py-6 text-center text-xs text-muted-foreground">
                      No ads data available. Trigger an ads scrape to populate.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-3 pt-3 border-t border-border">
              <span className="text-xs text-muted-foreground">
                Showing {adsOffset + 1}–{Math.min(adsOffset + currentPageSize, adsTotal)} of {adsTotal}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={goPrevPage}
                  disabled={currentPage <= 1}
                  className="flex items-center gap-1 px-2 py-1 text-xs border border-border rounded hover:bg-muted/50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronLeft className="w-3 h-3" /> Prev
                </button>
                <span className="text-xs font-mono">
                  {currentPage} / {totalPages}
                </span>
                <button
                  onClick={goNextPage}
                  disabled={currentPage >= totalPages}
                  className="flex items-center gap-1 px-2 py-1 text-xs border border-border rounded hover:bg-muted/50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Next <ChevronRight className="w-3 h-3" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Brand Intelligence */}
        <div className="lg:col-span-5 bg-card border border-border p-4">
          <h2 className="text-sm font-semibold mb-1">Brand Intelligence</h2>
          <p className="text-xs text-muted-foreground mb-3">
            Top brands by ad count from HookedAI
          </p>
          <div className="space-y-2">
            {adsLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : brandList.length > 0 ? (
              brandList.map((brand, i) => (
                <div
                  key={brand.name}
                  className="flex items-center gap-3 py-2 px-2 border-b border-border/50 last:border-0 hover:bg-muted/30 transition-colors rounded-sm"
                >
                  <span className="text-xs font-mono text-muted-foreground w-4">{i + 1}</span>
                  {brand.logo ? (
                    <img
                      src={brand.logo}
                      alt={brand.name}
                      className="w-6 h-6 rounded-full object-cover bg-muted"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                  ) : (
                    <div className="w-6 h-6 rounded-full bg-muted flex items-center justify-center text-[10px] font-bold text-muted-foreground">
                      {brand.name.charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">{brand.name}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {brand.count} ads &middot; {brand.active_ads} active &middot; avg score{" "}
                      {brand.avgScore.toFixed(0)}
                    </p>
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-mono font-semibold">{brand.count}</span>
                    <p className="text-[10px] text-muted-foreground">ads</p>
                  </div>
                </div>
              ))
            ) : (
              <p className="text-xs text-muted-foreground py-4 text-center">
                No brand data yet. Scrape ads to populate.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
