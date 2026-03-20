/*
 * Dashboard — Overview page
 * Fetches real data from the FastAPI backend.
 * Design: KPI strip → Main trend chart + Activity → Top Trends + Momentum
 *         → Ads Insight section (HookedAI data)
 */
import { useMemo } from "react";
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
} from "recharts";
import { useApi } from "@/hooks/useApi";
import {
  getTrends,
  getAllTrends,
  getAzureStatus,
  getNiches,
  getAdsInsight,
  type TrendRow,
  type AdsInsightRow,
} from "@/lib/api";

const HERO_IMG =
  "https://d2xsxph8kpxj0f.cloudfront.net/310519663454788231/FytdQNpTpcXmkbaLV4kBSe/hero-data-grid_2468fa04.png";

/* ── helpers ─────────────────────────────────────────────────────────────── */

function groupByMonth(rows: TrendRow[]) {
  const buckets: Record<string, Record<string, number>> = {};
  for (const r of rows) {
    const d = r.extracted_at || r.created_at;
    if (!d) continue;
    const dt = new Date(String(d));
    if (isNaN(dt.getTime())) continue;
    const key = dt.toLocaleString("en", { month: "short", year: "2-digit" });
    if (!buckets[key]) buckets[key] = {};
    const platform = String(r.platform || "other").toLowerCase();
    buckets[key][platform] = (buckets[key][platform] || 0) + 1;
  }
  return Object.entries(buckets)
    .sort(([a], [b]) => new Date(`1 ${a}`).getTime() - new Date(`1 ${b}`).getTime())
    .map(([date, platforms]) => ({ date, ...platforms }));
}

function topTrends(rows: TrendRow[], n = 8) {
  const scored = rows
    .filter((r) => r.title || r.keyword)
    .map((r) => ({
      name: r.title || r.keyword || "—",
      score: r.virality_score ?? r.search_volume ?? 0,
      platform: String(r.platform || "—"),
      geo: r.geo || "—",
    }));
  scored.sort((a, b) => (b.score as number) - (a.score as number));
  return scored.slice(0, n);
}

/* ── Ads helpers ─────────────────────────────────────────────────────────── */

function topAds(rows: AdsInsightRow[], n = 6) {
  return [...rows]
    .filter((r) => r.title || r.body)
    .sort((a, b) => (b.performance_score ?? 0) - (a.performance_score ?? 0))
    .slice(0, n);
}

function adsPlatformBreakdown(rows: AdsInsightRow[]) {
  const counts: Record<string, number> = {};
  for (const r of rows) {
    const p = String(r.platform || "unknown").toLowerCase();
    counts[p] = (counts[p] || 0) + 1;
  }
  return Object.entries(counts)
    .sort(([, a], [, b]) => b - a)
    .map(([name, value]) => ({ name, value }));
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
    const f = String(r.display_format || "unknown").toLowerCase();
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
];

/* ── component ───────────────────────────────────────────────────────────── */

export default function Dashboard() {
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
  } = useApi(() => getAdsInsight({ limit: 500 }), []);

  const trends = trendsData?.data ?? [];
  const allTrends = allTrendsData?.data ?? [];
  const ads = adsData?.data ?? [];

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
  const totalAds = ads.length;
  const avgPerfScore =
    ads.length > 0
      ? (ads.reduce((s, r) => s + (r.performance_score ?? 0), 0) / ads.length).toFixed(1)
      : "—";
  const avgDaysActive =
    ads.length > 0
      ? Math.round(ads.reduce((s, r) => s + (r.days_active ?? 0), 0) / ads.length)
      : 0;
  const uniqueBrands = new Set(ads.map((a) => a.brand_name).filter(Boolean)).size;

  /* ── Chart data ─────────────────────────────────────────────────────── */
  const chartData = useMemo(() => groupByMonth(allTrends), [allTrends]);
  const platforms = useMemo(() => {
    const set = new Set<string>();
    for (const r of allTrends) {
      if (r.platform) set.add(String(r.platform).toLowerCase());
    }
    return Array.from(set).slice(0, 6);
  }, [allTrends]);

  const PLATFORM_COLORS: Record<string, string> = {
    google_trends: "oklch(0.50 0.20 260)",
    youtube: "oklch(0.60 0.22 25)",
    reddit: "oklch(0.55 0.20 30)",
    hackernews: "oklch(0.65 0.15 70)",
    tiktok: "oklch(0.55 0.25 320)",
    instagram: "oklch(0.60 0.22 340)",
    threads: "oklch(0.50 0.15 200)",
    news: "oklch(0.65 0.15 170)",
    gethookdai: "oklch(0.60 0.20 145)",
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

  /* ── Ads derived data ───────────────────────────────────────────────── */
  const topAdsList = useMemo(() => topAds(ads), [ads]);
  const platformBreakdown = useMemo(() => adsPlatformBreakdown(ads), [ads]);
  const brandList = useMemo(() => topBrands(ads), [ads]);
  const formatBreakdown = useMemo(() => adsFormatBreakdown(ads), [ads]);
  const perfDist = useMemo(() => performanceDistribution(ads), [ads]);

  /* ── KPI card configs ───────────────────────────────────────────────── */
  const kpiData = [
    { label: "Active Trends", value: totalTrends.toLocaleString(), change: `${trends.length} rows`, up: totalTrends > 0, icon: TrendingUp },
    { label: "Avg Virality", value: String(avgScore), change: "virality score", up: Number(avgScore) > 0, icon: Activity },
    { label: "Niches", value: String(nicheCount), change: `${nicheCount} configured`, up: nicheCount > 0, icon: BarChart3 },
    { label: "Database", value: dbConnected ? "Online" : "Offline", change: `${tableCount} tables`, up: dbConnected, icon: Globe },
  ];

  const adsKpiData = [
    { label: "Tracked Ads", value: totalAds.toLocaleString(), change: "from HookedAI", up: totalAds > 0, icon: Megaphone },
    { label: "Avg Performance", value: String(avgPerfScore), change: "performance score", up: Number(avgPerfScore) > 50, icon: Target },
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

      {/* Ads Charts Row: Performance Distribution + Platform Breakdown + Format Breakdown */}
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

        {/* Ads by Platform (Pie) */}
        <div className="lg:col-span-4 bg-card border border-border p-4">
          <h2 className="text-sm font-semibold mb-1">Ads by Platform</h2>
          <p className="text-xs text-muted-foreground mb-3">Distribution across ad platforms</p>
          <div className="h-52">
            {platformBreakdown.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={platformBreakdown}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={70}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                    label={({ name, percent }: { name: string; percent: number }) =>
                      `${name} ${(percent * 100).toFixed(0)}%`
                    }
                    labelLine={false}
                  >
                    {platformBreakdown.map((_, idx) => (
                      <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
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
                  <th className="text-left py-2 text-xs font-medium text-muted-foreground">Platform</th>
                  <th className="text-right py-2 text-xs font-medium text-muted-foreground">Score</th>
                  <th className="text-right py-2 text-xs font-medium text-muted-foreground">Days</th>
                  <th className="text-center py-2 text-xs font-medium text-muted-foreground">CTA</th>
                  <th className="text-center py-2 text-xs font-medium text-muted-foreground">Link</th>
                </tr>
              </thead>
              <tbody>
                {adsLoading ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center">
                      <Loader2 className="w-5 h-5 animate-spin mx-auto text-muted-foreground" />
                    </td>
                  </tr>
                ) : topAdsList.length > 0 ? (
                  topAdsList.map((ad, i) => (
                    <tr
                      key={ad.hookd_id || i}
                      className="border-b border-border/50 last:border-0 hover:bg-muted/30 transition-colors"
                    >
                      <td className="py-2.5 font-medium text-xs max-w-[200px] truncate">
                        {ad.title || (ad.body ? String(ad.body).slice(0, 60) + "..." : "—")}
                      </td>
                      <td className="py-2.5 text-xs text-muted-foreground">{ad.brand_name || "—"}</td>
                      <td className="py-2.5 text-xs text-muted-foreground">{ad.platform || "—"}</td>
                      <td className="py-2.5 text-right font-mono font-semibold text-xs">
                        <span
                          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold"
                          style={{
                            backgroundColor:
                              (ad.performance_score ?? 0) >= 80
                                ? "oklch(0.65 0.17 165 / 0.15)"
                                : (ad.performance_score ?? 0) >= 50
                                  ? "oklch(0.72 0.17 70 / 0.15)"
                                  : "oklch(0.55 0.015 260 / 0.15)",
                            color:
                              (ad.performance_score ?? 0) >= 80
                                ? "oklch(0.45 0.17 165)"
                                : (ad.performance_score ?? 0) >= 50
                                  ? "oklch(0.52 0.17 70)"
                                  : "oklch(0.45 0.015 260)",
                          }}
                        >
                          {ad.performance_score ?? "—"}
                        </span>
                      </td>
                      <td className="py-2.5 text-right font-mono text-xs">{ad.days_active ?? "—"}</td>
                      <td className="py-2.5 text-center text-xs text-muted-foreground">
                        {ad.cta_type || "—"}
                      </td>
                      <td className="py-2.5 text-center">
                        {ad.share_url ? (
                          <a
                            href={String(ad.share_url)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center text-primary hover:text-primary/80"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-xs text-muted-foreground">
                      No ads data available. Trigger an ads scrape to populate.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
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
